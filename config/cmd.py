from functools import partial
import glob
import inspect
import os
import subprocess
import sys

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
    cmd = f"""xcodebuild -showBuildSettings -workspace '{workspace}' -scheme '{scheme}' 2>/dev/null | grep "\\bBUILD_DIR =" | head -1 | awk -F" = " '{{print $2}}' | tr -d '"' """
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


