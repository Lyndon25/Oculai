"""Typed error hierarchy and response helpers for Oculai tools.

This module provides a consistent error model compatible with the JSONL protocol
used by the Electron app and the MCP JSON-RPC transport used by Claude Code.

Protocol format (shared by both transports):
    Success: {"ok": true, "result": {...}}
    Error:   {"ok": false, "error": {"code": "...", "message": "...", "details": {...}}}

Usage in tool handlers:

    from oculai_mcp.tools.errors import OculaiError, ValidationError, NotFoundError, ok, err

    async def my_tool(run_id: str) -> dict[str, Any]:
        if not run_id:
            raise ValidationError("run_id is required")
        row = await db.fetch(UUID(run_id))
        if row is None:
            raise NotFoundError(f"Run {run_id} not found")
        return ok({"run_id": run_id, "status": row["status"]})

Or use the decorator for automatic error wrapping:

    from oculai_mcp.tools.errors import tool_error_handler, ValidationError

    @tool_error_handler
    async def my_tool(run_id: str) -> dict[str, Any]:
        if not run_id:
            raise ValidationError("run_id is required")
        return {"run_id": run_id}  # auto-wrapped as {"ok": true, "result": {...}}
"""

from __future__ import annotations

import functools
import traceback
from typing import Any, Callable, TypeVar

# ---------------------------------------------------------------------------
# Type variable for the decorator
# ---------------------------------------------------------------------------

_F = TypeVar("_F", bound=Callable[..., Any])


# ===========================================================================
# Exception Hierarchy
# ===========================================================================


class OculaiError(Exception):
    """Base exception for all Oculai tool errors.

    Every OculaiError carries a machine-readable ``code``, a human-readable
    ``message``, an optional ``details`` dict, and an HTTP-like ``status_code``
    for reporting semantics.

    Attributes:
        code: Machine-readable error code (e.g. "VALIDATION_ERROR").
        message: Human-readable description of the error.
        details: Optional structured payload with extra context.
        status_code: HTTP-style status code (default 500).
    """

    code: str = "OCULAI_ERROR"
    status_code: int = 500

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message: str = message or self.__class__.__doc__ or ""
        self.details: dict[str, Any] | None = details
        # Resolve code / status_code: explicit arg > subclass class attr > base default.
        # Subclasses define ``code`` / ``status_code`` as plain class-level strings/ints.
        # The @property below reads the instance-level ``_code`` / ``_status_code``
        # that __init__ sets here.
        cls = type(self)
        cls_dict = cls.__dict__
        resolved_code: str
        if code is not None:
            resolved_code = code
        elif "code" in cls_dict and not isinstance(cls_dict["code"], property):
            resolved_code = cls_dict["code"]  # type: ignore[assignment]
        else:
            resolved_code = "OCULAI_ERROR"
        resolved_status: int
        if status_code is not None:
            resolved_status = status_code
        elif "status_code" in cls_dict and not isinstance(cls_dict["status_code"], property):
            resolved_status = cls_dict["status_code"]  # type: ignore[assignment]
        else:
            resolved_status = 500
        object.__setattr__(self, "_code", resolved_code)
        object.__setattr__(self, "_status_code", resolved_status)

    # ------------------------------------------------------------------
    # Properties — expose the stored values as read-only attributes.
    # ------------------------------------------------------------------

    @property
    def code(self) -> str:
        """Machine-readable error code."""
        return self._code  # type: ignore[attr-defined]

    @property
    def status_code(self) -> int:
        """HTTP-style status code."""
        return self._status_code  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the error to the standard Oculai error envelope.

        Returns:
            A dict with shape ``{"ok": false, "error": {"code": ..., "message": ..., "details": ...}}``.
            The ``details`` key is omitted when None.
        """
        error_payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details is not None:
            error_payload["details"] = self.details
        return {"ok": False, "error": error_payload}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ===========================================================================
# Typed Subclasses
# ===========================================================================


class ValidationError(OculaiError):
    """Client-provided parameters are invalid or missing."""

    code = "VALIDATION_ERROR"
    status_code = 400


class NotFoundError(OculaiError):
    """The requested entity (run, person, task, etc.) does not exist."""

    code = "NOT_FOUND"
    status_code = 404


class ConflictError(OculaiError):
    """The operation cannot be completed due to a duplicate or conflicting state."""

    code = "CONFLICT"
    status_code = 409


class SourceError(OculaiError):
    """An external data source returned an error or could not be reached."""

    code = "SOURCE_ERROR"
    status_code = 502


class QuotaError(OculaiError):
    """A rate limit or quota has been exceeded for an external API."""

    code = "QUOTA_EXCEEDED"
    status_code = 429


class AuthError(OculaiError):
    """Authentication or authorization failed for an external resource."""

    code = "AUTH_ERROR"
    status_code = 401


class InternalError(OculaiError):
    """An unexpected internal failure occurred (catch-all for unhandled exceptions)."""

    code = "INTERNAL_ERROR"
    status_code = 500


# ===========================================================================
# Decorator
# ===========================================================================


def tool_error_handler(func: _F) -> _F:
    """Async decorator that wraps a tool function with standardised error handling.

    On success the return dict is wrapped in ``{"ok": True, "result": {...}}``.
    On failure the exception is converted to ``{"ok": False, "error": {...}}``
    according to the following mapping:

    * :class:`OculaiError` subclasses → ``error.to_dict()``
    * :class:`ValueError`, :class:`TypeError` → :class:`ValidationError`
    * Any other :class:`Exception` → :class:`InternalError` (includes traceback
      in ``details.traceback``)

    This decorator is designed for **async** functions.  For sync callables
    use :func:`ok` / :func:`err` directly.

    Example::

        @tool_error_handler
        async def oculai_get_candidate(person_id: str) -> dict[str, Any]:
            row = await db.fetch(UUID(person_id))
            if row is None:
                raise NotFoundError(f"Person {person_id} not found")
            return {"person_id": person_id, "name": row["name"]}
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = await func(*args, **kwargs)
            # If the function already returned an envelope, pass it through.
            if isinstance(result, dict) and "ok" in result:
                return result
            return ok(result)
        except OculaiError as exc:
            return exc.to_dict()
        except (ValueError, TypeError) as exc:
            return ValidationError(str(exc)).to_dict()
        except Exception as exc:
            return InternalError(
                str(exc),
                details={"traceback": traceback.format_exc()},
            ).to_dict()

    return wrapper  # type: ignore[return-value]


# ===========================================================================
# Convenience Helpers
# ===========================================================================


def ok(result: dict[str, Any] | Any) -> dict[str, Any]:
    """Wrap a successful result in the standard Oculai success envelope.

    Args:
        result: The result payload.  Typically a dict but any JSON-serializable
            value is accepted — non-dict values are wrapped as
            ``{"ok": True, "result": {"value": result}}``.

    Returns:
        A dict shaped ``{"ok": True, "result": {...}}``.
        Already-wrapped results (containing an ``"ok"`` key) are returned
        unchanged to prevent double-wrapping.
    """
    # Pass through already-wrapped results
    if isinstance(result, dict) and "ok" in result:
        return result
    if not isinstance(result, dict):
        result = {"value": result}
    return {"ok": True, "result": result}


def err(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard Oculai error envelope without raising an exception.

    This is useful in transport layers (e.g. JSONL server, MCP response
    formatters) or when you want to return an error dict directly rather
    than raising.

    Args:
        code: Machine-readable error code (e.g. ``"VALIDATION_ERROR"``).
        message: Human-readable description.
        details: Optional structured context.

    Returns:
        A dict shaped ``{"ok": False, "error": {"code": ..., "message": ..., "details": ...}}``.
    """
    error_payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error_payload["details"] = details
    return {"ok": False, "error": error_payload}
