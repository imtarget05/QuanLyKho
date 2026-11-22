"""Pilot safety: unconnected agent tools must never claim business mutations."""

import json
from typing import Any

import httpx
import pytest

from app.api.routes import orders
from app.services.retail_agent import nodes, tools


@pytest.mark.asyncio
async def test_unconnected_mutation_tools_fail_closed():
    stock = await tools.get_stock("item", "location")
    draft = await tools.draft_order("buyer", [{"item_id": "item"}], "branch")
    confirm = await tools.confirm_order("draft", "token")
    cancel = await tools.cancel_order("order")
    permission = await tools.check_permission("user", "retail:order:create")

    for result in (stock, draft, confirm, cancel, permission):
        assert result["success"] is False
        assert result["error_code"] == "DEPENDENCY_UNAVAILABLE"
    assert "draft_id" not in draft
    assert "order_id" not in confirm
    assert "status" not in cancel
    assert permission["can_perform"] is False


@pytest.mark.asyncio
async def test_agent_nodes_do_not_report_unconnected_writes_as_success():
    draft = await nodes.draft_order_node({"requested_items": [{"item_id": "item"}]})
    cancel = await nodes.cancel_order_node({"order_id": "order"})

    assert draft["draft_id"] is None
    assert draft["validation_result"] == "no_branch"
    assert cancel["cancelled"] is False
    assert nodes.report_result(cancel)["final_message"] != "Đơn hàng đã hủy"


@pytest.mark.asyncio
async def test_empty_location_grants_remain_distinct_from_admin(monkeypatch):
    async def no_grants(*args, **kwargs):
        return set()

    monkeypatch.setattr(orders, "get_accessible_location_ids", no_grants)
    assert await orders._get_accessible_locations(object(), object()) == set()

    async def admin_scope(*args, **kwargs):
        return None

    monkeypatch.setattr(orders, "get_accessible_location_ids", admin_scope)
    assert await orders._get_accessible_locations(object(), object()) is None


def _mock_client(handler) -> None:
    tools._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    )


@pytest.mark.asyncio
async def test_draft_order_forwards_to_quote_api():
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "draft_id": "d-1",
                "confirmation_token": "tok-x",
                "stock_ok": True,
                "total_amount": "50000",
            },
        )

    _mock_client(handler)
    result = await tools.draft_order(
        "buyer",
        [{"item_id": "i", "location_id": "l", "quantity": "2"}],
        "branch",
        idempotency_key="idem-1",
        access_token="actor-token",
    )
    assert result["draft_id"] == "d-1"
    assert result["confirmation_token"] == "tok-x"
    assert result["stock_ok"] is True
    assert captured["path"] == "/orders/quote"
    assert captured["body"]["branch_id"] == "branch"
    assert captured["body"]["idempotency_key"] == "idem-1"
    assert captured["path"] == "/orders/quote"


@pytest.mark.asyncio
async def test_confirm_order_forwards_to_confirm_api():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/orders/confirm"
        body = json.loads(request.content)
        assert body["draft_id"] == "d-1"
        assert body["confirmation_token"] == "tok-x"
        return httpx.Response(
            200,
            json={"order_id": "o-1", "status": "confirmed", "total_amount": "50000"},
        )

    _mock_client(handler)
    result = await tools.confirm_order("d-1", "tok-x", idempotency_key="idem-2", access_token="actor-token")
    assert result["order_id"] == "o-1"
    assert result["status"] == "confirmed"


@pytest.mark.asyncio
async def test_cancel_order_forwards_to_cancel_api():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/orders/cancel"
        return httpx.Response(
            200, json={"order_id": "o-1", "status": "cancelled", "message": "cancelled"}
        )

    _mock_client(handler)
    result = await tools.cancel_order("o-1", reason="user requested", idempotency_key="idem-3", access_token="actor-token")
    assert result["order_id"] == "o-1"
    assert result["status"] == "cancelled"


@pytest.mark.asyncio
async def test_tool_returns_dependency_unavailable_when_service_unreachable():
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    _mock_client(handler)
    result = await tools.draft_order(
        "buyer", [{"item_id": "i", "location_id": "l", "quantity": "2"}], "branch", access_token="actor-token"
    )
    assert result["success"] is False
    assert result["error_code"] == "DEPENDENCY_UNAVAILABLE"
    assert "draft_id" not in result


@pytest.mark.asyncio
async def test_tool_normalizes_api_error_response():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "INSUFFICIENT_STOCK",
                    "message": "Not enough available stock",
                }
            },
        )

    _mock_client(handler)
    result = await tools.confirm_order("d-1", "tok-x", access_token="actor-token")
    assert result["success"] is False
    assert result["error_code"] == "INSUFFICIENT_STOCK"
    assert result["message"] == "Not enough available stock"
    assert result["status_code"] == 409


@pytest.mark.asyncio
async def test_confirm_timeout_with_unknown_status_does_not_retry_write():
    calls = {"post": 0, "get": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            calls["post"] += 1
            raise httpx.ReadTimeout("lost response", request=request)
        calls["get"] += 1
        return httpx.Response(404, json={"error": {"code": "OPERATION_NOT_FOUND"}})

    _mock_client(handler)
    result = await tools.confirm_order(
        "d-1", "token", idempotency_key="same-operation-key", access_token="actor-token"
    )
    assert result["error_code"] == "RESULT_UNKNOWN"
    assert result["operation_id"] == "same-operation-key"
    assert calls == {"post": 1, "get": 1}
