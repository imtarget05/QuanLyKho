"""RO-03: durable checkpointer + HITL pause/resume for RetailOps graph."""

from __future__ import annotations

import pytest
from langgraph.types import Command

from app.services.retail_agent.graph import build_retail_graph
from app.services.retail_agent.state import RetailState


def _base_state() -> RetailState:
    return {
        "query": "mua tra sua",
        "buyer_id": "buyer-1",
        "intent": "",
        "requested_items": [],
        "ambiguous": False,
        "clarification_needed": False,
        "draft_id": None,
        "confirmation_token": None,
        "order_quote": None,
        "created_at": "",
        "stock_level": {},
        "validation_result": "",
        "validation_message": None,
        "confirmed": False,
        "confirmation_by": None,
        "confirmed_at": None,
        "order_id": None,
        "committed_at": None,
        "commit_result": None,
        "cancelled": False,
        "cancel_reason": None,
        "cancel_result": None,
        "tool_calls": [],
        "audit_trail": [],
        "error": None,
        "error_context": None,
        "retry_attempt": 0,
        "latency_ms": None,
        "tool_call_count": 0,
        "tokens_used": None,
    }


def test_graph_has_process_local_checkpointer():
    graph = build_retail_graph()
    assert graph is not None
    assert graph.checkpointer is not None


@pytest.mark.asyncio
async def test_graph_does_not_pause_or_commit_without_draft():
    graph = build_retail_graph()
    config = {"configurable": {"thread_id": "rt-03-1"}}

    state = _base_state()
    out = await graph.ainvoke(state, config)
    assert "__interrupt__" not in out
    assert out.get("order_id") is None


@pytest.mark.asyncio
async def test_graph_pauses_at_confirmation_and_resumes(monkeypatch):
    from app.services.retail_agent import nodes

    async def stock(_item_id, _location_id):
        return {"success": True, "available": 3}

    async def draft(**_kwargs):
        return {"draft_id": "d-1", "confirmation_token": "tok", "stock_ok": True}

    async def confirm(**_kwargs):
        return {"order_id": "o-1", "status": "confirmed"}

    monkeypatch.setattr(nodes, "get_stock", stock)
    monkeypatch.setattr(nodes, "draft_order", draft)
    monkeypatch.setattr(nodes, "confirm_order", confirm)
    graph = build_retail_graph()
    config = {"configurable": {"thread_id": "rt-03-confirm"}}
    state = _base_state()
    state["branch_id"] = "branch-1"
    state["requested_items"] = [{"item_id": "i-1", "location_id": "l-1", "quantity": 1}]
    out = await graph.ainvoke(state, config, context={"access_token": "test-token", "actor_id": "buyer-1"})
    assert "__interrupt__" in out

    # Snapshot should be paused at await_confirmation
    snap = await graph.aget_state(config)
    assert snap.next == ("await_confirmation",)

    # Resume after user confirmation
    result = await graph.ainvoke(Command(resume=True), config, context={"access_token": "test-token", "actor_id": "buyer-1"})
    assert result["order_id"] == "o-1"
    assert result["confirmed"] is True
    snap2 = await graph.aget_state(config)
    assert snap2.next == ()


@pytest.mark.asyncio
async def test_model_failure_uses_deterministic_intent_fallback(monkeypatch):
    from langgraph.runtime import Runtime

    from app.services.retail_agent import nodes

    async def unavailable(_query):
        return {"intent": None, "latency_ms": None}

    monkeypatch.setattr(nodes, "classify_intent_live", unavailable)
    result = await nodes.classify_intent(
        {"query": "hủy đơn này"}, Runtime(context={"use_llm": True})
    )
    assert result["intent"] == "cancel_request"
    assert result["intent_source"] == "deterministic_fallback"
