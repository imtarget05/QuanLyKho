#!/usr/bin/env python3
"""Pin image digest / SHA vào kustomize overlay cho GitOps đa repo.

Quy tắc:
- Chỉ viết vào `infra/k8s/overlays/*/kustomization.yaml`.
- Thay `newTag` thành giá trị digest `sha256:...` (dùng field `digest` của
  kustomize images) hoặc `newTag` sha nếu pipeline chưa hỗ trợ digest.
- Không đụng đến secret, không thay đổi replica / resource.
- Thoát 1 nếu không tìm thấy overlay hoặc file không hợp lệ.

Usage:

    python3 scripts/gitops-pin-overlay.py \
        --overlay overlays/production \
        --image ghcr.io/imtarget05/bankops-api \
        --digest sha256:0123...def
    python3 scripts/gitops-pin-overlay.py \
        --overlay overlays/production \
        --image ghcr.io/imtarget05/bankops-frontend \
        --tag v1.0.0-sha256abcd
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover - pyyaml là runtime dependency
    print(f"Thiếu dependency: {exc}. Chạy: pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[1]


def overlay_path(overlay: str) -> Path:
    return ROOT / "infra" / "k8s" / overlay / "kustomization.yaml"


def load_overlay(path: Path) -> dict:
    if not path.is_file():
        print(f"Không tìm thấy overlay kustomization: {path}", file=sys.stderr)
        raise SystemExit(1)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if data.get("kind") != "Kustomization":
        print(f"File không phải Kustomization: {path}", file=sys.stderr)
        raise SystemExit(1)
    return data


def save_overlay(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def pin_image(data: dict, image: str, digest: str | None, tag: str | None) -> bool:
    images = data.setdefault("images", [])
    matched = False
    for entry in images:
        if entry.get("name") == image:
            matched = True
            if digest is not None:
                entry["digest"] = digest
                entry.pop("newTag", None)
            elif tag is not None:
                entry["newTag"] = tag
                entry.pop("digest", None)
            entry.setdefault("newName", image)
    if not matched:
        entry: dict = {"name": image, "newName": image}
        if digest is not None:
            entry["digest"] = digest
        elif tag is not None:
            entry["newTag"] = tag
        images.append(entry)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay", required=True, help="overlay tương đối, vd overlays/production")
    parser.add_argument("--image", required=True, help="tên image cần pin (không tag/digest)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--digest", help="digest sha256:... (digest-pinned)")
    group.add_argument("--tag", help="tag SHA (fallback khi chưa hỗ trợ digest)")
    args = parser.parse_args(argv)

    path = overlay_path(args.overlay)
    data = load_overlay(path)
    pin_image(data, args.image, args.digest, args.tag)
    save_overlay(path, data)
    print(f"Đã pin {args.image} vào {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
