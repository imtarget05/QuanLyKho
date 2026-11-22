"""
AO-03: Traces & quality/cost dashboards via existing tooling.

Aggregates staging trace artifacts (AO-01) and comparative eval reports (AO-02)
into a simple dashboard (JSON + static HTML). No new SaaS/UI product — this is
a thin read-only view over existing traces, consistent with ADR-007 (use
existing tooling first).

Drilldown: each trace row links to its sanitized trace artifact file so an
operator can go from a metric (e.g. high latency) to the exact trace.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TRACE_GLOB = "agentops_staging_trace_*.json"
REPORT_GLOB = "agentops_comparative_report.json"


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _latency(envelope: dict[str, Any]) -> float:
    return float(envelope.get("latency_ms") or 0.0)


def build_dashboard(trace_dir: Path) -> dict[str, Any]:
    trace_files = sorted(trace_dir.glob(TRACE_GLOB))
    traces: list[dict[str, Any]] = []
    for fp in trace_files:
        env = _load_json(fp)
        if not env:
            continue
        traces.append(
            {
                "trace_id": env.get("trace_id"),
                "app": env.get("app"),
                "task_type": env.get("task_type"),
                "status": env.get("status"),
                "latency_ms": _latency(env),
                "artifact": fp.name,
                "redacted_fields": env.get("redacted_fields", []),
                "started_at": env.get("started_at"),
            }
        )

    by_app: dict[str, dict[str, Any]] = {}
    total_latency = 0.0
    total_cost = 0.0
    auth_violations = 0
    error_count = 0
    for t in traces:
        app = t["app"] or "unknown"
        by_app.setdefault(app, {"count": 0, "avg_latency_ms": 0.0, "total_cost_usd": 0.0})
        by_app[app]["count"] += 1
        total_latency += t["latency_ms"]
        cost = 0.0
        try:
            env = _load_json(trace_dir / t["artifact"])
            scoring = env.get("scoring") or {}
            cost = float(scoring.get("cost_usd") or 0.0)
            auth_violations += int(scoring.get("authorization_violations") or 0)
        except Exception:
            pass
        total_cost += cost
        by_app[app]["total_cost_usd"] += cost
        if t["status"] in ("error", "blocked"):
            error_count += 1

    n = len(traces)
    avg_latency = round(total_latency / n, 2) if n else 0.0
    for app in by_app.values():
        app["avg_latency_ms"] = round(app["avg_latency_ms"] / max(1, app["count"]), 2)

    # Comparative eval reports
    comparisons: list[dict[str, Any]] = []
    for rp in trace_dir.glob(REPORT_GLOB):
        rep = _load_json(rp)
        if rep:
            comparisons.append(
                {
                    "file": rp.name,
                    "baseline": rep.get("metadata", {}).get("baseline_version"),
                    "candidate": rep.get("metadata", {}).get("candidate_version"),
                    "exit_status": rep.get("metadata", {}).get("exit_status"),
                    "blocked": rep.get("metadata", {}).get("blocked"),
                    "delta_task_success": rep.get("delta", {}).get("task_success_rate"),
                    "delta_auth_violations": rep.get("delta", {}).get(
                        "authorization_violations"
                    ),
                }
            )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "trace_dir": str(trace_dir),
        "summary": {
            "total_traces": n,
            "avg_latency_ms": avg_latency,
            "total_cost_usd": round(total_cost, 4),
            "authorization_violations": auth_violations,
            "error_traces": error_count,
            "by_app": by_app,
        },
        "traces": traces,
        "comparisons": comparisons,
    }


def write_dashboard(dashboard: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8")


def dashboard_html(dashboard: dict[str, Any]) -> str:
    s = dashboard["summary"]
    rows = ""
    for t in dashboard["traces"]:
        rows += (
            "<tr>"
            f"<td><a href='{t['artifact']}' target='_blank'>{t['trace_id']}</a></td>"
            f"<td>{t['app']}</td>"
            f"<td>{t['task_type']}</td>"
            f"<td>{t['status']}</td>"
            f"<td>{t['latency_ms']} ms</td>"
            f"<td>{', '.join(t['redacted_fields']) or '—'}</td>"
            "</tr>"
        )
    comp_rows = ""
    for c in dashboard["comparisons"]:
        comp_rows += (
            "<tr>"
            f"<td>{c['baseline']} → {c['candidate']}</td>"
            f"<td>{c['exit_status']}</td>"
            f"<td>{'BLOCKED' if c['blocked'] else 'ok'}</td>"
            f"<td>{c['delta_task_success']}</td>"
            f"<td>{c['delta_auth_violations']}</td>"
            "</tr>"
        )
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><title>AgentOps Dashboard</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;padding:24px;background:#f8fafc;color:#0f172a}}
h2{{font-size:20px;margin-top:0}}table{{border-collapse:collapse;width:100%;margin-top:12px}}
th,td{{border:1px solid #cbd5e1;padding:8px;text-align:left;font-size:13px}}
th{{background:#e2e8f0}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px}}
.card{{background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:14px}}
.big{{font-size:26px;font-weight:700;color:#0f172a}} .cap{{font-size:12px;color:#64748b}}
.ok{{color:#15803d}}.bad{{color:#b91c1c}}</style></head><body>
<h1>AgentOps Dashboard</h1>
<div class="grid">
  <div class="card"><div class="cap">Tổng trace</div><div class="big">{s['total_traces']}</div></div>
  <div class="card"><div class="cap">Trung bình latency</div><div class="big">{s['avg_latency_ms']} ms</div></div>
  <div class="card"><div class="cap">Tổng chi phí ước tính</div><div class="big">${s['total_cost_usd']}</div></div>
  <div class="card"><div class="cap">Vi phạm phân quyền</div><div class="big {'bad' if s['authorization_violations'] else 'ok'}">{s['authorization_violations']}</div></div>
  <div class="card"><div class="cap">Trace lỗi/chặn</div><div class="big {'bad' if s['error_traces'] else 'ok'}">{s['error_traces']}</div></div>
</div>
<h2>Theo ứng dụng</h2>
<table><tr><th>Ứng dụng</th><th>Số trace</th><th>TB latency</th><th>Chi phí</th></tr>
{"".join(f"<tr><td>{a}</td><td>{d['count']}</td><td>{d['avg_latency_ms']} ms</td><td>${d['total_cost_usd']}</td></tr>" for a,d in s['by_app'].items())}
</table>
<h2>Traces (nhấn trace_id để xem chi tiết đã scrubbed)</h2>
<table><tr><th>Trace ID</th><th>Ứng dụng</th><th>Loại tác vụ</th><th>Trạng thái</th><th>Latency</th><th>Đã ẩn</th></tr>{rows}</table>
<h2>So sánh đánh giá (AO-02)</h2>
<table><tr><th>Baseline → Ứng viên</th><th>Exit status</th><th>Kết quả</th><th>Δ task_success</th><th>Δ auth_violation</th></tr>{comp_rows}</table>
<p><small>Tạo lúc {dashboard['generated_at']}. Tất cả trace đã được scrubbed (PII đã ẩn).</small></p>
</body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AgentOps dashboard (AO-03)")
    parser.add_argument("--trace-dir", default="tests/data", help="Directory with staging trace artifacts")
    parser.add_argument("--output", default="tests/data/agentops_dashboard.json", help="Output dashboard JSON path")
    parser.add_argument("--html", action="store_true", help="Also write an HTML view next to the JSON output")
    args = parser.parse_args(argv)

    trace_dir = Path(args.trace_dir)
    if not trace_dir.is_dir():
        print(f"ERROR: trace dir not found: {trace_dir}", file=sys.stderr)
        return 2

    dashboard = build_dashboard(trace_dir)
    out = Path(args.output)
    write_dashboard(dashboard, out)
    print(f"AO-03 dashboard: {dashboard['summary']['total_traces']} traces -> {out}")

    if args.html:
        html_path = out.with_suffix(".html")
        html_path.write_text(dashboard_html(dashboard), encoding="utf-8")
        print(f"AO-03 HTML dashboard -> {html_path}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
