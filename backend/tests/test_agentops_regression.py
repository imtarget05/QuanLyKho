"""AO-04: Reproduce regression & demonstrate go/no-go (offline tests)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.agentops_regression import run_regression_scenario
from app.services.retailops_eval import load_golden_dataset

DATASET = Path(__file__).resolve().parent / "data" / "golden_retailops.jsonl"


def test_regression_scenario_produces_go_no_go(tmp_path):
    dataset = load_golden_dataset(DATASET)
    decision = run_regression_scenario(
        dataset=dataset, out_dir=tmp_path / "regression"
    )

    assert decision["blocked"] is True
    assert decision["decision"] == "NO-GO"
    assert decision["candidate_task_success_rate"] < decision["baseline_task_success_rate"]
    assert decision["authorization_violations_delta"] >= 0

    # Two full run artifacts + comparative + decision
    for name in ["baseline_report.json", "candidate_report.json", "comparative_report.json", "go_no_go_decision.json"]:
        assert (tmp_path / "regression" / name).exists(), name

    decision_data = json.loads(
        (tmp_path / "regression" / "go_no_go_decision.json").read_text(encoding="utf-8")
    )
    assert decision_data["decision"] == "NO-GO"
    assert len(decision_data["failure_investigation"]) > 0
    assert decision_data["failure_investigation"][0]["likely_cause"]


def test_recovery_rollback_verifies_green(tmp_path):
    dataset = load_golden_dataset(DATASET)
    run_regression_scenario(dataset=dataset, out_dir=tmp_path / "regression")

    rec_dir = tmp_path / "regression"
    for name in ["recovered_report.json", "recovery_comparative.json"]:
        assert (rec_dir / name).exists(), name

    decision = json.loads(
        (rec_dir / "go_no_go_decision.json").read_text(encoding="utf-8")
    )
    rec = decision["recovery"]
    assert rec["rolled_back_to"] == "v1.0-baseline"
    assert rec["recovery_exit_status"] == 0
    assert rec["recovery_blocked"] is False
    assert rec["verification"] == "PASS"
    assert rec["recovered_task_success_rate"] == decision["baseline_task_success_rate"]
