from enum import Enum
import os
import subprocess
import struct

"""this file use to convert xcactivitylog. ignore it's structure, only extract pattern log string out"""


class TokenType(Enum):
    Null = 0
    String = 1
    Integer = 2
    Double = 3
    Array = 4
    Class = 5
    Instance = 6


def tokenizer(path):
    # pipe byte stream
    process = subprocess.Popen(["gunzip", "--stdout", path], stdout=subprocess.PIPE)
    buffer = bytearray()
    assert process.stdout
    head = process.stdout.read(4)
    if head != b"SLF0":
        raise ValueError(f"invalid file {path}, should be a xcactivitylog")

    def null_handler(index):
        del buffer[: index + 1]
        return (TokenType.Null, None)

    def int_handler(type):
        def handler(index):
            v = int(buffer[:index])
            del buffer[: index + 1]
            return (type, v)

        return handler

    def double_handler(index):
        v = buffer[:index]
        v = bytes.fromhex(v.decode())
        v = struct.unpack("<d", v)[0]
        del buffer[: index + 1]
        return (TokenType.Double, v)

    def str_handler(type):
        def handler(index):
            length = int(buffer[:index])
            start = index + 1
            available = len(buffer) - start
            if length > available:
                bstr = buffer[start:]
                bstr += process.stdout.read(length - available)  # type: ignore
                del buffer[:]
            else:
                bstr = buffer[start : (length + start)]
                del buffer[: start + length]
            return (type, bstr.decode())

        return handler

    handler_map = {
        ord(b'"'): str_handler(TokenType.String),
        ord(b"-"): null_handler,
        ord(b"#"): int_handler(TokenType.Integer),
        ord(b"^"): double_handler,
        ord(b"("): int_handler(TokenType.Array),
        ord(b"%"): str_handler(TokenType.Class),
        ord(b"@"): int_handler(TokenType.Instance),
    }

    i = 0
    while v := process.stdout.read(16):
        buffer.extend(v)
        l = len(buffer)
        while i < l:
            v = buffer[i]
            if handler := handler_map.get(v):
                yield handler(i)
                l = len(buffer)
                i = 0  # consume and reset
            else:
                i += 1


def extract_compile_log(path):
    for type, value in tokenizer(path):
        if type != TokenType.String:
            continue
        assert isinstance(value, str)
        if not value.startswith(
            (
                "CompileSwiftSources ",
                "SwiftDriver\\ Compilation ",
                "CompileC ",
                "ProcessPCH",
            )
        ):
            continue
        lines = value.splitlines()
        if len(lines) > 1:
            yield from iter(lines)
            yield ""  # a empty line means section log end


def newest_logpath(metapath: str, scheme=None):
    """returns None if no metapath or no logpath"""
    if not os.path.exists(metapath):
        return None

    import plistlib

    with open(metapath, "rb") as f:
        meta = plistlib.load(f)

        if scheme:
            valid = lambda v: v["schemeIdentifier-schemeName"] == scheme
        else:
            valid = bool
        logs = [v for v in meta["logs"].values() if valid(v)]
        if not logs:
            return None

        logs.sort(key=lambda v: v["timeStoppedRecording"], reverse=True)
        return os.path.join(os.path.dirname(metapath), logs[0]["fileName"])


# def play():
#     newest_logpath("LogStoreManifest.plist")
#     for l in extract_compile_log("36C1B4AD-7938-4FD2-B8EE-D0EDCCB00396.xcactivitylog"):
#         print(l)
