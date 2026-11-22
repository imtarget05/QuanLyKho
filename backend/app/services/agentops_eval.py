"""
AO-02: Evaluation runner + CI regression gate.

Connects versioned golden datasets, runs baseline vs candidate agent functions,
produces a comparative report with exit status and artifact export. Hard
blockers (authorization violations, missing dataset/credentials) yield a
non-zero exit status — never a false green.

Usage:
  python -m app.services.agentops_eval \\
    --dataset tests/data/golden_retailops.jsonl \\
    --baseline simulated --candidate simulated \\
    --output tests/data/agentops_comparative_report.json
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

from app.services.retailops_eval import (
    AgentFn,
    evaluate_retailops,
    load_golden_dataset,
    write_report,
)

# Regression thresholds (hard blockers first).
MAX_TASK_SUCCESS_DROP = 0.03  # 3 percentage points
MAX_AUTH_VIOLATION_DELTA = 0  # any new auth violation is a hard block


def _load_agent_fn(spec: str) -> AgentFn:
    """
    Resolve an agent function from a ``module:function`` spec, or return a
    deterministic simulation when spec == "simulated".
    """
    if spec == "simulated":
        def _sim(query: str) -> dict[str, Any]:
            q = query.lower()
            if "mua" in q or "đặt hàng" in q:
                return {"outcome": "success", "tools": ["draft_order", "confirm_order"], "args": {}}
            if "hủy" in q or "cancel" in q:
                return {"outcome": "cancelled", "tools": ["cancel_order"], "args": {}}
            if "tồn kho" in q or "stock" in q:
                return {"outcome": "success", "tools": ["get_stock"], "args": {}}
            return {"outcome": "clarify", "tools": [], "args": {}}
        return _sim
    if ":" not in spec:
        raise ValueError(f"Invalid agent spec '{spec}': use module:function")
    mod_name, fn_name = spec.split(":", 1)
    mod = importlib.import_module(mod_name)
    return getattr(mod, fn_name)


def run_comparative(
    *,
    baseline_fn: AgentFn,
    candidate_fn: AgentFn,
    dataset: list[dict],
    baseline_version: str = "baseline",
    candidate_version: str = "candidate",
) -> dict[str, Any]:
    """Run baseline + candidate on the same dataset and compare."""
    baseline = evaluate_retailops(baseline_fn, dataset)
    candidate = evaluate_retailops(candidate_fn, dataset)

    task_drop = baseline["task_success_rate"] - candidate["task_success_rate"]
    auth_delta = candidate["authorization_violations"] - baseline["authorization_violations"]

    blockers: list[str] = []
    if auth_delta > MAX_AUTH_VIOLATION_DELTA:
        blockers.append(
            f"authorization violations increased {baseline['authorization_violations']} "
            f"-> {candidate['authorization_violations']}"
        )
    if task_drop > MAX_TASK_SUCCESS_DROP:
        blockers.append(
            f"task success dropped {baseline['task_success_rate']:.2%} "
            f"-> {candidate['task_success_rate']:.2%} (drop {task_drop:.2%})"
        )

    blocked = len(blockers) > 0
    exit_status = 1 if blocked else 0

    return {
        "metadata": {
            "baseline_version": baseline_version,
            "candidate_version": candidate_version,
            "dataset_cases": len(dataset),
            "exit_status": exit_status,
            "blocked": blocked,
            "blockers": blockers,
            "max_task_success_drop": MAX_TASK_SUCCESS_DROP,
            "max_auth_violation_delta": MAX_AUTH_VIOLATION_DELTA,
        },
        "baseline": baseline,
        "candidate": candidate,
        "delta": {
            "task_success_rate": round(candidate["task_success_rate"] - baseline["task_success_rate"], 4),
            "tool_selection_accuracy": _safe_delta(
                baseline["tool_selection_accuracy"], candidate["tool_selection_accuracy"]
            ),
            "argument_validity_rate": _safe_delta(
                baseline["argument_validity_rate"], candidate["argument_validity_rate"]
            ),
            "authorization_violations": auth_delta,
        },
    }


def _safe_delta(a: Any, b: Any) -> Any:
    if a is None or b is None:
        return None
    return round(b - a, 4)


def gate_exit_status(report: dict[str, Any]) -> int:
    return 1 if report["metadata"]["blocked"] else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AgentOps comparative evaluation gate (AO-02)")
    parser.add_argument("--dataset", required=True, help="Path to golden dataset JSONL")
    parser.add_argument(
        "--baseline", required=True, help="Baseline agent spec: module:function or 'simulated'"
    )
    parser.add_argument(
        "--candidate", required=True, help="Candidate agent spec: module:function or 'simulated'"
    )
    parser.add_argument(
        "--output", required=True, help="Path to write comparative report JSON"
    )
    parser.add_argument(
        "--baseline-version", default="baseline", help="Baseline version label"
    )
    parser.add_argument(
        "--candidate-version", default="candidate", help="Candidate version label"
    )
    args = parser.parse_args(argv)

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"ERROR: dataset not found: {dataset_path}", file=sys.stderr)
        return 2

    dataset = load_golden_dataset(str(dataset_path))

    baseline_fn = _load_agent_fn(args.baseline)
    candidate_fn = _load_agent_fn(args.candidate)

    report = run_comparative(
        baseline_fn=baseline_fn,
        candidate_fn=candidate_fn,
        dataset=dataset,
        baseline_version=args.baseline_version,
        candidate_version=args.candidate_version,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(report, str(out_path))

    meta = report["metadata"]
    print(
        f"AO-02 gate: baseline={meta['baseline_version']} "
        f"candidate={meta['candidate_version']} "
        f"exit_status={meta['exit_status']} "
        f"blocked={meta['blocked']}"
    )
    if meta["blockers"]:
        for b in meta["blockers"]:
            print(f"  BLOCKER: {b}", file=sys.stderr)
    return meta["exit_status"]


if __name__ == "__main__":
    raise SystemExit(main())
