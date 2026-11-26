# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for deployment settings."""

from pathlib import Path

import pytest

from app.core.settings import REPO_ROOT, Settings, load_settings


def test_tests_never_use_real_push_credentials() -> None:
    """The test run blanks FCM_CREDENTIALS_FILE, which means "not set"."""
    assert load_settings().fcm_credentials_path is None


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_credentials_path_is_unset(blank: str) -> None:
    """An empty value in .env turns push messages off."""
    settings = Settings.model_validate({"fcm_credentials_file": blank})
    assert settings.fcm_credentials_path is None


def test_credentials_paths_are_relative_to_the_repo() -> None:
    """Relative paths start at the repository root; absolute ones are kept."""
    relative = Settings.model_validate(
        {"fcm_credentials_file": "secrets/firebase.json"}
    )
    assert relative.fcm_credentials_path == REPO_ROOT / "secrets" / "firebase.json"
    assert (REPO_ROOT / "backend" / "pyproject.toml").is_file()

    absolute = Settings.model_validate({"fcm_credentials_file": "/run/secrets/fcm"})
    assert absolute.fcm_credentials_path == Path("/run/secrets/fcm")
