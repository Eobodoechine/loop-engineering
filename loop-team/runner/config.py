"""config.py — parse ~/.loop-team-config (or a given path) into a Config object."""
import os
import pathlib


class RoleConfig:
    """Per-role overrides (provider, model)."""
    def __init__(self, provider=None, model=None):
        self.provider = provider
        self.model = model


class Config:
    """Structured configuration parsed from the loop-team config file."""
    def __init__(self, base_dir, provider, default_model, roles=None):
        self.base_dir = pathlib.Path(base_dir)
        self.provider = provider
        self.default_model = default_model
        # roles: dict of role_name -> RoleConfig
        self.roles = roles or {}


def parse_config(config_path=None):
    """Parse the loop-team config file and return a Config object.

    Args:
        config_path: Path to the config file. Defaults to ~/.loop-team-config.

    Returns:
        Config object with base_dir, provider, default_model, and roles.
    """
    if config_path is None:
        config_path = pathlib.Path("~/.loop-team-config").expanduser()
    else:
        config_path = pathlib.Path(config_path)

    raw = {}
    role_data = {}  # role_name -> {key: value}

    if config_path.exists():
        for line in config_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            if key.startswith("role."):
                # role.<name>.<attr>=<value>
                parts = key.split(".", 2)
                if len(parts) == 3:
                    _, role_name, attr = parts
                    if role_name not in role_data:
                        role_data[role_name] = {}
                    role_data[role_name][attr] = value
            else:
                raw[key] = value

    # Determine the default base_dir (used only when the config omits base_dir).
    # Primary default preserves the documented contract: ~/Claude/loop.
    _primary_default = pathlib.Path("~/Claude/loop").expanduser()
    if (_primary_default / "loop-team" / "roles").is_dir():
        _default_base = _primary_default
    else:
        # Fresh environment without the documented tree: derive from this
        # package's location so a config-less LoopTeam() still resolves roles.
        # config.py lives at <repo>/loop-team/runner/config.py, so parents[2] = <repo>.
        _default_base = pathlib.Path(__file__).resolve().parents[2]

    # Expand ~ in base_dir (an explicit config value is parsed/expanded as before)
    base_dir_raw = raw.get("base_dir", str(_default_base))
    base_dir = pathlib.Path(os.path.expanduser(base_dir_raw))

    provider = raw.get("provider", "anthropic")
    default_model = raw.get("default_model", "claude-haiku-4-5-20251001")

    roles = {}
    for role_name, attrs in role_data.items():
        roles[role_name] = RoleConfig(
            provider=attrs.get("provider"),
            model=attrs.get("model"),
        )

    return Config(
        base_dir=base_dir,
        provider=provider,
        default_model=default_model,
        roles=roles,
    )
