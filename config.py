import json
import subprocess
import sys
import glob
import os


def usage(msg=None):
    if msg:
        print(msg)
    print(
        f"""bind xcodeproj to buildServer.json. usage:

    {sys.argv[0]} -workspace name.xcworkspace -scheme schemename
    {sys.argv[0]} -project name.xcodeproj -scheme schemename

    see also `man xcodebuild` and xcodebuild -showBuildSettings
    """
    )
    exit(1 if msg else 0)


def main(argv=sys.argv):
    if "-h" == argv[1] or "--help" == argv[1] or "-help" == argv[1] or len(argv) < 3:
        usage()

    workspace = None
    scheme = None
    project = None
    it = iter(argv)
    try:
        while True:
            arg = next(it)
            if arg == "-workspace":
                workspace = next(it)
            elif arg == "-scheme":
                scheme = next(it)
            elif arg == "-project":
                project = next(it)
    except StopIteration:
        pass

    if scheme is None:
        usage("you need to specify scheme!")

    if workspace is None:

        def get_workspace():
            if project is None:
                workspaces = glob.glob("*.xcworkspace")
                if len(workspaces) > 1:
                    usage("there are multiple xcworkspace in pwd, please specify one")
                if len(workspaces) == 1:
                    return workspaces[0]

                projects = glob.glob("*.xcodeproj/*.xcworkspace")
                if len(projects) > 1:
                    usage("there are multiple xcodeproj in pwd, please specify one")
                if len(projects) == 1:
                    return projects[0]

                usage("there no xcworkspace or xcodeproj in pwd, please specify one")
            else:
                return os.path.join(project, "project.xcworkspace")

        workspace = get_workspace()

    cmd = f"""xcodebuild -showBuildSettings -workspace '{workspace}' -scheme '{scheme}' | grep "\bBUILD_DIR =" | head -1 | awk '{{print $3}}' | tr -d '"' """
    build_dir = subprocess.check_output(cmd, universal_newlines=True)
    build_root = os.path.join(build_dir, "../..")
    build_root = os.path.normpath(build_root)
    print("find root:", build_root)

    additional_config = {
        "workspace": workspace,
        "build_root": build_root,
    }
    if scheme:
        additional_config["scheme"] = scheme

    dump_server_config(additional=additional_config)
    print("writed buildServer.json")

    import xclog_parser
    args = ["xclog_parser", "-as", build_root, "-o", ".compile"]
    if scheme:
        args.append("--scheme")
        args.append(scheme)
    xclog_parser.main(args)


def dump_server_config(store=None, additional=None):
    """write buildServer.json to cwd"""
    h = {
        "name": "xcode build server",
        "version": "0.2",
        "bspVersion": "2.0",
        "languages": ["c", "cpp", "objective-c", "objective-cpp", "swift"],
        "argv": [sys.argv[0]],
    }
    if store:
        h["indexStorePath"] = store
    if additional:
        h.update(additional)

    with open("buildServer.json", "w") as f:
        json.dump(h, f, indent=2)
