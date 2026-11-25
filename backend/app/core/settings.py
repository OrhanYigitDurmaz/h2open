# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deployment settings, read from environment variables or ``.env``.

These are settings that differ per deployment (where the database is).
Business settings that staff change at runtime, such as the deposit refund
policy, live in the database instead.
"""

from typing import ClassVar

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


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
