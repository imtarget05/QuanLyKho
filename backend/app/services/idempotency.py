"""Idempotency-Key store (docs/06:3, docs/10 A3/A4).

Kho **bền vững**: bảng `idempotency_keys` (migration `027_idempotency_keys`)
lưu key + hash payload + response đã trả. Nhờ vậy:

- key còn hiệu lực **sau khi restart** process (store in-memory mất trắng),
- key dùng chung giữa nhiều replica/process (không còn per-process),
- `INSERT ... ON CONFLICT DO NOTHING` chạy trong cùng transaction với nghiệp vụ
  (xem `claim_key`) nên hai request cùng key không tạo ra hai bản ghi.

Store in-memory vẫn giữ làm **fast path** (không query DB cho key vừa dùng).
Khi không có trong memory, service tra bảng `idempotency_keys`; mọi lỗi DB ở
đường durable được nuốt (best-effort) để không làm hỏng request nghiệp vụ.

Hợp đồng:
- replay cùng key + cùng payload -> trả lại status/body đã lưu (A3)
- cùng key + khác payload       -> raise IdempotencyConflict -> 409 IDEMPOTENCY_KEY_REUSED (A4)
"""
import hashlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyKey

logger = logging.getLogger(__name__)

_store: dict[str, tuple[str, int, dict, float]] = {}  # key -> (hash, status, body, ts)
_RETENTION_SECONDS = 24 * 3600  # khớp idempotency_key_retention_hours (docs/04)

_sync_engine: Any = None
_claims_since_purge = 0
_PURGE_EVERY = 50  # dọn bản ghi hết hạn định kỳ (key cũ không giữ vô hạn)


def payload_hash(payload: Any) -> str:
    """Hash canonical (sorted keys) — thứ tự key trong JSON không được phép
    làm retry trở thành 'payload khác' (A3 phải replay, không phải 409)."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyConflict(Exception):
    """Cùng key nhưng payload khác (A4) — không được ghi thêm."""

    def __init__(self, existing_status: int, existing_body: dict):
        self.existing_status = existing_status
        self.existing_body = existing_body
        super().__init__("Idempotency-Key đã dùng cho payload khác")


def _purge_expired() -> None:
    now = time.time()
    for key in [k for k, (*_, ts) in _store.items() if now - ts > _RETENTION_SECONDS]:
        del _store[key]


# --------------------------------------------------------------------------
# Durable store (DB)
# --------------------------------------------------------------------------
def _get_sync_engine():
    """Engine sync (psycopg2) cho đường durable.

    Dùng engine riêng vì `check()`/`remember()` là API **sync** đã được các
    route gọi sẵn; đổi sang async sẽ phải sửa các route ngoài phạm vi của
    luồng này. Kết nối được tạo lazily và dùng chung (pool nhỏ).
    """
    global _sync_engine
    if _sync_engine is None:
        from sqlalchemy import create_engine

        from app.config import settings

        url = settings.database_url
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        _sync_engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
            future=True,
            connect_args={"connect_timeout": 3},
        )
    return _sync_engine


def _insert_stmt(engine):
    """`INSERT ... ON CONFLICT DO NOTHING` (Postgres) / `INSERT OR IGNORE` (SQLite)."""
    if engine.dialect.name == "postgresql":
        return pg_insert(IdempotencyKey)
    return sqlite_insert(IdempotencyKey)


def _durable_lookup(key: str) -> tuple[str, int | None, dict | None] | None:
    """Đọc bản ghi durable. None nếu chưa có key (hoặc DB lỗi)."""
    try:
        engine = _get_sync_engine()
        with Session(engine) as session:
            row = session.execute(
                select(IdempotencyKey).where(IdempotencyKey.key == key)
            ).first()
        if row is None:
            return None
        record = row[0]
        return (
            str(record.request_hash),
            int(record.status_code) if record.status_code is not None else None,
            record.response_body,
        )
    except Exception as ex:  # noqa: BLE001 - durable store là best-effort
        logger.warning(f"Idempotency durable lookup failed for key={key!r}: {ex}")
        return None


def _durable_claim(key: str, body_hash: str, scope: str = "") -> bool:
    """`INSERT ... ON CONFLICT DO NOTHING`. True nếu claim mới thành công."""
    global _claims_since_purge
    try:
        engine = _get_sync_engine()
        now = datetime.now(UTC)
        with engine.begin() as conn:
            stmt = _insert_stmt(engine).values(
                id=uuid.uuid4(),
                key=key,
                scope=scope,
                request_hash=body_hash,
                status_code=None,
                response_body=None,
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(seconds=_RETENTION_SECONDS),
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
            result = conn.execute(stmt)
            _claims_since_purge += 1
            if _claims_since_purge >= _PURGE_EVERY:
                _claims_since_purge = 0
                conn.execute(
                    IdempotencyKey.__table__.delete().where(
                        IdempotencyKey.expires_at < datetime.now(UTC)
                    )
                )
            return bool(result.rowcount)
    except Exception as ex:  # noqa: BLE001 - durable store là best-effort
        logger.warning(f"Idempotency durable claim failed for key={key!r}: {ex}")
        return False


def _durable_store(key: str, body_hash: str, status: int, body: dict) -> None:
    """Ghi response đã trả vào bảng durable (upsert)."""
    try:
        engine = _get_sync_engine()
        now = datetime.now(UTC)
        with engine.begin() as conn:
            updated = conn.execute(
                IdempotencyKey.__table__.update()
                .where(IdempotencyKey.key == key)
                .values(
                    request_hash=body_hash,
                    status_code=status,
                    response_body=body,
                    updated_at=now,
                )
            )
            if updated.rowcount:
                return
            stmt = _insert_stmt(engine).values(
                id=uuid.uuid4(),
                key=key,
                scope="",
                request_hash=body_hash,
                status_code=status,
                response_body=body,
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(seconds=_RETENTION_SECONDS),
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
            conn.execute(stmt)
    except Exception as ex:  # noqa: BLE001 - durable store là best-effort
        logger.warning(f"Idempotency durable store failed for key={key!r}: {ex}")


# --------------------------------------------------------------------------
# Public API (sync — dùng bởi các route hiện có)
# --------------------------------------------------------------------------
def check(key: str, body_hash: str) -> tuple[int, dict] | None:
    """Trả (status, body) để replay nếu key đã dùng; None nếu là request mới.

    Fast path: store in-memory. Nếu không có trong memory thì tra bảng durable
    `idempotency_keys` (sống sót qua restart / dùng chung giữa process) và
    claim key mới bằng `INSERT ... ON CONFLICT DO NOTHING`.
    """
    _purge_expired()
    entry = _store.get(key)
    if entry is not None:
        stored_hash, status, body, _ts = entry
        if stored_hash != body_hash:
            raise IdempotencyConflict(status, body)
        return status, body

    record = _durable_lookup(key)
    if record is not None:
        stored_hash, status, body = record
        if stored_hash != body_hash:
            raise IdempotencyConflict(status or 200, body or {})
        if status is not None:
            # Đã có response đã trả -> replay đúng như cũ.
            _store[key] = (stored_hash, status, body or {}, time.time())
            return status, body or {}
        # Đã claim nhưng chưa có response (tiến trình chết giữa chừng):
        # KHÔNG khoá vĩnh viễn — cho request đi tiếp.
    _durable_claim(key, body_hash)
    return None


def remember(db: Any, key: str, body_hash: str, status: int, body: dict) -> None:
    """Lưu kết quả sau khi transaction đã commit thành công.

    Ghi cả vào store in-memory (fast path) và bảng durable `idempotency_keys`
    để key còn hiệu lực sau restart / ở process khác.
    """
    _store[key] = (body_hash, status, body, time.time())
    _durable_store(key, body_hash, status, body)


async def lookup_persisted(db: Any, key: str, model: Any) -> Any | None:
    """Tra bản ghi đã lưu với `idempotency_key` trong DB — sống sót qua restart.

    `model` là ORM model có cột `idempotency_key` (unique). Trả về None nếu
    model không có cột đó (gọi site khác không bị ảnh hưởng).
    """
    if not key:
        return None
    column = getattr(model, "idempotency_key", None)
    if column is None:
        return None
    result = await db.execute(select(model).where(column == key))
    return result.scalars().first()


# --------------------------------------------------------------------------
# Public API (async — dùng khi endpoint muốn claim trong CÙNG transaction)
# --------------------------------------------------------------------------
async def claim_key(db: Any, key: str, body_hash: str, scope: str = "") -> bool:
    """Claim key bằng `INSERT ... ON CONFLICT DO NOTHING` trong transaction gọi.

    - Trả True nếu claim mới (request này là request duy nhất với key).
    - Trả False nếu key đã tồn tại (request trùng) — caller nên replay.

    Vì claim chạy trong transaction của caller, business write + key record
    commit/rollback cùng nhau: không còn trạng thái "key đã claim nhưng
    nghiệp vụ chưa ghi".
    """
    now = datetime.now(UTC)
    stmt = pg_insert(IdempotencyKey).values(
        id=uuid.uuid4(),
        key=key,
        scope=scope,
        request_hash=body_hash,
        status_code=None,
        response_body=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(seconds=_RETENTION_SECONDS),
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
    result = await db.execute(stmt)
    return bool(result.rowcount)


async def find_key(db: Any, key: str) -> IdempotencyKey | None:
    """Đọc bản ghi durable theo key (None nếu chưa có)."""
    if not key:
        return None
    result = await db.execute(select(IdempotencyKey).where(IdempotencyKey.key == key))
    return result.scalars().first()


async def store_response(db: Any, key: str, body_hash: str, status: int, body: dict) -> None:
    """Ghi response đã trả vào bảng durable (trong transaction của caller)."""
    now = datetime.now(UTC)
    updated = await db.execute(
        IdempotencyKey.__table__.update()
        .where(IdempotencyKey.key == key)
        .values(
            request_hash=body_hash,
            status_code=status,
            response_body=body,
            updated_at=now,
        )
    )
    if updated.rowcount:
        return
    stmt = pg_insert(IdempotencyKey).values(
        id=uuid.uuid4(),
        key=key,
        scope="",
        request_hash=body_hash,
        status_code=status,
        response_body=body,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(seconds=_RETENTION_SECONDS),
    )
    stmt = stmt.on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
    await db.execute(stmt)
