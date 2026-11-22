"""RetailOps agent evaluation harness (RO-04).

Loads the golden workflow dataset (JSONL) and scores an agent run by:
- task_success: expected outcome == actual outcome
- tool_selection_accuracy: expected tools subset of actual tools
- argument_validity: all required args present
- authorization_violations: count of forbidden/cross-tenant leaks

STATUS must be recorded as SIMULATED unless run against a real model + integrated tools.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

AgentFn = Callable[[str], dict[str, Any]]


def load_golden_dataset(path: str | Path) -> list[dict]:
    path = Path(path)
    entries: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def evaluate_retailops(agent_fn: AgentFn, dataset: list[dict]) -> dict:
    per_case: list[dict] = []
    success = 0
    tool_hits = 0
    arg_ok = 0
    tool_scored = 0
    arg_scored = 0
    auth_violations = 0

    for case in dataset:
        result = agent_fn(case["query"])
        actual = result.get("outcome", "unknown")
        expected = case.get("expected", "")
        case_success = actual == expected
        if case_success:
            success += 1

        expected_tools = set(case.get("metadata", {}).get("expected_tools", []))
        actual_tools = set(result.get("tools", []))
        tool_ok = None
        if expected_tools:
            tool_scored += 1
            tool_ok = expected_tools.issubset(actual_tools)
            if tool_ok:
                tool_hits += 1

        required_args = case.get("metadata", {}).get("required_args", [])
        args = result.get("args", {})
        arg_valid = None
        if required_args:
            arg_scored += 1
            arg_valid = all(k in args for k in required_args)
            if arg_valid:
                arg_ok += 1

        if result.get("authorization_violation"):
            auth_violations += 1

        per_case.append({
            "id": case["id"],
            "category": case.get("category"),
            "expected": expected,
            "actual": actual,
            "success": case_success,
            "tool_ok": tool_ok,
            "arg_ok": arg_valid,
        })

    n = len(dataset) or 1
    return {
        "total_cases": len(dataset),
        "task_success_rate": success / n,
        "task_success_count": success,
        "tool_selection_accuracy": tool_hits / tool_scored if tool_scored else None,
        "tool_scored_cases": tool_scored,
        "argument_validity_rate": arg_ok / arg_scored if arg_scored else None,
        "argument_scored_cases": arg_scored,
        "evaluation_scope": "scenario_label_match_without_backend_execution",
        "authorization_violations": auth_violations,
        "per_case": per_case,
    }


def write_report(report: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
