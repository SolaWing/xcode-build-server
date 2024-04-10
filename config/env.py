# use to get environ config
from functools import cache
import os

class Env:
    def on(self, value: str):
        try:
            c = value[0]
            if c.isdigit(): return bool(int(c))
            return c in ["t", "T", "y", "Y"]
        except Exception:
            return False

    def on_key(self, key: str, default = False):
        if value := os.environ.get(key):
            return self.on(value)
        return default

    @property
    @cache
    def new_file(self):
        return self.on_key("XBS_FEAT_NEWFILE", default=True)

env = Env()

