"""Eval harness: SOP agent golden-dataset regression test (D5).

Rule-based LLM-as-judge stand-in (local-only, no cloud LLM required). Classifies
each agent result into one of: abstain / grounded / write_pending and asserts
against the golden expectation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.ai_agent import run_sop_agent

GOLDEN_PATH = Path(__file__).resolve().parent / "data" / "golden_sop_agent.json"


class FakeSettings:
    ai_timeout_seconds = 5


class FakeClient:
    """Fake httpx client returning a canned grounded answer (local, no LLM)."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None, timeout=None):
        return _FakeResponse(
            {
                "result": {
                    "response": (
                        "Theo tai lieu FEFO: hang qua han phai lap phieu xoa huy. "
                        "Maker lap, Checker duyet."
                    )
                },
                "success": True,
            }
        )


class _FakeResponse:
    def __init__(self, data):
        self._data = data
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _judge(result: dict) -> dict:
    """Rule-based judge: classify agent result into a category."""
    if result.get("hitl_pending"):
        return {
            "category": "write_pending",
            "write_action_type": (result.get("write_action") or {}).get("action_type"),
            "auto_executed": False,
        }
    if result.get("abstained"):
        return {"category": "abstain"}
    if result.get("sources"):
        return {"category": "grounded"}
    return {"category": "abstain"}


def _load_cases():
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
async def test_sop_agent_golden_case(case):
    query = case["query"]
    expected = case["expect"]
    settings = FakeSettings()
    client = FakeClient()

    result = await run_sop_agent(query, settings, client)
    judged = _judge(result)

    # Category must match
    assert judged["category"] == case["category"], (
        f"case {case['id']}: expected {case['category']}, judged {judged['category']} "
        f"(answer={result.get('answer')!r})"
    )

    # Field-level expectations
    if expected.get("abstained") is True:
        assert result["abstained"] is True
    if expected.get("sources_empty") is True:
        assert result["sources"] == []
    if expected.get("sources_nonempty") is True:
        assert len(result["sources"]) > 0
    if expected.get("hitl_pending") is True:
        assert result["hitl_pending"] is True
        assert result["hitl_request_id"] is not None
    if expected.get("write_action_none") is True:
        assert result["write_action"] is None
    if expected.get("write_action_type") is not None:
        assert result["write_action"] is not None
        assert result["write_action"]["action_type"] == expected["write_action_type"]
    if expected.get("auto_executed") is False:
        assert result["hitl_pending"] is True  # never auto-executed


def test_golden_dataset_has_cases():
    cases = _load_cases()
    assert len(cases) >= 5
    categories = {c["category"] for c in cases}
    assert {"abstain", "grounded", "write_pending"} <= categories
