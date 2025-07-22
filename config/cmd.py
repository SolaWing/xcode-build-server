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
            nonlocal project
            if project is None:
                workspaces = glob.glob("*.xcworkspace")
                if len(workspaces) > 1:
                    _usage("there are multiple xcworkspace in pwd, please specify one")
                if len(workspaces) == 1:
                    return workspaces[0]

                projects = glob.glob("*.xcodeproj")
                if len(projects) > 1:
                    _usage("there are multiple xcodeproj in pwd, please specify one")
                if len(projects) == 1:
                    project = projects[0]
                    return os.path.join(project, "project.xcworkspace")

                _usage("there no xcworkspace or xcodeproj in pwd, please specify one")
            else:
                return os.path.join(project, "project.xcworkspace")

        workspace = get_workspace()
    else:
        project = None # clear to avoid specify both

    use_project = False
    if os.path.exists(workspace):
        cmd_target = f"-workspace '{workspace}'"
    elif project:
        cmd_target = f"-project '{project}'"
        use_project = True
    else:
        _usage("can't get exist xcworkspace, please specify one")

    lastest_scheme = False
    if scheme is None:
        cmd = f"xcodebuild -list -json {cmd_target}"
        print("run: ", cmd)
        output = subprocess.check_output(cmd, shell=True, universal_newlines=True)
        output = json_loads(output)
        if use_project:
            scheme = output["project"]["schemes"][0]
        else:
            scheme = output["workspace"]["schemes"][0]
        lastest_scheme = True
        # _usage("you need to specify scheme!")

    # find and record build_root for workspace and scheme
    cmd = f"xcodebuild -showBuildSettings -json {cmd_target} -scheme '{scheme}' 2>/dev/null"
    print("run: ", cmd)
    output = subprocess.check_output(cmd, shell=True, universal_newlines=True)
    output = json_loads(output)
    build_dir = output[0]["buildSettings"]["SYMROOT"]
    build_root = os.path.abspath(os.path.join(build_dir, "../.."))

    workspace = os.path.abspath(os.path.expanduser(workspace))
    return update(None if lastest_scheme else scheme)

def json_loads(s: str):
    if s[0] != "{" and s[0] != "[":
        # https://github.com/swiftlang/swift-package-manager/blob/f19d08cf79250514851490599319d22771074b01/Sources/PackageLoading/TargetSourcesBuilder.swift#L194
        # SPM print error message to stdout, skip it
        brace = s.find("{")
        bracket = s.find("[")
        if brace < 0: start = bracket
        elif bracket < 0: start = brace
        else: start = min(brace, bracket)
        if start > 0: s = s[start:]

    return json.loads(s)
