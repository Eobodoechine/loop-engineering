"""Repository-wide pytest environment normalization."""

import os


def _prepend_path_if_present(path):
    if not os.path.isdir(path):
        return
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if path not in parts:
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")


_prepend_path_if_present("/opt/homebrew/bin")
