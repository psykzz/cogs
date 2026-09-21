"""Unit tests for party cog settings."""

import importlib.util
from pathlib import Path

import pytest


_HELPERS_PATH = Path(__file__).parents[1] / "party" / "helpers.py"
_SPEC = importlib.util.spec_from_file_location("party_helpers", _HELPERS_PATH)
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)


def test_party_settings_default_user_signup_limit():
    """The user signup limit defaults to one."""
    allow_multiple, compact, max_signups_per_user, error = _HELPERS.parse_settings_text("")

    assert allow_multiple is True
    assert compact is False
    assert max_signups_per_user == 1
    assert error is None


def test_party_settings_accepts_positive_user_signup_limit():
    """A party may allow a user to sign up for multiple roles."""
    allow_multiple, compact, max_signups_per_user, error = _HELPERS.parse_settings_text(
        "allow_multiple=no\ncompact=yes\nmax_signups_per_user=2"
    )

    assert allow_multiple is False
    assert compact is True
    assert max_signups_per_user == 2
    assert error is None


@pytest.mark.parametrize("value", ("0", "-1", "one"))
def test_party_settings_rejects_non_positive_user_signup_limit(value):
    """The user signup limit must be a positive whole number."""
    *_, error = _HELPERS.parse_settings_text(f"max_signups_per_user={value}")

    assert error == "❌ 'max_signups_per_user' must be a positive whole number."


def test_single_user_signup_limit_replaces_existing_role():
    """The default retains the existing one-role replacement behavior."""
    signups = {"Tank": ["1"], "Healer": ["2"]}

    error = _HELPERS.add_user_signup(signups, "1", "Healer", 1)

    assert error is None
    assert signups == {"Tank": [], "Healer": ["2", "1"]}


def test_multiple_user_signup_limit_adds_distinct_roles():
    """A higher limit preserves existing roles and adds another distinct role."""
    signups = {"Tank": ["1"], "Healer": []}

    error = _HELPERS.add_user_signup(signups, "1", "Healer", 2)

    assert error is None
    assert signups == {"Tank": ["1"], "Healer": ["1"]}


def test_multiple_user_signup_limit_rejects_duplicate_role():
    """A user may not consume multiple slots for the same role."""
    signups = {"Tank": ["1"], "Healer": []}

    error = _HELPERS.add_user_signup(signups, "1", "Tank", 2)

    assert error == "duplicate_role"
    assert signups == {"Tank": ["1"], "Healer": []}


def test_multiple_user_signup_limit_rejects_role_beyond_limit():
    """A user cannot add a distinct role after reaching the configured limit."""
    signups = {"Tank": ["1"], "Healer": ["1"], "DPS": []}

    error = _HELPERS.add_user_signup(signups, "1", "DPS", 2)

    assert error == "limit_reached"
    assert signups == {"Tank": ["1"], "Healer": ["1"], "DPS": []}
