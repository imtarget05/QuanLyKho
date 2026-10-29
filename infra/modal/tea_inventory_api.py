"""Modal App: FastAPI Quản Lý Kho Trà Sữa (Tea Inventory API) — backend chính thức (free host, scale-to-zero).

Vì sao Modal: HF Docker Space bị chặn (chỉ gói PRO mới tạo được), và máy này
không có CLI/token của Fly.io/Render/Railway. Modal Starter miễn phí $30/tháng
và scale-to-zero (ngủ sau `scaledown_window` giây không traffic) — đúng pattern
đã dùng cho app `bankops-llm` cùng thư mục. DB là Neon PostgreSQL.

Lưu ý gì cho người duy trì:
    modal secret create bankops-api ...              # cấu hình bí mật kết nối Neon DB, JWT, ...
    modal deploy infra/modal/tea_inventory_api.py   # deploy production backend

URL dạng https://<workspace>--quan-ly-kho-tra-sua-api.modal.run — lấy từ
`modal app list` hoặc output của deploy, rồi nối vào Flutter bằng
`flutter build web --dart-define=API_BASE_URL=<url>/api/v1`.
"""

from __future__ import annotations

import modal

# Pin đúng phiên bản đã chạy xanh 232 test ở QA venv — chép từ `uv pip list`.
# Giữ đồng bộ với backend/pyproject.toml; đừng "upgrade" bừa khi deploy.
REQUIREMENTS = [
    "alembic==1.20.0",
    "annotated-types==0.8.0",
    "anyio==4.15.1",
    "async-timeout==5.0.1",
    "asyncpg==0.29.0",
    "bcrypt==4.0.1",
    "certifi==2026.7.22",
    "cffi==2.1.1",
    "charset-normalizer==3.5.2",
    "click==8.5.0",
    "cryptography==50.0.2",
    "ecdsa==0.19.2",
    "fastapi==0.115.14",
    "google-auth==2.61.0",
    "greenlet==3.5.6",
    "h11==0.16.0",
    "httpcore==1.0.9",
    "httptools==0.9.0",
    "httpx==0.27.2",
    "idna==3.20",
    "itsdangerous==2.2.0",
    "librt==0.16.0",
    "mako==1.4.3",
    "markupsafe==3.0.4",
    "opentelemetry-api==1.45.1",
    "passlib==1.7.4",
    "psycopg2-binary==2.9.13",
    "pyasn1-modules==0.4.2",
    "pyasn1==0.6.4",
    "pycparser==3.11",
    "pydantic==2.14.0",
    "pydantic-core==2.50.0",
    "pydantic-settings==2.15.0",
    "pyjwt==2.15.1",
    "python-dotenv==1.2.4",
    "python-jose==3.5.0",
    "python-multipart==0.0.10",
    "pyyaml==6.0.3",
    "redis==5.3.1",
    "requests==2.34.2",
    "rsa==4.9.1",
    "six==1.17.0",
    "sniffio==1.3.1",
    "sqlalchemy==2.1.4",
    "starlette==0.46.2",
    "typing-extensions==4.16.0",
    "typing-inspection==0.4.4",
    "urllib3==2.8.0",
    "uvicorn==0.30.6",
    "uvloop==0.23.0",
    "watchfiles==1.3.0",
    "websockets==17.2",
    "wrapt==2.5.0",
]

# Mẫu của app.seed: path sẽ resolve qua SAMPLE_DATA_DIR (set ở dưới), vì
# REPO_DIR = parents[2] của seed.py sẽ trỏ tới /root trong container.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(*REQUIREMENTS)
    .add_local_dir("backend/app", remote_path="/root/bankops/app", copy=True)
    .add_local_dir("backend/alembic", remote_path="/root/bankops/alembic", copy=True)
    .add_local_file("backend/alembic.ini", remote_path="/root/bankops/alembic.ini", copy=True)
    .add_local_dir("sample-data", remote_path="/root/bankops/sample-data", copy=True)
    .add_local_dir("docs", remote_path="/root/bankops/docs", copy=True)
    .env(
        {
            "PYTHONPATH": "/root/bankops",
            # seed_demo đọc sample-data/*.json NGAY khi khởi động (database.py
            # gọi seed) — thiếu file này là container chết ngay khi lên.
            "SAMPLE_DATA_DIR": "/root/bankops/sample-data",
            "DOCS_DIR": "/root/bankops/docs",
            "AI_PROVIDER": "modal_llm",
            "MODAL_LLM_URL": "https://imtarget05--bankops-llm-serve.us-east.modal.run/v1/chat/completions",
            "MODAL_LLM_MODEL": "Qwen2.5-1.5B-Instruct.Q4_K_M",
            "SERVER_RELOAD": "false",
            "ALLOWED_ORIGINS": '["http://localhost:3000","http://localhost:8080","http://localhost:5000","https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev"]',
            "FRONTEND_BASE_URL": "https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev",
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "admin@example.com",
            "SMTP_FROM_NAME": "quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev",
        }
    )
)

app = modal.App("quan-ly-kho-tra-sua", image=image)


@app.function(secrets=[modal.Secret.from_name("bankops-api")], timeout=10 * 60)
def migrate_database() -> None:
    """Apply the versioned schema before a compatible API release is served."""
    import subprocess

    subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        cwd="/root/bankops",
        check=True,
    )


@app.function(
    secrets=[
        modal.Secret.from_name("bankops-api"),
        modal.Secret.from_dict({"AI_PROVIDER": "modal_llm"}),
    ]
)
def debug_origins():
    import os
    import sys
    sys.path.insert(0, "/root/bankops")
    print("ENV ALLOWED_ORIGINS:", os.environ.get("ALLOWED_ORIGINS"))
    from app.config import settings
    print("settings.allowed_origins:", repr(settings.allowed_origins))
    from app.main import _allowed_origins
    print("main._allowed_origins:", repr(_allowed_origins))
    return {
        "env": os.environ.get("ALLOWED_ORIGINS"),
        "settings": str(settings.allowed_origins),
        "main": str(_allowed_origins),
    }


@app.function(
    secrets=[
        modal.Secret.from_name("bankops-api"),
        modal.Secret.from_dict({"AI_PROVIDER": "modal_llm"}),
    ],
    # 5 phút không traffic -> container ngủ (tiết kiệm credit $30/tháng).
    scaledown_window=5 * 60,
    # request tối đa 15 phút (bao gồm cold start ~10-30s lần đầu).
    timeout=15 * 60,
)
@modal.asgi_app()
def api():
    import os
    import sys

    if "/root/bankops" not in sys.path:
        sys.path.insert(0, "/root/bankops")

    os.environ["AI_PROVIDER"] = "modal_llm"
    os.environ["DOCS_DIR"] = "/root/bankops/docs"
    os.environ["ALLOWED_ORIGINS"] = (
        '["http://localhost:3000","http://localhost:8080","http://localhost:5000","https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev"]'
    )

    from app.main import app as fastapi_app

    return fastapi_app
