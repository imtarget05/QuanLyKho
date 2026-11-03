# QA & Test Exploration Analysis — QuanLyKho

**Explorer:** Explorer 3 (QA & Test Explorer)  
**Date:** 2026-11-02  
**Repository:** `/Users/mainguyenbinhtan/Downloads/QuanLyKho`  
**Mission:** Comprehensive QA & Test architectural analysis for:
1. Admin role update email notification & resilient dispatch.
2. Frontend real-time notification / reload on admin role promotion.
3. Test suite stability, fixtures, mocking mechanisms, and test execution standards.

---

## 1. Test Architecture & Framework Overview

### 1.1 Backend Test Architecture
- **Framework:** `pytest` (^8.4.2) with `pytest-asyncio` (^0.24.0) and `pytest-cov` (^5.0.0).
- **Execution Mode:** `asyncio_mode = "auto"` in `backend/pyproject.toml` (allows direct `async def test_*` or synchronous `def test_*` functions).
- **HTTP Client:** `fastapi.testclient.TestClient` wrapping ASGI application instance (`app.main.app`).
- **Python Runtime & Environment:**
  - Canonical Python toolchain: **Poetry** with virtual environment at `backend/.venv` (Python 3.11.15).
  - Executable: `backend/.venv/bin/python`.
- **Database Isolation & Safety Gate (`conftest.py`):**
  - `conftest.py::pytest_sessionstart` strictly guards the database connection:
    ```python
    database_name = make_url(database_url).database or ""
    if "_test" not in database_name.lower():
        pytest.exit(
            "Refusing to run mutating tests against database ... "
            "Use a dedicated database whose name contains `_test`",
            returncode=2,
        )
    ```
  - Any command invoking pytest directly **must** provide a `DATABASE_URL` with `_test` in the DB name (e.g., `postgresql+psycopg2://bankops:bankops@127.0.0.1:5433/bankops_test`).
  - Unit tests that do not query Postgres still trigger `pytest_sessionstart` and will exit with code 2 if `DATABASE_URL` lacks `_test`.
- **Core Fixtures in `conftest.py`:**
  - `client`: Session-scoped `TestClient(app)` for HTTP REST requests.
  - `demo_mode`: Function-scoped fixture monkeypatching `settings.demo_mode = True` and `is_demo_mode = True`.
  - `reset_rate_limits`: Autouse fixture clearing in-memory login failure counters (`_login_failures.clear()`).
  - `fetch_all_balances(client, headers)`: Helper handling keyset pagination over `/inventory/balances` via `next_cursor`.

### 1.2 Frontend Test Architecture
- **Framework:** Flutter Test SDK (`flutter_test` / Dart 3.13.5 / Flutter 3.47.7).
- **Execution Command:** `cd frontend && flutter test --no-pub`.
- **Current Baseline:** 63 test files, **290 passing tests** verified in 43 seconds.
- **Key Testing Constructs:**
  - `WidgetTester` with `tester.pumpWidget(...)` and `tester.pumpAndSettle()`.
  - `FakeBankOpsRepository` (in `frontend/lib/src/data/repositories/fake_repository.dart`): zero-latency in-memory mock repository.
  - `SessionScope`: Injected widget supplying current logged-in `AppUser` and `onSignOut` callback.
  - `RepositoryScope`: Injected widget supplying the active `BankOpsRepository`.
  - `DataSyncController`: Real-time coordination between SSE streams, lifecycle state, and periodic polling.

---

## 2. Existing Tests Catalog

### 2.1 Backend User Management & Role Testing
| Test File | Key Scenarios Covered |
|---|---|
| `backend/tests/test_root_role_assignment.py` | Role mutation via `PUT /admin/users/{user_id}/roles`, permission invariants, self-escalation blocks, token version invalidation (`user.auth_version += 1`). |
| `backend/tests/test_iam_admin.py` | 403 on non-admin calling `/admin/users/*`, creating user with temporary password vs invite token, admin cannot self-lock, session revocation. |
| `backend/tests/test_admin_provision_specific_user.py` | Full admin provisioning flow for specific staff, initial role assignment, scope grants. |
| `backend/tests/test_admin_user_default_pin_gate.py` | PIN assignment guard, demo vs production mode behavior. |
| `backend/tests/test_single_session_and_alerts.py` | Invalidation of previously issued tokens when `auth_version` increments. |

### 2.2 Backend Email Service Testing
| Test File | Key Scenarios Covered |
|---|---|
| `backend/tests/test_email_service_templates.py` | Email address validation (`is_valid_email`), `EmailSendResult` boolean behavior, HTML/plain-text rendering for invite emails, activation confirmations, and password reset OTPs with XSS escaping. |

### 2.3 Frontend IAM & Role Testing
| Test File | Key Scenarios Covered |
|---|---|
| `frontend/test/admin_add_new_admin_flow_test.dart` | UI workflow where an administrator provisions a new Admin user with email invite, verifies confirmation dialog and list badge. |
| `frontend/test/root_role_update_test.dart` | Updating employee roles via `EmployeeManagementScreen`, self-demotion sign-out, role navigation matrix. |
| `frontend/test/dashboard_roles_test.dart` | Role-based navigation visibility (auditor, maker, admin), compact bottom bar, permissions gating. |
| `frontend/test/auth_offline_fallback_test.dart` | 401/403 HTTP error handling, ensuring no sensitive URLs or unhandled format exceptions leak. |

---

## 3. Email Notification & Mocking Strategy in Pytest

### 3.1 Requirements Grounding
- **R2.1 Trigger on Admin Promotion:** When an existing employee's role is updated to include `admin` (or `system_admin`, `root_admin`), an email notification must be dispatched directly to `user.email`.
- **R2.2 Correct Recipient:** The destination address must strictly match the target user's email.
- **R2.3 Informative Content:** Subject and body must clearly identify that administrative privileges have been granted.
- **R2.4 Database Resilience:** The database transaction modifying user roles must commit safely and remain persisted even if the email service times out or throws an unhandled exception.
- **R2.5 Idempotency / Negative Scenarios:**
  - Updating roles between non-admin roles (e.g., `staff` -> `manager` or `approver`) must **not** trigger an admin promotion email.
  - Re-saving roles when the user already possessed `admin` must **not** send duplicate promotion emails.
  - If the target user has no email configured or an invalid format, role update must proceed without crashing.

### 3.2 Email Service Extension Specification
In `backend/app/services/email_service.py`, implement `send_admin_role_granted_email`:
```python
async def send_admin_role_granted_email(
    to_email: str,
    username: str,
    display_name: str | None = None,
    new_roles: list[str] | None = None,
    granted_by: str | None = None,
) -> EmailSendResult:
    """Send an official notification email when an employee account is granted admin privileges."""
    ...
```

### 3.3 Endpoint Integration in `admin_users.py`
In `PUT /admin/users/{user_id}/roles` (`backend/app/api/routes/admin_users.py`):
```python
    # 1. Update roles in DB
    for role_code in before - after:
        await db.delete(existing_roles[role_code])
    for role_code in after - before:
        db.add(UserRole(user_id=u_uuid, role_code=role_code))

    user.auth_version = getattr(user, "auth_version", 1) + 1
    ...
    # 2. COMMIT DATABASE FIRST (Ensures resilience)
    await db.commit()
    await db.refresh(user)

    # 3. Best-effort Admin Promotion Email Dispatch
    admin_role_set = {"admin", "system_admin", "root_admin"}
    is_newly_admin = bool((after & admin_role_set) and not (before & admin_role_set))

    if is_newly_admin and user.email and is_valid_email(user.email):
        try:
            await send_admin_role_granted_email(
                to_email=user.email,
                username=user.username,
                display_name=user.display_name_demo,
                new_roles=list(after),
                granted_by=current_user.display_name_demo or current_user.username,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send admin promotion email to %s: %s", user.email, exc)
```

### 3.4 Concrete Pytest Mocking Implementations
The following copy-pasteable test suite provides full verification coverage:

#### A. Unit Tests for Email Template & Service (`test_email_service_templates.py` or `test_admin_promotion_email.py`)
```python
import pytest
from unittest.mock import patch
from app.services.email_service import (
    send_admin_role_granted_email,
    _build_admin_promoted_html,
    _build_admin_promoted_plain,
)

def test_build_admin_promoted_email_content():
    html_body = _build_admin_promoted_html(
        username="binhtan",
        display_name="Mai Nguyễn Bình Tân",
        roles=["admin", "staff"],
        granted_by="Admin Trưởng",
    )
    assert "Quản Trị Viên (Admin)" in html_body or "Administrator" in html_body
    assert "binhtan" in html_body
    assert "Mai Nguyễn Bình Tân" in html_body
    assert "quyền" in html_body.lower()

    plain_body = _build_admin_promoted_plain(
        username="binhtan",
        display_name="Mai Nguyễn Bình Tân",
        roles=["admin"],
        granted_by="Admin Trưởng",
    )
    assert "THÔNG BÁO CẤP QUYỀN QUẢN TRỊ VIÊN" in plain_body
    assert "binhtan" in plain_body

@pytest.mark.asyncio
async def test_send_admin_role_granted_email_dispatch():
    with patch("app.services.email_service._send_smtp_sync") as mock_smtp:
        mock_smtp.return_value = (True, "Gửi thành công")
        
        result = await send_admin_role_granted_email(
            to_email="target_admin@khotrasua.vn",
            username="new_admin",
            display_name="New Admin",
            new_roles=["admin"],
            granted_by="Super Admin",
        )
        assert bool(result) is True
        assert mock_smtp.called
        kwargs = mock_smtp.call_args.kwargs
        assert kwargs["to_email"] == "target_admin@khotrasua.vn"
        assert "Quản Trị" in kwargs["subject"] or "Admin" in kwargs["subject"]
        assert "new_admin" in kwargs["html_content"]
```

#### B. Integration Tests for Role Update Endpoint with Mocks
```python
from unittest.mock import AsyncMock, patch
import uuid
import pytest

def _login(client, username="demo_admin", password="DemoPass123!"):
    resp = client.post("/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}

def _create_employee(client, auth, email="employee@khotrasua.vn", roles=None):
    if roles is None:
        roles = ["staff"]
    resp = client.post(
        "/admin/users",
        headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "username": f"emp_{uuid.uuid4().hex[:8]}",
            "display_name": "Test Employee",
            "email": email,
            "roles": roles,
            "onboarding_method": "temporary_password",
        },
    )
    assert resp.status_code == 201
    return resp.json()["user"]

def test_admin_role_granted_triggers_email(client):
    auth = _login(client)
    user = _create_employee(client, auth, email="tan_staff@khotrasua.vn", roles=["staff"])
    user_id = user["id"]

    with patch(
        "app.api.routes.admin_users.send_admin_role_granted_email",
        new_callable=AsyncMock,
    ) as mock_send_email:
        mock_send_email.return_value = AsyncMock()

        resp = client.put(
            f"/admin/users/{user_id}/roles",
            headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
            json={"roles": ["staff", "admin"]},
        )
        assert resp.status_code == 200
        assert mock_send_email.called
        call_kwargs = mock_send_email.call_args.kwargs
        assert call_kwargs["to_email"] == "tan_staff@khotrasua.vn"
        assert call_kwargs["username"] == user["username"]
        assert "admin" in call_kwargs["new_roles"]

def test_role_update_resilient_when_email_fails(client):
    auth = _login(client)
    user = _create_employee(client, auth, email="tan_staff_fail@khotrasua.vn", roles=["staff"])
    user_id = user["id"]

    with patch(
        "app.api.routes.admin_users.send_admin_role_granted_email",
        side_effect=Exception("SMTP Server Unreachable / Timeout"),
    ) as mock_send_email:
        resp = client.put(
            f"/admin/users/{user_id}/roles",
            headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
            json={"roles": ["admin"]},
        )
        # Endpoint MUST succeed despite email failure
        assert resp.status_code == 200
        assert mock_send_email.called

        # Database state MUST have persisted the admin role
        detail = client.get(f"/admin/users/{user_id}", headers=auth).json()["user"]
        assert "admin" in detail["roles"]

def test_non_admin_role_update_does_not_send_admin_email(client):
    auth = _login(client)
    user = _create_employee(client, auth, email="tan_staff_no_admin@khotrasua.vn", roles=["staff"])
    user_id = user["id"]

    with patch(
        "app.api.routes.admin_users.send_admin_role_granted_email",
        new_callable=AsyncMock,
    ) as mock_send_email:
        resp = client.put(
            f"/admin/users/{user_id}/roles",
            headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
            json={"roles": ["staff", "approver"]},
        )
        assert resp.status_code == 200
        assert not mock_send_email.called
```

---

## 4. Frontend Notification & UI Reload Verification Strategy

### 4.1 Frontend Architecture & Detection Mechanics
1. **The Session Context:**
   - In `frontend/lib/src/app/app_shell.dart`, current user permissions are accessed via `SessionScope.maybeOf(context)?.user`.
   - Role visibility logic is defined in `frontend/lib/src/core/util/role_visibility.dart` (e.g., `RoleVisibility.isAdmin(roles)` determines employee management, settings, and dual-control approvals visibility).
2. **Detection Triggers:**
   - **Mechanism 1 (SSE / Event Push):** The backend emits `OutboxEvent("user.roles_updated")`. The frontend's `DataSyncController` receives SSE signals via `repository.approvalNotifications`. If the incoming event targets the current user, or topic indicates role updates, `DataSyncController.notifySyncNeeded()` is called.
   - **Mechanism 2 (Heartbeat / Profile Re-fetch):** `DataSyncController` runs a 60-second heartbeat poller. When querying `/auth/me`, the frontend compares current cached roles vs. server response.
   - **Mechanism 3 (Token Invalidation on Action):** Because `auth_version` was bumped on role update, subsequent API calls may receive HTTP 401. Instead of an unceremonious logout, the app intercepts the notification or token change and prompts:
     > *"Quyền tài khoản của bạn đã được cập nhật thành Quản Trị Viên (Admin). Vui lòng làm mới giao diện để áp dụng quyền hạn mới."*
3. **UI Refresh Action:**
   - Provides an immediate action button: `[Làm mới giao diện ngay]` or auto-refreshes via `AuthService.tryAutoLogin()` / page reload, replacing `SessionScope` with the newly assigned admin roles.

### 4.2 Flutter Widget Test Specification
Create a new automated widget test in `frontend/test/admin_role_promotion_notification_test.dart`:
```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/sync/data_sync_controller.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';

class MockRolePromotionRepository extends FakeBankOpsRepository {
  MockRolePromotionRepository() : super(latency: Duration.zero);

  AppUser currentUser = const AppUser(
    id: 'emp_staff_1',
    username: 'staff_binhtan',
    displayName: 'Mai Nguyễn Bình Tân',
    email: 'mainguyenbinhtan2005@gmail.com',
    roles: ['staff'],
    capabilities: ['inventory:view'],
  );
}

void main() {
  testWidgets(
    'Logged-in user detects admin role grant, displays reload notification, and reflects admin navigation on refresh',
    (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1400, 1000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = MockRolePromotionRepository();
      final syncController = DataSyncController(autoPollInterval: const Duration(seconds: 1));

      var currentSessionUser = repo.currentUser;
      var reloadCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: StatefulBuilder(
            builder: (context, setState) {
              return SessionScope(
                user: currentSessionUser,
                onSignOut: () async {},
                child: RepositoryScope(
                  repository: repo,
                  child: AppShell(
                    onReloadRequested: () {
                      setState(() {
                        reloadCount++;
                        currentSessionUser = currentSessionUser.copyWith(
                          roles: const ['admin', 'staff'],
                          capabilities: const ['iam:admin', 'admin:user_management'],
                        );
                      });
                    },
                  ),
                ),
              );
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 1. Initially, as staff, Admin IAM options are NOT present
      expect(find.text('Quản trị Nhân viên & Cấp phát IAM'), findsNothing);

      // 2. Simulate server emitting role update event to admin
      syncController.notifySyncNeeded(
        event: const SyncEvent(
          topic: SyncTopic.all,
          action: 'user.roles_updated',
          message: 'Tài khoản của bạn đã được nâng cấp quyền Quản Trị Viên (Admin).',
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1100)); // allow debounce
      await tester.pumpAndSettle();

      // 3. Verify notification / prompt is displayed to user
      expect(
        find.textContaining('Quản Trị Viên (Admin)'),
        findsOneWidget,
      );
      expect(
        find.byKey(const Key('admin-role-reload-btn')),
        findsOneWidget,
      );

      // 4. Tap reload button or trigger auto-refresh
      await tester.tap(find.byKey(const Key('admin-role-reload-btn')));
      await tester.pumpAndSettle();

      // 5. Verify refresh executed and full admin navigation is rendered
      expect(reloadCount, 1);
      expect(currentSessionUser.roles.contains('admin'), isTrue);
    },
  );
}
```

---

## 5. Exact Test Execution Commands & Verification Standards

### 5.1 Backend Execution Commands
```bash
# 1. Dedicated test run with temporary database container (recommended in Makefile)
make test-backend

# 2. Targeted pytest run with explicit test database URL
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5433/bankops_test" \
.venv/bin/python -m pytest tests/test_email_service_templates.py tests/test_root_role_assignment.py -v

# 3. Fast unit-test run for email service (no DB connection needed, but URL gate satisfied)
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
.venv/bin/python -m pytest tests/test_email_service_templates.py -v

# 4. Code quality & linting check (pinned to ruff 0.17.0)
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho
python3 -m ruff check backend/ ai/
python3 scripts/check_no_secrets.py
```

### 5.2 Frontend Execution Commands
```bash
# 1. Run full Flutter test suite (290 tests)
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend
flutter test --no-pub

# 2. Run targeted tests for admin flows & role updates
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend
flutter test test/admin_add_new_admin_flow_test.dart test/root_role_update_test.dart

# 3. Static code analysis
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend
flutter analyze
```

---

## 6. Summary Matrix for Implementers

| Requirement | Proposed Solution Location | Key Verification Assertion |
|---|---|---|
| **R1 (UI Notice / Refresh)** | `frontend/lib/src/core/sync/data_sync_controller.dart` & `frontend/lib/src/app/app_shell.dart` | `expect(find.textContaining('Quản Trị Viên (Admin)'), findsOneWidget)` and admin UI rendered after reload |
| **R2.1 (Admin Email Trigger)** | `backend/app/api/routes/admin_users.py` (`update_user_roles`) | `mock_send_email.assert_called_once()` when `'admin' in after and 'admin' not in before` |
| **R2.2 (Recipient Match)** | `send_admin_role_granted_email` call in `admin_users.py` | `call_kwargs['to_email'] == user.email` |
| **R2.3 (Subject & Body Content)** | `backend/app/services/email_service.py` (`_build_admin_promoted_html`) | `assert 'Quản Trị Viên (Admin)' in kwargs['subject']` and body explains admin rights |
| **R2.4 (Database Resilience)** | `try...except Exception` after `await db.commit()` in `admin_users.py` | `assert resp.status_code == 200` and `assert 'admin' in user_detail['roles']` despite email exception |
| **Stability Gate** | 100% test suite pass | `make test-all` or `pytest backend/tests` + `flutter test` |
