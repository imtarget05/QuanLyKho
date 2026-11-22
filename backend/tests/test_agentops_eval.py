"""AO-02: Evaluation runner + CI regression gate (offline tests)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.agentops_eval import (
    MAX_AUTH_VIOLATION_DELTA,
    MAX_TASK_SUCCESS_DROP,
    _load_agent_fn,
    gate_exit_status,
    main,
    run_comparative,
)
from app.services.retailops_eval import load_golden_dataset

DATASET = Path(__file__).resolve().parent / "data" / "golden_retailops.jsonl"


def _load_dataset():
    return load_golden_dataset(DATASET)


def _worse_agent(query: str) -> dict:
    # Intentionally wrong: never uses confirm_order, so success drops.
    return {"outcome": "clarify", "tools": [], "args": {}}


def _auth_leak_agent(query: str) -> dict:
    return {"outcome": "success", "tools": ["draft_order"], "args": {}, "authorization_violation": True}


def test_load_agent_fn_simulated():
    fn = _load_agent_fn("simulated")
    assert fn("Mua 2 ly tra sua")["outcome"] == "success"


def test_comparative_simulated_vs_simulated_not_blocked():
    dataset = _load_dataset()
    sim = _load_agent_fn("simulated")
    report = run_comparative(
        baseline_fn=sim, candidate_fn=sim, dataset=dataset,
        baseline_version="v1.0", candidate_version="v1.1",
    )
    assert report["metadata"]["exit_status"] == 0
    assert report["metadata"]["blocked"] is False
    assert report["metadata"]["blockers"] == []
    assert report["delta"]["task_success_rate"] == 0.0


def test_comparative_detects_task_success_regression():
    dataset = _load_dataset()
    sim = _load_agent_fn("simulated")
    report = run_comparative(
        baseline_fn=sim, candidate_fn=_worse_agent, dataset=dataset,
        baseline_version="v1.0", candidate_version="v1.1-broken",
    )
    assert report["metadata"]["exit_status"] == 1
    assert report["metadata"]["blocked"] is True
    assert any("task success dropped" in b for b in report["metadata"]["blockers"])
    assert report["delta"]["task_success_rate"] < 0


def test_comparative_detects_auth_violation_hard_blocker():
    dataset = _load_dataset()
    sim = _load_agent_fn("simulated")
    report = run_comparative(
        baseline_fn=sim, candidate_fn=_auth_leak_agent, dataset=dataset,
        baseline_version="v1.0", candidate_version="v1.1-leak",
    )
    assert report["metadata"]["exit_status"] == 1
    assert report["metadata"]["blocked"] is True
    assert any("authorization violations increased" in b for b in report["metadata"]["blockers"])


def test_gate_exit_status():
    assert gate_exit_status({"metadata": {"blocked": False}}) == 0
    assert gate_exit_status({"metadata": {"blocked": True}}) == 1


def test_threshold_constants_sensible():
    assert MAX_TASK_SUCCESS_DROP == 0.03
    assert MAX_AUTH_VIOLATION_DELTA == 0


def test_main_missing_dataset_exit_2(capsys):
    rc = main([
        "--dataset", "tests/data/nope.jsonl",
        "--baseline", "simulated",
        "--candidate", "simulated",
        "--output", "/tmp/agentops_should_not_exist.json",
    ])
    assert rc == 2


def test_main_writes_report(tmp_path, monkeypatch):
    out = tmp_path / "report.json"
    sim = _load_agent_fn("simulated")
    dataset = _load_dataset()
    report = run_comparative(
        baseline_fn=sim, candidate_fn=sim, dataset=dataset,
        baseline_version="v1", candidate_version="v2",
    )
    from app.services.retailops_eval import write_report
    write_report(report, str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["metadata"]["exit_status"] == 0
    assert "baseline" in data and "candidate" in data
