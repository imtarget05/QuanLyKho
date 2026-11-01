"""R2 — Idempotency-Key bền vững (bảng `idempotency_keys`).

- `INSERT ... ON CONFLICT DO NOTHING` trong cùng transaction: 2 session/process
  cùng key => chỉ 1 bản ghi.
- Key còn hiệu lực **sau khi restart** (store in-memory bị xoá) => replay đúng
  response cũ, không tạo nghiệp vụ lần hai.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.schema import CreateTable

from app.database import AsyncSessionLocal
from app.models.idempotency import IdempotencyKey
from app.services import idempotency

DEMO_PASSWORD = "DemoPass123!"


@pytest.fixture(scope="module", autouse=True)
async def _ensure_idempotency_table():
    """Bảng `idempotency_keys` do Alembic tạo; trên DB demo `create_all` lo.

    Test này không phụ thuộc app đã khởi động nên tự tạo bảng nếu thiếu.
    """
    async with AsyncSessionLocal() as session:
        await session.run_sync(
            lambda sync_session: sync_session.execute(
                CreateTable(IdempotencyKey.__table__, if_not_exists=True)
            )
        )
        await session.commit()


def _login(client, username: str = "demo_checker") -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_claim_key_in_two_sessions_creates_exactly_one_row():
    key = f"test-claim-{uuid.uuid4().hex}"
    body_hash = idempotency.payload_hash({"amount": 10})

    async with AsyncSessionLocal() as session_a:
        first = await idempotency.claim_key(session_a, key, body_hash, scope="test")
        await session_a.commit()

    async with AsyncSessionLocal() as session_b:
        second = await idempotency.claim_key(session_b, key, body_hash, scope="test")
        await session_b.commit()

    assert first is True
    assert second is False

    async with AsyncSessionLocal() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(IdempotencyKey).where(IdempotencyKey.key == key)
            )
        ).scalar()
        assert count == 1


@pytest.mark.asyncio
async def test_stored_response_survives_process_restart():
    """Sau 'restart' (xoá store in-memory) key vẫn replay được response cũ."""
    key = f"test-restart-{uuid.uuid4().hex}"
    payload = {"amount": 42}
    body_hash = idempotency.payload_hash(payload)
    body = {"id": str(uuid.uuid4()), "status": "matched"}

    assert idempotency.check(key, body_hash) is None
    async with AsyncSessionLocal() as session:
        idempotency.remember(session, key, body_hash, 201, body)

    # Giả lập restart: mất store in-memory.
    idempotency._store.clear()

    replay = idempotency.check(key, body_hash)
    assert replay is not None
    status, replayed_body = replay
    assert status == 201
    assert replayed_body == body


@pytest.mark.asyncio
async def test_durable_store_rejects_same_key_with_different_payload():
    key = f"test-conflict-{uuid.uuid4().hex}"
    first_hash = idempotency.payload_hash({"amount": 1})
    second_hash = idempotency.payload_hash({"amount": 2})

    assert idempotency.check(key, first_hash) is None
    async with AsyncSessionLocal() as session:
        idempotency.remember(session, key, first_hash, 201, {"ok": True})

    idempotency._store.clear()
    with pytest.raises(idempotency.IdempotencyConflict):
        idempotency.check(key, second_hash)


def test_reconciliation_endpoint_replays_after_restart(client):
    """Endpoint idempotent quan trọng: reconciliation không tạo run lần hai."""
    headers = _login(client)
    key = f"test-recon-{uuid.uuid4().hex}"
    payload = {"scope": "cash"}

    first = client.post("/reconciliations", headers={**headers, "Idempotency-Key": key}, json=payload)
    assert first.status_code == 201, first.text

    # 'Restart' — mất store in-memory, key phải còn trong DB.
    idempotency._store.clear()

    second = client.post("/reconciliations", headers={**headers, "Idempotency-Key": key}, json=payload)
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
