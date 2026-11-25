# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Errors that modules raise and the API turns into HTTP responses.

Services raise these instead of ``HTTPException`` so business logic stays
independent of HTTP. :func:`domain_error_handler` maps them to responses.
"""

from http import HTTPStatus
from typing import TYPE_CHECKING, ClassVar

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import Request


class DomainError(Exception):
    """A business rule was violated, e.g. confirming an empty order."""

    status_code: ClassVar[HTTPStatus] = HTTPStatus.UNPROCESSABLE_CONTENT
    code: ClassVar[str] = "business_rule_violated"


class NotFoundError(DomainError):
    """The requested entity does not exist."""

    status_code: ClassVar[HTTPStatus] = HTTPStatus.NOT_FOUND
    code: ClassVar[str] = "not_found"


class ConflictError(DomainError):
    """The request conflicts with the current state, e.g. a stale update."""

    status_code: ClassVar[HTTPStatus] = HTTPStatus.CONFLICT
    code: ClassVar[str] = "conflict"


def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """Turn a domain error into a JSON response.

    Args:
        _request: The request that failed (unused).
        exc: The error raised by a service.

    Returns:
        A response with the error's status, a stable machine-readable
        ``code`` and a human-readable ``detail``.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "detail": str(exc)},
    )


class OverrideRequiredError(ConflictError):
    """The action breaks a soft rule; staff may repeat it with a reason.

    The caller retries with an override reason, which is stored for audit.
    """

    code: ClassVar[str] = "override_required"
