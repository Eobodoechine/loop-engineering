import re


def parse_duration(s):
    """Parse a duration string like '1h30m', '45m', '90s', '2h15m30s'
    into a total number of seconds.

    Supported units: h (hours), m (minutes), s (seconds).
    Raises ValueError on empty or unrecognized input.
    """
    if not isinstance(s, str) or not s.strip():
        raise ValueError("duration must be a non-empty string")
    parts = re.findall(r"(\d+)\s*([hms])", s.strip().lower())
    if not parts:
        raise ValueError("unrecognized duration: %r" % s)
    mult = {"h": 3600, "m": 60, "s": 1}
    return sum(int(n) * mult[u] for n, u in parts)
