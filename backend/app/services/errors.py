from __future__ import annotations

from dataclasses import dataclass


class AppError(Exception):
    """Predictable error object rendered as {code, user_message, field_errors, request_id}."""

    def __init__(self, code: str, user_message: str, status: int = 400, field_errors: dict | None = None, extra: dict | None = None):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.status = status
        self.field_errors = field_errors
        self.extra = extra or {}


def not_found(kind: str = "Record") -> AppError:
    # Same message whether the object is missing or owned by another tenant (no existence leak).
    return AppError("NOT_FOUND", f"{kind} not found.", 404)


@dataclass(frozen=True)
class Actor:
    user_id: str
    tenant_id: str
    role: str
    username: str
    display_name: str
    session_token_hash: str | None = None
    agent_mode: str = "replay"

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


def require_owner(actor: Actor) -> None:
    if not actor.is_owner:
        raise AppError("FORBIDDEN", "Only the business owner can perform this operation.", 403)
