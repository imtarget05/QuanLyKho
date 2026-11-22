"""RO-04 evaluation smoke test (SIMULATED).

Loads the golden dataset, runs a deterministic simulation agent, and writes
an evidence report. Metrics are SIMULATED — not real-model results.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.retailops_eval import (
    evaluate_retailops,
    load_golden_dataset,
    write_report,
)

DATASET = Path(__file__).resolve().parents[1] / "tests" / "data" / "golden_retailops.jsonl"
REPORT = Path(__file__).resolve().parents[1] / "tests" / "data" / "retailops_eval_report.json"


def _simulated_agent(query: str) -> dict:
    q = query.lower()
    if "khong xac nhan" in q or "no_commit" in q:
        return {"outcome": "no_commit", "tools": ["quote_order"], "args": {}}
    if "sai token" in q:
        return {"outcome": "invalid_confirmation", "tools": ["commit_order"], "args": {}}
    if "payload khac" in q:
        return {"outcome": "idempotency_conflict", "tools": [], "args": {}}
    if "het hang" in q or "100 ly" in q or "10 tra sua" in q or "8 tra sua" in q:
        return {"outcome": "insufficient_stock", "tools": ["get_stock"], "args": {}}
    if "huy don" in q and "6,000,000" in q:
        return {"outcome": "cancel_pending_approval", "tools": ["request_cancel_order"], "args": {}}
    if "huy don" in q and "50,000" in q:
        return {"outcome": "cancelled", "tools": ["request_cancel_order"], "args": {}}
    if "doi y" in q:
        return {"outcome": "draft_cancelled", "tools": [], "args": {}}
    if "chi nhanh khac" in q or "user khac" in q:
        return {"outcome": "forbidden", "tools": ["get_order"], "args": {}}
    if "khong ton tai" in q:
        return {"outcome": "not_found", "tools": [], "args": {}}
    if q.strip() == "mua tra sua":
        return {"outcome": "clarify", "tools": ["search_catalog"], "args": {}}
    if "0 ly" in q or "-5 ly" in q:
        return {"outcome": "invalid_argument", "tools": [], "args": {}}
    if "xoa toan bo" in q:
        return {"outcome": "forbidden", "tools": [], "args": {}}
    if "bo qua xac nhan" in q:
        return {"outcome": "confirmation_required", "tools": [], "args": {}}
    if "timeout" in q:
        return {"outcome": "result_unknown", "tools": [], "args": {}}
    if "2 lan cung key" in q:
        return {"outcome": "single_order", "tools": [], "args": {}}
    if "da huy roi" in q:
        return {"outcome": "invalid_transition", "tools": [], "args": {}}
    if "khuyen mai" in q:
        return {"outcome": "backend_price_prevails", "tools": ["quote_order"], "args": {}}
    if "expired" in q or "het han ttl" in q:
        return {"outcome": "expired_draft", "tools": [], "args": {}}
    if "branch khong co hang" in q:
        return {"outcome": "insufficient_stock", "tools": ["get_stock"], "args": {}}
    return {"outcome": "success", "tools": ["quote_order", "commit_order"], "args": {}}


def test_golden_dataset_loads():
    cases = load_golden_dataset(DATASET)
    assert len(cases) >= 30
    ids = {c["id"] for c in cases}
    assert len(ids) == len(cases)


def test_retailops_eval_runs_and_writes_report():
    cases = load_golden_dataset(DATASET)
    report = evaluate_retailops(_simulated_agent, cases)
    assert report["total_cases"] >= 30
    assert report["task_success_rate"] >= 0.9
    assert report["tool_scored_cases"] == 0
    assert report["tool_selection_accuracy"] is None
    assert report["argument_validity_rate"] is None
    write_report(report, REPORT)
    assert REPORT.exists()
    data = json.loads(REPORT.read_text())
    assert data["total_cases"] == len(cases)
