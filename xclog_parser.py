#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, os, sys


def echo(s):
    print(s, file=sys.stderr)


compile_swift_module = re.compile(r"""
    ^CompileSwiftSources\s*
""", re.X)
compile_swift = re.compile(
    r"""^CompileSwift\s+
                          \w+\s+ # normal
                          \w+\s+ # x86_64
                          (.+)$""",  # file
    re.X)
cmd_split_pattern = re.compile(
    r"""
"([^"]*)" |     # like "xxx xxx"
'([^']*)' |     # like 'xxx xxx'
((?:\\[ ]|\S)+) # like xxx\ xxx
""", re.X)


def cmd_split(s):
    # shlex.split is slow, use a simple version, only consider most case
    def extract(m):
        if m.lastindex == 3:  # \ escape version. remove it
            return m.group(m.lastindex).replace("\\ ", " ")
        return m.group(m.lastindex)

    return [extract(m) for m in cmd_split_pattern.finditer(s)]


def read_until_empty_line(i):
    li = []
    while True:
        line = next(i).strip()
        if not line: return li
        li.append(line)


def extract_swift_files_from_swiftc(command):
    # realpath解决了唯一性问题，但是swiftc好像要求传递的参数和命令行的一致...
    # TODO：如果用相对路径，有current directory的问题
    args = cmd_split(command)
    module_name = next((args[i+1] for (i, v) in enumerate(args) if v == '-module-name'), None)
    files = [os.path.realpath(a) for a in args if a.endswith(".swift")]
    # .SwiftFileList begin with a @ in command
    fileLists = [a[1:] for a in args if a.endswith(".SwiftFileList")]
    return (files, fileLists, module_name)


class XcodeLogParser(object):
    def __init__(self, _input, _logFunc):
        self._input = _input
        self._log = _logFunc

    def parse_compile_swift_module(self, line):
        m = compile_swift_module.match(line)
        if not m: return

        li = read_until_empty_line(self._input)
        if not li: return

        command = li[-1]  # type: str
        if "bin/swiftc " not in command:
            echo("Error: ================= Can't found swiftc\n" + command)
            return

        module = {}
        directory = next((i[len("cd "):] for i in li if i.startswith("cd ")), None)
        if directory: module["directory"] = directory
        module["command"] = command
        files = extract_swift_files_from_swiftc(command)
        module['module_name'] = files[2]
        module["files"] = files[0]
        module["fileLists"] = files[1]
        echo(f"CompileSwiftModule {module['module_name']}")
        return module

    def parse_compile_swift(self, line):
        m = compile_swift.match(line)
        if not m: return

        li = read_until_empty_line(self._input)
        if not li: return

        echo(f"CompileSwift {m.group(1)}")
        item = {"file": m.group(1), "command": li[-1]}
        for line in li:
            if line.startswith("cd "):
                item["directory"] = line[len("cd "):]
                break
        return item

    def parse(self):
        from inspect import iscoroutine
        import asyncio
        items = []
        futures = []

        def append(item):
            if isinstance(item, dict): items.append(item)
            else: items.extend(item)

        # @return Future or Item, None to skip it
        matcher = [
            self.parse_compile_swift_module,
            # self.parse_compile_swift,
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
            for item in asyncio.get_event_loop().run_until_complete(asyncio.gather(*futures)):
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
            if ident: new_file_map[ident] = item

        dealed = set()

        def get_new_item(old_item):
            if isinstance(old_item, dict):
                ident = identifier(old_item)
                if ident:
                    dealed.add(ident)

                    new_item = new_file_map.get(ident)
                    if new_item: return new_item
            return old_item

        # 旧item中不变的, 以及被更新的，和新item中新添加的
        final = [get_new_item(item) for item in old_items]
        final.extend(item for item in items if identifier(item) not in dealed)

        f.seek(0)
        dump_database(final, f)
        f.truncate()


def main(argv = sys.argv):
    import argparse
    parser = argparse.ArgumentParser(prog = argv[0], description="pass xcodebuild output log, use stderr as log")
    parser.add_argument("input", nargs="?", default="-", help="input file, default will use stdin")
    parser.add_argument("-o", "--output", default="-", help="output file, default will be stdout")
    parser.add_argument("-a",
                        "--append",
                        action="store_true",
                        help="append to output file instead of replace. same item will be overwrite. should specify output")
    a = parser.parse_args(argv[1:])

    if a.input == "-": in_fd = sys.stdin
    else: in_fd = open(a.input, "r")
    if a.output == "-": get_out_fd = lambda: sys.stdout
    else:
        get_out_fd = lambda: open(a.output, "w")  # open will clear file

    items = XcodeLogParser(in_fd, echo).parse()
    if a.append and os.path.exists(a.output):
        merge_database(items, a.output)
    else:
        dump_database(items, get_out_fd())


if __name__ == "__main__":
    main()
