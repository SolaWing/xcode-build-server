import json
import sys

def dump_server_config(store=None):
    """write buildServer.json to cwd"""
    h = {
        "name": "xcode build server",
        "version": "0.1",
        "bspVersion": "2.0",
        "languages": ["c","cpp","objective-c","objective-cpp","swift"],
        "argv": [sys.argv[0]],
    }
    if store:
        h["indexStorePath"] = store
    with open("buildServer.json", "w") as f:
        json.dump(h, f)
