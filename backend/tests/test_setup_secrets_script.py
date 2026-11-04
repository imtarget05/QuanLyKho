"""`scripts/setup_secrets_and_deploy.sh` phải ghi ĐỦ key chuẩn và KHÔNG ghi đè
file khi còn thiếu biến bắt buộc.

Residual (wave inventory §4 + đề mục #14/#15 của bảng "còn lại cần owner"):
- script chỉ ghi `SECRET_KEY` (tên legacy) + `SUPERVISOR_PIN` => file sinh ra
  thiếu `BANKOPS_SIGNING_KEY` / `BANKOPS_SESSION_SECRET` / `SMTP_USER` /
  `SMTP_PASSWORD` mà `backend/app/config.py` đọc;
- script **ghi đè** `secret-production.yaml` / `.env.production` một cách
  vô điều kiện => chạy với env thiếu sẽ XOÁ mất secret đang chạy;
- các nhánh `echo` in ra giá trị (URL DB, 8 ký tự đầu Cloudflare account id).

Contract sau khi sửa:
1. Thiếu biến bắt buộc -> exit 1, in ra **danh sách TÊN biến thiếu**, KHÔNG
   ghi/đụng file nào.
2. Đủ biến -> ghi đủ key chuẩn (`BANKOPS_SIGNING_KEY`, `BANKOPS_SESSION_SECRET`,
   `SMTP_USER`, `SMTP_PASSWORD`, `SUPERVISOR_PIN`) và KHÔNG ghi `SECRET_KEY`.
3. KHÔNG in giá trị secret ra stdout/stderr.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
SCRIPT = REPO_DIR / "scripts" / "setup_secrets_and_deploy.sh"

# Giá trị thử nghiệm — KHÔNG phải credential thật, KHÔNG dùng ở production.
TEST_SIGNING_KEY = "demo-signing-key"
TEST_SESSION_SECRET = "demo-session-secret"
TEST_SMTP_USER = "demo-smtp-user@example.invalid"
TEST_SMTP_PASSWORD = "demo-smtp-password"
TEST_PIN = "918273"
TEST_DB_URL = "postgresql+asyncpg://testonly:testonly@127.0.0.1:5432/testonly_db"

CANONICAL_KEYS = (
    "BANKOPS_SIGNING_KEY",
    "BANKOPS_SESSION_SECRET",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SUPERVISOR_PIN",
)


def _stage_repo(tmp_path: Path) -> Path:
    """Copy script vào tmp repo (ROOT_DIR = tmp) để KHÔNG ghi vào repo thật."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    target = scripts_dir / "setup_secrets_and_deploy.sh"
    shutil.copy2(SCRIPT, target)
    (tmp_path / "infra" / "k8s" / "base").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _run(root: Path, env_extra: dict | None = None, args: tuple[str, ...] = ()):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
    }
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", str(root / "scripts" / "setup_secrets_and_deploy.sh"), *args],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _full_env() -> dict:
    return {
        "DATABASE_URL": TEST_DB_URL,
        "BANKOPS_SIGNING_KEY": TEST_SIGNING_KEY,
        "BANKOPS_SESSION_SECRET": TEST_SESSION_SECRET,
        "SMTP_USER": TEST_SMTP_USER,
        "SMTP_PASSWORD": TEST_SMTP_PASSWORD,
        "SUPERVISOR_PIN": TEST_PIN,
    }


def test_missing_required_env_exits_1_and_writes_nothing(tmp_path):
    root = _stage_repo(tmp_path)
    proc = _run(root, env_extra={}, args=("--from-env",))

    assert proc.returncode == 1, (
        f"phải exit 1 khi thiếu biến bắt buộc, exit={proc.returncode}\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    combined = proc.stdout + proc.stderr
    for name in ("DATABASE_URL", "BANKOPS_SIGNING_KEY", "BANKOPS_SESSION_SECRET"):
        assert name in combined, f"phải liệt kê tên biến thiếu, thấy:\n{combined}"
    assert not (root / ".env.production").exists(), "KHÔNG được tạo .env.production"
    assert not (root / "infra" / "k8s" / "base" / "secret-production.yaml").exists(), (
        "KHÔNG được tạo secret-production.yaml"
    )


def test_missing_required_env_does_not_overwrite_existing_files(tmp_path):
    root = _stage_repo(tmp_path)
    k8s_file = root / "infra" / "k8s" / "base" / "secret-production.yaml"
    env_file = root / ".env.production"
    k8s_file.write_text("# SENTINEL K8S\n", encoding="utf-8")
    env_file.write_text("# SENTINEL ENV\n", encoding="utf-8")
    before_k8s = k8s_file.read_text(encoding="utf-8")
    before_env = env_file.read_text(encoding="utf-8")

    proc = _run(root, env_extra={}, args=("--from-env",))

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert k8s_file.read_text(encoding="utf-8") == before_k8s, (
        "KHÔNG được ghi đè secret-production.yaml khi thiếu biến bắt buộc"
    )
    assert env_file.read_text(encoding="utf-8") == before_env, (
        "KHÔNG được ghi đè .env.production khi thiếu biến bắt buộc"
    )


def test_missing_one_required_env_still_fails(tmp_path):
    root = _stage_repo(tmp_path)
    env = _full_env()
    env.pop("SMTP_PASSWORD")
    proc = _run(root, env_extra=env, args=("--from-env",))

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "SMTP_PASSWORD" in (proc.stdout + proc.stderr)
    assert not (root / ".env.production").exists()


def test_full_env_writes_all_canonical_keys(tmp_path):
    root = _stage_repo(tmp_path)
    proc = _run(root, env_extra=_full_env(), args=("--from-env",))

    assert proc.returncode == 0, proc.stdout + proc.stderr

    k8s_text = (root / "infra" / "k8s" / "base" / "secret-production.yaml").read_text(
        encoding="utf-8"
    )
    env_text = (root / ".env.production").read_text(encoding="utf-8")

    for key in CANONICAL_KEYS:
        assert key in k8s_text, f"secret-production.yaml thiếu key chuẩn {key}"
        assert key in env_text, f".env.production thiếu key chuẩn {key}"

    # Tên legacy KHÔNG được ghi nữa (2 tên / 1 giá trị = rotate lệch).
    assert "SECRET_KEY" not in k8s_text, "KHÔNG được ghi SECRET_KEY (legacy)"
    assert "SECRET_KEY" not in env_text, "KHÔNG được ghi SECRET_KEY (legacy)"


def test_script_never_prints_secret_values(tmp_path):
    root = _stage_repo(tmp_path)
    proc = _run(root, env_extra=_full_env(), args=("--from-env",))

    combined = proc.stdout + proc.stderr
    for value in (
        TEST_SIGNING_KEY,
        TEST_SESSION_SECRET,
        TEST_SMTP_PASSWORD,
        TEST_PIN,
    ):
        assert value not in combined, (
            "KHÔNG được in giá trị secret ra stdout/stderr"
        )


def test_legacy_secret_key_is_not_used_as_fallback(tmp_path):
    """`SECRET_KEY` legacy không được dùng thay cho `BANKOPS_SIGNING_KEY`."""
    root = _stage_repo(tmp_path)
    env = _full_env()
    env.pop("BANKOPS_SIGNING_KEY")
    env["SECRET_KEY"] = "TESTONLY-LEGACY-SECRET-KEY-DO-NOT-USE"

    proc = _run(root, env_extra=env, args=("--from-env",))

    assert proc.returncode == 1, (
        "thiếu BANKOPS_SIGNING_KEY phải fail dù có SECRET_KEY legacy\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    assert not (root / ".env.production").exists()
