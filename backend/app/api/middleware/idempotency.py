"""Idempotency-Key + conditional-request (If-Match / If-Unmodified-Since) middleware for write endpoints.

Triển khai docs/10 A3/A4 (khoản P1 trong QA_REPORT.md) cho POST/PUT/PATCH/DELETE:

- A3: retry cùng Idempotency-Key + cùng payload -> trả lại response đã lưu.
- A4: cùng Idempotency-Key + khác payload -> 409 IDEMPOTENCY_KEY_REUSED (không ghi thêm).

Dùng chung dịch vụ `app.services.idempotency` (`check` / `remember` / `payload_hash`) với
các route, do đó hash phải nhất quán: bám toàn bộ JSON body đã parse (thứ tự key trong
JSON không tạo ra "payload khác"). Key bền vững lưu trong bảng `idempotency_keys`
(migration 027), store in-memory là fast path.

ETag/Last-Modified gắn vào response của endpoint ghi để client có thể gửi
If-Match / If-Unmodified-Since ở lần gọi sau (optimistic lock, docs/00 invariant 2).
Việc so sánh phiên bản thực tế vẫn do từng route tự thực hiện (`_check_if_match`).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.services import idempotency

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_MAX_REQUEST_BODY_BYTES = 1024 * 1024
_MAX_RESPONSE_BODY_BYTES = 1024 * 1024


def _parse_body(body: bytes) -> Any:
    if not body:
        return {}
    try:
        return json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return body.decode("utf-8", errors="replace")


async def _send_json(
    send: Send,
    scope: Scope,
    receive: Receive,
    status: int,
    body: Any,
    request_id: str,
) -> None:
    from starlette.responses import JSONResponse

    headers = {"X-Request-ID": request_id} if request_id else {}
    response = JSONResponse(status_code=status, content=body, headers=headers)
    await response(scope, receive, send)


async def _emit_final(
    send: Send,
    start_message: dict[str, Any] | None,
    chunks: list[bytes],
) -> None:
    if start_message is None:
        return
    body_bytes = b"".join(chunks)
    etag = hashlib.sha256(body_bytes).hexdigest() if body_bytes else ""
    start = dict(start_message)
    raw_headers = list(start.get("headers", []))
    if etag and not any(k.lower() == b"etag" for k, _ in raw_headers):
        raw_headers.append((b"etag", f'"{etag}"'.encode("ascii")))
    start["headers"] = raw_headers
    await send(start)
    await send({"type": "http.response.body", "body": body_bytes, "more_body": False})


class IdempotencyMiddleware:
    """Starlette middleware tập trung Idempotency-Key và ETag cho các endpoint ghi."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        method = request.method
        key = (request.headers.get("idempotency-key") or "").strip()

        is_write = method in _WRITE_METHODS and bool(key)
        body_hash: str | None = None
        downstream_receive = receive

        if is_write:
            body = await request.body()
            body_replayed = False

            async def replay_body() -> dict[str, Any]:
                nonlocal body_replayed
                if not body_replayed:
                    body_replayed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            downstream_receive = replay_body
            if len(body) > _MAX_REQUEST_BODY_BYTES:
                is_write = False
            else:
                body_hash = idempotency.payload_hash(_parse_body(body))
                try:
                    cached = idempotency.check(key, body_hash)
                except idempotency.IdempotencyConflict:
                    request_id = request.headers.get("x-request-id", "")
                    await _send_json(
                        send,
                        scope,
                        receive,
                        409,
                        {
                            "error": {
                                "code": "IDEMPOTENCY_KEY_REUSED",
                                "message": "Idempotency-Key đã được dùng với nội dung khác.",
                                "request_id": request_id,
                                "details": {},
                            }
                        },
                        request_id,
                    )
                    return
                if cached is not None:
                    status, cached_body = cached
                    await _send_json(
                        send,
                        scope,
                        receive,
                        status,
                        cached_body,
                        request.headers.get("x-request-id", ""),
                    )
                    return

        # Chỉ bắt(response) khi là ghi để tính ETag và lưu store sau khi xong.
        send_wrapper = _ResponseCapture(send) if is_write else send
        await self.app(scope, downstream_receive, send_wrapper)

        if (
            is_write
            and not send_wrapper.passthrough
            and send_wrapper.start is not None
        ):
            status = int(send_wrapper.start["status"])
            body_bytes = b"".join(send_wrapper.chunks)
            response_body: Any
            if body_bytes:
                try:
                    response_body = json.loads(body_bytes)
                except (ValueError, json.JSONDecodeError):
                    response_body = body_bytes.decode("utf-8", errors="replace")
            else:
                response_body = {}
            idempotency.remember(None, key, body_hash or "", status, response_body or {})


class _ResponseCapture:
    """Gói `send` để buffering response ghi, gắn ETag, rồi mới gửi xuống client."""

    def __init__(self, inner_send: Send) -> None:
        self._inner = inner_send
        self.start: dict[str, Any] | None = None
        self.chunks: list[bytes] = []
        self.passthrough = False
        self._total = 0

    async def __call__(self, message: dict[str, Any]) -> None:
        if self.passthrough:
            await self._inner(message)
            return

        message_type = message.get("type")
        if message_type == "http.response.start":
            self.start = message
        elif message_type == "http.response.body":
            chunk = message.get("body") or b""
            self._total += len(chunk)
            if self._total > _MAX_RESPONSE_BODY_BYTES:
                self.passthrough = True
                if self.start is not None:
                    await self._inner(self.start)
                    self.start = None
                for buffered in self.chunks:
                    await self._inner(
                        {"type": "http.response.body", "body": buffered, "more_body": True}
                    )
                self.chunks.clear()
                await self._inner(message)
            else:
                self.chunks.append(chunk)
                if not message.get("more_body", False):
                    await _emit_final(self._inner, self.start, self.chunks)
        else:
            await self._inner(message)
