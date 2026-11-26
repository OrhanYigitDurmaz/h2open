# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command-line tools for running h2open on the server.

Create the first admin (the password is asked for, never passed as an
argument, so it doesn't end up in shell history)::

    uv run python -m app.cli create-user --username admin --name "Admin" --role admin

Write the API description (OpenAPI) to ``docs/openapi.json``, for the apps
and for agents building them::

    uv run python -m app.cli export-openapi
"""

import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.core.db import Database
from app.core.errors import DomainError
from app.core.settings import REPO_ROOT, load_settings
from app.main import app
from app.modules.identity import api as identity

if TYPE_CHECKING:
    from collections.abc import Sequence


OPENAPI_FILE = REPO_ROOT / "docs" / "openapi.json"


class _Args(argparse.Namespace):
    """Typed parsed arguments."""

    def __init__(self) -> None:
        super().__init__()
        self.command: str = ""
        self.output: Path = OPENAPI_FILE
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
    create.set_defaults(command="create-user")
    export = commands.add_parser(
        "export-openapi", help="write the API description as OpenAPI JSON"
    )
    _ = export.add_argument(
        "--output", type=Path, default=OPENAPI_FILE, help="default: %(default)s"
    )
    export.set_defaults(command="export-openapi")
    return parser


async def _add_user(data: identity.UserCreate) -> identity.UserView:
    database = Database.connect(load_settings().database_url)
    try:
        async with database.transaction() as session:
            return await identity.create_user(session, data)
    finally:
        await database.dispose()


def _fail(message: str) -> int:
    _ = sys.stderr.write(f"error: {message}\n")
    return 1


def _export_openapi(output: Path) -> int:
    """Write the OpenAPI description, only touching the file if it changed.

    Returns:
        The exit code.
    """
    text = json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"
    if output.is_file() and output.read_text(encoding="utf-8") == text:
        _ = sys.stdout.write(f"{output} is up to date\n")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(text, encoding="utf-8")
    _ = sys.stdout.write(f"updated {output}\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run a command.

    Args:
        argv: Arguments without the program name; defaults to ``sys.argv``.

    Returns:
        The process exit code.
    """
    args = _parser().parse_args(argv, namespace=_Args())
    if args.command == "export-openapi":
        return _export_openapi(args.output)
    return _create_user(args)


def _create_user(args: _Args) -> int:
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
        user = asyncio.run(_add_user(data))
    except ValidationError as error:
        problems = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in error.errors())
        return _fail(problems)
    except DomainError as error:
        return _fail(str(error))
    _ = sys.stdout.write(f"created {user.username} ({', '.join(user.roles)})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
