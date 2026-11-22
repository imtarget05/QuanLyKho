"""A6 — DataLoader cho các relationship read trong GraphQL.

Mục tiêu: khi client truy vấn danh sách tài khoản kèm `ledgerEntries`, resolver
không được phát một query cho mỗi tài khoản (N+1). Hai loader dưới đây gom mọi
khoá trong cùng một lượt của event loop thành **một** câu `IN (...)`.

Loader được tạo mới cho mỗi request (xem `app/graphql/context.py`) để cache
không rò dữ liệu giữa các request/người dùng khác nhau.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.graphql.loaders.base import BatchLoader
from app.models.ledger import GeneralLedgerEntry, GLAccountBalance


def account_to_dict(bal: GLAccountBalance) -> dict[str, Any]:
    """Chuyển row balance sang shape của GraphQL type `Account`."""
    return {
        "id": str(bal.account_code),
        "code": bal.account_code,
        "name": bal.account_code,
        "accountType": "asset",
        "normalBalance": "debit",
        "currency": bal.currency,
        "ledgerBalance": bal.ledger_balance,
        "availableBalance": bal.available_balance,
        "holdBalance": bal.hold_balance,
        "version": bal.version,
        "updatedAt": bal.updated_at,
    }


def ledger_entry_to_dict(entry: GeneralLedgerEntry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "journalId": str(entry.journal_id),
        "accountCode": entry.account_code,
        "debit": entry.debit,
        "credit": entry.credit,
        "postedAt": None,
    }


class AccountLoader(BatchLoader[str, dict[str, Any] | None]):
    """Batch load `Account` theo `account_code`."""

    async def batch_load_fn(self, keys: list[str]) -> list[dict[str, Any] | None]:
        codes = [str(k) for k in keys]
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(GLAccountBalance).where(GLAccountBalance.account_code.in_(codes))
            )
            by_code = {bal.account_code: account_to_dict(bal) for bal in res.scalars()}
        return [by_code.get(code) for code in codes]


class LedgerEntryLoader(BatchLoader[str, list[dict[str, Any]]]):
    """Batch load danh sách `LedgerEntry` (mới nhất trước) theo `accountCode`."""

    def __init__(self, limit: int = 100) -> None:
        super().__init__()
        self._limit = max(1, int(limit))

    async def batch_load_fn(self, keys: list[str]) -> list[list[dict[str, Any]]]:
        codes = [str(k) for k in keys]
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(GeneralLedgerEntry)
                .where(GeneralLedgerEntry.account_code.in_(codes))
                .order_by(GeneralLedgerEntry.id.desc())
            )
            grouped: dict[str, list[dict[str, Any]]] = {code: [] for code in codes}
            for entry in res.scalars():
                bucket = grouped.setdefault(entry.account_code, [])
                if len(bucket) < self._limit:
                    bucket.append(ledger_entry_to_dict(entry))
        return [grouped.get(code, []) for code in codes]
