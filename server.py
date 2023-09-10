from typing import Optional
import json
import logging
import os
import sys
import urllib.parse
import time
from threading import Thread, main_thread, Lock
from pathlib import Path

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


def get_mtime(path):
    if os.path.exists(path):
        try:
            return os.stat(path).st_mtime
        except FileNotFoundError:
            pass
    return 0


def uptodate(target: str, srcs: list[str]):
    target_mtime = get_mtime(target)
    srcs_mtime = (get_mtime(src) for src in srcs)
    return all(src_mtime < target_mtime for src_mtime in srcs_mtime)


class State(object):
    def __init__(self, root_path: str):
        self.root_path = root_path

        # 优先共用root compile_file里的编译信息
        self._compile_file = os.path.join(root_path, ".compile")
        if os.path.exists(self._compile_file):
            self.compile_file = self._compile_file
        else:
            self.compile_file = None

        self.store = {}  # store use to save compile_datainfo

        # buildServer.json used as config dict
        self.config_dict: dict = {}
        config_path = os.path.join(root_path, "buildServer.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                self.config_dict = json.load(f)

        self.observed_uri = set()
        self.observed_thread: Optional[Thread] = None

    @property
    def indexStorePath(self) -> Optional[str]:
        if not self.config_dict:
            return None

        indexStorePath: Optional[str] = self.config_dict.get("indexStorePath", None)
        if indexStorePath:
            return indexStorePath

        indexStorePath = self.config_dict.get("build_root", None)
        if indexStorePath:
            return os.path.join(indexStorePath, "Index.noindex/DataStore")

    @property
    def compile_lock_path(self):
        return self._compile_file + ".lock"

    def optionsForFile(self, uri):
        file_path = uri2filepath(uri)
        flags = GetFlags(file_path, self.compile_file, store=self.store)[
            "flags"
        ]  # type: list
        try:
            workdir = flags[flags.index("-working-directory") + 1]
        except (IndexError, ValueError):
            workdir = os.getcwd()
        return {
            "options": flags,
            "workingDirectory": workdir,
        }

    def notify_option_changed(self, uri):
        try:
            notification = {
                "jsonrpc": "2.0",
                "method": "build/sourceKitOptionsChanged",
                "params": {
                    "uri": uri,
                    "updatedOptions": self.optionsForFile(uri),
                },
            }
            send(notification)
            return True
        except ValueError as e:  # may have other type change register, like target
            logging.debug(e)

    def shutdown(self):
        self.observed_thread = None  # release to end in subthread

    ########## observed flag changes in background

    def start_observe_changes(self):
        if self.observed_thread:
            logging.warn("already observing!!")
            return

        def start():
            try:
                while (
                    self.observed_thread
                    and main_thread().is_alive()
                    and self == shared_state
                ):
                    self.tick()
                    time.sleep(1)
            except Exception as e:
                logging.warn(f"observe thread exit by exception: {e}")

        self.observed_info = {
            self._compile_file: get_mtime(self._compile_file)
        }  # path => mtime
        self.locking_compile_file = False

        self.observed_thread = Thread(target=start)
        self.observed_thread.start()

    def tick(self):
        if self.handle_compile_file_change():
            return
        if not self.config_dict.get("build_root", None):
            return
        if self.check_locking_compile_file():
            return
        if log_path := self.log_path_for_invalid_compile_file():
            self.trigger_parse(log_path)

    def handle_compile_file_change(self):
        compile_file_mtime = get_mtime(self._compile_file)
        if compile_file_mtime > self.observed_info.get(self._compile_file, 0):
            self.sync_compile_file()
            self.observed_info[self._compile_file] = compile_file_mtime
            return True

    def check_locking_compile_file(self):
        if self.locking_compile_file:
            mtime = get_mtime(self.compile_lock_path)
            if not mtime:
                pass
            elif time.time() - mtime < 180:
                return True
            else:
                logging.warn("updating compile lock timeout! reset it")
                try:
                    os.remove(self.compile_lock_path)
                except FileNotFoundError:  # already removed by other. skip this check
                    return True

            self.locking_compile_file = False

    def log_path_for_invalid_compile_file(self) -> Optional[str]:
        """return log path if not valid, else None"""

        # TODO: xcodebuild not generate log until specify -resultBundlePath #

        build_root = self.config_dict.get("build_root")
        assert isinstance(build_root, str)

        from xcactivitylog import metapath_from_buildroot, newest_logpath

        def update_check_time(path):
            """return mtime if updated, else None"""
            mtime = get_mtime(path)
            if mtime > self.observed_info.get(path, 0):
                self.observed_info[path] = mtime
                return mtime
            return None

        compile_file_mtime = self.observed_info[self._compile_file]
        xcactivitylog_index = metapath_from_buildroot(build_root)
        if not (xcactivitylog_index_mtime := update_check_time(xcactivitylog_index)):
            return
        if compile_file_mtime > xcactivitylog_index_mtime:
            return

        xcpath = newest_logpath(
            xcactivitylog_index, self.config_dict.get("scheme", None)
        )
        if not (xcpath and (xcpath_mtime := update_check_time(xcpath))):
            return
        if compile_file_mtime > xcpath_mtime:
            return

        return xcpath

    def trigger_parse(self, xcpath):
        # lock and trigger parse compile
        lock_path = self.compile_lock_path
        try:
            Path(lock_path).touch(exist_ok=False)
        except FileExistsError:
            self.locking_compile_file = True
            return

        try:
            from xclog_parser import main

            # TODO: echo handle
            args = ["xclog_parser", "-al", xcpath, "-o", self._compile_file]
            main(args)
        finally:
            try:
                os.remove(lock_path)
            except FileNotFoundError:
                pass

        self.handle_compile_file_change()

    def sync_compile_file(self):
        """update to newest compile info"""
        with lock:
            self.store = {}
            self.compile_file = (
                self._compile_file if os.path.exists(self._compile_file) else None
            )

            # TODO: increment diff change and notify #
            for v in self.observed_uri:
                self.notify_option_changed(v)


# valid after build_initialize. access before should throw
shared_state: State = None  # type: ignore


def server_api():
    """nest def is api, return by locals()"""

    def build_initialize(message):
        rootUri = message["params"]["rootUri"]
        cache_path = os.path.join(
            os.path.expanduser("~/Library/Caches/xcode-build-server"),
            rootUri.replace("/", "-").replace("%", "X"),
        )
        rootPath = uri2filepath(rootUri)

        state = State(rootPath)
        global shared_state
        if shared_state:
            logging.warn("already initialized!!")
        else:
            shared_state = state

        indexStorePath = state.indexStorePath
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
                    "languageIds": ["c", "cpp", "objective-c", "objective-cpp", "swift"]
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
        shared_state.start_observe_changes()

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
        action = message["params"]["action"]
        uri = message["params"]["uri"]
        if action == "register":
            if shared_state.notify_option_changed(uri):
                shared_state.observed_uri.add(uri)
        elif action == "unregister":
            shared_state.observed_uri.remove(uri)

    def textDocument_sourceKitOptions(message):
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": shared_state.optionsForFile(message["params"]["uri"]),
        }

    # TODO: outputPaths, no spec? #
    def build_shutdown(message):
        shared_state.shutdown()
        return {"jsonrpc": "2.0", "id": message["id"], "result": None}

    def build_exit(message):
        sys.exit()

    return locals()


dispatch = server_api()
lock = Lock()


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

        with lock:
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
