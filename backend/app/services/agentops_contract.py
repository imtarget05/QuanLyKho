"""
AgentOps telemetry contract (AO-01).

Defines the unified trace envelope, version fields, dataset/scoring contract,
and trace scrubbing (PII redaction). All functions are deterministic and
offline-safe: they never call Langfuse/OTLP and never write secrets.

Implemented on top of existing QuanLyKho tooling:
  - app/api/telemetry.py  (OpenTelemetry tracer/meter providers, version field)
  - app/core/observability.py (mask_sensitive_data, fail-safe Langfuse client)

Evidence level: STAGING (local artifacts; no live Langfuse/OTLP claim).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.observability import mask_sensitive_data

APP_VERSION = "dev"

# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------
def make_trace_id() -> str:
    return f"tr-{uuid.uuid4().hex}"


def make_span_id() -> str:
    return f"sp-{uuid.uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _pseudonymize(value: str | None) -> str | None:
    if value is None:
        return None
    return "user-" + hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------
class Span(dict):
    """A single traced operation with scrubbed input/output."""

    def __init__(
        self,
        name: str,
        *,
        input: Any = None,
        output: Any = None,
        status: str = "ok",
        latency_ms: float | None = None,
    ):
        super().__init__(
            {
                "span_id": make_span_id(),
                "name": name,
                "started_at": _now_iso(),
                "ended_at": _now_iso(),
                "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
                "status": status,
                "input": mask_sensitive_data(input),
                "output": mask_sensitive_data(output),
            }
        )

    def finish(self, output: Any = None, status: str = "ok") -> None:
        self["ended_at"] = _now_iso()
        if output is not None:
            self["output"] = mask_sensitive_data(output)
        self["status"] = status


# ---------------------------------------------------------------------------
# Trace envelope
# ---------------------------------------------------------------------------
class TraceEnvelope(dict):
    """
    Unified trace envelope for AO-01.

    Version fields (dataset_version, prompt_version, model_version,
    scoring_version) make every trace comparable across runs so CI can
    detect regressions (AO-02).
    """

    def __init__(
        self,
        *,
        app: str,
        task_type: str,
        dataset_version: str = "v1",
        prompt_version: str = "v1",
        model_version: str = "none",
        scoring_version: str = "v1",
        environment: str = "demo",
        tenant_id: str | None = None,
        user_id: str | None = None,
    ):
        tid = make_trace_id()
        super().__init__(
            {
                "trace_id": tid,
                "span_id": make_span_id(),
                "app": app,
                "task_type": task_type,
                "dataset_version": dataset_version,
                "prompt_version": prompt_version,
                "model_version": model_version,
                "scoring_version": scoring_version,
                "environment": environment,
                "tenant_id": _pseudonymize(tenant_id),
                "user_id": _pseudonymize(user_id),
                "started_at": _now_iso(),
                "ended_at": None,
                "latency_ms": None,
                "status": "running",
                "spans": [],
                "result": None,
                "scoring": None,
                "redacted_fields": [],
            }
        )

    def add_span(self, span: Span) -> None:
        self["spans"].append(dict(span))

    def finish(
        self,
        *,
        status: str = "ok",
        result: Any = None,
        scoring: dict[str, Any] | None = None,
    ) -> None:
        self["ended_at"] = _now_iso()
        self["status"] = status
        self["result"] = mask_sensitive_data(result)
        self["scoring"] = scoring
        try:
            started = datetime.fromisoformat(self["started_at"])
            ended = datetime.fromisoformat(self["ended_at"])
            self["latency_ms"] = round((ended - started).total_seconds() * 1000, 2)
        except Exception:
            self["latency_ms"] = None


def validate_trace(envelope: dict[str, Any]) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors: list[str] = []
    required = [
        "trace_id", "span_id", "app", "task_type", "dataset_version",
        "prompt_version", "model_version", "scoring_version",
        "environment", "started_at", "status", "spans",
    ]
    for field in required:
        if field not in envelope:
            errors.append(f"missing field: {field}")
    if envelope.get("app") not in ("retailops", "knowledge"):
        errors.append("invalid app")
    if envelope.get("status") not in (
        "running",
        "ok",
        "interrupted",
        "error",
        "blocked",
        "abstain",
        "out_of_domain",
        "forbidden",
    ):
        errors.append("invalid status")
    if not isinstance(envelope.get("spans"), list):
        errors.append("spans must be a list")
    return errors


def redact_trace_fields(envelope: dict[str, Any]) -> list[str]:
    """
    Scan envelope result/input/output for remaining sensitive patterns and
    return the list of redacted field paths. Idempotent.
    """
    redacted: list[str] = []
    sensitive = {"password", "secret", "pin", "token", "authorization", "api_key"}

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else k
                if any(s in str(k).lower() for s in sensitive):
                    redacted.append(p)
                walk(v, p)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(envelope.get("result", {}), "result")
    for span in envelope.get("spans", []):
        walk(span.get("input", {}), "spans[].input")
        walk(span.get("output", {}), "spans[].output")
    return sorted(set(redacted))


def scoring_contract(
    *,
    task_completion: bool,
    tool_calls: int,
    tool_successes: int,
    authorization_violations: int,
    latency_ms: float,
    cost_usd: float | None = None,
) -> dict[str, Any]:
    """Standard AO-01 scoring block for a single trace."""
    total = tool_calls or 1
    return {
        "task_completion": task_completion,
        "task_completion_rate": 1.0 if task_completion else 0.0,
        "tool_selection_accuracy": round(tool_successes / total, 4),
        "authorization_violations": authorization_violations,
        "latency_ms": round(latency_ms, 2),
        "cost_usd": cost_usd,
        "scoring_version": "v1",
    }


def write_trace(envelope: dict[str, Any], path: str) -> None:
    """Write a sanitized trace artifact to disk (staging artifact)."""
    errors = validate_trace(envelope)
    if errors:
        raise ValueError(
            f"Invalid trace envelope (status={envelope.get('status')!r}): {errors}"
        )
    redacted = redact_trace_fields(envelope)
    envelope["redacted_fields"] = redacted
    with open(path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2, ensure_ascii=False)
