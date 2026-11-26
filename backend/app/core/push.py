# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sending push messages through Firebase Cloud Messaging.

Uses the FCM HTTP v1 API directly. Google wants a short-lived OAuth token
for it, which we mint by signing a JWT with the service account's private
key (RS256) and trading it at Google's token endpoint. The token is cached
until shortly before it expires.

Only data messages are sent, at high priority: the app decides what to
show, and Android wakes it even in the background (for incoming calls).
"""

import base64
import json
import logging
import time
from enum import StrEnum
from http import HTTPStatus
from typing import TYPE_CHECKING, ClassVar, Literal, Protocol

import httpx2
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.settings import load_settings

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

logger = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
GOOGLE_OAUTH_ENDPOINT = "https://oauth2.googleapis.com/token"
JWT_BEARER = "urn:ietf:params:oauth:grant-type:jwt-bearer"
TOKEN_LIFETIME = 3600
REFRESH_MARGIN = 60
"""Seconds before expiry when a cached access token is replaced."""
DEAD_TOKEN_CODES = frozenset({"UNREGISTERED", "SENDER_ID_MISMATCH"})


class SendOutcome(StrEnum):
    """What happened to one push message."""

    SENT = "sent"
    UNREGISTERED = "unregistered"
    """The phone's token is no longer valid (app removed or reinstalled)."""
    SKIPPED = "skipped"
    """Push messages are not configured; the message was only logged."""


class PushError(Exception):
    """Sending failed in a way that may work later (network, quota, outage)."""


class PushStatus(BaseModel):
    """Whether push messages can be sent, for the admin page."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    configured: bool
    project_id: str | None
    problem: str | None
    """Why push messages are off, if they are."""


class PushSender(Protocol):
    """Something that delivers push messages to phones."""

    @property
    def status(self) -> PushStatus:
        """Whether this sender really sends."""
        ...

    async def send(
        self, token: str, data: Mapping[str, str], *, ttl_seconds: int
    ) -> SendOutcome:
        """Send one data message to one phone."""
        ...


class LoggingSender:
    """Used when Firebase is not configured: logs messages instead."""

    def __init__(self, problem: str) -> None:
        """Create the sender.

        Args:
            problem: Why push messages are off, shown to admins.
        """
        self._status: PushStatus = PushStatus(
            configured=False, project_id=None, problem=problem
        )

    @property
    def status(self) -> PushStatus:
        """Push messages are off.

        Returns:
            The status, with the reason.
        """
        return self._status

    async def send(
        self, token: str, data: Mapping[str, str], *, ttl_seconds: int
    ) -> SendOutcome:
        """Log the message instead of sending it.

        Returns:
            Always ``SKIPPED``.
        """
        logger.info(
            "push skipped (%s): %s to …%s, ttl %ss",
            self._status.problem,
            dict(data),
            token[-6:],
            ttl_seconds,
        )
        return SendOutcome.SKIPPED


class ServiceAccount(BaseModel):
    """The parts of a Firebase service account key file we use."""

    type: Literal["service_account"]
    project_id: str
    client_email: str
    private_key: str
    token_uri: str = GOOGLE_OAUTH_ENDPOINT


class _TokenResponse(BaseModel):
    access_token: str
    expires_in: int = TOKEN_LIFETIME


class _ErrorDetail(BaseModel):
    error_code: str | None = Field(default=None, alias="errorCode")


class _Error(BaseModel):
    details: list[_ErrorDetail] = []


class _ErrorBody(BaseModel):
    error: _Error


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _error_codes(response: httpx2.Response) -> set[str]:
    try:
        body = _ErrorBody.model_validate_json(response.content)
    except ValidationError:
        return set()
    return {d.error_code for d in body.error.details if d.error_code is not None}


class FcmSender:
    """Sends data messages through FCM HTTP v1."""

    def __init__(
        self,
        account: ServiceAccount,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Create the sender.

        Args:
            account: The service account.
            transport: How HTTP requests are made; tests replace it.
            clock: The current Unix time; tests replace it.

        Raises:
            TypeError: The private key is not an RSA key.
        """
        key = serialization.load_pem_private_key(
            account.private_key.encode(), password=None
        )
        if not isinstance(key, rsa.RSAPrivateKey):
            msg = "the service account's private key is not an RSA key"
            raise TypeError(msg)
        self._account: ServiceAccount = account
        self._key: rsa.RSAPrivateKey = key
        self._transport: httpx2.AsyncBaseTransport | None = transport
        self._clock: Callable[[], float] = clock
        self._token: str | None = None
        self._token_expires: float = 0.0

    @property
    def status(self) -> PushStatus:
        """Push messages are on.

        Returns:
            The status, with the Firebase project.
        """
        return PushStatus(
            configured=True, project_id=self._account.project_id, problem=None
        )

    def _assertion(self, now: int) -> str:
        header = {"alg": "RS256", "typ": "JWT"}
        claims = {
            "iss": self._account.client_email,
            "scope": SCOPE,
            "aud": self._account.token_uri,
            "iat": now,
            "exp": now + TOKEN_LIFETIME,
        }
        signing_input = ".".join(
            _b64(json.dumps(part, separators=(",", ":")).encode())
            for part in (header, claims)
        )
        signature = self._key.sign(
            signing_input.encode(), padding.PKCS1v15(), hashes.SHA256()
        )
        return f"{signing_input}.{_b64(signature)}"

    async def _access_token(self, http: httpx2.AsyncClient) -> str:
        """A valid OAuth access token, fetched again when about to expire.

        Returns:
            The token.

        Raises:
            PushError: Google refused or could not be reached.
        """
        now = self._clock()
        if self._token is not None and now < self._token_expires - REFRESH_MARGIN:
            return self._token
        response = await http.post(
            self._account.token_uri,
            data={"grant_type": JWT_BEARER, "assertion": self._assertion(int(now))},
        )
        if response.status_code != HTTPStatus.OK:
            msg = f"Google token endpoint answered {response.status_code}"
            raise PushError(msg)
        token = _TokenResponse.model_validate_json(response.content)
        self._token = token.access_token
        self._token_expires = now + token.expires_in
        return token.access_token

    async def send(
        self, token: str, data: Mapping[str, str], *, ttl_seconds: int
    ) -> SendOutcome:
        """Send one high-priority data message.

        Returns:
            ``SENT``, or ``UNREGISTERED`` if the phone's token is dead.

        Raises:
            PushError: Anything that may succeed on a later try.
        """
        url = (
            "https://fcm.googleapis.com/v1/projects/"
            f"{self._account.project_id}/messages:send"
        )
        message = {
            "token": token,
            "data": dict(data),
            "android": {"priority": "high", "ttl": f"{ttl_seconds}s"},
        }
        try:
            async with httpx2.AsyncClient(
                transport=self._transport, timeout=10
            ) as http:
                access = await self._access_token(http)
                response = await http.post(
                    url,
                    json={"message": message},
                    headers={"Authorization": f"Bearer {access}"},
                )
        except httpx2.HTTPError as error:
            msg = f"could not reach Firebase: {error!r}"
            raise PushError(msg) from error
        if response.status_code == HTTPStatus.OK:
            return SendOutcome.SENT
        if _error_codes(response) & DEAD_TOKEN_CODES:
            return SendOutcome.UNREGISTERED
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            self._token = None
        msg = f"FCM answered {response.status_code}: {response.text[:300]}"
        raise PushError(msg)


def load_sender(path: Path | None) -> PushSender:
    """The sender for this deployment's settings.

    A missing or broken credentials file turns push messages off rather
    than stopping the whole backend; admins see why on the status page.

    Args:
        path: The service account file, if configured.

    Returns:
        A sender that sends, or one that only logs.
    """
    if path is None:
        return LoggingSender("FCM_CREDENTIALS_FILE is not set")
    try:
        account = ServiceAccount.model_validate_json(path.read_bytes())
        return FcmSender(account)
    except (OSError, ValidationError, ValueError, TypeError) as error:
        logger.exception("push messages are off: cannot use %s", path)
        return LoggingSender(f"cannot use {path.name}: {type(error).__name__}")


class _Current:
    """The process-wide sender, created from the settings on first use."""

    sender: ClassVar[PushSender | None] = None


def get_sender() -> PushSender:
    """The sender for this deployment.

    Returns:
        The sender.
    """
    if _Current.sender is None:
        _Current.sender = load_sender(load_settings().fcm_credentials_path)
    return _Current.sender


def use_sender(sender: PushSender | None) -> None:
    """Replace the sender (tests), or forget it so settings are read again.

    Args:
        sender: The new sender, or ``None``.
    """
    _Current.sender = sender
