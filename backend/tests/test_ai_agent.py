"""Tests for the SOP retrieval agent (ai_agent.py)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.services.ai_agent import (
    WRITE_ACTIONS,
    AgentState,
    classify_write_action,
    decide_node,
    decide_write_action,
    get_pending_write_action,
    pend_write_action,
    retrieve_node,
    run_sop_agent,
)


class FakeSettings:
    ai_timeout_seconds = 5


class FakeResponse:
    def __init__(self, json_data: dict[str, Any], status_code: int = 200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)  # type: ignore[arg-type]

    def json(self) -> dict[str, Any]:
        return self._json


class FakeClient:
    """Fake httpx client that returns a canned grounded answer."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None, timeout=None):
        return FakeResponse(
            {
                "result": {
                    "response": (
                        "Theo tài liệu FEFO: hàng quá hạn phải lập phiếu xuất hủy. "
                        "Maker lập, Checker duyệt."
                    )
                },
                "success": True,
            }
        )


def _state(query: str) -> AgentState:
    return AgentState(query=query)


def test_retrieve_node_populates_sources():
    state = _state("nhap hang het han lam sao")
    retrieve_node(state, FakeSettings(), FakeClient())
    assert state["sources"], "retrieve should return sources for SOP query"
    assert state["abstained"] is False


def test_decide_node_abstains_when_no_sources():
    state = _state("xinh dep tai sao")
    state["sources"] = []
    decide_node(state)
    assert state["abstained"] is True
    assert "không tìm thấy" in state["abstain_reason"].lower()
    assert state["answer"]


def test_decide_node_continues_when_sources_exist():
    state = _state("nhap hang")
    state["sources"] = [{"source": "docs/x.md", "section": "S", "content": "noidung"}]
    decide_node(state)
    assert state["abstained"] is False


def test_write_actions_contains_expected():
    assert WRITE_ACTIONS == {"adjust_inventory", "send_email", "create_ticket"}


def test_classify_write_action_detects_adjust_inventory():
    action = classify_write_action("điều chỉnh tồn kho mặt hàng A")
    assert action is not None
    assert action["action_type"] == "adjust_inventory"


def test_classify_write_action_detects_send_email():
    action = classify_write_action("gửi email thông báo cho quản lý")
    assert action is not None
    assert action["action_type"] == "send_email"


def test_classify_write_action_detects_create_ticket():
    action = classify_write_action("tạo ticket hỗ trợ nhập hàng")
    assert action is not None
    assert action["action_type"] == "create_ticket"


def test_classify_write_action_read_query_returns_none():
    assert classify_write_action("nhập hàng hết hạn làm sao") is None
    assert classify_write_action("quy trình kiểm soát kép maker checker") is None


def test_pend_and_get_write_action():
    rid = pend_write_action("điều chỉnh tồn", "adjust_inventory", {"raw_query": "x"})
    rec = get_pending_write_action(rid)
    assert rec is not None
    assert rec["request_id"] == rid
    assert rec["status"] == "pending"
    assert rec["action_type"] == "adjust_inventory"


def test_decide_write_action_approve_and_reject():
    rid = pend_write_action("gửi email", "send_email", {})
    approved = decide_write_action(rid, "approved", "manager-01")
    assert approved is not None
    assert approved["status"] == "approved"
    assert approved["approver"] == "manager-01"

    rid2 = pend_write_action("tạo ticket", "create_ticket", {})
    rejected = decide_write_action(rid2, "rejected", "manager-01")
    assert rejected is not None
    assert rejected["status"] == "rejected"

    # invalid decision
    assert decide_write_action(rid, "maybe", "manager-01") is None
    # already decided
    assert decide_write_action(rid, "rejected", "manager-01") is None


@pytest.mark.asyncio
async def test_run_sop_agent_write_action_is_pended_not_executed():
    result = await run_sop_agent("điều chỉnh tồn kho mặt hàng A", FakeSettings(), FakeClient())
    assert result["hitl_pending"] is True
    assert result["hitl_request_id"] is not None
    assert result["write_action"] is not None
    assert result["write_action"]["action_type"] == "adjust_inventory"
    assert "không tự thực hiện" in result["answer"]
    assert result["sources"] == []
    assert result["abstained"] is False


@pytest.mark.asyncio
async def test_run_sop_agent_abstains_for_irrelevant_query():
    result = await run_sop_agent("mua bitcoin dau tu", FakeSettings(), FakeClient())
    assert result["abstained"] is True
    assert result["sources"] == []
    assert result["answer"]


@pytest.mark.asyncio
async def test_run_sop_agent_grounded_for_sop_query():
    result = await run_sop_agent("quy trinh xuat hang het han", FakeSettings(), FakeClient())
    assert result["abstained"] is False
    assert result["hitl_pending"] is False
    assert result["write_action"] is None
    assert len(result["sources"]) > 0
    assert result["answer"]
    assert "provider" in result


def test_agent_state_defaults():
    state = _state("test query")
    assert state["query"] == "test query"
    assert state["sources"] == []
    assert state["abstained"] is False
    assert state["answer"] == ""
    assert state["error"] is None
    assert state["hitl_pending"] is False
    assert state["write_action"] is None
