# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Password hashing with scrypt from the standard library. Private.

Parameters follow the OWASP Password Storage Cheat Sheet (N=2^15, r=8,
p=3: about 32 MiB per hash). They are stored in each hash, so they can be
raised later without breaking existing passwords. Hashing runs in a worker
thread so a login never blocks other requests.
"""

import base64
import binascii
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from anyio import to_thread

_PREFIX = "scrypt"
_SALT_BYTES = 16
_KEY_BYTES = 32
_MAX_MEMORY = 256 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Cost:
    """scrypt work factors."""

    n: int
    r: int
    p: int


COST = Cost(n=2**15, r=8, p=3)
"""Used for new hashes. Tests lower it to keep the suite fast."""


def _derive(password: str, salt: bytes, cost: Cost) -> bytes:
    return hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=cost.n,
        r=cost.r,
        p=cost.p,
        maxmem=_MAX_MEMORY,
        dklen=_KEY_BYTES,
    )


def _encode(salt: bytes, key: bytes, cost: Cost) -> str:
    salt_text = base64.b64encode(salt).decode()
    key_text = base64.b64encode(key).decode()
    return f"{_PREFIX}${cost.n}${cost.r}${cost.p}${salt_text}${key_text}"


def _hash_sync(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    return _encode(salt, _derive(password, salt, COST), COST)


def _verify_sync(password: str, encoded: str) -> bool:
    try:
        prefix, n, r, p, salt_text, key_text = encoded.split("$")
        cost = Cost(n=int(n), r=int(r), p=int(p))
        salt, key = base64.b64decode(salt_text), base64.b64decode(key_text)
    except ValueError, binascii.Error:
        return False
    if prefix != _PREFIX:
        return False
    return hmac.compare_digest(_derive(password, salt, cost), key)


async def hash_password(password: str) -> str:
    """Hash a password for storage.

    Args:
        password: The plain-text password.

    Returns:
        A self-describing hash: ``scrypt$N$r$p$salt$key``.
    """
    return await to_thread.run_sync(_hash_sync, password)


async def verify_password(password: str, encoded: str) -> bool:
    """Check a password against a stored hash, in constant time.

    Args:
        password: The plain-text password to check.
        encoded: A hash from :func:`hash_password`.

    Returns:
        Whether the password matches. Malformed hashes never match.
    """
    return await to_thread.run_sync(_verify_sync, password, encoded)


DUMMY_HASH = _encode(b"\0" * _SALT_BYTES, b"\0" * _KEY_BYTES, COST)
"""Checked against when a username is unknown, so that takes as long as a
wrong password and response times don't reveal which usernames exist."""
