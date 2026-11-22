"""Field resolvers cho object type GraphQL."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.graphql.context import get_loader
from app.graphql.loaders import ledger_entry_to_dict
from app.models.ledger import GeneralLedgerEntry


async def resolve_account_ledger_entries(
    account: dict[str, Any], info, limit: int = 100
) -> list[dict[str, Any]]:
    """`Account.ledgerEntries` — dùng DataLoader để tránh N+1."""
    code = str(account.get("code") or account.get("id"))
    limit = max(0, int(limit))
    loader = get_loader(info, "ledger_entries")
    if loader is not None and limit <= loader._limit:  # noqa: SLF001 - cùng module
        entries = await loader.load(code)
        return entries[:limit]

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(GeneralLedgerEntry)
            .where(GeneralLedgerEntry.account_code == code)
            .order_by(GeneralLedgerEntry.id.desc())
            .limit(limit)
        )
        return [ledger_entry_to_dict(entry) for entry in res.scalars()]


account_type_resolvers = {
    "ledgerEntries": resolve_account_ledger_entries,
}
