"""runner — loop-team orchestration package.

Exports:
    LoopTeam    — main orchestration class
    parse_config — config file parser
    load_role   — role file loader
    dispatch_role — bound method of LoopTeam; exposed here as a module-level alias
                    for convenience (delegates to LoopTeam.dispatch_role).
"""
from .config import parse_config
from .roles import load_role
from .dispatch import LoopTeam

# Expose dispatch_role as a module-level name pointing at the LoopTeam method.
# Callers who want a standalone function should construct a LoopTeam first.
dispatch_role = LoopTeam.dispatch_role

def version() -> str:
    """Return the package version string."""
    return "0.1.0"


__all__ = ["LoopTeam", "parse_config", "load_role", "dispatch_role", "version"]
