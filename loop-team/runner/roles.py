"""roles.py — load role prompt files from the roles/ directory."""
import pathlib


def load_role(role_name: str, base_dir) -> str:
    """Load a role's prompt from roles/<role_name>.md under the loop-team directory.

    Args:
        role_name: The name of the role (e.g. 'coder', 'verifier').
        base_dir: The base directory (e.g. ~/Claude/loop).
                  The roles directory is expected at <base_dir>/loop-team/roles/.

    Returns:
        The content of the role file as a string.

    Raises:
        FileNotFoundError: If the role file does not exist.
    """
    base_dir = pathlib.Path(base_dir)
    path = base_dir / "loop-team" / "roles" / f"{role_name}.md"
    if not path.exists():
        raise FileNotFoundError(
            f"Role file not found: roles/{role_name}.md (looked in {path})"
        )
    return path.read_text()
