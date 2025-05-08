from functools import partial
import glob
import inspect
import os
import subprocess
import sys
import json

from .config import ServerConfig

def usage(name, msg=None):
    if msg:
        print(msg)

    print(
        inspect.cleandoc(
            f"""
            usage: bind xcworkspace and generate a buildServer.json to current dir.

            {name} -workspace *.xcworkspace -scheme <schemename>
            {name} -project *.xcodeproj -scheme <schemename>

            workspace and project and be infered if only one in pwd.
            scheme can be omit to bind the lastest build scheme.
            see also `man xcodebuild` and xcodebuild -showBuildSettings

            Other Options:

            --skip-validate-bin: if skip validate bin for background log parser.
            --build_root: specify build root directly
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
    build_root = None
    while (arg := next(it, None)) is not None:
        if arg == "-workspace" or arg == "--workspace":
            workspace = next(it, None)
        elif arg == "-scheme" or arg == "--scheme":
            scheme = next(it, None)
        elif arg == "-project" or arg == "--project":
            project = next(it, None)
        elif arg == "--build_root":
            build_root = next(it, None)
        elif arg == "--skip-validate-bin":
            skip_validate_bin = True
        elif "-h" == arg or "--help" == arg or "-help" == arg:
            _usage()
        else:
            _usage(f"unknown arg {arg}")

    def update(scheme):
        print("find root:", build_root)

        config = ServerConfig.shared()
        config.workspace = workspace
        config.build_root = build_root
        config.scheme = scheme
        config.kind = "xcode"
        config.skip_validate_bin = skip_validate_bin
        config.save()
        print("updated buildServer.json")

    if build_root:
        build_root = os.path.abspath(os.path.expanduser(build_root))
        return update(scheme)

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

    lastest_scheme = False
    if scheme is None:
        cmd = f"xcodebuild -list -json -workspace '{workspace}'"
        print("run: ", cmd)
        output = subprocess.check_output(cmd, shell=True, universal_newlines=True)
        output = json.loads(output)
        scheme = output["workspace"]["schemes"][0]
        lastest_scheme = True
        # _usage("you need to specify scheme!")

    # find and record build_root for workspace and scheme
    cmd = f"xcodebuild -showBuildSettings -json -workspace '{workspace}' -scheme '{scheme}' 2>/dev/null"
    print("run: ", cmd)
    output = subprocess.check_output(cmd, shell=True, universal_newlines=True)
    output = json.loads(output)
    build_dir = output[0]["buildSettings"]["SYMROOT"]
    build_root = os.path.abspath(os.path.join(build_dir, "../.."))

    workspace = os.path.abspath(os.path.expanduser(workspace))
    return update(None if lastest_scheme else scheme)
