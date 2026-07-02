"""Root-level ``python -m runner`` entrypoint.

Delegates to the implementation package under ``loop-team/runner``.
"""

from pathlib import Path
import runpy


_IMPL_MAIN = Path(__file__).resolve().parent.parent / "loop-team" / "runner" / "__main__.py"
runpy.run_path(str(_IMPL_MAIN), run_name="__main__")
