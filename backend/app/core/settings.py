# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deployment settings, read from environment variables or ``.env``.

These are settings that differ per deployment (where the database is).
Business settings that staff change at runtime, such as the deposit refund
policy, live in the database instead.
"""

from pathlib import Path
from typing import ClassVar

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

REPO_ROOT = Path(__file__).resolve().parents[3]
"""Relative file paths in settings are relative to the repository root."""


class Settings(BaseSettings):
    """Settings for one deployment.

    Variable names match the official Postgres image, so one ``.env`` file
    configures both docker compose and the backend.
    """

    # The backend runs from backend/, so also look one level up for .env.
    # Missing files are skipped; real environment variables win over both.
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=("../.env", ".env"), extra="ignore"
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "h2open"
    postgres_user: str = "h2open"
    postgres_password: SecretStr
    fcm_credentials_file: Path | None = None
    """The Firebase service account JSON for sending push messages.

    Keep it in ``secrets/`` (gitignored) and readable only by the backend.
    Without it, push messages are skipped and logged.
    """

    @field_validator("fcm_credentials_file", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def fcm_credentials_path(self) -> Path | None:
        """Where the Firebase credentials are, resolved against the repo root.

        Returns:
            An absolute path, or ``None`` if not configured.
        """
        if self.fcm_credentials_file is None:
            return None
        return REPO_ROOT / self.fcm_credentials_file

    @property
    def database_url(self) -> URL:
        """The SQLAlchemy URL for the async psycopg driver.

        Returns:
            A URL with the password escaped correctly.
        """
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


def load_settings() -> Settings:
    """Read settings from the environment.

    Returns:
        The validated settings.
    """
    return Settings.model_validate({})
