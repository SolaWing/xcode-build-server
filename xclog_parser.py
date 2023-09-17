#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import shlex
import sys
from typing import Iterator, List


def echo(s):
    print(s, file=sys.stderr)


cmd_split_pattern = re.compile(
    r"""
        "((?:[^"]|(?<=\\)")*)" | # like "xxx xxx", allow \"
        '([^']*)' |              # like 'xxx xxx'
        ((?:\\[ ]|\S)+)          # like xxx\ xxx
    """,
    re.X,
)
pch_capture = re.compile(
    r"""
    -include\s (?:
        "(?:[^"]|(?<=\\)")*" | # like "xxx xxx", allow \"
        '[^']*' |              # like 'xxx xxx'
        (?:\\[ ]|\S)+          # like xxx\ xxx
    )
""",
    re.X,
)


def cmd_split(s):
    # shlex.split is slow, use a simple version, only consider most case
    # in mine project test, custom regex is 2.54s, shlex.split is 4.9s
    return shlex.split(s)  # shlex is more right


def cmd_split_fast(s):
    def extract(m):
        if m.lastindex == 3:  # \ escape version. remove it
            return m.group(m.lastindex).replace("\\ ", " ")
        return m.group(m.lastindex)

    return [extract(m) for m in cmd_split_pattern.finditer(s)]


def read_until_empty_line(i: Iterator[str]) -> List[str]:
    li = []
    while True:
        line = next(i).rstrip("\r\n")
        if not line:
            return li
        li.append(line.strip())


def extract_swift_files_from_swiftc(command):
    # realpath解决了唯一性问题，但是swiftc好像要求传递的参数和命令行的一致...
    # TODO：如果用相对路径，有current directory的问题
    args = cmd_split(command)
    module_name = next(
        (args[i + 1] for (i, v) in enumerate(args) if v == "-module-name"), None
    )
    index_store_path = next(
        (args[i + 1] for (i, v) in enumerate(args) if v == "-index-store-path"), None
    )
    files = [os.path.realpath(a) for a in args if a.endswith(".swift")]
    # .SwiftFileList begin with a @ in command
    fileLists = [a[1:] for a in args if a.endswith(".SwiftFileList")]
    return (files, fileLists, module_name, index_store_path)


class XcodeLogParser(object):
    swiftc_exec = "bin/swiftc "
    clang_exec = re.compile(r"^\s*\S*clang\S*")

    def __init__(self, _input: Iterator[str], _logFunc, skip_validate_bin):
        self._input = _input
        self._log = _logFunc
        self.skip_validate_bin = skip_validate_bin
        self._pch_info = {}  # {condition => pch_file_path}

    def parse_compile_swift_module(self, line: str):
        if not line.startswith("CompileSwiftSources "):
            return

        li = read_until_empty_line(self._input)
        if not li:
            return

        command = li[-1]  # type: str
        if not self.skip_validate_bin and self.swiftc_exec not in command:
            echo(f"Error: ================= Can't found {self.swiftc_exec}\n" + command)
            return

        module = {}
        directory = next((cmd_split(i)[1] for i in li if i.startswith("cd ")), None)
        if directory:
            module["directory"] = directory
        module["command"] = command
        files = extract_swift_files_from_swiftc(command)
        module["module_name"] = files[2]
        module["files"] = files[0]
        module["fileLists"] = files[1]
        if files[3]:
            self.index_store_path.add(files[3])
        echo(f"CompileSwiftModule {module['module_name']}")
        return module

    def parse_swift_driver_module(self, line: str):
        # match cases 1:
        # SwiftDriver XXXDevEEUnitTest normal x86_64 com.apple.xcode.tools.swift.compiler (in target 'XXXDevEEUnitTest' from project 'XXXDev')
        # cd ...
        # builtin-SwiftDriver -- /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc -module-name XXXDevEEUnitTest

        # match cases 2:
        # SwiftDriver\ Compilation XXX normal x86_64 com.apple.xcode.tools.swift.compiler (in target 'XXX' from project 'XXX')
        # cd ...
        # builtin-Swift-Compilation -- /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc -module-name XXX

        # may appear both case, seems Compilation must show, driver may show..
        if not line.startswith("SwiftDriver"):
            return

        li = read_until_empty_line(self._input)
        if not li:
            return

        command = li[-1]
        # 忽略builtin-Swift-Compilation-Requirements
        if not (
            command.startswith("builtin-Swift-Compilation -- ")
            or command.startswith("builtin-SwiftDriver -- ")
        ):
            return

        if not self.skip_validate_bin and self.swiftc_exec not in command:
            echo(f"Error: ================= Can't found {self.swiftc_exec}\n" + command)
            return

        command = command[(command.index(" -- ") + len(" -- ")) :]

        module = {}
        directory = next((cmd_split(i)[1] for i in li if i.startswith("cd ")), None)
        if directory:
            module["directory"] = directory
        module["command"] = command
        files = extract_swift_files_from_swiftc(command)
        module["module_name"] = files[2]
        module["files"] = files[0]
        module["fileLists"] = files[1]
        if files[3]:
            self.index_store_path.add(files[3])
        echo(f"CompileSwiftModule {module['module_name']}")
        return module

    def parse_c(self, line):
        if not line.startswith("CompileC "):
            return

        li = read_until_empty_line(self._input)
        if not li:
            return

        command = li[-1]
        if not self.skip_validate_bin and not re.match(self.clang_exec, command):
            echo("Error: ========== Can't found clang\n" + command)
            return

        info = cmd_split(line)

        module = {}
        directory = next((cmd_split(i)[1] for i in li if i.startswith("cd ")), None)
        if directory:
            module["directory"] = directory
        pch = self._pch_info.get(" ".join(info[3:]))
        if pch is not None:
            # when GCC_PRECOMPILE_PREFIX_HEADER=YES, pch is processed and command specify a invalid pch path, replace it to the local pch path
            # same behavior like xcpretty
            command = pch_capture.sub(f"-include {shlex.quote(pch)}", command)

        module["command"] = command
        module["file"] = info[2]
        module["output"] = info[1]

        echo(f"CompileC {info[2]}")
        return module

    def parse_pch(self, line):
        """
        when GCC_PRECOMPILE_PREFIX_HEADER=YES, will has a ProcessPCH or ProcessPCH++ Section, which format is:
        ProcessPCH[++] <output> <input> <condition>..
        """
        if not line.startswith("ProcessPCH"):
            return
        info = cmd_split(line)
        self._pch_info[" ".join(info[3:])] = info[2]
        echo(f"ProcessPCH {info[2]}")

    def parse(self):
        from inspect import iscoroutine
        import asyncio

        items = []
        futures = []
        self.index_store_path = set()
        self.items = items

        def append(item):
            if isinstance(item, dict):
                items.append(item)
            else:
                items.extend(item)

        # @return Future or Item, None to skip it
        matcher = [
            self.parse_swift_driver_module,
            self.parse_compile_swift_module,
            self.parse_c,
            self.parse_pch,
        ]
        try:
            while True:
                line = next(self._input)  # type: str

                if line.startswith("==="):
                    echo(line)
                    continue
                for m in matcher:
                    item = m(line)
                    if item:
                        if iscoroutine(item):
                            futures.append(item)
                        else:
                            append(item)
                        break
        except StopIteration:
            pass

        if len(futures) > 0:
            echo("waiting... ")
            for item in asyncio.get_event_loop().run_until_complete(
                asyncio.gather(*futures)
            ):
                append(item)

        return items


def dump_database(items, output):
    import json

    # pretty print, easy to read with editor. compact save little size. only about 0.2%
    json.dump(items, output, ensure_ascii=False, check_circular=False, indent="\t")


def merge_database(items, database_path):
    import json

    #  TODO: swiftc模块的增量更新
    # 根据ident(file属性)，增量覆盖更新
    def identifier(item):
        if isinstance(item, dict):
            return item.get("file") or item.get("module_name")
        return None  # other type info without identifier simplely append into file

    with open(database_path, "r+") as f:
        # try best effort to keep old data
        old_items = json.load(f)

        new_file_map = {}
        for item in items:
            ident = identifier(item)
            if ident:
                # swift-driver和swift-compile的重复看来是正常的，命令也一样。所以先兼容观察一段时间
                # if ident in new_file_map:
                #     echo(f"Error: duplicate compile for {ident}")
                new_file_map[ident] = item

        dealed = set()

        def get_new_item(old_item):
            if isinstance(old_item, dict):
                ident = identifier(old_item)
                if ident:
                    dealed.add(ident)

                    new_item = new_file_map.get(ident)
                    if new_item:
                        return new_item
            return old_item

        # 旧item中不变的, 以及被更新的，和新item中新添加的
        final = [get_new_item(item) for item in old_items]
        final.extend(item for item in items if identifier(item) not in dealed)

        f.seek(0)
        dump_database(final, f)
        f.truncate()


def output_lock_path(output_path):
    return output_path + ".lock"

default_output_path = ".compile"

class OutputLockedError(FileExistsError):
    pass


def within_output_lock(output_path, action, timeout=180):
    """raise OutputLockedError when already locked"""
    # lock and trigger parse compile
    if output_path == "-":
        return action()

    from misc import force_remove, get_mtime

    lock_path = output_lock_path(output_path or default_output_path)
    while True:
        try:
            from pathlib import Path

            Path(lock_path).touch(exist_ok=False)
            break
        except FileExistsError as e:
            from time import time

            if time() - get_mtime(lock_path) >= timeout:
                echo(f"{lock_path} locked so long! clear it and relock")
                force_remove(lock_path)
                # continue next try
            else:
                raise OutputLockedError(*e.args, e.filename)

    try:
        return action()
    finally:
        force_remove(lock_path)


def _parse(args):
    from xcactivitylog import (
        newest_logpath,
        extract_compile_log,
        metapath_from_buildroot,
    )

    """args: same as main.parse args"""
    if args.sync:
        xcpath = newest_logpath(metapath_from_buildroot(args.sync), scheme=args.scheme)
        if not xcpath:
            echo(
                f"no newest_logpath xcactivitylog at {args.sync}/Logs/Build/LogStoreManifest.plist"
            )
            return 1

        echo(f"extract_compile_log at {xcpath}")
        in_fd = extract_compile_log(xcpath)
    elif args.xcactivitylog:
        in_fd = extract_compile_log(args.xcactivitylog)
    elif args.input == "-":
        in_fd = sys.stdin
    elif args.input.endswith(".xcactivitylog"):
        in_fd = extract_compile_log(args.input)
    else:
        in_fd = open(args.input, "r")

    parser = XcodeLogParser(in_fd, echo, skip_validate_bin=args.skip_validate_bin)
    items = parser.parse()

    if args.output == "-":
        return dump_database(items, sys.stdout)
    if not args.output:
        output = default_output_path

        for index_store_path in parser.index_store_path:
            echo(f"use index_store_path at {index_store_path}")
            break
        else:
            index_store_path = None

        from config import ServerConfig

        c = ServerConfig.shared()
        c.indexStorePath = index_store_path
        c.kind = "manual"
        c.save()
    else:
        output = args.output

    if args.append and os.path.exists(output):
        merge_database(items, output)
    else:
        # open will clear file
        dump_database(items, open(output, "w"))


def parse(argv):
    import argparse

    parser = argparse.ArgumentParser(
        prog=argv[0], description="pass xcodebuild output log, use stderr as log"
    )
    parser.add_argument(
        "input", nargs="?", default="-", help="input file, default will use stdin"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="output file, when this not set, will dump to cwd .compile file, also generate a buildServer.json with indexStorePath",
    )
    parser.add_argument(
        "-a",
        "--append",
        action="store_true",
        help="append to output file instead of replace. same item will be overwrite. should specify output",
    )
    parser.add_argument(
        "-l", "--xcactivitylog", help="xcactivitylog path, overwrite input param"
    )
    parser.add_argument(
        "-s",
        "--sync",
        help="xcode build root path, use to extract newest xcactivitylog, eg: /Users/xxx/Library/Developer/Xcode/DerivedData/XXXProject-xxxhash/",
    )
    parser.add_argument(
        "--scheme",
        help=argparse.SUPPRESS
        # help="scheme for extract from sync build root, default ignore this filter param",
    )
    parser.add_argument(
        "--skip-validate-bin",
        help="if skip validate the compile command which start with swiftc or clang, you should use this only when use custom binary",
        action="store_true",
    )
    a = parser.parse_args(argv[1:])
    within_output_lock(a.output, lambda: _parse(a))


def main(argv=sys.argv):
    try:
        parse(argv)
    except OutputLockedError as e:
        echo(f"{e.filename} exists! parse already run")
        sys.exit(1)


if __name__ == "__main__":
    main()
