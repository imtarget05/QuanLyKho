"""Comprehensive Unit & Integration Test Suite for Milestone M5 (Audit Trail Engine).

Covers:
1. Canonical Hash Calculation (compute_canonical_hash):
   - Key order invariance (dict ordering independence).
   - Nested dictionary canonicalization.
   - Unicode & special character fidelity.
   - Consistent hashing across raw dict and serialized JSON string.
2. Cryptographic Audit Hash Calculation (compute_audit_hash):
   - Formula: H_n = SHA-256(H_{n-1} || timestamp_iso || actor_id || action || entity_type || entity_id || payload_hash).
   - Bit-level sensitivity: altering any field changes the resulting hash.
   - Fixed 64-character lowercase hex digest.
3. Genesis Hash Linkage & Multi-Entry Chaining:
   - Genesis record links to GENESIS_HASH ("0" * 64).
   - Record n links strictly to current_hash of Record n-1.
   - Monotonic sequence accumulation across multi-entry chains.
4. Append-Only Immutability Enforcement (F20):
   - ORM event listener rejects UPDATE, raising AuditImmutabilityException / PermissionError.
   - ORM event listener rejects DELETE, raising AuditImmutabilityException / PermissionError.
5. Cryptographic Tamper Detection Verifier (F21 - verify_audit_chain_integrity):
   - Empty trail verifies as pristine (True, None, None).
   - Single and multi-entry intact chains verify cleanly.
   - Payload tampering detection: pinpoints exact broken ID with "payload_hash_mismatch".
   - Current hash corruption detection: pinpoints exact broken ID with "current_hash_mismatch".
   - Prev hash chain disruption detection: pinpoints exact broken ID with "prev_hash_mismatch".
   - Dual-unpacking support (2-tuple and 3-tuple callers).
6. PostgreSQL Database-Level Trigger Enforcement:
   - Direct SQL UPDATE fails with trigger exception.
   - Direct SQL DELETE fails with trigger exception.
7. REST API Endpoints:
   - POST /banking/audit/record
   - GET /banking/audit/verify
   - GET /banking/audit/trail
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.models.audit import (
    GENESIS_HASH,
    AuditChainRecord,
    AuditEntry,
    AuditImmutabilityException,
    AuditLogEntry,
    AuditTrailRecord,
)
from app.services.audit_service import (
    compute_audit_hash,
    compute_canonical_hash,
    get_audit_entry_by_id,
    get_audit_trail,
    record_audit_entry,
    verify_audit_chain_integrity,
)

# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def sqlite_session():
    """Provides an isolated in-memory SQLite AsyncSession for audit tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[AuditEntry.__table__]))

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session():
    """Provides a PostgreSQL AsyncSession connecting to bankops_test if available."""
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://bankops:bankops@127.0.0.1:5432/bankops_test",
    )
    if "asyncpg" not in db_url:
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace("postgresql://", "postgresql+asyncpg://")

    try:
        engine = create_async_engine(db_url, poolclass=StaticPool)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL bankops_test not accessible; skipping PostgreSQL integration test")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        # Clean any leftover records from audit_trail for isolation
        try:
            await session.execute(text("TRUNCATE TABLE audit_trail;"))
            await session.commit()
        except Exception:
            await session.rollback()
        yield session

    await engine.dispose()


# ============================================================================
# 1. CANONICAL HASH CALCULATIONS
# ============================================================================

def test_canonical_hash_key_order_invariance():
    """Canonical hash must be strictly identical regardless of dictionary key insertion order."""
    payload_a = {"currency": "VND", "amount_cents": 100000, "account_id": "111", "meta": {"k": "v"}}
    payload_b = {"meta": {"k": "v"}, "account_id": "111", "amount_cents": 100000, "currency": "VND"}
    assert compute_canonical_hash(payload_a) == compute_canonical_hash(payload_b)


def test_canonical_hash_nested_key_order_invariance():
    """Nested dictionaries must also be sorted deterministically."""
    nested_a = {"details": {"z": 26, "a": 1, "m": 13}, "outer": "val"}
    nested_b = {"outer": "val", "details": {"m": 13, "z": 26, "a": 1}}
    assert compute_canonical_hash(nested_a) == compute_canonical_hash(nested_b)


def test_canonical_hash_unicode_support():
    """Canonical hash properly handles UTF-8 Vietnamese diacritics and symbols."""
    payload_vn1 = {"note": "Chuyển khoản kho Trà Sữa Tân Phú", "so_tien": 500000}
    payload_vn2 = {"so_tien": 500000, "note": "Chuyển khoản kho Trà Sữa Tân Phú"}
    h1 = compute_canonical_hash(payload_vn1)
    h2 = compute_canonical_hash(payload_vn2)
    assert h1 == h2
    assert len(h1) == 64


def test_canonical_hash_string_and_dict_parity():
    """Hashing a serialized JSON string or a parsed dictionary yields identical results."""
    data = {"step": "STEP_1", "status": "COMPLETED"}
    h_dict = compute_canonical_hash(data)
    h_str = compute_canonical_hash('{"status":"COMPLETED","step":"STEP_1"}')
    assert h_dict == h_str


# ============================================================================
# 2. AUDIT HASH CALCULATION & SENSITIVITY
# ============================================================================

def test_compute_audit_hash_deterministic():
    """Audit hash produces fixed 64-character SHA-256 digest adhering to formula."""
    h = compute_audit_hash(
        prev_hash=GENESIS_HASH,
        timestamp_str="2026-11-16T10:00:00+00:00",
        actor_id="user_teller_01",
        action="TRANSFER",
        entity_type="ACCOUNT",
        entity_id="111",
        payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    assert isinstance(h, str)
    assert len(h) == 64
    assert h == h.lower()


def test_compute_audit_hash_avalanche_effect():
    """Altering any single parameter fundamentally changes the audit hash output."""
    base_args = {
        "prev_hash": GENESIS_HASH,
        "timestamp_str": "2026-11-16T10:00:00+00:00",
        "actor_id": "user_teller_01",
        "action": "TRANSFER",
        "entity_type": "ACCOUNT",
        "entity_id": "111",
        "payload_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }
    h_base = compute_audit_hash(**base_args)

    for key in base_args:
        modified_args = dict(base_args)
        modified_args[key] = str(base_args[key]) + "_alt"
        h_modified = compute_audit_hash(**modified_args)
        assert h_modified != h_base, f"Failed avalanche test on key {key}"


# ============================================================================
# 3. GENESIS HASH LINKAGE & CRYPTOGRAPHIC CHAINING
# ============================================================================

@pytest.mark.asyncio
async def test_genesis_hash_linkage_for_first_entry(sqlite_session):
    """First audit record in database links to GENESIS_HASH ('0' * 64)."""
    entry = await record_audit_entry(
        session=sqlite_session,
        actor_id="sec-admin",
        action="GENESIS_INIT",
        entity_type="SYSTEM",
        entity_id="sys-0",
        state_payload={"init": True},
    )
    await sqlite_session.commit()

    assert entry.id is not None
    assert entry.prev_hash == GENESIS_HASH
    assert len(entry.current_hash) == 64
    assert entry.current_hash != GENESIS_HASH


@pytest.mark.asyncio
async def test_cryptographic_hash_chaining_sequential(sqlite_session):
    """Subsequent records link strictly: H_{prev}(n) == H_{current}(n-1)."""
    e1 = await record_audit_entry(
        session=sqlite_session,
        actor_id="teller-1",
        action="TRANSFER",
        entity_type="ACCOUNT",
        entity_id="111",
        state_payload={"amount_cents": 1000},
    )
    await sqlite_session.commit()

    e2 = await record_audit_entry(
        session=sqlite_session,
        actor_id="teller-2",
        action="TRANSFER",
        entity_type="ACCOUNT",
        entity_id="112",
        state_payload={"amount_cents": 2000},
    )
    await sqlite_session.commit()

    e3 = await record_audit_entry(
        session=sqlite_session,
        actor_id="auditor",
        action="VERIFY",
        entity_type="LEDGER",
        entity_id="gl-main",
        state_payload={"status": "OK"},
    )
    await sqlite_session.commit()

    assert e1.prev_hash == GENESIS_HASH
    assert e2.prev_hash == e1.current_hash
    assert e3.prev_hash == e2.current_hash
    assert e1.id < e2.id < e3.id


@pytest.mark.asyncio
async def test_model_aliases_and_to_dict(sqlite_session):
    """AuditEntry aliases (AuditLogEntry, AuditTrailRecord, AuditChainRecord) and to_dict method."""
    assert AuditLogEntry is AuditEntry
    assert AuditTrailRecord is AuditEntry
    assert AuditChainRecord is AuditEntry

    entry = await record_audit_entry(
        session=sqlite_session,
        actor_id="batch-worker",
        action="SYNC_BALANCES",
        entity_type="WAREHOUSE",
        entity_id="wh-01",
        state_payload={"synced": 50},
    )
    await sqlite_session.commit()

    d = entry.to_dict()
    assert d["id"] == entry.id
    assert d["actor_id"] == "batch-worker"
    assert d["action"] == "SYNC_BALANCES"
    assert d["entity_type"] == "WAREHOUSE"
    assert d["entity_id"] == "wh-01"
    assert d["state_payload"] == {"synced": 50}
    assert d["prev_hash"] == entry.prev_hash
    assert d["current_hash"] == entry.current_hash
    assert d["timestamp"] is not None


# ============================================================================
# 4. APPEND-ONLY IMMUTABILITY ENFORCEMENT (F20)
# ============================================================================

@pytest.mark.asyncio
async def test_orm_listener_rejects_update(sqlite_session):
    """ORM event listener raises AuditImmutabilityException on UPDATE attempt."""
    entry = await record_audit_entry(
        session=sqlite_session,
        actor_id="admin",
        action="UPDATE_CONFIG",
        entity_type="CONFIG",
        entity_id="cfg-1",
        state_payload={"rate": 0.05},
    )
    await sqlite_session.commit()

    # Attempt to mutate record
    entry.action = "FRAUDULENT_ACTION"
    with pytest.raises(AuditImmutabilityException, match="immutable and append-only: UPDATE is forbidden") as exc_info:
        await sqlite_session.flush()

    # Verify that AuditImmutabilityException is a PermissionError subclass
    assert isinstance(exc_info.value, PermissionError)


@pytest.mark.asyncio
async def test_orm_listener_rejects_delete(sqlite_session):
    """ORM event listener raises AuditImmutabilityException on DELETE attempt."""
    entry = await record_audit_entry(
        session=sqlite_session,
        actor_id="admin",
        action="LOGOUT",
        entity_type="SESSION",
        entity_id="sess-9",
        state_payload={"ip": "10.0.0.1"},
    )
    await sqlite_session.commit()

    await sqlite_session.delete(entry)
    with pytest.raises(AuditImmutabilityException, match="immutable and append-only: DELETE is forbidden"):
        await sqlite_session.flush()


# ============================================================================
# 5. CRYPTOGRAPHIC TAMPER DETECTION VERIFIER (F21)
# ============================================================================

@pytest.mark.asyncio
async def test_verify_empty_audit_trail(sqlite_session):
    """Empty audit trail verifies as completely intact (True, None, None)."""
    res = await verify_audit_chain_integrity(sqlite_session)
    assert res.is_valid is True
    assert res.broken_id is None
    assert res.reason is None

    # Test 2-tuple unpacking
    is_clean, broken_id = res
    assert is_clean is True
    assert broken_id is None

    # Test 3-tuple unpacking
    is_clean3, broken_id3, reason3 = res
    assert is_clean3 is True
    assert broken_id3 is None
    assert reason3 is None


@pytest.mark.asyncio
async def test_verify_intact_multi_entry_chain(sqlite_session):
    """Unbroken multi-entry chain verifies successfully."""
    for i in range(10):
        await record_audit_entry(
            session=sqlite_session,
            actor_id=f"actor-{i}",
            action="TRANSACTION",
            entity_type="TX",
            entity_id=f"tx-{i}",
            state_payload={"index": i, "val": i * 100},
        )
    await sqlite_session.commit()

    res = await verify_audit_chain_integrity(sqlite_session)
    assert res.is_valid is True
    assert res.broken_id is None
    assert res.reason is None


@pytest.mark.asyncio
async def test_tamper_detection_modified_payload(sqlite_session):
    """Tampering with historical payload is detected immediately, pinpointing record ID."""
    entries = []
    for i in range(5):
        e = await record_audit_entry(
            session=sqlite_session,
            actor_id=f"actor-{i}",
            action="POST_GL",
            entity_type="JOURNAL",
            entity_id=f"j-{i}",
            state_payload={"amount": 1000 * (i + 1)},
        )
        entries.append(e)
    await sqlite_session.commit()

    # Artificially alter entry #3 payload via raw SQL (bypassing ORM listeners)
    target_id = entries[2].id
    await sqlite_session.execute(
        text(f"UPDATE audit_trail SET state_payload = '{{\"amount\": 9999999}}' WHERE id = {target_id}")
    )
    await sqlite_session.commit()

    res = await verify_audit_chain_integrity(sqlite_session)
    assert res.is_valid is False
    assert res.broken_id == target_id
    assert res.reason == "payload_hash_mismatch"


@pytest.mark.asyncio
async def test_tamper_detection_modified_current_hash(sqlite_session):
    """Tampering with current_hash of a record is detected immediately."""
    entries = []
    for i in range(4):
        e = await record_audit_entry(
            session=sqlite_session,
            actor_id=f"user-{i}",
            action="HOLD",
            entity_type="FUNDS",
            entity_id=f"f-{i}",
            state_payload={"hold": 500},
        )
        entries.append(e)
    await sqlite_session.commit()

    target_id = entries[1].id
    await sqlite_session.execute(
        text(f"UPDATE audit_trail SET current_hash = 'badhash0000000000000000000000000000000000000000000000000000000000' WHERE id = {target_id}")
    )
    await sqlite_session.commit()

    res = await verify_audit_chain_integrity(sqlite_session)
    assert res.is_valid is False
    assert res.broken_id == target_id
    assert res.reason == "current_hash_mismatch"


@pytest.mark.asyncio
async def test_tamper_detection_broken_chain_link(sqlite_session):
    """Tampering with prev_hash breaks cryptographic chain link and is caught."""
    entries = []
    for i in range(4):
        e = await record_audit_entry(
            session=sqlite_session,
            actor_id=f"user-{i}",
            action="SAGA_STEP",
            entity_type="SAGA",
            entity_id=f"saga-{i}",
            state_payload={"step": i},
        )
        entries.append(e)
    await sqlite_session.commit()

    target_id = entries[2].id
    await sqlite_session.execute(
        text(f"UPDATE audit_trail SET prev_hash = 'severedlink000000000000000000000000000000000000000000000000000000' WHERE id = {target_id}")
    )
    await sqlite_session.commit()

    res = await verify_audit_chain_integrity(sqlite_session)
    assert res.is_valid is False
    assert res.broken_id == target_id
    assert res.reason == "prev_hash_mismatch"


# ============================================================================
# 6. POSTGRESQL DATABASE TRIGGER ENFORCEMENT
# ============================================================================

@pytest.mark.asyncio
async def test_postgresql_db_trigger_rejects_sql_update(pg_session):
    """PostgreSQL trigger prevent_audit_trail_mutation blocks raw SQL UPDATE."""
    e = await record_audit_entry(
        session=pg_session,
        actor_id="admin-pg",
        action="DIRECT_INSERT",
        entity_type="ACCOUNT",
        entity_id="999",
        state_payload={"balance": 1000},
    )
    await pg_session.commit()

    # Raw SQL UPDATE should be blocked by trigger
    with pytest.raises(Exception) as exc_info:
        await pg_session.execute(
            text(f"UPDATE audit_trail SET action = 'HACKED' WHERE id = {e.id}")
        )
        await pg_session.commit()

    await pg_session.rollback()
    assert "audit_trail is append-only: UPDATE operations are prohibited" in str(exc_info.value)


@pytest.mark.asyncio
async def test_postgresql_db_trigger_rejects_sql_delete(pg_session):
    """PostgreSQL trigger prevent_audit_trail_mutation blocks raw SQL DELETE."""
    e = await record_audit_entry(
        session=pg_session,
        actor_id="admin-pg",
        action="DIRECT_INSERT",
        entity_type="ACCOUNT",
        entity_id="999",
        state_payload={"balance": 1000},
    )
    await pg_session.commit()

    # Raw SQL DELETE should be blocked by trigger
    with pytest.raises(Exception) as exc_info:
        await pg_session.execute(
            text(f"DELETE FROM audit_trail WHERE id = {e.id}")
        )
        await pg_session.commit()

    await pg_session.rollback()
    assert "audit_trail is append-only: DELETE operations are prohibited" in str(exc_info.value)


# ============================================================================
# 7. AUDIT TRAIL QUERIES & GET METHODS
# ============================================================================

@pytest.mark.asyncio
async def test_get_audit_trail_pagination_and_filter(sqlite_session):
    """get_audit_trail supports pagination and filtering by entity_type and entity_id."""
    for i in range(15):
        ent_type = "ACCOUNT" if i % 2 == 0 else "JOURNAL"
        await record_audit_entry(
            session=sqlite_session,
            actor_id=f"actor-{i}",
            action=f"ACT_{i}",
            entity_type=ent_type,
            entity_id=f"ent-{i}",
            state_payload={"i": i},
        )
    await sqlite_session.commit()

    # Pagination: first page (10 items)
    page1, total1 = await get_audit_trail(sqlite_session, limit=10, offset=0)
    assert len(page1) == 10
    assert total1 == 15

    # Pagination: second page (5 items)
    page2, total2 = await get_audit_trail(sqlite_session, limit=10, offset=10)
    assert len(page2) == 5
    assert total2 == 15

    # Filtering by entity_type
    acc_items, acc_total = await get_audit_trail(sqlite_session, entity_type="ACCOUNT")
    assert acc_total == 8
    assert all(r.entity_type == "ACCOUNT" for r in acc_items)

    # get_audit_entry_by_id
    first_id = page1[0].id
    fetched = await get_audit_entry_by_id(sqlite_session, first_id)
    assert fetched is not None
    assert fetched.id == first_id


# ============================================================================
# 8. REST API ENDPOINTS VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_api_record_audit_endpoint():
    """POST /banking/audit/record records entry and returns 201 with serializable payload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req_payload = {
            "actor_id": "api-teller",
            "action": "API_TRANSFER",
            "entity_type": "ACCOUNT",
            "entity_id": "acc-api-101",
            "state_payload": {"amount_cents": 250000, "note": "Payment via API"},
        }
        resp = await client.post("/banking/audit/record", json=req_payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "SUCCESS"
        entry_data = data["data"]
        assert entry_data["actor_id"] == "api-teller"
        assert entry_data["action"] == "API_TRANSFER"
        assert entry_data["entity_type"] == "ACCOUNT"
        assert entry_data["entity_id"] == "acc-api-101"
        assert len(entry_data["current_hash"]) == 64
        assert len(entry_data["prev_hash"]) == 64


@pytest.mark.asyncio
async def test_api_audit_verify_endpoint():
    """GET /banking/audit/verify scans and returns audit chain integrity status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/banking/audit/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["valid"] is True
        assert data["is_clean"] is True
        assert data["broken_record_id"] is None


@pytest.mark.asyncio
async def test_api_audit_trail_endpoint():
    """GET /banking/audit/trail lists recorded audit entries with metadata."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/banking/audit/trail?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
