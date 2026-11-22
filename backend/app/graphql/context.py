"""Context dùng chung cho GraphQL: request + idempotency + DataLoader (A6).

Mỗi request tạo một context mới, kéo theo loader mới ⇒ cache không rò giữa
request/người dùng.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from app.graphql.loaders import AccountLoader, LedgerEntryLoader
from app.graphql.middleware.idempotency import IdempotencyMiddleware


def build_context(
    request: Request | None, idempotency_key: str | None = None
) -> dict[str, Any]:
    """Tạo context cho một lần execute GraphQL."""
    return {
        "request": request,
        "idempotency_key": idempotency_key,
        "idempotency_middleware": IdempotencyMiddleware(),
        "loaders": {
            "account": AccountLoader(),
            "ledger_entries": LedgerEntryLoader(),
        },
    }


def get_loader(info: Any, name: str) -> Any | None:
    """Lấy loader theo tên từ `info.context`, None nếu context không có."""
    context = getattr(info, "context", None) or {}
    return (context.get("loaders") or {}).get(name)
