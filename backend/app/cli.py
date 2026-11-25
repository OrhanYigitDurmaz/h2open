# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command-line tools for running h2open on the server.

Create the first admin (the password is asked for, never passed as an
argument, so it doesn't end up in shell history)::

    uv run python -m app.cli create-user --username admin --name "Admin" --role admin
"""

import argparse
import asyncio
import getpass
import sys
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.core.db import Database
from app.core.errors import DomainError
from app.core.settings import load_settings
from app.modules.identity import api as identity

if TYPE_CHECKING:
    from collections.abc import Sequence


class _Args(argparse.Namespace):
    """Typed parsed arguments."""

    def __init__(self) -> None:
        super().__init__()
        self.username: str = ""
        self.name: str = ""
        self.roles: list[str] = []


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(required=True, metavar="command")
    create = commands.add_parser(
        "create-user", help="add a user; asks for the password"
    )
    _ = create.add_argument("--username", required=True)
    _ = create.add_argument("--name", required=True)
    _ = create.add_argument(
        "--role",
        dest="roles",
        action="append",
        required=True,
        choices=[role.value for role in identity.Role],
        help="repeat for several roles",
    )
    return parser


async def _create_user(data: identity.UserCreate) -> identity.UserView:
    database = Database.connect(load_settings().database_url)
    try:
        async with database.transaction() as session:
            return await identity.create_user(session, data)
    finally:
        await database.dispose()


def _fail(message: str) -> int:
    _ = sys.stderr.write(f"error: {message}\n")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run a command.

    Args:
        argv: Arguments without the program name; defaults to ``sys.argv``.

    Returns:
        The process exit code.
    """
    args = _parser().parse_args(argv, namespace=_Args())
    password = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != password:
        return _fail("the passwords do not match")
    try:
        data = identity.UserCreate(
            username=args.username,
            name=args.name,
            password=password,
            roles={identity.Role(role) for role in args.roles},
        )
        user = asyncio.run(_create_user(data))
    except ValidationError as error:
        problems = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in error.errors())
        return _fail(problems)
    except DomainError as error:
        return _fail(str(error))
    _ = sys.stdout.write(f"created {user.username} ({', '.join(user.roles)})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
