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

    @property
    @cache
    def new_file(self):
        if newfile := os.environ.get("XBS_FEAT_NEWFILE"):
            return self.on(newfile)
        return False

env = Env()

