from datetime import datetime, timezone
from typing import Optional

IDENTIFIER = 2847102938475019
EMBED_FIELD_MAX_LENGTH = 1024


def parse_allow_multiple(allow_multiple_text: str) -> tuple[bool, Optional[str]]:
    """Parse and validate allow_multiple_per_role setting."""
    allow_multiple_text = allow_multiple_text.strip().lower()
    allow_multiple = allow_multiple_text in ["yes", "true", "y", "1", ""]

    if allow_multiple_text and allow_multiple_text not in ["yes", "no", "true", "false", "y", "n", "1", "0", ""]:
        return False, "❌ Invalid value for 'Allow Multiple Per Role'. Use 'yes' or 'no'."

    return allow_multiple, None


def _parse_bool_value(value: str) -> Optional[bool]:
    """Parse a yes/no/true/false string to bool, or None if empty."""
    v = value.strip().lower()
    if v in ("yes", "true", "y", "1"):
        return True
    if v in ("no", "false", "n", "0"):
        return False
    return None


def parse_settings_text(
    settings_text: str,
    default_allow_multiple: bool = True,
    default_compact: bool = False,
) -> tuple[bool, bool, Optional[str]]:
    """Parse the combined settings field (allow_multiple + compact)."""
    allow_multiple = default_allow_multiple
    compact = default_compact

    valid_keys = {"allow_multiple", "compact"}
    valid_values = {"yes", "no", "true", "false", "y", "n", "1", "0"}

    for line in settings_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "=" in line:
            key, _, raw_val = line.partition("=")
        elif ":" in line:
            key, _, raw_val = line.partition(":")
        else:
            return allow_multiple, compact, (
                f"❌ Invalid settings format in '{line}'. " 
                "Use 'allow_multiple=yes' or 'compact=no'."
            )

        key = key.strip().lower()
        raw_val = raw_val.strip().lower()

        if key not in valid_keys:
            return allow_multiple, compact, (
                f"❌ Unknown setting '{key}'. "
                "Supported settings: allow_multiple, compact."
            )
        if raw_val not in valid_values:
            return allow_multiple, compact, (
                f"❌ Invalid value '{raw_val}' for '{key}'. Use 'yes' or 'no'."
            )

        parsed = _parse_bool_value(raw_val)
        if key == "allow_multiple":
            allow_multiple = parsed if parsed is not None else default_allow_multiple
        elif key == "compact":
            compact = parsed if parsed is not None else default_compact

    return allow_multiple, compact, None


def parse_roles_from_text(roles_text: str) -> list[str]:
    """Parse roles from multiline text, removing duplicates while preserving order."""
    roles_list = [line.strip() for line in roles_text.split('\n') if line.strip()]

    seen = set()
    unique_roles = []
    for role in roles_list:
        if role and role not in seen:
            seen.add(role)
            unique_roles.append(role)

    return unique_roles


def _parse_roles_from_args(roles: str) -> list[str]:
    """Parse roles from a command argument string (comma or space separated)."""
    if ',' in roles:
        parsed = [r.strip() for r in roles.split(',') if r.strip()]
    else:
        parsed = [r.strip() for r in roles.split() if r.strip()]

    seen = set()
    unique_roles = []
    for role in parsed:
        if role and role not in seen:
            seen.add(role)
            unique_roles.append(role)

    return unique_roles


def validate_roles(roles: list[str]) -> Optional[str]:
    """Validate role list meets requirements."""
    if not roles:
        return "❌ You must specify at least one role for the party."

    if len(roles) > 25:
        return f"❌ You can specify a maximum of 25 roles per party. You provided {len(roles)} roles."

    return None


def parse_scheduled_time(time_str: str) -> tuple[Optional[float], Optional[str]]:
    """Parse a scheduled time string into a Unix timestamp (UTC)."""
    time_str = time_str.strip()

    if time_str.lower() in ("clear", "none", ""):
        return None, None

    formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
    for fmt in formats:
        try:
            dt = datetime.strptime(time_str, fmt)
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp(), None
        except ValueError:
            continue

    return None, (
        "❌ Invalid date format. Use `YYYY-MM-DD HH:MM` (UTC), e.g. `2024-01-15 20:00`."
    )


def format_timestamp(ts) -> str:
    if ts is None:
        return "None"
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, OSError):
        return str(ts)
