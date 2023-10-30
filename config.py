from functools import cache, partial
import glob
import inspect
import json
import os
import subprocess
import sys


def usage(name, msg=None):
    if msg:
        print(msg)

    print(
        inspect.cleandoc(
            f"""
            usage: bind xcworkspace and generate a buildServer.json to current dir.

            {name} -workspace *.xcworkspace -scheme <schemename>
            {name} -project *.xcodeproj -scheme <schemename>

            workspace and project and be infered if only one in pwd. scheme must be specified.
            see also `man xcodebuild` and xcodebuild -showBuildSettings

            Other Options:

            --skip-validate-bin: if skip validate bin for background log parser.
            """
        )
    )
    exit(1 if msg else 0)


def main(argv=sys.argv):
    it = iter(argv)
    name = next(it, None)
    _usage = partial(usage, name)
    # generate a config bind xcodeproj
    if len(argv) < 3 or "-h" == argv[1] or "--help" == argv[1] or "-help" == argv[1]:
        _usage()

    workspace = None
    scheme = None
    project = None
    skip_validate_bin = None
    while (arg := next(it, None)) is not None:
        if arg == "-workspace":
            workspace = next(it, None)
        elif arg == "-scheme":
            scheme = next(it, None)
        elif arg == "-project":
            project = next(it, None)
        elif arg == "--skip-validate-bin":
            skip_validate_bin = True
        elif "-h" == arg or "--help" == arg or "-help" == arg:
            _usage()
        else:
            _usage(f"unknown arg {arg}")

    if scheme is None:
        _usage("you need to specify scheme!")

    if workspace is None:

        def get_workspace():
            if project is None:
                workspaces = glob.glob("*.xcworkspace")
                if len(workspaces) > 1:
                    _usage("there are multiple xcworkspace in pwd, please specify one")
                if len(workspaces) == 1:
                    return workspaces[0]

                projects = glob.glob("*.xcodeproj/*.xcworkspace")
                if len(projects) > 1:
                    _usage("there are multiple xcodeproj in pwd, please specify one")
                if len(projects) == 1:
                    return projects[0]

                _usage("there no xcworkspace or xcodeproj in pwd, please specify one")
            else:
                return os.path.join(project, "project.xcworkspace")

        workspace = get_workspace()

    # find and record build_root for workspace and scheme
    cmd = f"""xcodebuild -showBuildSettings -workspace '{workspace}' -scheme '{scheme}' | grep "\\bBUILD_DIR =" | head -1 | awk '{{print $3}}' | tr -d '"' """
    build_dir = subprocess.check_output(cmd, shell=True, universal_newlines=True)
    build_root = os.path.join(build_dir, "../..")
    build_root = os.path.abspath(build_root)
    print("find root:", build_root)

    config = ServerConfig.shared()
    config.workspace = os.path.abspath(os.path.expanduser(workspace))
    config.build_root = build_root
    config.scheme = scheme
    config.kind = "xcode"
    config.skip_validate_bin = skip_validate_bin
    config.save()
    print("updated buildServer.json")


def _config_property(name, default=None, doc=None, delete_none=True):
    """
    default only affect getter, not write into data
    """
    def fget(self):
        return self.data.get(name, default)

    def fset(self, value):
        if delete_none and value is None:
            self.data.pop(name, None)
        else:
            self.data[name] = value

    def fdel(self):
        del self.data[name]

    return property(fget, fset, fdel, doc)


class ServerConfig(object):
    """this class control all user config. options:

    kind: xcode|manual  # where to find flags. default: manual
    when kind=xcode:
        workspace: the bind workspace path
        scheme: the bind scheme
        build_root: the build_root find from xcworkspace and scheme
    when kind=manual(or no kind):
        indexStorePath?: the manual parsed index path. may not exists

    user can change scheme by call `xcode-build-server config`,
    or change to manual by call `xcode-build-server parse` directly.

    after config change. server should change to new flags too..

    other config:
    skip_validate_bin: if true, will skip validate bin for background parser
    """

    # TODO: distinguish configuration and destination #

    default_path = "buildServer.json"

    kind = _config_property("kind", default="manual")
    workspace = _config_property("workspace")
    scheme = _config_property("scheme")
    build_root = _config_property("build_root")
    indexStorePath = _config_property("indexStorePath")

    skip_validate_bin = _config_property("skip_validate_bin")

    @cache
    def shared():
        return ServerConfig(ServerConfig.default_path)

    def __init__(self, path):
        self.path = os.path.abspath(path)
        if os.path.exists(path):
            with open(path, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {
                "name": "xcode build server",
                "version": "0.2",
                "bspVersion": "2.0",
                "languages": ["c", "cpp", "objective-c", "objective-cpp", "swift"],
                "argv": [sys.argv[0]],
            }

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent="\t")
