import os
import subprocess
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

"""Shared fixtures for BankOps audit tests.

These tests are written by the independent QA reviewer. They must not import
`app.*` at module import time, so that collection always succeeds even when the
application itself is broken.
"""


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
APP_DIR = BACKEND_DIR / "app"

# Make `app` importable the same way uvicorn/alembic would.
sys.path.insert(0, str(BACKEND_DIR))

# A syntactically valid placeholder so `app.config.Settings()` can be built
# without a real database. Tests never open a connection through this URL.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops"
)

# Demo mode là opt-in TƯỜNG MINH (APP_ENV=demo + DEMO_MODE=true). Bộ test chạy
# trên dữ liệu demo (user demo_*, seed lúc startup) nên bật tường minh ở đây.
# Test kiểm tra an toàn sẽ TẮT lại bằng monkeypatch (`demo_mode=False`) để
# khẳng định hành vi ngoài demo mode.
os.environ.setdefault("DEMO_MODE", "true")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Refuse to mutate a developer, UAT, or production database in pytest.

    The backend suite performs real HTTP writes, seeds roles, and runs Alembic.
    A shared ``bankops`` database made those operations depend on stale data and
    could mutate a developer's demo data.  Test execution is therefore allowed
    only when the selected database name visibly carries the ``_test`` marker.
    CI and ``make test-backend`` provide ``bankops_test``.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.exit(
            "DATABASE_URL is required for integration tests; use `make test-backend` "
            "to start the isolated PostgreSQL test database.",
            returncode=2,
        )

    database_name = make_url(database_url).database or ""
    if "_test" not in database_name.lower():
        pytest.exit(
            "Refusing to run mutating tests against database "
            f"`{database_name}`. Use a dedicated database whose name contains "
            "`_test` (for example `bankops_test`) or run `make test-backend`.",
            returncode=2,
        )


def _import_or_fail(module: str):
    try:
        return __import__(module, fromlist=["*"])
    except BaseException as exc:  # noqa: BLE001 - we want every failure kind
        pytest.fail(
            f"Không import được `{module}`: {type(exc).__name__}: {exc}\n"
            f"-> Ứng dụng/khối đó không khởi động được, mọi ca kiểm thử phụ thuộc "
            f"vào nó đều không chạy được.",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def app():
    """Import the FastAPI application, failing loudly if it cannot boot."""
    return _import_or_fail("app.main").app


@pytest.fixture(scope="session")
def client(app):
    """HTTP client against the real app. Needs a reachable database for /health/ready."""
    from fastapi.testclient import TestClient

    try:
        with TestClient(app) as c:
            yield c
    except BaseException as exc:  # noqa: BLE001
        pytest.fail(
            f"Không khởi động được ASGI app (startup hook): {type(exc).__name__}: {exc}",
            pytrace=False,
        )


@pytest.fixture
def demo_mode(monkeypatch):
    """Bật demo mode TƯỜNG MINH (fixture dùng chung) cho test cần hành vi demo.

    Superset của các bản sao cục bộ trước đây:
    - bản gốc `test_change_security.py` / `test_google_auth.py`: bật
      `settings.demo_mode = True` (và dựa vào `app_env == "demo"` cho property).
    - bản gốc `test_admin_user_default_pin_gate.py`: ghim property
      `is_demo_mode` trên class Settings để không phụ thuộc `app_env`.

    Bật cả hai để mọi con đường (trường `demo_mode` hoặc property
    `is_demo_mode`) đều thấy demo mode, bất kể `APP_ENV`.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(
        type(settings), "is_demo_mode", property(lambda self: True), raising=False
    )
    assert settings.is_demo_mode is True
    return settings


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset in-memory login failure rate limits between tests."""
    try:
        from app.api.routes.auth_utils import _login_failures
        _login_failures.clear()
    except Exception:
        pass
    yield
    try:
        from app.api.routes.auth_utils import _login_failures
        _login_failures.clear()
    except Exception:
        pass


@pytest.fixture(autouse=True, scope="session")
def setup_demo_user_scopes():
    """Setup scope grants for demo users so tests can access locations/items."""
    import os

    
    # Only set up in test environment
    if os.environ.get("DATABASE_URL", "").endswith("_test") or "test" in os.environ.get("DATABASE_URL", ""):
        yield
        return
    
    yield


@pytest.fixture(scope="session")
def models():
    """Import every SQLAlchemy model module, failing loudly on any broken module."""
    broken = []
    loaded = []
    for name in ("iam", "inventory", "cash_sim", "approval", "activity", "integration", "reconciliation"):
        try:
            loaded.append(__import__(f"app.models.{name}", fromlist=["*"]))
        except BaseException as exc:  # noqa: BLE001
            broken.append(f"  app.models.{name}: {type(exc).__name__}: {exc}")
    if broken:
        pytest.fail(
            "Một hoặc nhiều model module không import được:\n" + "\n".join(broken),
            pytrace=False,
        )
    return loaded


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd or REPO_DIR), capture_output=True, text=True, timeout=timeout
    )


def open_shift(client, headers, location_id: str, shift_code: str = "morning"):
    """Open a stocktake shift on a business date that is still free.

    The application allows only one *open* shift per
    ``(location_id, business_date, shift_code)``.  Every test run leaves its
    shift open, so a randomly chosen date eventually collides with a previous
    run and the API answers ``409 SHIFT_ALREADY_OPEN``.  This helper retries
    across a wide window of dates until the shift can be opened, and returns
    ``(response, stocktake_id)``.
    """
    base = date(2040, 1, 1)
    offset = uuid.uuid4().int % 3650
    response = None
    for attempt in range(50):
        candidate = (base + timedelta(days=(offset + attempt) % 3650)).isoformat()
        response = client.post(
            "/inventory/stocktakes",
            headers=headers,
            json={
                "location_id": location_id,
                "shift_code": shift_code,
                "business_date": candidate,
            },
        )
        if response.status_code != 409:
            break
    assert response is not None and response.status_code == 201, (
        f"Không mở được ca kiểm kê: {response.status_code} {response.text}"
    )
    return response, response.json()["id"]


def fetch_all_balances(
    client,
    headers: dict[str, str],
    path: str = "/inventory/balances",
    params: dict | None = None,
) -> list[dict]:
    """Duyệt hết các trang của /inventory/balances qua keyset cursor.

    Endpoint giới hạn ``limit`` (tối đa 100) và trả ``next_cursor``; một GET
    duy nhất chỉ thấy trang đầu. Trên database dùng chung tích tụ balance row
    qua nhiều lần chạy, test phải đi theo cursor để nhìn thấy toàn bộ tồn kho
    thay vì chỉ trang đầu tiên.
    """
    query = dict(params or {})
    rows: list[dict] = []
    while True:
        resp = client.get(path, headers=headers, params=query)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        rows.extend(body["balances"])
        next_cursor = body.get("next_cursor")
        if not next_cursor:
            return rows
        query["cursor"] = next_cursor
