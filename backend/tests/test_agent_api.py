"""Tests for the SOP agent API surface (D1/D2/D4) — handler-level, no DB."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import agent as agent_api
from app.services.ai_agent import pend_write_action


def _user(user_id: int = 1, status: str = "active"):
    return SimpleNamespace(id=user_id, status=status, email=f"u{user_id}@example.com", username=f"u{user_id}")


@pytest.fixture(autouse=True)
def _clear_rate_windows():
    agent_api._windows.clear()
    yield
    agent_api._windows.clear()


async def test_ask_returns_agent_result(monkeypatch):
    captured: dict = {}

    async def fake_run(query, settings, client, provider=None, limit=3, executor=None, enable_tools=True):
        captured.update(query=query, provider=provider, enable_tools=enable_tools, executor=executor)
        return {"answer": "ok", "abstained": False, "tool_calls": [], "tool_results": [],
                "tool_errors": [], "sources": []}

    monkeypatch.setattr(agent_api, "run_sop_agent", fake_run)
    result = await agent_api.ask(
        agent_api.AgentAskRequest(message="quy trinh xuat hang het han", enable_tools=False),
        user=_user(),
    )
    assert result["answer"] == "ok"
    assert captured["query"] == "quy trinh xuat hang het han"
    assert captured["enable_tools"] is False
    # Route must never inject an executor: production path = in-process real schema.
    assert captured["executor"] is None


async def test_ask_rejects_inactive_user(monkeypatch):
    async def fake_run(*args, **kwargs):  # pragma: no cover
        raise AssertionError("must not run for inactive user")

    monkeypatch.setattr(agent_api, "run_sop_agent", fake_run)
    with pytest.raises(HTTPException) as exc:
        await agent_api.ask(agent_api.AgentAskRequest(message="số dư tài khoản"), user=_user(status="disabled"))
    assert exc.value.status_code == 403


async def test_ask_rate_limited_with_retry_after(monkeypatch):
    import time

    async def fake_run(*args, **kwargs):  # pragma: no cover
        raise AssertionError("must not run when rate limited")

    monkeypatch.setattr(agent_api, "run_sop_agent", fake_run)
    user = _user()
    agent_api._windows[str(user.id)] = (time.monotonic(), 10_000)
    with pytest.raises(HTTPException) as exc:
        await agent_api.ask(agent_api.AgentAskRequest(message="health"), user=user)
    assert exc.value.status_code == 429
    assert exc.value.headers == {"Retry-After": "60"}


async def test_hitl_get_unknown_request_returns_404():
    with pytest.raises(HTTPException) as exc:
        await agent_api.get_hitl_request("hitl-missing", user=_user())
    assert exc.value.status_code == 404


async def test_hitl_decision_records_without_executing():
    request_id = pend_write_action(
        "điều chỉnh tồn kho", "adjust_inventory", {"raw_query": "điều chỉnh tồn kho"}
    )
    user = _user()

    record = await agent_api.get_hitl_request(request_id, user=user)
    assert record["status"] == "pending"

    result = await agent_api.decide_hitl_request(
        request_id,
        agent_api.HitlDecisionRequest(decision="approved", note="checked stock sheet"),
        user=user,
    )
    assert result["status"] == "approved"
    assert result["approver"] == user.email
    assert result["executed"] is False
    assert result["note"] == "checked stock sheet"

    # Second decision must conflict (already decided).
    with pytest.raises(HTTPException) as exc:
        await agent_api.decide_hitl_request(
            request_id,
            agent_api.HitlDecisionRequest(decision="rejected"),
            user=user,
        )
    assert exc.value.status_code == 409
