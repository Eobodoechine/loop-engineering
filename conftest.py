"""Repository-wide pytest environment normalization."""

import os
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent
CANONICAL_LOOP_ROOT = pathlib.Path("~/Claude/loop").expanduser()


def _prepend_path_if_present(path):
    if not os.path.isdir(path):
        return
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if path not in parts:
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")


def _ensure_canonical_loop_root():
    """Make this checkout reachable at the canonical ``~/Claude/loop`` path.

    Much of the suite resolves kit files through the canonical loop root
    (``os.path.expanduser("~/Claude/loop/...")``) rather than relative to the
    test file. On a developer machine that path *is* the checkout, so the
    tests pass. In CI, a container, or any fresh clone it does not exist, and
    roughly 120 tests fail for reasons unrelated to the code under test —
    which would make the suite unusable as a required merge-gate check.

    This only ever creates a symlink, and only when nothing occupies the
    path. An existing real directory, or a link pointing at a different
    checkout, is left untouched: a developer with a real ``~/Claude/loop``
    keeps exactly the behavior they had before.
    """
    if CANONICAL_LOOP_ROOT.exists() or CANONICAL_LOOP_ROOT.is_symlink():
        return
    try:
        CANONICAL_LOOP_ROOT.parent.mkdir(parents=True, exist_ok=True)
        CANONICAL_LOOP_ROOT.symlink_to(REPO_ROOT, target_is_directory=True)
    except OSError:
        # Read-only or unwritable HOME. Tests that genuinely need the root
        # will still report it themselves; do not mask that here.
        pass


_prepend_path_if_present("/opt/homebrew/bin")
_ensure_canonical_loop_root()
