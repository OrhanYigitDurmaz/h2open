# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for sending through Firebase Cloud Messaging, against a fake Google."""

import asyncio
import base64
import json
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

import httpx2
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from app.core.push import (
    JWT_BEARER,
    SCOPE,
    FcmSender,
    LoggingSender,
    PushError,
    SendOutcome,
    ServiceAccount,
    load_sender,
)

if TYPE_CHECKING:
    from pathlib import Path

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OAUTH_URL = "https://oauth2.example.test/token"
SEND_URL = "https://fcm.googleapis.com/v1/projects/h2open-test/messages:send"
DATA = {"type": "pool_changed", "order_id": "x", "number": "7"}
TTL = 300
HOUR = 3600
TWO = 2


def pem(key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey) -> str:
    """A private key in PEM, as service account files have it.

    Returns:
        The PEM text.
    """
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


ACCOUNT = ServiceAccount(
    type="service_account",
    project_id="h2open-test",
    client_email="push@h2open-test.iam.gserviceaccount.com",
    private_key=pem(KEY),
    token_uri=OAUTH_URL,
)


def unpad(part: str) -> bytes:
    """Decode unpadded base64url.

    Returns:
        The bytes.
    """
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


@dataclass
class FakeGoogle:
    """Answers token and FCM requests; records what it was sent."""

    fcm_status: int = HTTPStatus.OK
    fcm_body: bytes = b"{}"
    token_status: int = HTTPStatus.OK
    token_requests: list[httpx2.Request] = field(default_factory=list)
    messages: list[httpx2.Request] = field(default_factory=list)
    now: float = 1_800_000_000.0

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        """Route a request.

        Returns:
            The canned response.
        """
        if str(request.url) == OAUTH_URL:
            self.token_requests.append(request)
            n = len(self.token_requests)
            body = {"access_token": f"access-{n}", "expires_in": HOUR}
            return httpx2.Response(self.token_status, json=body)
        assert str(request.url) == SEND_URL
        self.messages.append(request)
        return httpx2.Response(self.fcm_status, content=self.fcm_body)

    def sender(self) -> FcmSender:
        """A sender talking to this fake.

        Returns:
            The sender.
        """
        return FcmSender(
            ACCOUNT, transport=httpx2.MockTransport(self.handle), clock=self.time
        )

    def time(self) -> float:
        """The fake's clock.

        Returns:
            Seconds since the epoch.
        """
        return self.now


def send(sender: FcmSender, phone: str = "phone-1") -> SendOutcome:
    """Send DATA to one phone.

    Returns:
        The outcome.
    """
    return asyncio.run(sender.send(phone, DATA, ttl_seconds=TTL))


def test_sends_a_high_priority_data_message() -> None:
    """The message goes to FCM v1 with a token signed by the service account."""
    google = FakeGoogle()
    assert send(google.sender()) is SendOutcome.SENT

    [token_request] = google.token_requests
    form = parse_qs(token_request.content.decode())
    assert form["grant_type"] == [JWT_BEARER]
    [assertion] = form["assertion"]
    header, claims, signature = assertion.split(".")
    KEY.public_key().verify(
        unpad(signature),
        f"{header}.{claims}".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    assert json.loads(unpad(header)) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(unpad(claims)) == {
        "iss": ACCOUNT.client_email,
        "scope": SCOPE,
        "aud": OAUTH_URL,
        "iat": int(google.now),
        "exp": int(google.now) + HOUR,
    }

    [message] = google.messages
    assert message.headers["Authorization"] == "Bearer access-1"
    assert json.loads(message.content) == {
        "message": {
            "token": "phone-1",
            "data": DATA,
            "android": {"priority": "high", "ttl": "300s"},
        }
    }


def test_access_token_is_reused_until_nearly_expired() -> None:
    """One token serves many messages; it is renewed a minute before expiry."""
    google = FakeGoogle()
    sender = google.sender()
    _ = send(sender)
    google.now += HOUR - 61
    _ = send(sender)
    assert len(google.token_requests) == 1
    google.now += 1
    _ = send(sender)
    assert len(google.token_requests) == TWO
    assert google.messages[-1].headers["Authorization"] == "Bearer access-2"


def test_dead_tokens_are_reported() -> None:
    """FCM's UNREGISTERED (app removed) means: stop using this token."""
    body = {"error": {"details": [{"errorCode": "UNREGISTERED"}]}}
    google = FakeGoogle(
        fcm_status=HTTPStatus.NOT_FOUND, fcm_body=json.dumps(body).encode()
    )
    assert send(google.sender()) is SendOutcome.UNREGISTERED


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (HTTPStatus.INTERNAL_SERVER_ERROR, b"<html>oops</html>"),
        (HTTPStatus.TOO_MANY_REQUESTS, b'{"error": {"details": []}}'),
        (HTTPStatus.BAD_REQUEST, b'{"error": {"details": [{"@type": "x"}]}}'),
    ],
)
def test_other_failures_are_worth_retrying(status: int, body: bytes) -> None:
    """Outages, quotas and the like raise, so the outbox tries again."""
    google = FakeGoogle(fcm_status=status, fcm_body=body)
    with pytest.raises(PushError, match=f"FCM answered {status}"):
        _ = send(google.sender())


def test_a_rejected_access_token_is_renewed() -> None:
    """After a 401 the next message fetches a fresh access token."""
    google = FakeGoogle(fcm_status=HTTPStatus.UNAUTHORIZED)
    sender = google.sender()
    with pytest.raises(PushError):
        _ = send(sender)
    google.fcm_status = HTTPStatus.OK
    assert send(sender) is SendOutcome.SENT
    assert len(google.token_requests) == TWO


def test_token_endpoint_and_network_failures() -> None:
    """Google refusing a token, or no network at all, are retryable errors."""
    google = FakeGoogle(token_status=HTTPStatus.BAD_REQUEST)
    with pytest.raises(PushError, match="token endpoint answered 400"):
        _ = send(google.sender())

    def offline(request: httpx2.Request) -> httpx2.Response:
        msg = "no route"
        raise httpx2.ConnectError(msg, request=request)

    sender = FcmSender(ACCOUNT, transport=httpx2.MockTransport(offline))
    with pytest.raises(PushError, match="could not reach Firebase"):
        _ = send(sender)


def test_status() -> None:
    """Admins see whether pushes are on, and for which Firebase project."""
    status = FakeGoogle().sender().status
    assert (status.configured, status.project_id, status.problem) == (
        True,
        "h2open-test",
        None,
    )
    off = LoggingSender("FCM_CREDENTIALS_FILE is not set")
    assert off.status.configured is False
    assert asyncio.run(off.send("t", DATA, ttl_seconds=TTL)) is SendOutcome.SKIPPED


def test_loading_credentials(tmp_path: Path) -> None:
    """A good key file turns pushes on; anything wrong turns them off."""
    assert load_sender(None).status.problem == "FCM_CREDENTIALS_FILE is not set"
    missing = load_sender(tmp_path / "nope.json").status
    assert missing.problem == "cannot use nope.json: FileNotFoundError"

    garbage = tmp_path / "garbage.json"
    _ = garbage.write_text('{"type": "authorized_user"}')
    assert load_sender(garbage).status.problem == (
        "cannot use garbage.json: ValidationError"
    )

    elliptic = tmp_path / "ec.json"
    ec_key = ec.generate_private_key(ec.SECP256R1())
    _ = elliptic.write_text(
        ACCOUNT.model_copy(update={"private_key": pem(ec_key)}).model_dump_json()
    )
    assert load_sender(elliptic).status.problem == "cannot use ec.json: TypeError"

    good = tmp_path / "firebase-service-account.json"
    _ = good.write_text(ACCOUNT.model_dump_json())
    assert load_sender(good).status.project_id == "h2open-test"
