"""Model registry đơn giản (Option B — AI/MLOps).

Quản lý vòng đời model: register phiên bản mới, gán alias (staging / production),
promote staging -> production, lấy latest theo alias. Lưu trạng thái trong file
JSON duy nhất (registry.json) để không phụ thuộc dịch vụ bên ngoài; có thể
thay thế bằng MLflow Model Registry sau khi triển khai thật.

Mỗi phiên bản model lưu:
  - version: chuỗi (vd "v1.2.3", "20261114-01")
  - artifact_uri: URI tới artifact (model adapter, checkpoint)
  - sha256: checksum không thay đổi của artifact
  - metrics: {tên: giá trị} (retrieval_accuracy, answer_correctness, ...)
  - created_at: timestamp ISO-8601
  - alias: staging | production | archived
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ModelVersion:
    version: str
    artifact_uri: str
    sha256: str
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: str = ""
    alias: str = "staging"  # staging | production | archived
    source: str = "airflow-retrain"  # airflow-retrain | manual | finetune

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelRegistry:
    def __init__(self, registry_path: str | os.PathLike[str] = "model_registry.json"):
        self.path = Path(registry_path)
        self._versions: list[ModelVersion] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._versions = [ModelVersion(**v) for v in data.get("versions", [])]
            except Exception:  # pragma: no cover -- file hỏng, bắt đầu lại  # noqa: BLE001
                self._versions = []
        else:
            self._versions = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {"versions": [v.to_dict() for v in self._versions]}
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def register(
        self,
        version: str,
        artifact_uri: str,
        sha256: str,
        *,
        metrics: dict[str, float] | None = None,
        source: str = "airflow-retrain",
    ) -> ModelVersion:
        """Đăng ký một phiên bản model mới (mặc định alias = staging)."""
        mv = ModelVersion(
            version=version,
            artifact_uri=artifact_uri,
            sha256=sha256,
            metrics=metrics or {},
            source=source,
        )
        # Không cho phép trùng version
        if any(v.version == version for v in self._versions):
            raise ValueError(f"Model version already registered: {version}")
        self._versions.append(mv)
        self._save()
        return mv

    def list_versions(self, alias: str | None = None) -> list[ModelVersion]:
        if alias is None:
            return list(self._versions)
        return [v for v in self._versions if v.alias == alias]

    def get_latest(self, alias: str = "production") -> ModelVersion | None:
        versions = self.list_versions(alias)
        if not versions:
            return None
        return max(versions, key=lambda v: v.created_at or "")

    def promote(self, version: str, alias: str) -> ModelVersion:
        """Thay đổi alias của một phiên bản (staging -> production, v.v.)."""
        for v in self._versions:
            if v.version == version:
                v.alias = alias
                self._save()
                return v
        raise KeyError(f"Model version not found: {version}")

    def archive(self, version: str) -> ModelVersion:
        return self.promote(version, "archived")

    def production_ready(self, version: str, quality_gate: dict[str, float]) -> bool:
        """Kiểm tra phiên bản đạt chất lượng production hay không."""
        for v in self._versions:
            if v.version == version:
                for metric, threshold in quality_gate.items():
                    actual = v.metrics.get(metric)
                    if actual is None:
                        return False
                    if metric.endswith("_rate") or metric == "error_rate":
                        if actual > threshold:
                            return False
                    else:
                        if actual < threshold:
                            return False
                return True
        return False


def load_registry(registry_path: str | os.PathLike[str] = "model_registry.json") -> ModelRegistry:
    return ModelRegistry(registry_path)
