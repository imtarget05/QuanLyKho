"""Model drift detection (PSI / KS) cho Option B — AI/MLOps.

Tính toán độ chênh lệch phân phối giữa tập tham chiếu (reference, training) và
tập hiện tại (current, production/inference) để phát hiện data drift và kích
off retraining.

Các chỉ số:
  - PSI (Population Stability Index) cho biến phân loại / bucketed.
  - KS (Kolmogorov-Smirnov) cho biến liên tục.

Không phụ thuộc thư viện ML nặng — chỉ dùng stdlib + numpy (nếu có), chạy được
trong Airflow task hoặc CI gate.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # numpy là optional; fallback pure-python khi không có
    import numpy as np  # type: ignore[import]
except Exception:  # pragma: no cover -- optional dependency  # noqa: BLE001
    np = None  # type: ignore[assignment]

_EPS = 1e-6


def _histogram(values: Sequence[float], buckets: Sequence[float]) -> list[int]:
    """Đếm số giá trị rơi vào từng bucket (bucket[i] là ranh giới trên)."""
    counts = [0] * len(buckets)
    for v in values:
        placed = False
        for i, b in enumerate(buckets):
            if v <= b:
                counts[i] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1
    return counts


def _quantile_buckets(values: Sequence[float], n_buckets: int = 10) -> list[float]:
    """Tính ranh giới bucket từ phân vị của tập tham chiếu."""
    if np is not None:
        qs = [100.0 * i / n_buckets for i in range(1, n_buckets)]
        return [float(q) for q in np.quantile(values, [q / 100.0 for q in qs])]  # type: ignore[union-attr]
    # Pure-python xấp xỉ phân vị (linear interpolation)
    s = sorted(values)
    n = len(s)
    edges: list[float] = []
    for i in range(1, n_buckets):
        pos = (n - 1) * i / n_buckets
        lo = math.floor(pos)
        hi = math.ceil(pos)
        frac = pos - lo
        edges.append(s[lo] + frac * (s[hi] - s[lo]) if lo != hi else s[lo])
    return edges


def population_stability_index(
    reference: Iterable[float],
    current: Iterable[float],
    n_buckets: int = 10,
) -> float:
    """Population Stability Index (PSI).

    PSI < 0.1 : không có ý nghĩa (stable)
    0.1 <= PSI < 0.2 : mức trung bình (moderate)
    PSI >= 0.2 : drift rõ rệt (significant)
    """
    ref = list(reference)
    cur = list(current)
    if not ref or not cur:
        return 0.0
    buckets = _quantile_buckets(ref, n_buckets)
    ref_counts = _histogram(ref, buckets)
    cur_counts = _histogram(cur, buckets)

    psi = 0.0
    for r, c in zip(ref_counts, cur_counts):
        r_pct = max(r, 1) / len(ref)
        c_pct = max(c, 1) / len(cur)
        psi += (c_pct - r_pct) * math.log(c_pct / r_pct)
    return psi


def _ecdf(values: Sequence[float]):
    s = sorted(values)
    n = len(s)

    def cdf(x: float) -> float:
        # số phần tử <= x (binary search)
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if s[mid] <= x:
                lo = mid + 1
            else:
                hi = mid
        return lo / n

    return cdf


def kolmogorov_smirnov_statistic(
    reference: Iterable[float], current: Iterable[float]
) -> float:
    """KS statistic = max khoảng cách giữa hai hàm phân phối thực nghiệm."""
    ref = list(reference)
    cur = list(current)
    if not ref or not cur:
        return 0.0
    ref_cdf = _ecdf(ref)
    cur_cdf = _ecdf(cur)
    points = sorted(set(ref) | set(cur))
    return max(abs(ref_cdf(x) - cur_cdf(x)) for x in points)


@dataclass
class DriftResult:
    feature: str
    psi: float | None
    ks: float | None
    drift_detected: bool
    psi_threshold: float
    ks_threshold: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "psi": self.psi,
            "ks": self.ks,
            "drift_detected": self.drift_detected,
            "psi_threshold": self.psi_threshold,
            "ks_threshold": self.ks_threshold,
        }


def detect_drift(
    reference: dict[str, Sequence[float]],
    current: dict[str, Sequence[float]],
    *,
    psi_threshold: float = 0.2,
    ks_threshold: float = 0.2,
    n_buckets: int = 10,
) -> dict[str, DriftResult]:
    """Chạy drift detection cho từng đặc trưng chung giữa reference và current."""
    results: dict[str, DriftResult] = {}
    for feature, ref_vals in reference.items():
        cur_vals = current.get(feature)
        if cur_vals is None:
            continue
        ref_list = list(ref_vals)
        cur_list = list(cur_vals)
        try:  # pragma: no cover -- defensive math
            psi = population_stability_index(ref_list, cur_list, n_buckets)
        except Exception:  # pragma: no cover -- graceful degradation  # noqa: BLE001
            psi = None
        try:  # pragma: no cover -- defensive math
            ks = kolmogorov_smirnov_statistic(ref_list, cur_list)
        except Exception:  # pragma: no cover -- graceful degradation  # noqa: BLE001
            ks = None
        drift = False
        if psi is not None and psi >= psi_threshold:
            drift = True
        if ks is not None and ks >= ks_threshold:
            drift = True
        results[feature] = DriftResult(
            feature=feature,
            psi=psi,
            ks=ks,
            drift_detected=drift,
            psi_threshold=psi_threshold,
            ks_threshold=ks_threshold,
        )
    return results


def write_report(results: dict[str, DriftResult], path: str | Path) -> None:
    """Ghi báo cáo drift ra JSON."""
    report: dict[str, Any] = {
        "drift_detected_any": any(r.drift_detected for r in results.values()),
        "features": {name: r.to_dict() for name, r in results.items()},
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Detect model data drift (PSI/KS).")
    parser.add_argument("--reference", required=True, help="JSON: {feature: [values]}")
    parser.add_argument("--current", required=True, help="JSON: {feature: [values]}")
    parser.add_argument("--output", default="drift_report.json")
    parser.add_argument("--psi-threshold", type=float, default=0.2)
    parser.add_argument("--ks-threshold", type=float, default=0.2)
    args = parser.parse_args(argv)

    with open(args.reference, encoding="utf-8") as f:
        reference = json.load(f)
    with open(args.current, encoding="utf-8") as f:
        current = json.load(f)

    results = detect_drift(
        reference,
        current,
        psi_threshold=args.psi_threshold,
        ks_threshold=args.ks_threshold,
    )
    write_report(results, args.output)

    any_drift = any(r.drift_detected for r in results.values())
    print(json.dumps(
        {
            "drift_detected_any": any_drift,
            "features": {name: r.to_dict() for name, r in results.items()},
        },
        indent=2,
    ))
    return 1 if any_drift else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
