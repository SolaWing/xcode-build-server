import json
import logging
import os
import sys
import urllib.parse

from compile_database import GetFlags


def send(data):
    data_str = json.dumps(data)
    logging.debug("Res <-- %s", data_str)
    try:
        sys.stdout.write(f"Content-Length: {len(data_str)}\r\n\r\n{data_str}")
        sys.stdout.flush()
    except IOError as e:
        # stdout closed, time to quit
        raise SystemExit(0) from e


def uri2filepath(uri):
    result = urllib.parse.urlparse(uri)
    if result.scheme != "file":
        raise ValueError(uri)
    return urllib.parse.unquote(result.path)


def optionsForFile(uri, compile_file=None):
    file_path = uri2filepath(uri)
    flags = GetFlags(file_path, compile_file)["flags"]  # type: list
    try:
        workdir = flags[flags.index("-working-directory") + 1]
    except (IndexError, ValueError):
        workdir = os.getcwd()
    return {
        "options": flags,
        "workingDirectory": workdir,
    }


def server_api():
    """nest def is api, return by locals()"""
    compile_file = None  # 优先共用root compile_file里的编译信息

    def build_initialize(message):
        nonlocal compile_file

        rootUri = message["params"]["rootUri"]
        cache_path = os.path.join(
            os.path.expanduser("~/Library/Caches/xcode-build-server"),
            rootUri.replace("/", "-").replace("%", "X"),
        )
        rootPath = uri2filepath(rootUri)
        v = os.path.join(rootPath, ".compile")
        if os.path.exists(v) and compile_file is None:
            compile_file = v

        configPath = os.path.join(rootPath, "buildServer.json")
        indexStorePath = None
        if os.path.exists(configPath):
            with open(configPath) as f:
                indexStorePath = json.load(f).get("indexStorePath", None)

        if not indexStorePath:
            indexStorePath = f"{cache_path}/indexStorePath"
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "displayName": "xcode build server",
                "version": "0.1",
                "bspVersion": "2.0",
                "rootUri": rootUri,
                "capabilities": {
                    "languageIds": ["c","cpp","objective-c","objective-cpp","swift"]
                },
                "data": {
                    # storepath是build生成的数据
                    # db是相应的加速缓存
                    # 需要根据rooturi拿到对应的indexstorepath的路径
                    "indexDatabasePath": f"{cache_path}/indexDatabasePath",
                    "indexStorePath": indexStorePath,
                },
            },
        }

    def build_initialized(message):
        pass

    def workspace_buildTargets(message):
        # TODO: 这个可能用不上? #
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "targets": [
                    # {
                    # "id": {
                    #     "uri": "target:test-swiftTests"
                    # },
                    # "displayName": "Second Target",
                    # "baseDirectory": "file:///Users/wang/Desktop/test-swift/Tests/test-swiftTests",
                    # "tags": ["library", "test"],
                    # "capabilities": {
                    #     "canCompile": True,
                    #     "canTest": False,
                    #     "canRun": False
                    # },
                    # "languageIds": ["objective-c", "swift"],
                    # "dependencies": [{
                    #     "uri": "target:test-swift"
                    # }]
                    # }
                ]
            },
        }

    def buildTarget_sources(message):
        # TODO: 这个可能用不上? #
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "items": [
                    # {
                    # "target": {
                    #     "uri": "target:test-swift"
                    # },
                    # "sources": [
                    #     {
                    #         "uri": "file:///Users/wang/Desktop/test-swift/Sources/test-swift/a.swift",
                    #         "kind": 1,
                    #         "generated": False
                    #     },
                    #     {
                    #         "uri": "file:///Users/wang/Desktop/test-swift/Sources/test-swift/test_swift.swift",
                    #         "kind": 1,
                    #         "generated": False
                    #     },
                    # ]
                    # }, {
                    # "target": {
                    #     "uri": "target:test-swiftTests"
                    # },
                    # "sources": [{
                    #     "uri": "file:///Users/wang/Desktop/test-swift/Tests/test-swiftTests/test_swiftTests.swift",
                    #     "kind": 1,
                    #     "generated": False
                    # }]
                    # }
                ]
            },
        }

    def textDocument_registerForChanges(message):
        # empty response, ensure response before notification
        send({"jsonrpc": "2.0", "id": message["id"], "result": None})

        # TODO: observe compile info change
        # is file save trigger a change and update index?
        if message["params"]["action"] == "register":
            uri = message["params"]["uri"]
            try:
                notification = {
                    "jsonrpc": "2.0",
                    "method": "build/sourceKitOptionsChanged",
                    "params": {
                        "uri": uri,
                        "updatedOptions": optionsForFile(uri, compile_file),
                    },
                }
                send(notification)
            except ValueError as e:  # may have other type change register, like target
                logging.debug(e)

    def textDocument_sourceKitOptions(message):
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": optionsForFile(message["params"]["uri"], compile_file),
        }

    # TODO: outputPaths, no spec? #
    def build_shutdown(message):
        return {"jsonrpc": "2.0", "id": message["id"], "result": None}

    def build_exit(message):
        sys.exit()

    return locals()


dispatch = server_api()


def serve():
    logging.info("Xcode Build Server Startup. Waiting Request...")
    while True:
        line = sys.stdin.readline()
        if len(line) == 0:
            break

        assert line.startswith("Content-Length:")
        length = int(line[len("Content-Length:") :])
        sys.stdin.readline()
        raw = sys.stdin.read(length)
        message = json.loads(raw)
        logging.debug("Req --> " + raw)

        response = None
        handler = dispatch.get(message["method"].replace("/", "_"))
        if handler:
            response = handler(message)
        # ignore other notifications
        elif "id" in message:
            response = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {
                    "code": 123,
                    "message": "unhandled method {}".format(message["method"]),
                },
            }

        if response:
            send(response)
