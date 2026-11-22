"""Idempotency middleware cho GraphQL.

Đọc header `Idempotency-Key`, inject vào context để resolvers mutation
có thể gọi execute_idempotent_operation.
"""

from __future__ import annotations

from typing import Any


class IdempotencyMiddleware:
    """Middleware đơn giản: trích xuất Idempotency-Key từ request headers."""

    def extract_key(self, headers: Any) -> str | None:
        """Lấy Idempotency-Key từ headers (dạng dict-like hoặc Starlette Headers)."""
        if headers is None:
            return None
        try:
            return headers.get("Idempotency-Key")
        except AttributeError:
            # Nếu headers là dict thông thường
            return headers.get("Idempotency-Key") if isinstance(headers, dict) else None