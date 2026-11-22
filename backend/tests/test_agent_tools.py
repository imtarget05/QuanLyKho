"""Tests for D4 — read-only GraphQL tools for the SOP agent (Track D).

The agent may only READ through GraphQL. Mutations/subscriptions and unknown
root fields must be rejected before any executor is invoked (fail-closed).
"""

from __future__ import annotations

import pytest

from app.services import agent_tools
from app.services.agent_tools import (
    ALLOWED_ROOT_FIELDS,
    TOOLS,
    ReadOnlyViolation,
    assert_read_only,
    call_tool,
    detect_tools,
    run_tools,
)
from app.services.ai_agent import run_sop_agent


class FakeSettings:
    ai_timeout_seconds = 5


class FakeClient:
    """Retriever doesn't call HTTP; kept for signature compatibility."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None, timeout=None):  # pragma: no cover
        raise AssertionError("agent must not call an external LLM in D4 tests")


def _fake_executor(response: dict):
    calls: list[tuple[str, dict | None]] = []

    async def executor(document: str, variables: dict | None = None) -> dict:
        calls.append((document, variables))
        return response

    executor.calls = calls  # type: ignore[attr-defined]
    return executor


# ---------------------------------------------------------------------------
# AST / whitelist guard
# ---------------------------------------------------------------------------


def test_allowed_root_fields_are_schema_query_fields():
    # Query root fields available in app/graphql/schema.graphql
    assert {"accounts", "balance", "sagas", "auditTrail", "outboxEvents", "health"} <= ALLOWED_ROOT_FIELDS
    # Mutations must never be part of the read-only whitelist.
    assert "transferFunds" not in ALLOWED_ROOT_FIELDS
    assert "adjustInventory" not in ALLOWED_ROOT_FIELDS


def test_assert_read_only_accepts_query():
    assert_read_only("{ health { status service } }")
    assert_read_only("query AgentAccounts { accounts(limit: 5) { code } }")


def test_assert_read_only_rejects_mutation():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(
            'mutation { transferFunds(input: {sourceAccountId: "a", destAccountId: "b", amount: "1"}) { success } }'
        )


def test_assert_read_only_rejects_subscription():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only('subscription { newOutboxEvent { id } }')


def test_assert_read_only_rejects_unknown_root_field():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only("query { secretDump { everything } }")


def test_assert_read_only_rejects_schema_introspection():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only("{ __schema { types { name } } }")


def test_assert_read_only_rejects_oversized_document():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only("{ health { status } }" + (" " * 10_000))


def test_assert_read_only_rejects_multiple_operations():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only("query A { health { status } }\nquery B { health { status } }")


def test_assert_read_only_rejects_syntax_error():
    with pytest.raises(ReadOnlyViolation):
        assert_read_only("{ health { status }")


# ---------------------------------------------------------------------------
# Tool registry + intent detection
# ---------------------------------------------------------------------------


def test_tool_documents_pass_the_guard():
    for spec in TOOLS.values():
        assert_read_only(spec.document)


def test_detect_tools_matches_vietnamese_intents():
    assert "account_balances" in detect_tools("cho tôi xem số dư tài khoản hiện tại")
    assert "saga_status" in detect_tools("trạng thái các giao dịch chuyển tiền gần đây")
    assert "outbox_events" in detect_tools("outbox có event nào đang pending")
    assert "audit_trail" in detect_tools("lịch sử thao tác kiểm toán của kho")
    assert "service_health" in detect_tools("health của hệ thống thế nào")


def test_detect_tools_handles_diacritics_and_returns_empty_for_docs_query():
    assert "account_balances" in detect_tools("so du tai khoan")
    assert detect_tools("quy trinh xuat hang het han") == []


def test_detect_tools_is_deterministic_order_and_capped():
    names = detect_tools("số dư tài khoản và trạng thái saga và outbox", limit=2)
    assert len(names) == 2
    assert names == detect_tools("số dư tài khoản và trạng thái saga và outbox", limit=2)


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def test_call_tool_executes_whitelisted_query():
    executor = _fake_executor({"data": {"health": {"status": "healthy", "service": "x"}}})
    result = await call_tool("service_health", executor=executor)
    assert result == {"health": {"status": "healthy", "service": "x"}}
    assert len(executor.calls) == 1
    assert executor.calls[0][0] == TOOLS["service_health"].document


async def test_call_tool_rejects_unknown_tool():
    with pytest.raises(ReadOnlyViolation):
        await call_tool("drop_tables", executor=_fake_executor({"data": {}}))


async def test_call_tool_rejects_injected_mutation_document():
    """Even a tool spec tampered with at runtime cannot emit a mutation."""
    executor = _fake_executor({"data": {"transferFunds": {"success": True}}})
    with pytest.raises(ReadOnlyViolation):
        await agent_tools._execute_document(
            'mutation { transferFunds(input: {sourceAccountId: "a", destAccountId: "b", amount: "1"}) { success } }',
            None,
            executor,
        )
    assert executor.calls == []  # guard ran before the executor


async def test_run_tools_collects_results_and_errors_fail_soft():
    async def flaky_executor(document: str, variables: dict | None = None) -> dict:
        if "sagas" in document:
            raise RuntimeError("db down")
        return {"data": {"health": {"status": "healthy", "service": "s"}}}

    out = await run_tools("health và saga", executor=flaky_executor)
    assert out["calls"], "at least one tool must be attempted"
    assert out["errors"], "executor failure must be captured, not raised"
    assert all("error" in err for err in out["errors"])


async def test_default_executor_runs_in_process_against_real_schema():
    payload = await agent_tools.default_executor(TOOLS["service_health"].document, None)
    assert payload["data"]["health"]["status"] == "healthy"
    assert payload["data"]["health"]["service"] == "quanlykho-graphql"


# ---------------------------------------------------------------------------
# Agent integration
# ---------------------------------------------------------------------------


async def test_agent_uses_graphql_tool_and_grounds_answer():
    executor = _fake_executor(
        {"data": {"accounts": [
            {"code": "101", "ledgerBalance": "1000", "availableBalance": "900", "holdBalance": "100"}
        ]}}
    )
    result = await run_sop_agent(
        "cho tôi xem số dư tài khoản 101",
        FakeSettings(),
        FakeClient(),
        executor=executor,
    )
    assert result["tool_calls"] and result["tool_calls"][0]["tool"] == "account_balances"
    assert result["tool_results"]
    assert "101" in str(result["tool_results"])
    assert result["tool_errors"] == []
    assert "Dữ liệu hệ thống" in result["answer"]
    assert result["abstained"] is False


async def test_agent_tool_failure_is_reported_but_agent_still_answers_docs():
    async def broken_executor(document: str, variables: dict | None = None) -> dict:
        raise RuntimeError("graphql unavailable")

    result = await run_sop_agent(
        "trạng thái saga và quy trình xuất hàng hết hạn",
        FakeSettings(),
        FakeClient(),
        executor=broken_executor,
    )
    assert result["tool_errors"], "tool failure must surface in response"
    assert result["abstained"] is False
    assert result["sources"], "SOP docs are still used when the tool fails"
    assert result["answer"]


async def test_agent_write_action_never_calls_tools():
    executor = _fake_executor({"data": {"accounts": []}})
    result = await run_sop_agent(
        "điều chỉnh tồn kho mặt hàng A và xem số dư tài khoản",
        FakeSettings(),
        FakeClient(),
        executor=executor,
    )
    assert result["hitl_pending"] is True
    assert result["tool_calls"] == []
    assert executor.calls == []


async def test_agent_can_disable_tools_explicitly():
    executor = _fake_executor({"data": {"health": {"status": "healthy"}}})
    result = await run_sop_agent(
        "health hệ thống",
        FakeSettings(),
        FakeClient(),
        executor=executor,
        enable_tools=False,
    )
    assert result["tool_calls"] == []
    assert executor.calls == []
