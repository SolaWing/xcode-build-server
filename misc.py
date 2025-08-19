import os

VERSION = "1.3.0"

def bundle_path(path):
    return os.path.abspath(os.path.join(os.path.realpath(__file__), "..", path))

def get_mtime(path):
    """return mtime, or 0 when not exists"""
    if os.path.exists(path):
        try:
            return os.stat(path).st_mtime
        except FileNotFoundError:
            pass
    return 0


def force_remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

def version_compare(a: str, b: str):
    """
    compare version string
    return 1 if a > b
    return 0 if a == b
    return -1 if a < b
    """
    a_parts = a.split(".")
    b_parts = b.split(".")
    for i in range(max(len(a_parts), len(b_parts))):
        a_i = int(a_parts[i]) if i < len(a_parts) else 0
        b_i = int(b_parts[i]) if i < len(b_parts) else 0
        if a_i > b_i:
            return 1
        elif a_i < b_i:
            return -1
    return 0
