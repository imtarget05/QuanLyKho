"""P0-7 — `entrypoint.sh` KHÔNG gọi alembic (migration do ArgoCD PreSync Job),
vẫn start uvicorn thành công, exit 0.

Migration chạy riêng qua ArgoCD PreSync Job (infra/k8s/base/migration-job.yaml,
argocd.argoproj.io/hook: PreSync) trước khi Deployment rollout. Mỗi pod khởi
động KHÔNG tự chạy alembic để tránh race condition database lock khi HPA scale
lên nhiều pod cùng lúc.

Test chạy THẬT `backend/entrypoint.sh` với `alembic`/`uvicorn` giả (trong
thư mục tạm, đưa vào PATH), `APP_ENV=demo` để kiểm chứng **hành vi**:
- alembic KHÔNG được gọi (`alembic-called` KHÔNG tồn tại);
- log có "Skipping alembic upgrade head";
- uvicorn được start với `app.main:app`, exit 0.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENTRYPOINT = BACKEND_DIR / "entrypoint.sh"


def _make_fake_bin(tmp_path: Path, alembic_exit: int) -> tuple[Path, Path]:
    """Tạo thư mục bin giả với `alembic` (ghi marker `alembic-called`) và `uvicorn`."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "uvicorn-args.txt"
    alembic_called = tmp_path / "alembic-called"

    alembic = bindir / "alembic"
    alembic.write_text(
        "#!/bin/sh\n"
        f'touch "{alembic_called}"\n'
        f'echo "fake alembic called" >&2\n'
        f"exit {alembic_exit}\n",
        encoding="utf-8",
    )
    alembic.chmod(alembic.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    uvicorn = bindir / "uvicorn"
    uvicorn.write_text(
        "#!/bin/sh\n"
        f'echo "$@" > "{marker}"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    uvicorn.chmod(uvicorn.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir, marker


def _run_entrypoint(tmp_path: Path, alembic_exit: int, extra_env: dict | None = None):
    bindir, marker = _make_fake_bin(tmp_path, alembic_exit)
    env = {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
        "DATABASE_URL": "postgresql+psycopg2://fake:fake@127.0.0.1:5432/fake",
        # `entrypoint.sh` fail-fast khi thiếu `BANKOPS_SIGNING_KEY` ở
        # production/staging. Test này chỉ kiểm tra hành vi MIGRATION nên chạy
        # ở chế độ demo (biến môi trường được set tường minh, không phụ thuộc
        # môi trường CI).
        "APP_ENV": "demo",
    }
    env.update(extra_env or {})
    proc = subprocess.run(
        ["sh", str(ENTRYPOINT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    args = marker.read_text(encoding="utf-8") if marker.exists() else None
    return proc, args


def test_entrypoint_skips_alembic_and_starts_server(tmp_path):
    """P0-7: entrypoint KHÔNG gọi alembic, vẫn start uvicorn thành công, exit 0."""
    alembic_called = tmp_path / "alembic-called"
    proc, uvicorn_args = _run_entrypoint(tmp_path, alembic_exit=0)

    assert proc.returncode == 0, (
        f"entrypoint phải exit 0 khi bỏ qua alembic, thấy {proc.returncode}: "
        f"{proc.stdout}\n{proc.stderr}"
    )
    assert not alembic_called.exists(), (
        f"entrypoint KHÔNG được gọi alembic (P0-7), nhưng marker đã tạo: {alembic_called}"
    )
    assert uvicorn_args is not None, "entrypoint phải start uvicorn khi bỏ qua alembic"
    assert "app.main:app" in uvicorn_args, uvicorn_args
    assert "Skipping alembic upgrade head" in (proc.stdout + proc.stderr), (
        f"phải log 'Skipping alembic upgrade head', thấy: {proc.stdout}\n{proc.stderr}"
    )


def test_migration_success_starts_server(tmp_path):
    """Migration OK -> server được start (và script exit 0)."""
    proc, uvicorn_args = _run_entrypoint(tmp_path, alembic_exit=0)

    assert proc.returncode == 0, (
        f"entrypoint phải exit 0 khi migration thành công, thấy {proc.returncode}: "
        f"{proc.stdout}\n{proc.stderr}"
    )
    assert uvicorn_args is not None, "entrypoint phải start uvicorn khi migration OK"
    assert "app.main:app" in uvicorn_args, uvicorn_args


def test_uvicorn_receives_forwarded_allow_ips(tmp_path):
    """Reverse proxy: uvicorn phải được cấu hình proxy đáng tin.

    Mặc định chỉ tin loopback; deploy sau nginx/Cloudflare thì set
    `FORWARDED_ALLOW_IPS` -> uvicorn mới lấy IP client thật từ
    `X-Forwarded-For` (rate-limit theo IP không bị gộp về 1 IP).
    """
    proc, uvicorn_args = _run_entrypoint(tmp_path, alembic_exit=0)
    assert uvicorn_args is not None, proc.stderr
    assert "--forwarded-allow-ips" in uvicorn_args, uvicorn_args
    assert "127.0.0.1" in uvicorn_args, (
        f"mặc định chỉ tin proxy loopback, thấy: {uvicorn_args!r}"
    )


def test_uvicorn_uses_env_forwarded_allow_ips(tmp_path):
    """`FORWARDED_ALLOW_IPS` từ env được truyền vào uvicorn."""
    custom = tmp_path / "custom"
    custom.mkdir()
    proc, uvicorn_args = _run_entrypoint(
        custom, alembic_exit=0, extra_env={"FORWARDED_ALLOW_IPS": "10.0.0.7"}
    )
    assert proc.returncode == 0, proc.stderr
    assert uvicorn_args is not None, proc.stderr
    assert "--forwarded-allow-ips" in uvicorn_args, uvicorn_args
    assert "10.0.0.7" in uvicorn_args, (
        f"FORWARDED_ALLOW_IPS phải được truyền cho uvicorn, thấy: {uvicorn_args!r}"
    )


def test_missing_database_url_skips_migration_but_starts_server(tmp_path):
    """Không có DATABASE_URL -> bỏ qua migration nhưng vẫn start server."""
    bindir, marker = _make_fake_bin(tmp_path, alembic_exit=1)
    env = {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
        "APP_ENV": "demo",
    }
    env.pop("DATABASE_URL", None)
    proc = subprocess.run(
        ["sh", str(ENTRYPOINT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert marker.exists(), "phải start server khi không có DATABASE_URL"
