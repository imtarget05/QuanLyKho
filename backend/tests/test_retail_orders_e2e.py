"""RetailOps HTTP E2E tests (RO-T01..T14).

Transaction-safe order lifecycle over the real FastAPI app + Postgres test DB.
Uses `create_access_token` directly (no login flow) and seeds a minimal
role/capability/inventory scope per module.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.schema import CreateTable

from app.api.routes.auth_utils import create_access_token
from app.database import AsyncSessionLocal
from app.models.iam import Branch, Capability, Role, RoleCapability, User, UserRole
from app.models.inventory import Balance, Item, Location
from app.models.order import Order, OrderLine, OrderStatus

BASE = "/orders"


async def _exec(session, stmt):
    return await session.execute(stmt)


async def _ensure_role(session, code: str, name: str) -> Role:
    role = (await _exec(session, select(Role).where(Role.code == code))).scalars().first()
    if role is None:
        role = Role(code=code, name=name)
        session.add(role)
        await session.flush()
    return role


async def _ensure_cap(session, code: str, name: str) -> Capability:
    cap = (
        await _exec(session, select(Capability).where(Capability.code == code))
    ).scalars().first()
    if cap is None:
        cap = Capability(code=code, name=name)
        session.add(cap)
        await session.flush()
    return cap


async def _seed_retail_scope(session) -> dict:
    role_admin = await _ensure_role(session, "retail_admin", "Retail Admin")
    role_staff = await _ensure_role(session, "retail_staff", "Retail Staff")
    caps = {
        "write": await _ensure_cap(session, "retail:order:write", "Create retail orders"),
        "read": await _ensure_cap(session, "retail:order:read", "Read retail orders"),
        "cancel": await _ensure_cap(session, "retail:order:cancel", "Cancel retail orders"),
        "manage_all": await _ensure_cap(
            session, "retail:order:manage_all", "Manage all retail orders"
        ),
        "view_balances": await _ensure_cap(
            session, "inventory:view_balances", "View inventory balances"
        ),
        "approve_cancel": await _ensure_cap(
            session, "retail:order:approve_cancel", "Approve retail order cancellation"
        ),
        "approval_inbox": await _ensure_cap(
            session, "approval:view_inbox", "View approval inbox"
        ),
    }
    for role in (role_admin, role_staff):
        for cap in caps.values():
            if role is role_staff and cap.code in {
                "retail:order:manage_all", "retail:order:approve_cancel", "approval:view_inbox"
            }:
                existing = (
                    await _exec(
                        session,
                        select(RoleCapability).where(
                            RoleCapability.role_code == role.code,
                            RoleCapability.capability_code == cap.code,
                        ),
                    )
                ).scalars().first()
                if existing is not None:
                    await session.delete(existing)
                continue
            exists = (
                await _exec(
                    session,
                    select(RoleCapability).where(
                        RoleCapability.role_code == role.code,
                        RoleCapability.capability_code == cap.code,
                    ),
                )
            ).scalars().first()
            if exists is None:
                session.add(RoleCapability(role_code=role.code, capability_code=cap.code))

    branch = Branch(
        id=uuid.uuid4(), code=f"BR-{uuid4().hex[:6]}", name="Branch One", active=True
    )
    session.add(branch)
    await session.flush()

    admin = User(
        id=uuid.uuid4(),
        username=f"retail_admin_{uuid4().hex[:6]}",
        password_hash="x",
        status="active",
        display_name_demo="Retail Admin",
        branch_id=branch.id,
    )
    staff = User(
        id=uuid.uuid4(),
        username=f"retail_staff_{uuid4().hex[:6]}",
        password_hash="x",
        status="active",
        display_name_demo="Retail Staff",
        branch_id=branch.id,
    )
    session.add_all([admin, staff])
    await session.flush()
    session.add_all(
        [
            UserRole(user_id=admin.id, role_code=role_admin.code),
            UserRole(user_id=staff.id, role_code=role_staff.code),
        ]
    )
    location = Location(
        id=uuid.uuid4(),
        code=f"LOC-{uuid4().hex[:6]}",
        name="Location One",
        active=True,
        branch_id=branch.id,
    )
    item = Item(
        id=uuid.uuid4(),
        sku=f"SKU-{uuid4().hex[:6]}",
        name="Tra sua",
        unit="ly",
        category="tra",
        cost_price=Decimal("10000"),
        selling_price=Decimal("25000"),
        min_stock=Decimal("10"),
        tracked_serial=False,
        active=True,
    )
    session.add_all([branch, location, item])
    await session.flush()

    balance = Balance(
        item_id=item.id,
        location_id=location.id,
        quantity=Decimal("1"),
        reserved_quantity=Decimal("0"),
    )
    session.add(balance)
    await session.commit()

    return {
        "admin_id": str(admin.id),
        "staff_id": str(staff.id),
        "branch_id": str(branch.id),
        "location_id": str(location.id),
        "item_id": str(item.id),
    }


def _headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


@pytest.fixture(scope="module", autouse=True)
async def _create_order_tables():
    """Tạo bảng retail_orders/retail_order_lines nếu chưa có (dùng cho test)."""
    async with AsyncSessionLocal() as session:
        await session.run_sync(
            lambda sync_session: sync_session.execute(
                CreateTable(Order.__table__, if_not_exists=True)
            )
        )
        await session.run_sync(
            lambda sync_session: sync_session.execute(
                CreateTable(OrderLine.__table__, if_not_exists=True)
            )
        )
        await session.commit()


@pytest.fixture()
async def scope_data():
    async with AsyncSessionLocal() as session:
        data = await _seed_retail_scope(session)
        yield data


@pytest.mark.asyncio
async def test_quote_then_confirm_creates_one_order(scope_data):
    d = scope_data
    async with AsyncSessionLocal() as session:
        admin_id = d["admin_id"]
    async with AsyncClient(
        transport=ASGITransport(app=None), base_url="http://testserver"
    ) as client:
        pass
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            f"{BASE}/quote",
            headers=_headers(admin_id),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-{uuid4().hex}",
            },
        )
        assert quote.status_code == 200, quote.text
        draft_id = quote.json()["draft_id"]
        token = quote.json()["confirmation_token"]

        confirm = await client.post(
            f"{BASE}/confirm",
            headers=_headers(admin_id),
            json={
                "draft_id": draft_id,
                "confirmation_token": token,
                "idempotency_key": f"confirm-{uuid4().hex}",
            },
        )
        assert confirm.status_code == 200, confirm.text
        order_id = confirm.json()["order_id"]
        assert confirm.json()["status"] == "confirmed"

        async with AsyncSessionLocal() as session:
            order = (
                await _exec(session, select(Order).where(Order.id == order_id))
            ).scalars().first()
            assert order is not None
            assert order.status == OrderStatus.CONFIRMED.value
            bal = (
                await _exec(
                    session,
                    select(Balance).where(
                        Balance.item_id == d["item_id"],
                        Balance.location_id == d["location_id"],
                    ),
                )
            ).scalars().first()
            assert bal.available_quantity == Decimal("0")


@pytest.mark.asyncio
async def test_agent_adapter_uses_actor_token_for_real_order_api(scope_data, monkeypatch):
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        lines = [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}]
        denied = await tools.draft_order("buyer", lines, d["branch_id"])
        assert denied["success"] is False
        assert denied["error_code"] == "DEPENDENCY_UNAVAILABLE"

        token = create_access_token({"sub": d["staff_id"]})
        quote = await tools.draft_order("buyer", lines, d["branch_id"], access_token=token)
        assert quote["draft_id"]
        assert quote["stock_ok"] is True

        confirmed = await tools.confirm_order(
            quote["draft_id"], quote["confirmation_token"],
            idempotency_key=f"agent-confirm-{uuid4().hex}", access_token=token,
        )
        assert confirmed["status"] == "confirmed"
        assert confirmed["order_id"]


@pytest.mark.asyncio
async def test_agent_graph_uses_actor_context_without_checkpointing_token(scope_data, monkeypatch):
    from langgraph.types import Command

    from app.main import app
    from app.services.retail_agent import tools
    from app.services.retail_agent.graph import build_retail_graph

    d = scope_data
    actor = d["staff_id"]
    token = create_access_token({"sub": actor})
    graph = build_retail_graph()
    config = {"configurable": {"thread_id": f"agent-http-{uuid4().hex}"}}
    state = {
        "query": "mua tra sua",
        "buyer_id": actor,
        "branch_id": d["branch_id"],
        "requested_items": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
        "confirmed": False,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        paused = await graph.ainvoke(state, config, context={"access_token": token, "actor_id": actor})
        assert "__interrupt__" in paused, (paused.get("intent"), paused.get("validation_result"), paused.get("order_quote"))
        checkpoint = await graph.aget_state(config)
        assert token not in repr(checkpoint)
        assert checkpoint.next == ("await_confirmation",)

        result = await graph.ainvoke(
            Command(resume=True), config, context={"access_token": token, "actor_id": actor}
        )
        assert result["order_id"]
        assert result["confirmed"] is True


@pytest.mark.asyncio
async def test_catalog_selection_resolves_unique_sku_and_abstains_on_ambiguity(scope_data, monkeypatch):
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    async with AsyncSessionLocal() as session:
        original = await session.get(Item, uuid.UUID(d["item_id"]))
        sku = original.sku
        duplicate = Item(
            id=uuid4(), sku=f"SKU-{uuid4().hex[:8]}", name="Tra sua",
            unit="ly", active=True,
        )
        session.add(duplicate)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        common = {"query": "mua trà sữa", "branch_id": d["branch_id"]}
        ambiguous = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={**common, "catalog_selection": {
                "query": "Tra sua", "location_id": d["location_id"], "quantity": "1",
            }},
        )
        assert ambiguous.status_code == 200, ambiguous.text
        body = ambiguous.json()
        assert body["thread_id"] is None
        assert body["validation_result"] == "CATALOG_AMBIGUOUS"
        assert len(body["catalog_candidates"]) >= 2
        assert body["tool_calls"] == ["search_catalog"]
        assert body["pending_confirmation"] is False

        missing = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={**common, "catalog_selection": {
                "query": "no-such-sku-xyz", "location_id": d["location_id"], "quantity": "1",
            }},
        )
        assert missing.status_code == 200, missing.text
        assert missing.json()["validation_result"] == "ITEM_NOT_FOUND"
        assert missing.json()["thread_id"] is None
        assert missing.json()["catalog_candidates"] == []

        exact = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={**common, "catalog_selection": {
                "query": sku, "location_id": d["location_id"], "quantity": "1",
            }},
        )
        assert exact.status_code == 200, exact.text
        assert exact.json()["pending_confirmation"] is True
        assert exact.json()["tool_calls"] == ["search_catalog", "draft_order"]
        assert exact.json()["order_id"] is None


@pytest.mark.asyncio
async def test_retail_agent_rejects_invalid_line_arguments_before_tool_call(scope_data, monkeypatch):
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    calls = []

    async def forbidden_request(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("invalid arguments reached business service")

    monkeypatch.setattr(tools, "_request", forbidden_request)
    valid_line = {"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}
    invalid_lines = [
        {**valid_line, "quantity": "0"},
        {**valid_line, "quantity": "-1"},
        {**valid_line, "item_id": "invented-sku"},
        {**valid_line, "unit_price": "0"},
        {"item_id": d["item_id"], "quantity": "1"},
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        for line in invalid_lines:
            response = await client.post(
                "/retail-agent/threads", headers=_headers(d["staff_id"]),
                json={"query": "mua hàng", "branch_id": d["branch_id"], "requested_items": [line]},
            )
            assert response.status_code == 422, response.text
        missing_branch = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={"query": "mua hàng", "requested_items": [valid_line]},
        )
        assert missing_branch.status_code == 200, missing_branch.text
        assert missing_branch.json()["validation_result"] == "no_branch"
        assert missing_branch.json()["pending_confirmation"] is False
    assert calls == []


@pytest.mark.asyncio
async def test_authenticated_retail_agent_start_and_resume_rejects_other_actor(scope_data, monkeypatch):
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        started = await client.post(
            "/retail-agent/threads",
            headers=_headers(d["staff_id"]),
            json={
                "query": "mua tra sua",
                "branch_id": d["branch_id"],
                "requested_items": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
            },
        )
        assert started.status_code == 200, started.text
        thread_id = started.json()["thread_id"]
        assert started.json()["pending_confirmation"] is True
        assert "confirmation_token" not in started.json()

        other_actor = await client.post(
            f"/retail-agent/threads/{thread_id}/resume",
            headers=_headers(d["admin_id"]), json={"confirmed": True},
        )
        assert other_actor.status_code == 404

        resumed = await client.post(
            f"/retail-agent/threads/{thread_id}/resume",
            headers=_headers(d["staff_id"]), json={"confirmed": True},
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["order_id"]
        assert resumed.json()["pending_confirmation"] is False

        duplicate = await client.post(
            f"/retail-agent/threads/{thread_id}/resume",
            headers=_headers(d["staff_id"]), json={"confirmed": True},
        )
        assert duplicate.status_code == 409

        status = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={"query": "trạng thái đơn", "order_id": resumed.json()["order_id"]},
        )
        assert status.status_code == 200, status.text
        assert status.json()["order_id"] == resumed.json()["order_id"]
        assert status.json()["validation_result"] == "order_found", status.json()
        assert "confirmed" in status.json()["final_message"]


@pytest.mark.asyncio
async def test_authenticated_retail_agent_rejection_does_not_create_order(scope_data, monkeypatch):
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        started = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={
                "query": "mua tra sua", "branch_id": d["branch_id"],
                "requested_items": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
            },
        )
        assert started.status_code == 200, started.text
        thread_id = started.json()["thread_id"]
        rejected = await client.post(
            f"/retail-agent/threads/{thread_id}/resume",
            headers=_headers(d["staff_id"]), json={"confirmed": False},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["order_id"] is None


@pytest.mark.asyncio
async def test_authenticated_retail_agent_reads_stock_without_order_write(scope_data, monkeypatch):
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        response = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={
                "query": "kiểm tra tồn kho",
                "requested_items": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["pending_confirmation"] is False
        assert data["stock_level"][d["item_id"]]["available"] == "1.000"
        assert data["order_id"] is None


@pytest.mark.asyncio
async def test_retail_agent_start_requires_authentication(async_client):
    response = await async_client.post(
        "/retail-agent/threads", json={"query": "kiểm tra tồn kho"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_retail_agent_resume_after_postgres_checkpoint_reconnect(scope_data, monkeypatch):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    from app.api.routes import retail_agent as route
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    original_graph = route._graph
    checkpoint_url = "postgresql://bankops:bankops@127.0.0.1:5433/bankops_test"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            monkeypatch.setattr(tools, "_client", client)
            async with AsyncPostgresSaver.from_conn_string(
                checkpoint_url, serde=JsonPlusSerializer(allowed_msgpack_modules=[])
            ) as saver:
                await saver.setup()
                route.set_checkpointer(saver)
                started = await client.post(
                    "/retail-agent/threads", headers=_headers(d["staff_id"]),
                    json={
                        "query": "mua tra sua", "branch_id": d["branch_id"],
                        "requested_items": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
                    },
                )
                assert started.status_code == 200, started.text
                assert started.json()["pending_confirmation"] is True
                thread_id = started.json()["thread_id"]

            # Close the first DB connection and create a fresh graph and saver.
            async with AsyncPostgresSaver.from_conn_string(
                checkpoint_url, serde=JsonPlusSerializer(allowed_msgpack_modules=[])
            ) as saver:
                route.set_checkpointer(saver)
                resumed = await client.post(
                    f"/retail-agent/threads/{thread_id}/resume",
                    headers=_headers(d["staff_id"]), json={"confirmed": True},
                )
                assert resumed.status_code == 200, resumed.text
                assert resumed.json()["order_id"]
    finally:
        route._graph = original_graph


@pytest.mark.asyncio
async def test_confirm_timeout_recovers_committed_result_without_retry(scope_data, monkeypatch):
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    token = create_access_token({"sub": d["staff_id"]})
    lines = [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        draft = await tools.draft_order("buyer", lines, d["branch_id"], access_token=token)
        assert draft["draft_id"]

    calls = {"confirm": 0, "status": 0}
    underlying = ASGITransport(app=app)

    async def handler(request):
        response = await underlying.handle_async_request(request)
        if request.url.path == "/orders/confirm":
            calls["confirm"] += 1
            raise httpx.ReadTimeout("response lost after commit", request=request)
        if request.url.path.startswith("/orders/operations/"):
            calls["status"] += 1
        return response

    async with AsyncClient(transport=httpx.MockTransport(handler), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        result = await tools.confirm_order(
            draft["draft_id"], draft["confirmation_token"],
            idempotency_key=f"timeout-confirm-{uuid4().hex}", access_token=token,
        )
    assert result["order_id"] == draft["draft_id"]
    assert result["recovered_from_status"] is True
    assert calls == {"confirm": 1, "status": 1}


@pytest.mark.asyncio
async def test_retail_agent_two_drafts_for_last_unit_only_one_commits(scope_data, monkeypatch):
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    payload = {
        "query": "mua tra sua", "branch_id": d["branch_id"],
        "requested_items": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        first = await client.post("/retail-agent/threads", headers=_headers(d["staff_id"]), json=payload)
        second = await client.post("/retail-agent/threads", headers=_headers(d["staff_id"]), json=payload)
        assert first.status_code == second.status_code == 200
        assert first.json()["pending_confirmation"] is True
        assert second.json()["pending_confirmation"] is True

        committed = await client.post(
            f"/retail-agent/threads/{first.json()['thread_id']}/resume",
            headers=_headers(d["staff_id"]), json={"confirmed": True},
        )
        oversold = await client.post(
            f"/retail-agent/threads/{second.json()['thread_id']}/resume",
            headers=_headers(d["staff_id"]), json={"confirmed": True},
        )
        assert committed.status_code == oversold.status_code == 200
        assert committed.json()["order_id"]
        assert oversold.json()["order_id"] is None
        assert oversold.json()["validation_result"] == "commit_failed"
        assert oversold.json()["error_code"] == "INSUFFICIENT_STOCK"


@pytest.mark.asyncio
async def test_retail_agent_expired_draft_cannot_commit(scope_data, monkeypatch):
    from app.api.routes import retail_agent as route
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        started = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={
                "query": "mua tra sua", "branch_id": d["branch_id"],
                "requested_items": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
            },
        )
        assert started.status_code == 200, started.text
        snapshot = await route._graph.aget_state(
            {"configurable": {"thread_id": started.json()["thread_id"]}}
        )
        async with AsyncSessionLocal() as session:
            order = (
                await session.execute(select(Order).where(Order.id == snapshot.values["draft_id"]))
            ).scalars().one()
            order.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()

        resumed = await client.post(
            f"/retail-agent/threads/{started.json()['thread_id']}/resume",
            headers=_headers(d["staff_id"]), json={"confirmed": True},
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["order_id"] is None
        assert resumed.json()["validation_result"] == "commit_failed"
        assert resumed.json()["error_code"] == "DRAFT_EXPIRED"


@pytest.mark.asyncio
async def test_high_value_cancel_requires_separate_manager_decision(scope_data):
    from app.main import app

    d = scope_data
    async with AsyncSessionLocal() as session:
        item = (await session.execute(select(Item).where(Item.id == d["item_id"]))).scalars().one()
        item.selling_price = Decimal("6000000")
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            "/orders/quote", headers=_headers(d["staff_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
            },
        )
        assert quote.status_code == 200, quote.text
        confirmed = await client.post(
            "/orders/confirm", headers=_headers(d["staff_id"]),
            json={"draft_id": quote.json()["draft_id"], "confirmation_token": quote.json()["confirmation_token"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        order_id = confirmed.json()["order_id"]

        requested = await client.post(
            "/orders/cancel", headers=_headers(d["staff_id"]),
            json={"order_id": order_id, "reason": "Khách yêu cầu hủy"},
        )
        assert requested.status_code == 200, requested.text
        assert requested.json()["status"] == "pending_approval"
        inbox = await client.get("/approvals/inbox", headers=_headers(d["admin_id"]))
        assert inbox.status_code == 200, inbox.text
        assert any(
            entry["id"] == order_id and entry["kind"] == "retail_order_cancel"
            for entry in inbox.json()["approvals"]
        )
        async with AsyncSessionLocal() as session:
            order = (await session.execute(select(Order).where(Order.id == order_id))).scalars().one()
            assert order.status == OrderStatus.CONFIRMED.value

        no_self_approval = await client.post(
            f"/orders/{order_id}/cancel-decision", headers=_headers(d["staff_id"]),
            json={"decision": "approved", "idempotency_key": f"decision-staff-{uuid4().hex}"},
        )
        assert no_self_approval.status_code == 403
        key = f"decision-manager-{uuid4().hex}"
        approved = await client.post(
            f"/orders/{order_id}/cancel-decision", headers=_headers(d["admin_id"]),
            json={"decision": "approved", "idempotency_key": key},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "cancelled"
        replay = await client.post(
            f"/orders/{order_id}/cancel-decision", headers=_headers(d["admin_id"]),
            json={"decision": "approved", "idempotency_key": key},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["decision_id"] == approved.json()["decision_id"]
        async with AsyncSessionLocal() as session:
            balance = (await session.execute(select(Balance).where(
                Balance.item_id == d["item_id"], Balance.location_id == d["location_id"]
            ))).scalars().one()
            assert balance.quantity == Decimal("1")


@pytest.mark.asyncio
async def test_high_value_cancel_rejection_preserves_confirmed_order(scope_data):
    from app.main import app

    d = scope_data
    async with AsyncSessionLocal() as session:
        item = (await session.execute(select(Item).where(Item.id == d["item_id"]))).scalars().one()
        item.selling_price = Decimal("6000000")
        await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            "/orders/quote", headers=_headers(d["staff_id"]),
            json={"branch_id": d["branch_id"], "lines": [{
                "item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"
            }]},
        )
        assert quote.status_code == 200, quote.text
        confirmed = await client.post(
            "/orders/confirm", headers=_headers(d["staff_id"]),
            json={"draft_id": quote.json()["draft_id"], "confirmation_token": quote.json()["confirmation_token"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        order_id = confirmed.json()["order_id"]
        requested = await client.post(
            "/orders/cancel", headers=_headers(d["staff_id"]),
            json={"order_id": order_id, "reason": "Khách yêu cầu hủy"},
        )
        assert requested.json()["status"] == "pending_approval"
        rejected = await client.post(
            f"/orders/{order_id}/cancel-decision", headers=_headers(d["admin_id"]),
            json={"decision": "rejected", "note": "Không đủ căn cứ", "idempotency_key": f"reject-{uuid4().hex}"},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "confirmed"
        again = await client.post(
            f"/orders/{order_id}/cancel-decision", headers=_headers(d["admin_id"]),
            json={"decision": "approved", "idempotency_key": f"late-approve-{uuid4().hex}"},
        )
        assert again.status_code == 409
        async with AsyncSessionLocal() as session:
            balance = (await session.execute(select(Balance).where(
                Balance.item_id == d["item_id"], Balance.location_id == d["location_id"]
            ))).scalars().one()
            assert balance.quantity == Decimal("0")


@pytest.mark.asyncio
async def test_quote_idempotency_key_cannot_replay_across_actors(scope_data):
    from app.main import app

    d = scope_data
    key = f"cross-actor-quote-{uuid4().hex}"
    payload = {
        "branch_id": d["branch_id"], "idempotency_key": key,
        "lines": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        first = await client.post("/orders/quote", headers=_headers(d["staff_id"]), json=payload)
        assert first.status_code == 200, first.text
        second = await client.post("/orders/quote", headers=_headers(d["admin_id"]), json=payload)
        assert second.status_code == 409
        assert "confirmation_token" not in second.text


@pytest.mark.asyncio
async def test_retail_agent_thread_owner_can_delete_checkpoint(scope_data, monkeypatch):
    from app.api.routes import retail_agent as route
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        started = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={"query": "mua tra sua", "branch_id": d["branch_id"], "requested_items": [{
                "item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"
            }]},
        )
        assert started.status_code == 200, started.text
        thread_id = started.json()["thread_id"]
        denied = await client.delete(
            f"/retail-agent/threads/{thread_id}", headers=_headers(d["admin_id"])
        )
        assert denied.status_code == 404
        removed = await client.delete(
            f"/retail-agent/threads/{thread_id}", headers=_headers(d["staff_id"])
        )
        assert removed.status_code == 200, removed.text
        assert (await route._graph.aget_state({"configurable": {"thread_id": thread_id}})).values == {}
        retry = await client.post(
            f"/retail-agent/threads/{thread_id}/resume",
            headers=_headers(d["staff_id"]), json={"confirmed": True},
        )
        assert retry.status_code == 404


@pytest.mark.asyncio
async def test_two_graph_instances_share_postgres_checkpoint(scope_data, monkeypatch):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    from app.api.routes import retail_agent as route
    from app.main import app
    from app.services.retail_agent import tools

    d = scope_data
    original_graph = route._graph
    url = "postgresql://bankops:bankops@127.0.0.1:5433/bankops_test"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            monkeypatch.setattr(tools, "_client", client)
            async with AsyncPostgresSaver.from_conn_string(
                url, serde=JsonPlusSerializer(allowed_msgpack_modules=[])
            ) as saver_a:
                await saver_a.setup()
                async with AsyncPostgresSaver.from_conn_string(
                    url, serde=JsonPlusSerializer(allowed_msgpack_modules=[])
                ) as saver_b:
                    route.set_checkpointer(saver_a)
                    actor_headers = _headers(d["staff_id"])
                    started = await client.post(
                        "/retail-agent/threads", headers=actor_headers,
                        json={"query": "mua tra sua", "branch_id": d["branch_id"], "requested_items": [{
                            "item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"
                        }]},
                    )
                    assert started.status_code == 200, started.text
                    actor_token = actor_headers["Authorization"].removeprefix("Bearer ")
                    snapshot = await route._graph.aget_state(
                        {"configurable": {"thread_id": started.json()["thread_id"]}}
                    )
                    assert actor_token not in repr(snapshot)
                    route.set_checkpointer(saver_b)
                    resumed = await client.post(
                        f"/retail-agent/threads/{started.json()['thread_id']}/resume",
                        headers=_headers(d["staff_id"]), json={"confirmed": True},
                    )
                    assert resumed.status_code == 200, resumed.text
                    assert resumed.json()["order_id"]
    finally:
        route._graph = original_graph


@pytest.mark.asyncio
async def test_checkpoint_retention_prunes_only_expired_threads():
    import psycopg
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    from app.services.retail_agent.graph import build_retail_graph
    from app.services.retail_agent.retention import prune_expired_threads

    url = "postgresql://bankops:bankops@127.0.0.1:5433/bankops_test"
    old_thread = f"retention-old-{uuid4().hex}"
    fresh_thread = f"retention-fresh-{uuid4().hex}"
    async with AsyncPostgresSaver.from_conn_string(
        url, serde=JsonPlusSerializer(allowed_msgpack_modules=[])
    ) as saver:
        await saver.setup()
        graph = build_retail_graph(checkpointer=saver)
        for thread_id in (old_thread, fresh_thread):
            await graph.ainvoke(
                {"query": "kiểm tra tồn kho", "requested_items": [], "buyer_id": "actor"},
                {"configurable": {"thread_id": thread_id}},
            )
        async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
            await conn.execute(
                "UPDATE checkpoints SET checkpoint = jsonb_set(checkpoint, '{ts}', to_jsonb(%s::text)) WHERE thread_id = %s",
                ("2020-01-01T00:00:00+00:00", old_thread),
            )
        assert await prune_expired_threads(saver, url, retention_days=30) >= 1
        assert (await graph.aget_state({"configurable": {"thread_id": old_thread}})).values == {}
        assert (await graph.aget_state({"configurable": {"thread_id": fresh_thread}})).values


@pytest.mark.asyncio
async def test_live_model_selects_stock_tool_in_authenticated_graph(scope_data, monkeypatch):
    from app.main import app
    from app.services.retail_agent import tools

    try:
        tags = httpx.get("http://127.0.0.1:11434/api/tags", timeout=2)
        if tags.status_code != 200 or not any(
            m.get("model") == "qwen2.5:1.5b" for m in tags.json().get("models", [])
        ):
            pytest.skip("local Ollama model unavailable")
    except httpx.RequestError:
        pytest.skip("local Ollama unavailable")

    d = scope_data
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        monkeypatch.setattr(tools, "_client", client)
        response = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={
                "query": "kiểm tra tồn kho trà sữa", "use_llm": True,
                "requested_items": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["intent_source"] == "model"
        assert result["intent"] == "check_stock"
        assert result["tool_calls"] == ["get_stock"]
        assert result["stock_level"][d["item_id"]]["available"] == "1.000"

        draft = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={
                "query": "mua 1 ly trà sữa", "use_llm": True,
                "branch_id": d["branch_id"],
                "requested_items": [{"item_id": d["item_id"], "location_id": d["location_id"], "quantity": "1"}],
            },
        )
        assert draft.status_code == 200, draft.text
        assert draft.json()["intent_source"] == "model"
        assert draft.json()["intent"] == "draft_order"
        assert draft.json()["tool_calls"] == ["draft_order"]
        assert draft.json()["pending_confirmation"] is True
        assert draft.json()["order_id"] is None
        confirmed = await client.post(
            f"/retail-agent/threads/{draft.json()['thread_id']}/resume",
            headers=_headers(d["staff_id"]), json={"confirmed": True},
        )
        assert confirmed.status_code == 200, confirmed.text
        order_id = confirmed.json()["order_id"]
        assert order_id

        lookup = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={"query": "xem trạng thái đơn", "use_llm": True, "order_id": order_id},
        )
        assert lookup.status_code == 200, lookup.text
        assert lookup.json()["intent_source"] == "model"
        assert lookup.json()["intent"] == "order_status"
        assert lookup.json()["tool_calls"] == ["get_order"]
        assert lookup.json()["order_id"] == order_id

        cancel = await client.post(
            "/retail-agent/threads", headers=_headers(d["staff_id"]),
            json={"query": "hủy đơn này", "use_llm": True, "order_id": order_id},
        )
        assert cancel.status_code == 200, cancel.text
        assert cancel.json()["intent_source"] == "model"
        assert cancel.json()["intent"] == "cancel_request"
        assert cancel.json()["tool_calls"] == ["cancel_order"]
        assert cancel.json()["cancel_status"] == "cancelled"

        trace = {
            "evidence_level": "LOCAL_REAL_MODEL_AND_TEST_DB",
            "model": "qwen2.5:1.5b",
            "cases": [
                {"case": name, "intent": data["intent"], "intent_source": data["intent_source"],
                 "tool_calls": data["tool_calls"], "model_latency_ms": data["latency_ms"]}
                for name, data in (
                    ("stock", result), ("draft", draft.json()),
                    ("status", lookup.json()), ("cancel", cancel.json())
                )
            ],
        }
        artifact = Path(__file__).parent / "data" / "retailops_live_tool_trace.json"
        artifact.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.asyncio
async def test_no_confirmation_no_order_persisted(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-nc-{uuid4().hex}",
            },
        )
        assert quote.status_code == 200
        draft_id = quote.json()["draft_id"]

        # Confirm with a wrong token must not commit.
        bad = await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": "wrong-token",
                "idempotency_key": f"confirm-bad-{uuid4().hex}",
            },
        )
        assert bad.status_code == 403, bad.text

        async with AsyncSessionLocal() as session:
            order = (
                await _exec(session, select(Order).where(Order.id == draft_id))
            ).scalars().first()
            assert order is not None
            assert order.status == OrderStatus.DRAFT.value


@pytest.mark.asyncio
async def test_same_key_same_payload_replay(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-replay-{uuid4().hex}",
            },
        )
        assert quote.status_code == 200
        draft_id = quote.json()["draft_id"]
        token = quote.json()["confirmation_token"]
        key = f"confirm-replay-{uuid4().hex}"

        first = await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": token,
                "idempotency_key": key,
            },
        )
        assert first.status_code == 200, first.text

        second = await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": token,
                "idempotency_key": key,
            },
        )
        assert second.status_code == 200, second.text

        async with AsyncSessionLocal() as session:
            orders = (
                await _exec(session, select(Order).where(Order.id == draft_id))
            ).scalars().all()
            assert len(orders) == 1
            bal = (
                await _exec(
                    session,
                    select(Balance).where(
                        Balance.item_id == d["item_id"],
                        Balance.location_id == d["location_id"],
                    ),
                )
            ).scalars().first()
            assert bal.available_quantity == Decimal("0")


@pytest.mark.asyncio
async def test_same_key_different_payload_conflict(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-conflict-{uuid4().hex}",
            },
        )
        assert quote.status_code == 200
        draft_id = quote.json()["draft_id"]
        token = quote.json()["confirmation_token"]
        key = f"confirm-conflict-{uuid4().hex}"

        await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": token,
                "idempotency_key": key,
            },
        )

        conflict = await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": "different-token",
                "idempotency_key": key,
            },
        )
        assert conflict.status_code == 409, conflict.text


@pytest.mark.asyncio
async def test_request_more_than_stock_no_order(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "9999",
                    }
                ],
                "idempotency_key": f"quote-oversell-{uuid4().hex}",
            },
        )
        assert quote.status_code == 200
        assert quote.json()["stock_ok"] is False
        assert len(quote.json()["insufficient_items"]) == 1
        draft_id = quote.json()["draft_id"]
        token = quote.json()["confirmation_token"]

        confirm = await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": token,
                "idempotency_key": f"confirm-oversell-{uuid4().hex}",
            },
        )
        assert confirm.status_code == 409, confirm.text
        assert "INSUFFICIENT_STOCK" in confirm.text

        async with AsyncSessionLocal() as session:
            order = (
                await _exec(session, select(Order).where(Order.id == draft_id))
            ).scalars().first()
            assert order.status == OrderStatus.DRAFT.value


@pytest.mark.asyncio
async def test_unknown_sku_no_mutation(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": str(uuid.uuid4()),
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-unknown-{uuid4().hex}",
            },
        )
        assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_invalid_quantity_400(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "not-a-number",
                    }
                ],
                "idempotency_key": f"quote-badqty-{uuid4().hex}",
            },
        )
        assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_cancel_then_repeat_cancel_conflict(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-cancel-{uuid4().hex}",
            },
        )
        assert quote.status_code == 200
        draft_id = quote.json()["draft_id"]
        token = quote.json()["confirmation_token"]
        await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": token,
                "idempotency_key": f"confirm-cancel-{uuid4().hex}",
            },
        )

        async with AsyncSessionLocal() as session:
            order = (
                await _exec(session, select(Order).where(Order.id == draft_id))
            ).scalars().first()
            order_id = str(order.id)

        key = f"cancel-{uuid4().hex}"
        first = await client.post(
            f"{BASE}/cancel",
            headers=_headers(d["admin_id"]),
            json={"order_id": order_id, "idempotency_key": key},
        )
        assert first.status_code == 200, first.text

        # Same key + same payload replay -> cached result, one transition.
        second = await client.post(
            f"{BASE}/cancel",
            headers=_headers(d["admin_id"]),
            json={"order_id": order_id, "idempotency_key": key},
        )
        assert second.status_code == 200, second.text

        # Same key + different payload -> 409 conflict.
        conflict = await client.post(
            f"{BASE}/cancel",
            headers=_headers(d["admin_id"]),
            json={"order_id": order_id, "reason": "different reason", "idempotency_key": key},
        )
        assert conflict.status_code == 409, conflict.text

        async with AsyncSessionLocal() as session:
            order = (
                await _exec(session, select(Order).where(Order.id == order_id))
            ).scalars().first()
            assert order.status == OrderStatus.CANCELLED.value
            bal = (
                await _exec(
                    session,
                    select(Balance).where(
                        Balance.item_id == d["item_id"],
                        Balance.location_id == d["location_id"],
                    ),
                )
            ).scalars().first()
            assert bal.available_quantity == Decimal("1")


@pytest.mark.asyncio
async def test_cancel_already_cancelled_invalid_transition(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-tc-{uuid4().hex}",
            },
        )
        assert quote.status_code == 200
        draft_id = quote.json()["draft_id"]
        token = quote.json()["confirmation_token"]
        await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": token,
                "idempotency_key": f"confirm-tc-{uuid4().hex}",
            },
        )
        async with AsyncSessionLocal() as session:
            order = (
                await _exec(session, select(Order).where(Order.id == draft_id))
            ).scalars().first()
            order_id = str(order.id)

        await client.post(
            f"{BASE}/cancel",
            headers=_headers(d["admin_id"]),
            json={"order_id": order_id, "idempotency_key": f"cancel-tc-{uuid4().hex}"},
        )
        repeat = await client.post(
            f"{BASE}/cancel",
            headers=_headers(d["admin_id"]),
            json={"order_id": order_id, "idempotency_key": f"cancel-tc-2-{uuid4().hex}"},
        )
        assert repeat.status_code == 409, repeat.text


@pytest.mark.asyncio
async def test_cross_tenant_read_forbidden(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-xt-{uuid4().hex}",
            },
        )
        assert quote.status_code == 200
        draft_id = quote.json()["draft_id"]
        token = quote.json()["confirmation_token"]
        await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": token,
                "idempotency_key": f"confirm-xt-{uuid4().hex}",
            },
        )
        async with AsyncSessionLocal() as session:
            order = (
                await _exec(session, select(Order).where(Order.id == draft_id))
            ).scalars().first()
            order_id = str(order.id)

        # Outsider user: has read capability but no branch/scope grant to this
        # branch/location -> 403 (no leakage of another tenant's order).
        async with AsyncSessionLocal() as session:
            outsider = User(
                id=uuid.uuid4(),
                username=f"retail_outsider_{uuid4().hex[:6]}",
                password_hash="x",
                status="active",
                display_name_demo="Retail Outsider",
                branch_id=None,
            )
            session.add(outsider)
            await session.flush()
            session.add(UserRole(user_id=outsider.id, role_code="retail_staff"))
            await session.commit()
        outsider_headers = _headers(str(outsider.id))

        resp = await client.get(f"{BASE}/{order_id}", headers=outsider_headers)
        assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_operation_status_committed(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        quote = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-op-{uuid4().hex}",
            },
        )
        assert quote.status_code == 200
        draft_id = quote.json()["draft_id"]
        token = quote.json()["confirmation_token"]
        key = f"confirm-op-{uuid4().hex}"
        await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": token,
                "idempotency_key": key,
            },
        )

        resp = await client.get(f"{BASE}/operations/{key}", headers=_headers(d["admin_id"]))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["operation_id"] == key
        assert body["status"] == "committed"

        other_actor = await client.get(f"{BASE}/operations/{key}", headers=_headers(d["staff_id"]))
        assert other_actor.status_code == 404


@pytest.mark.asyncio
async def test_operation_status_unknown_missing_key(scope_data):
    d = scope_data
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        resp = await client.get(
            f"{BASE}/operations/does-not-exist-{uuid4().hex}", headers=_headers(d["admin_id"])
        )
        assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_last_unit_race_exactly_one_success(scope_data):
    """Two concurrent confirm requests for the same last unit: one wins."""
    d = scope_data
    from app.main import app

    async def confirm_once(client, draft_id, token, key):
        return await client.post(
            f"{BASE}/confirm",
            headers=_headers(d["admin_id"]),
            json={
                "draft_id": draft_id,
                "confirmation_token": token,
                "idempotency_key": key,
            },
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Two separate drafts, same last unit.
        q1 = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-race-1-{uuid4().hex}",
            },
        )
        assert q1.status_code == 200
        q2 = await client.post(
            f"{BASE}/quote",
            headers=_headers(d["admin_id"]),
            json={
                "branch_id": d["branch_id"],
                "lines": [
                    {
                        "item_id": d["item_id"],
                        "location_id": d["location_id"],
                        "quantity": "1",
                    }
                ],
                "idempotency_key": f"quote-race-2-{uuid4().hex}",
            },
        )
        assert q2.status_code == 200

        draft_id1 = q1.json()["draft_id"]
        draft_id2 = q2.json()["draft_id"]
        results = await asyncio.gather(
            confirm_once(client, draft_id1, q1.json()["confirmation_token"], f"race-1-{uuid4().hex}"),
            confirm_once(client, draft_id2, q2.json()["confirmation_token"], f"race-2-{uuid4().hex}"),
        )

        statuses = sorted([r.status_code for r in results])
        assert statuses == [200, 409], statuses

        async with AsyncSessionLocal() as session:
            bal = (
                await _exec(
                    session,
                    select(Balance).where(
                        Balance.item_id == d["item_id"],
                        Balance.location_id == d["location_id"],
                    ),
                )
            ).scalars().first()
            assert bal.available_quantity == Decimal("0")
            states = {}
            for did in (draft_id1, draft_id2):
                o = (
                    await _exec(session, select(Order).where(Order.id == did))
                ).scalars().first()
                states[did] = o.status
            assert sorted(states.values()) == [
                OrderStatus.CONFIRMED.value,
                OrderStatus.DRAFT.value,
            ]
