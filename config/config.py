from functools import cache
import json
import os
import sys


def _config_property(name, default=None, doc=None, delete_none=True):
    """
    default only affect getter, not write into data
    """
    def fget(self):
        return self.data.get(name, default)

    def fset(self, value):
        if delete_none and value is None:
            self.data.pop(name, None)
        else:
            self.data[name] = value

    def fdel(self):
        del self.data[name]

    return property(fget, fset, fdel, doc)

class ServerConfig(object):
    """this class control all user config. options:

    kind: xcode|manual  # where to find flags. default: manual
    when kind=xcode:
        workspace: the bind workspace path
        scheme: the bind scheme
        build_root: the build_root find from xcworkspace and scheme
    when kind=manual(or no kind):
        indexStorePath?: the manual parsed index path. may not exists

    user can change scheme by call `xcode-build-server config`,
    or change to manual by call `xcode-build-server parse` directly.

    after config change. server should change to new flags too..

    other config:
    skip_validate_bin: if true, will skip validate bin for background parser
    """

    # TODO: distinguish configuration and destination #

    default_path = "buildServer.json"

    kind = _config_property("kind", default="manual")
    workspace = _config_property("workspace")
    scheme = _config_property("scheme")
    build_root = _config_property("build_root")
    indexStorePath = _config_property("indexStorePath")

    skip_validate_bin = _config_property("skip_validate_bin")

    @cache
    def shared():
        return ServerConfig(ServerConfig.default_path)

    def __init__(self, path):
        self.path = os.path.abspath(path)
        if os.path.exists(path):
            with open(path, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {}

        self.data.update({
            "name": "xcode build server",
            "version": "0.2",
            "bspVersion": "2.0",
            "languages": ["c", "cpp", "objective-c", "objective-cpp", "swift"],
            "argv": [sys.argv[0]]
        })

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent="\t")
