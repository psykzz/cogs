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
