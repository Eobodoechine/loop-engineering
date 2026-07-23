"""Compatibility entrypoint for the nested loop-team runner package.

The implementation lives in ``loop-team/runner`` because it belongs to the
loop-team bundle.  Tests and users invoke it from the repository root as
``python -m runner`` or ``import runner``.  This shim makes that root-level
contract work without moving the implementation package.
"""

from pathlib import Path


_IMPL_DIR = Path(__file__).resolve().parent.parent / "loop-team" / "runner"
__path__ = [str(_IMPL_DIR)]

from .config import parse_config  # noqa: E402
from .dispatch import LoopTeam  # noqa: E402
from .roles import load_role  # noqa: E402

dispatch_role = LoopTeam.dispatch_role


def version() -> str:
    """Return the runner package version string."""
    return "0.1.0"


__all__ = ["LoopTeam", "parse_config", "load_role", "dispatch_role", "version"]
