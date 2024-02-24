import hashlib
import json
import logging
import os
import sys
from threading import Lock, Thread, main_thread
import time
from typing import Optional
import urllib.parse

from compile_database import GetFlags
from config import ServerConfig
from misc import force_remove, get_mtime


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


def uptodate(target: str, srcs: list[str]):
    target_mtime = get_mtime(target)
    srcs_mtime = (get_mtime(src) for src in srcs)
    return all(src_mtime < target_mtime for src_mtime in srcs_mtime)


class State(object):
    def __init__(self, root_path: str, cache_path):
        """pass in path should be absolute and normalized"""
        self.root_path = root_path
        self.cache_path = cache_path
        os.makedirs(cache_path, exist_ok=True)

        # buildServer.json used as config dict
        config_path = os.path.join(root_path, "buildServer.json")
        self.config = ServerConfig(config_path)

        # opened files need to be notified when flags changed
        self.observed_uri = set()
        # background thread to observe changes
        self.observed_thread: Optional[Thread] = None
        # {path: mtime} cache. use to find changes
        self.observed_info = {self.config.path: get_mtime(self.config.path)}

        self.reinit_compile_info()
        # NOTE:thread-safety: for state shared by main and background thread,
        # can only changed in sync_compile_file

    def get_compile_file(self, config):
        # isolate xcode generate compile file and manual compile_file
        if config.kind == "xcode":
            hash = hashlib.md5(config.build_root.encode("utf-8")).hexdigest()
            name = ["compile_file", config.scheme, hash]
            if config.skip_validate_bin:
                name[0] = "compile_file1"
            return os.path.join(self.cache_path, "-".join(name))
        # manual compile_file
        return os.path.join(self.root_path, ".compile_file")

    def reinit_compile_info(self):
        """all the compile information may change in background"""

        # store use to save compile_datainfo. it will be reload when config changes.
        self.store = {}
        self._compile_file = self.get_compile_file(self.config)
        if os.path.exists(self._compile_file):
            self.compile_file = self._compile_file
            logging.info(f"use flags from {self._compile_file}")
        else:
            self.compile_file = None

        # self._compile_file may change. need to init mtime to avoid trigger a change event
        self.observed_info[self._compile_file] = get_mtime(self._compile_file)

    @property
    def indexStorePath(self) -> Optional[str]:
        if self.config.kind == "xcode":
            if not (root := self.config.build_root):
                return None
            return os.path.join(root, "Index.noindex/DataStore")

        return self.config.indexStorePath

    @property
    def compile_lock_path(self):
        from xclog_parser import output_lock_path

        return output_lock_path(self._compile_file)

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
                logging.exception(f"observe thread exit by exception: {e}")

        self.locking_compile_file = False

        self.observed_thread = Thread(target=start)
        self.observed_thread.start()

    def tick(self):
        if self.handle_build_server_config_change():
            return
        if self.handle_compile_file_change():
            return
        if self.config.kind != "xcode":
            return
        if self.check_locking_compile_file():
            return
        if log_path := self.log_path_for_invalid_compile_file():
            self.trigger_parse(log_path)

    def handle_build_server_config_change(self):
        mtime = get_mtime(self.config.path)
        if mtime > self.observed_info.get(self.config.path, 0):
            self.observed_info[self.config.path] = mtime
            # currently config update is useto change isolate compile_file path.
            # so just check if the path changes
            new_config = ServerConfig(self.config.path)
            if self.get_compile_file(new_config) == self._compile_file:
                return False

            # compile_file did change.. so change it
            def assign():
                self.config = new_config

            self.sync_compile_file(before=assign)
            return True

    def handle_compile_file_change(self):
        compile_file_mtime = get_mtime(self._compile_file)
        if compile_file_mtime > self.observed_info.get(self._compile_file, 0):
            self.sync_compile_file()
            return True

    def check_locking_compile_file(self):
        if self.locking_compile_file:
            mtime = get_mtime(self.compile_lock_path)
            if not mtime:
                pass
            elif time.time() - mtime < 180:
                return True  # still wait
            else:
                logging.warn("updating compile lock timeout! reset it")
                force_remove(self.compile_lock_path)

            self.locking_compile_file = False

    def log_path_for_invalid_compile_file(self) -> Optional[str]:
        """return log path if not valid, else None"""

        # TODO: xcodebuild not generate log until specify -resultBundlePath #

        build_root = self.config.build_root
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

        xcpath = newest_logpath(xcactivitylog_index, self.config.scheme)
        if not (xcpath and (xcpath_mtime := update_check_time(xcpath))):
            return
        if compile_file_mtime > xcpath_mtime:
            return

        return xcpath

    def trigger_parse(self, xcpath):
        # FIXME: ensure index_store_path from buildServer.json consistent with parsed .compile file..
        import xclog_parser
        xclog_parser.hooks_echo_to_log = True

        from xclog_parser import parse, OutputLockedError

        try:
            cmd = ["xclog_parser", "-al", xcpath, "-o", self._compile_file]
            if self.config.skip_validate_bin:
                cmd.append("--skip-validate-bin")
            parse(cmd)
            self.handle_compile_file_change()
        except OutputLockedError:
            self.locking_compile_file = True

    def sync_compile_file(self, before=None):
        """update to newest compile info to main thread

        NOTE: called by observe thread, and block main thread,
        to ensure when exit, all thread is in the runloop and no middle state.
        """
        with lock:
            if before:
                before()
            self.reinit_compile_info()

            # TODO: increment diff change and notify #
            for v in self.observed_uri:
                self.notify_option_changed(v)


# valid after build_initialize. access before should throw
shared_state: State = None  # type: ignore


def server_api():
    """nest def is api, return by locals()"""

    def build_initialize(message):
        rootUri = message["params"]["rootUri"]
        root_path = os.path.abspath(os.path.expanduser(uri2filepath(rootUri)))
        cache_path = os.path.join(
            os.path.expanduser("~/Library/Caches/xcode-build-server"),
            root_path.replace("/", "-"),
        )

        state = State(root_path, cache_path)
        global shared_state
        if shared_state:
            logging.warn("already initialized!!")
        else:
            shared_state = state

        # FIXME: currently indexStorePath can't change dynamicly. have to restart server.
        # though it rarely changes.. need to watch sourcekit-lsp implementation
        indexStorePath = state.indexStorePath
        if not indexStorePath:
            indexStorePath = f"{cache_path}/indexStorePath"

        indexStorePathHash = hashlib.md5(indexStorePath.encode("utf-8")).hexdigest()
        # database should unique to a indexStorePath
        indexDatabasePath = f"{cache_path}/indexDatabasePath-{indexStorePathHash}"

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
                    "indexDatabasePath": indexDatabasePath,
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
    logging.info("Xcode Build Server Startup")
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
