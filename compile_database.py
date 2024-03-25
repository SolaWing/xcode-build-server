import logging
import os
import re
import subprocess
from typing import Dict, List


globalStore = {}

cmd_split_pattern = re.compile(
    r"""
"((?:[^"]|(?<=\\)")*)" |     # like "xxx xxx", allow \"
'([^']*)' |     # like 'xxx xxx'
((?:\\[ ]|\S)+) # like xxx\ xxx
""",
    re.X,
)


def isProjectRoot(directory):
    return os.path.exists(os.path.join(directory, ".git"))


def additionalFlags(flagsPath):
    if flagsPath and os.path.isfile(flagsPath):

        def valid(s):
            return s and not s.startswith("#")

        with open(flagsPath) as f:
            return list(filter(valid, (line.strip() for line in f)))
    return []


def findAllHeaderDirectory(rootDirectory, store):
    headerDirsCacheDict = store.setdefault("headerDirs", {})
    headerDirs = headerDirsCacheDict.get(rootDirectory)
    if headerDirs:
        return headerDirs

    output = subprocess.check_output(
        ["find", "-L", rootDirectory, "-name", "*.h"], universal_newlines=True
    )
    headers = output.splitlines()
    headerDirs = set()
    frameworks = set()
    for h in headers:
        frameworkIndex = h.rfind(".framework")
        if frameworkIndex != -1:
            h = os.path.dirname(h[:frameworkIndex])
            frameworks.add(h)
        else:
            h = os.path.dirname(h)
            headerDirs.add(h)
            # contains more one dir for import with module name
            # don't contains more one module name dir. if need, can specify in .flags
            # conflict with #if_include framework check
            #  h = os.path.dirname(h)
            #  headerDirs.add(h)

    headerDirsCacheDict[rootDirectory] = (headerDirs, frameworks)
    return headerDirs, frameworks


def findAllSwiftFiles(rootDirectory):
    output = subprocess.check_output(
        ["find", "-H", rootDirectory, "-name", "*.swift"], universal_newlines=True
    )
    return [os.path.realpath(l) for l in output.splitlines()]


def cmd_split(s):
    import shlex

    return shlex.split(s)  # shlex is more right
    # shlex.split is slow, use a simple version, only consider most case
    # def extract(m):
    #     if m.lastindex == 3:  # \ escape version. remove it
    #         return m.group(m.lastindex).replace("\\ ", " ")
    #     return m.group(m.lastindex)

    # return [extract(m) for m in cmd_split_pattern.finditer(s)]


def readFileArgs(path):
    with open(path) as f:
        return cmd_split(f.read())


# 以文件里的内容作为命令行参数，会进行shell分词展开
def getFileArgs(path, cache) -> List[str]:
    files = cache.get(path)
    if files is None:
        files = readFileArgs(path)
        cache[path] = files
    return files


def filterFlags(items, fileCache):
    """
    f: should return True to accept, return number to skip next number flags
    """
    it = iter(items)
    try:
        while True:
            arg: str = next(it)

            # # -working-directory raise unsupported arg error
            if arg in {
                "-emit-localized-strings-path"
                # "-primary-file", "-o", "-serialize-diagnostics-path", "-working-directory", "-Xfrontend"
            }:
                next(it)
                continue
            # if arg.startswith("-emit"):
            #     if arg.endswith("-path"): next(it)
            #     continue
            if arg in {  # will make sourcekit report errors
                "-use-frontend-parseable-output",
                "-emit-localized-strings"
                # "-frontend", "-c", "-pch-disable-validation", "-index-system-modules", "-enable-objc-interop",
                # '-whole-module-optimization',
            }:
                continue
            if arg == "-filelist":  # sourcekit dont support filelist, unfold it
                yield from getFileArgs(next(it), fileCache)
                continue
            if arg.startswith("@"):
                # swift 5.1 filelist, unfold it
                # xcode 15.3 clang extra args, unfold it
                yield from getFileArgs(arg[1:], fileCache)
                continue
            yield arg
    except StopIteration:
        pass


def findSwiftModuleRoot(filename):
    """return project root or None. if not found"""
    filename = os.path.abspath(filename)
    directory = os.path.dirname(filename)
    flagFile = None
    compileFile = None
    while directory and directory != "/":
        p = os.path.join(directory, ".swiftflags")
        if os.path.isfile(p):
            return (
                directory,
                p,
                compileFile,
            )  # prefer use swiftflags file as module root directory

        if compileFile is None:
            p = os.path.join(directory, ".compile")
            if os.path.isfile(p):
                compileFile = p

        if isProjectRoot(directory):
            break
        else:
            directory = os.path.dirname(directory)
    else:
        return (None, flagFile, compileFile)

    return (directory, flagFile, compileFile)

class CompileFileInfo:
    def __init__(self, compileFile, store):
        self.info = {}

        # load compileFile into info
        import json
        with open(compileFile) as f:
            m: List[dict] = json.load(f)
            for i in m:
                command = i.get("command")
                if not command:
                    continue
                if files := i.get("files"):  # batch files, eg: swift module
                    self.info.update((self.key(f), command) for f in files)
                if fileLists := i.get("fileLists"):  # file list store in a dedicated file
                    self.info.update(
                        (self.key(f), command)
                        for l in fileLists if os.path.isfile(l)
                        for f in getFileArgs(l, store.setdefault("filelist", {}))
                    )
                if file := i.get("file"):  # single file info
                    self.info[self.key(file)] = command

    def get(self, filename):
        if command := self.info.get(filename.lower()):
            return command.replace("\\=", "=")

    def key(self, filename):
        return os.path.realpath(filename).lower()


def commandForFile(filename, compileFile, store: Dict):
    """
    command = store["compile"][<compileFile>][filename]
    """
    compile_store = store.setdefault("compile", {})
    info: CompileFileInfo = compile_store.get(compileFile)
    if info is None:  # load {filename.lower: command} dict
        info = CompileFileInfo(compileFile, store)  # cache first to avoid re enter when error
        compile_store[compileFile] = info

    # xcode 12 escape =, but not recognized...
    return info.get(filename)


def GetFlagsInCompile(filename, compileFile, store):
    """read flags from compileFile"""
    if compileFile:
        command = commandForFile(filename, compileFile, store)
        if command:
            flags = cmd_split(command)[1:]  # ignore executable
            return list(filterFlags(flags, store.setdefault("filelist", {})))


def GetFlags(filename: str, compileFile=None, **kwargs):
    """sourcekit entry function"""
    # NOTE: use store to ensure toplevel storage. child store should be other name
    # see store.setdefault to get all child attributes
    store = kwargs.get("store", globalStore)
    filename = os.path.realpath(filename)

    if compileFile:
        if final_flags := GetFlagsInCompile(filename, compileFile, store):
            return {"flags": final_flags, "do_cache": True}

    if filename.endswith(".swift"):
        return InferFlagsForSwift(filename, compileFile, store)
    return {"flags": [], "do_cache": False}

# TODO: c family infer flags #
def InferFlagsForSwift(filename, compileFile, store):
    """try infer flags by convention and workspace files"""
    project_root, flagFile, compileFile = findSwiftModuleRoot(filename)
    logging.debug(f"infer root: {project_root}, {compileFile}")
    final_flags = GetFlagsInCompile(filename, compileFile, store)

    if not final_flags and flagFile:
        final_flags = []
        headers, frameworks = findAllHeaderDirectory(project_root, store)
        for h in headers:
            final_flags += ["-Xcc", "-I" + h]
        for f in frameworks:
            final_flags.append("-F" + f)
        swiftfiles = findAllSwiftFiles(project_root)
        final_flags += swiftfiles
        a = additionalFlags(flagFile)
        if a:
            # sourcekit not allow same swift name. so if same name, use the find one to support move file
            swift_names = set(os.path.basename(p) for p in swiftfiles)
            final_flags += (
                arg
                for arg in filterFlags(a, store.setdefault("filelist", {}))
                if os.path.basename(arg) not in swift_names
            )
        else:
            final_flags += [
                "-sdk",
                "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/",
            ]
    if not final_flags:
        final_flags = [
            filename,
            "-sdk",
            "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/",
        ]

    return {"flags": final_flags, "do_cache": True}
