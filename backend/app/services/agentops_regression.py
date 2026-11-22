"""
AO-04: Reproduce regression & demonstrate go/no-go decision.

Runs an intentional, safe candidate regression against a versioned golden
dataset, collects two full run artifacts (baseline + candidate), identifies
the regression, performs recovery (rollback to baseline), and verifies the
fix. All artifacts are written to disk; no fake metrics, no production
claims. Evidence level: STAGING.

Usage:
  python -m app.services.agentops_regression \\
    --dataset tests/data/golden_retailops.jsonl \\
    --out-dir tests/data/agentops_regression
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.agentops_eval import (
    evaluate_retailops,
    run_comparative,
    write_report,
)


def _baseline_agent(query: str) -> dict[str, Any]:
    q = query.lower()
    if "mua" in q or "đặt hàng" in q:
        return {"outcome": "success", "tools": ["draft_order", "confirm_order"], "args": {}}
    if "hủy" in q or "cancel" in q:
        return {"outcome": "cancelled", "tools": ["cancel_order"], "args": {}}
    if "tồn kho" in q or "stock" in q:
        return {"outcome": "success", "tools": ["get_stock"], "args": {}}
    return {"outcome": "clarify", "tools": [], "args": {}}


def _regressed_agent(query: str) -> dict[str, Any]:
    """Candidate that drops task success: never confirms orders."""
    q = query.lower()
    if "mua" in q or "đặt hàng" in q:
        return {"outcome": "clarify", "tools": [], "args": {}}
    if "hủy" in q or "cancel" in q:
        return {"outcome": "cancelled", "tools": ["cancel_order"], "args": {}}
    if "tồn kho" in q or "stock" in q:
        return {"outcome": "success", "tools": ["get_stock"], "args": {}}
    return {"outcome": "clarify", "tools": [], "args": {}}


def _recovered_agent(query: str) -> dict[str, Any]:
    """Rollback: identical to baseline."""
    return _baseline_agent(query)


def _failure_investigation(candidate_report: dict[str, Any]) -> list[dict[str, Any]]:
    """Inspect per-case failures to identify the regression root cause."""
    investigated: list[dict[str, Any]] = []
    for case in candidate_report.get("per_case", []):
        if not case.get("success"):
            investigated.append(
                {
                    "case_id": case["id"],
                    "category": case.get("category"),
                    "expected": case.get("expected"),
                    "actual": case.get("actual"),
                    "likely_cause": (
                        "candidate never emits confirm_order for purchase queries"
                        if case.get("expected") == "success"
                        else "unexpected outcome"
                    ),
                }
            )
    return investigated


def run_regression_scenario(
    *,
    dataset: list[dict],
    out_dir: Path,
    baseline_version: str = "v1.0-baseline",
    candidate_version: str = "v1.1-candidate",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Run 1: baseline (known-good) ---
    baseline_report = evaluate_retailops(_baseline_agent, dataset)
    baseline_path = out_dir / "baseline_report.json"
    write_report(baseline_report, str(baseline_path))

    # --- Run 2: candidate (intentional, safe regression) ---
    candidate_report = evaluate_retailops(_regressed_agent, dataset)
    candidate_path = out_dir / "candidate_report.json"
    write_report(candidate_report, str(candidate_path))

    # --- Comparative + gate ---
    comparative = run_comparative(
        baseline_fn=_baseline_agent,
        candidate_fn=_regressed_agent,
        dataset=dataset,
        baseline_version=baseline_version,
        candidate_version=candidate_version,
    )
    comparative_path = out_dir / "comparative_report.json"
    write_report(comparative, str(comparative_path))

    blocked = comparative["metadata"]["blocked"]
    investigation = _failure_investigation(candidate_report)

    decision = {
        "scenario": "intentional_candidate_regression",
        "baseline_version": baseline_version,
        "candidate_version": candidate_version,
        "blocked": blocked,
        "decision": "NO-GO" if blocked else "GO",
        "reason": (
            "Candidate v1.1 regresses task success vs baseline v1.0; do not promote."
            if blocked
            else "Candidate meets baseline; safe to promote."
        ),
        "baseline_task_success_rate": baseline_report["task_success_rate"],
        "candidate_task_success_rate": candidate_report["task_success_rate"],
        "authorization_violations_delta": comparative["delta"][
            "authorization_violations"
        ],
        "failure_investigation": investigation,
        "artifacts": {
            "baseline": str(baseline_path),
            "candidate": str(candidate_path),
            "comparative": str(comparative_path),
        },
    }
    decision_path = out_dir / "go_no_go_decision.json"
    out_dir.joinpath("go_no_go_decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # --- Recovery: rollback candidate -> baseline, verify green ---
    recovered_report = evaluate_retailops(_recovered_agent, dataset)
    recovered_path = out_dir / "recovered_report.json"
    write_report(recovered_report, str(recovered_path))

    recovery_comparative = run_comparative(
        baseline_fn=_baseline_agent,
        candidate_fn=_recovered_agent,
        dataset=dataset,
        baseline_version=baseline_version,
        candidate_version="v1.0-baseline-rollback",
    )
    recovery_path = out_dir / "recovery_comparative.json"
    write_report(recovery_comparative, str(recovery_path))

    decision["recovery"] = {
        "rolled_back_to": baseline_version,
        "recovered_task_success_rate": recovered_report["task_success_rate"],
        "recovery_exit_status": recovery_comparative["metadata"]["exit_status"],
        "recovery_blocked": recovery_comparative["metadata"]["blocked"],
        "verification": "PASS"
        if recovery_comparative["metadata"]["exit_status"] == 0
        else "FAIL",
    }
    decision_path.write_text(
        json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return decision
