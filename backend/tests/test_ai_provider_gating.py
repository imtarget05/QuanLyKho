"""F1 — AI provider gating (không rò dữ liệu phiếu ra ngoài khi AI tắt).

RED trước khi sửa `app/services/ai.py` + `app/api/routes/ai.py`:

- `AI_PROVIDER=disabled` (hoặc provider khác) => **0 outbound request**,
  dữ liệu nghiệp vụ (request_id / amount / maker / reason) KHÔNG được rời hệ
  thống.
- Mọi client HTTP của route AI phải có `timeout` => provider treo không làm
  treo request (trả lỗi có kiểm soát).
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from decimal import Decimal

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import select

from app.features.ai import routes as ai_routes
from app.config import Settings
from app.database import AsyncSessionLocal
from app.models.iam import User
from app.models.inventory import InventoryRequest, InventoryRequestLine, Item
from app.services.ai import assess_request, generate, stream_ollama

DEMO_PASSWORD = "DemoPass123!"

GATE_REQUEST_ID = str(uuid.UUID("11111111-2222-3333-4444-555555555555"))

BUSINESS_DATA = {
    "request_id": GATE_REQUEST_ID,
    "kind": "adjustment",
    "amount_or_qty": "35.000.000",
    "maker": "Trưởng ca Nguyễn Văn A",
    "reason": "Lệch kiểm kê ca sáng thiếu bột kem béo",
}


@pytest.fixture(autouse=True)
async def seed_gate_request():
    async with AsyncSessionLocal() as session:
        admin_user = (await session.execute(select(User).where(User.username == "demo_admin"))).scalars().first()
        if not admin_user:
            return
        existing = (await session.execute(select(InventoryRequest).where(InventoryRequest.id == uuid.UUID(GATE_REQUEST_ID)))).scalars().first()
        if not existing:
            item = (await session.execute(select(Item).limit(1))).scalars().first()
            inv_req = InventoryRequest(
                id=uuid.UUID(GATE_REQUEST_ID),
                kind="adjustment",
                status="submitted",
                maker_id=admin_user.id,
                reason="Lệch kiểm kê ca sáng thiếu bột kem béo",
                version=1,
                created_by=admin_user.id,
            )
            session.add(inv_req)
            if item:
                session.add(InventoryRequestLine(
                    id=uuid.uuid4(),
                    request_id=uuid.UUID(GATE_REQUEST_ID),
                    item_id=item.id,
                    quantity=Decimal("35.0"),
                    direction="increase",
                ))
            await session.commit()


def _login(client, username: str = "demo_admin") -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _settings(provider: str, **kwargs) -> Settings:
    return Settings(
        database_url="sqlite://",
        ai_provider=provider,
        cloudflare_account_id="a" * 32,
        cloudflare_api_token="test-secret",
        **kwargs,
    )


class _Recorder:
    """Tripwire: ghi lại MỌI request đi ra ngoài (kể cả body của nó)."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "response": json.dumps(
                        {
                            "risk_level": "low",
                            "risk_score": 5,
                            "summary": "ok",
                            "flagged_rules": [],
                            "recommendations": [],
                        }
                    )
                },
            },
        )


def _assert_no_business_data_leaked(recorder: _Recorder) -> None:
    assert recorder.calls == [], f"expected 0 outbound request, got {len(recorder.calls)}"
    for request in recorder.calls:
        body = request.content.decode("utf-8", "replace")
        assert BUSINESS_DATA["request_id"] not in body
        assert BUSINESS_DATA["maker"] not in body
        assert BUSINESS_DATA["reason"] not in body
        assert BUSINESS_DATA["amount_or_qty"] not in body


# --------------------------------------------------------------------------
# F1 — service level
# --------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["disabled", "ollama", "modal_llm"])
async def test_assess_request_makes_no_outbound_call_for_non_cloudflare_provider(provider):
    recorder = _Recorder()
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler)) as client:
        result = await assess_request(BUSINESS_DATA, _settings(provider), client)
    _assert_no_business_data_leaked(recorder)
    assert result["assessment_source"] == "heuristic_fallback"
    assert result["provider"] == "heuristic"
    assert result["risk_level"] in ("low", "medium", "high")


@pytest.mark.asyncio
async def test_assess_request_still_calls_cloudflare_when_enabled():
    recorder = _Recorder()
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler)) as client:
        result = await assess_request(BUSINESS_DATA, _settings("cloudflare"), client)
    assert len(recorder.calls) == 1
    assert str(recorder.calls[0].url.host) == "api.cloudflare.com"
    assert result["assessment_source"] == "cloudflare"


@pytest.mark.asyncio
async def test_stream_ollama_is_gated_when_provider_is_not_ollama():
    recorder = _Recorder()
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler)) as client:
        with pytest.raises(HTTPException) as error:
            async for _ in stream_ollama("xin chào", _settings("disabled"), client):
                pass
    assert error.value.status_code == 503
    _assert_no_business_data_leaked(recorder)


@pytest.mark.asyncio
async def test_generate_is_gated_when_provider_disabled():
    recorder = _Recorder()
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler)) as client:
        with pytest.raises(HTTPException) as error:
            await generate("xin chào", _settings("disabled"), client)
    assert error.value.status_code == 503
    _assert_no_business_data_leaked(recorder)


# --------------------------------------------------------------------------
# F1 — route level (tripwire trên httpx.AsyncClient của route)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("provider", ["disabled", "ollama", "modal_llm"])
def test_assess_request_route_makes_no_outbound_call(client, monkeypatch, provider):
    recorder = _Recorder()
    real_client_cls = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client_cls(*args, transport=httpx.MockTransport(recorder.handler), **kwargs)

    monkeypatch.setattr(ai_routes.httpx, "AsyncClient", fake_client)
    monkeypatch.setattr(ai_routes.settings, "ai_provider", provider)
    monkeypatch.setattr(ai_routes.settings, "ai_timeout_seconds", 5)
    # Tripwire đầy đủ: provider Cloudflare ĐÃ cấu hình (token + account id).
    # Nếu route không gate theo provider thì dữ liệu phiếu sẽ rời hệ thống.
    monkeypatch.setattr(ai_routes.settings, "cloudflare_account_id", "a" * 32)
    monkeypatch.setattr(ai_routes.settings, "cloudflare_api_token", SecretStr("tripwire-secret"))

    headers = _login(client)
    response = client.post("/ai/assess-request", headers=headers, json=BUSINESS_DATA)
    assert response.status_code == 200, response.text
    _assert_no_business_data_leaked(recorder)
    body = response.json()
    assert body["provider"] == "heuristic"
    assert body["assessment_source"] == "heuristic_fallback"


def test_assess_request_route_calls_cloudflare_only_when_enabled(client, monkeypatch):
    """Đối chứng: provider=cloudflare thì đúng 1 request, không gửi nhầm sang chỗ khác."""
    recorder = _Recorder()
    real_client_cls = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client_cls(*args, transport=httpx.MockTransport(recorder.handler), **kwargs)

    monkeypatch.setattr(ai_routes.httpx, "AsyncClient", fake_client)
    monkeypatch.setattr(ai_routes.settings, "ai_provider", "cloudflare")
    monkeypatch.setattr(ai_routes.settings, "ai_timeout_seconds", 5)
    monkeypatch.setattr(ai_routes.settings, "cloudflare_account_id", "a" * 32)
    monkeypatch.setattr(ai_routes.settings, "cloudflare_api_token", SecretStr("tripwire-secret"))

    headers = _login(client)
    response = client.post("/ai/assess-request", headers=headers, json=BUSINESS_DATA)
    assert response.status_code == 200, response.text
    assert len(recorder.calls) == 1
    assert str(recorder.calls[0].url.host) == "api.cloudflare.com"


def test_chat_route_makes_no_outbound_call_when_provider_disabled(client, monkeypatch):
    recorder = _Recorder()
    real_client_cls = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client_cls(*args, transport=httpx.MockTransport(recorder.handler), **kwargs)

    monkeypatch.setattr(ai_routes.httpx, "AsyncClient", fake_client)
    monkeypatch.setattr(ai_routes.settings, "ai_provider", "disabled")
    monkeypatch.setattr(ai_routes.settings, "ai_timeout_seconds", 5)
    monkeypatch.setattr(ai_routes.settings, "cloudflare_account_id", "a" * 32)
    monkeypatch.setattr(ai_routes.settings, "cloudflare_api_token", SecretStr("tripwire-secret"))

    headers = _login(client)
    response = client.post(
        "/ai/chat",
        headers=headers,
        json={"message": "quy trinh duyet phieu kho maker checker thep"},
    )
    assert response.status_code == 200, response.text
    _assert_no_business_data_leaked(recorder)
    assert response.json()["provider"] == "grounded_fallback"


# --------------------------------------------------------------------------
# R7 — timeout cho mọi HTTP client của route AI
# --------------------------------------------------------------------------
def test_ai_clients_are_created_with_timeout(client, monkeypatch):
    captured: list[object] = []
    real_client_cls = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        captured.append(kwargs.get("timeout"))
        kwargs.pop("transport", None)
        return real_client_cls(
            *args, transport=httpx.MockTransport(lambda r: httpx.Response(503, json={})), **kwargs
        )

    monkeypatch.setattr(ai_routes.httpx, "AsyncClient", fake_client)
    monkeypatch.setattr(ai_routes.settings, "ai_provider", "ollama")
    monkeypatch.setattr(ai_routes.settings, "ai_timeout_seconds", 7)

    headers = _login(client)
    client.post("/ai/assess-request", headers=headers, json=BUSINESS_DATA)
    client.post("/ai/chat", headers=headers, json={"message": "Ai là gì?"})
    client.post("/ai/chat/stream", headers=headers, json={"message": "Ai là gì?"})

    assert captured, "route AI phải khởi tạo HTTP client"
    assert all(value == 7 for value in captured), captured


def test_chat_route_returns_controlled_error_when_provider_hangs(client, monkeypatch):
    """Provider treo => phải trả lỗi có kiểm soát, không treo request."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    port = server.getsockname()[1]
    stop = threading.Event()

    def _accept_loop():
        server.settimeout(0.5)
        while not stop.is_set():
            try:
                conn, _addr = server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            # Nhận request nhưng KHÔNG trả lời -> provider treo.
            threading.Thread(target=_blackhole, args=(conn,), daemon=True).start()

    def _blackhole(conn):
        try:
            conn.settimeout(30)
            conn.recv(4096)
            stop.wait(30)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    threading.Thread(target=_accept_loop, daemon=True).start()
    try:
        monkeypatch.setattr(ai_routes.settings, "ai_provider", "ollama")
        monkeypatch.setattr(ai_routes.settings, "ai_timeout_seconds", 1)
        monkeypatch.setattr(ai_routes.settings, "ollama_base_url", f"http://127.0.0.1:{port}")
        headers = _login(client)
        started = time.monotonic()
        response = client.post(
            "/ai/chat",
            headers=headers,
            json={"message": "quy trinh duyet phieu kho maker checker thep"},
        )
        elapsed = time.monotonic() - started
    finally:
        stop.set()
        server.close()

    assert response.status_code == 200, response.text
    assert elapsed < 20, f"request bị treo {elapsed:.1f}s"
    # Provider treo -> fallback tài liệu nội bộ, không phải 500.
    assert response.json()["provider"] == "grounded_fallback"
