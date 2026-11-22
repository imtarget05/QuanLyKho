"""Helper dùng chung cho bộ test GraphQL (A7)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.ledger import ChartOfAccounts, GLAccountBalance

GRAPHQL_PATH = "/graphql"


def new_account_code() -> str:
    """Mã tài khoản là UUID hợp lệ (scalar `UUID` của schema yêu cầu)."""
    return str(uuid.uuid4())


async def gql(
    client,
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    idempotency_key: str | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    response = await client.post(
        GRAPHQL_PATH, json={"query": query, "variables": variables}, headers=headers
    )
    return response.status_code, response.json()


async def seed_accounts(codes: list[str], available_cents: int = 1_000_000) -> None:
    """Tạo COA + GLAccountBalance với số dư khả dụng cho trước."""
    async with AsyncSessionLocal() as session:
        for code in codes:
            coa = await session.get(ChartOfAccounts, code)
            if coa is None:
                session.add(
                    ChartOfAccounts(
                        code=code,
                        name=f"Test account {code[:8]}",
                        account_type="asset",
                        normal_balance="debit",
                        is_active=True,
                    )
                )
            bal = await session.get(GLAccountBalance, code)
            if bal is None:
                session.add(
                    GLAccountBalance(
                        account_code=code,
                        currency="VND",
                        ledger_balance=available_cents,
                        available_balance=available_cents,
                        hold_balance=0,
                        version=1,
                    )
                )
            else:
                bal.ledger_balance = available_cents
                bal.available_balance = available_cents
        await session.commit()


async def read_balance(code: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(GLAccountBalance).where(GLAccountBalance.account_code == code)
        )
        bal = res.scalars().first()
        if bal is None:
            return None
        return {
            "ledger": bal.ledger_balance,
            "available": bal.available_balance,
            "hold": bal.hold_balance,
            "version": bal.version,
        }
