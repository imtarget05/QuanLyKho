# Handoff Report — Explorer 3 (QA & Test Explorer)

**Role:** QA & Test Explorer  
**Working Directory:** `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_3`  
**Repository:** `/Users/mainguyenbinhtan/Downloads/QuanLyKho`  
**Target File:** `handoff.md`  
**Date:** 2026-11-02  

---

## 1. Observation

### 1.1 Test Infrastructure & Isolation Gate
- **Backend Test Runner & Gating:**
  Direct execution of `pytest` fails immediately with exit code 2 if `DATABASE_URL` does not explicitly contain `_test`.
  *Verbatim code from `backend/tests/conftest.py:56-63`:*
  ```python
  database_name = make_url(database_url).database or ""
  if "_test" not in database_name.lower():
      pytest.exit(
          "Refusing to run mutating tests against database "
          f"`{database_name}`. Use a dedicated database whose name contains "
          "`_test` (for example `bankops_test`) or run `make test-backend`.",
          returncode=2,
      )
  ```
  *Command and result:*
  Running `cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" .venv/bin/python -m pytest tests/test_email_service_templates.py`:
  ```
  ========================= 8 passed, 1 warning in 0.54s =========================
  ```
- **Frontend Test Suite:**
  Flutter 3.47.7 and Dart 3.13.5 are installed and operational on the host machine.
  *Command and result:*
  Running `cd frontend && flutter test --no-pub`:
  ```
  00:43 +290: All tests passed!
  ```
  All 290 frontend tests pass without failure.

### 1.2 Role Mutation Endpoint & Invariants
- In `backend/app/api/routes/admin_users.py:594-656`, the endpoint `PUT /admin/users/{user_id}/roles`:
  - Validates role codes against catalog (`_validated_roles`).
  - Blocks self-escalation and self-demotion (`CANNOT_ESCALATE_SELF`, `CANNOT_DEMOTE_SELF`).
  - Bumps `user.auth_version = getattr(user, "auth_version", 1) + 1` (line 636).
  - Emits an `AuditEvent` (`IAM_USER_ROLES_UPDATED`) and an `OutboxEvent` (`user.roles_updated`).
  - Calls `await db.commit()` and `await db.refresh(user)` (lines 652-653).
  - Currently does **not** call any email dispatch service for admin promotions.

### 1.3 Existing Email Notification Implementation
- In `backend/app/services/email_service.py`:
  - Line 119: `def _send_smtp_sync(...)` uses synchronous `smtplib.SMTP` (STARTTLS port 587) or `smtplib.SMTP_SSL` (SSL port 465) executed inside `asyncio.to_thread`.
  - Line 162: `send_password_reset_email`
  - Line 417: `send_invite_email`
  - Line 630: `send_activation_confirmation_email`
  - Line 773: `send_security_alert_email`
  - Lines 101-117: `EmailSendResult` provides a boolean-evaluable wrapper (`res.ok`, `res.success`, `res.message`).
  - If SMTP credentials are missing, services log to console and return `EmailSendResult(False, "Chưa cấu hình tài khoản SMTP")` without throwing an exception.

### 1.4 Frontend Real-time Coordination
- In `frontend/lib/src/core/sync/data_sync_controller.dart`:
  - `DataSyncController` manages push notifications via `repository.approvalNotifications` (SSE), app lifecycle transitions (`AppLifecycleState.resumed`), and a 60-second heartbeat poller.
  - Line 135: Debounces events by 1000ms and fires `notifyListeners()`.
- In `frontend/lib/src/app/app_shell.dart`:
  - Line 86: `DataSyncController _syncController` is listened to in `initState`.
  - Line 116: Listens to update notifications (`onAppUpdateAvailable`) and renders an update banner (`_AppUpdateBanner(onUpdate: forceAppUpdate)`).

---

## 2. Logic Chain

1. **Email Notification Triggering (R2.1 & R2.2):**
   - From Observation 1.2, `PUT /admin/users/{user_id}/roles` compares `before = set(existing_roles)` and `after = set(cleaned_roles)`.
   - The condition for an admin promotion is unambiguously determined by:
     `is_newly_admin = bool((after & {"admin", "system_admin", "root_admin"}) and not (before & {"admin", "system_admin", "root_admin"}))`.
   - When `is_newly_admin` is true and `user.email` is valid (`is_valid_email(user.email)`), `send_admin_role_granted_email(...)` must be called with `to_email=user.email`.

2. **Database Resilience Under Email Failure (R2.4):**
   - From Observation 1.2, line 652 executes `await db.commit()` for the database role changes.
   - By placing the `send_admin_role_granted_email` call **after** `await db.commit()` inside a guarded `try...except Exception as exc:` block:
     - Any network failure, SMTP timeout, or exception raised by the email service will be logged and swallowed.
     - The database transaction has already been committed to PostgreSQL.
     - The API endpoint returns `200 OK` with the updated role payload, ensuring 100% resilience.

3. **Pytest Mocking Strategy (Acceptance Criteria):**
   - In unit/integration tests for the backend, `unittest.mock.patch` with `AsyncMock` on `app.api.routes.admin_users.send_admin_role_granted_email` allows direct verification of:
     - `mock_send_email.assert_called_once()`
     - `call_kwargs["to_email"] == target_user_email`
     - `call_kwargs["new_roles"]` contains `admin`
   - Testing resilience: Setting `mock_send_email.side_effect = Exception("SMTP Connection Failed")` confirms that the HTTP endpoint returns 200 and subsequent `GET /admin/users/{user_id}` returns the newly assigned admin role.

4. **Frontend Real-time Notification & Refresh (R1):**
   - From Observation 1.2, `admin_users.py` increments `user.auth_version` and writes an `OutboxEvent("user.roles_updated")`.
   - In the frontend, `DataSyncController` can dispatch an event or the app detects the role change when polling `/auth/me`.
   - Upon detecting that the logged-in user is now an `admin`, `AppShell` displays a prominent notification dialog or banner (`"Quyền tài khoản của bạn đã được cập nhật thành Quản Trị Viên (Admin)"`) with an action button `[Tải lại ngay]`.
   - When reloaded, `SessionScope` receives the fresh `AppUser` with `roles: ['admin']`, immediately rendering admin navigation items via `RoleVisibility.isAdmin(roles)`.

---

## 3. Caveats

1. **Docker Daemon Availability:**
   - Docker daemon was not running during the exploration turn (`failed to connect to unix:///Users/mainguyenbinhtan/.docker/run/docker.sock`).
   - `make test-backend` uses `docker compose -f docker-compose.test.yml up -d` to spin up a temporary PostgreSQL instance on port 5433.
   - For environments without Docker, unit tests mocking `_send_smtp_sync` and `FastAPI` dependencies run entirely in memory and satisfy all test criteria without needing a live Postgres instance, provided `DATABASE_URL` contains `_test`.
2. **Email Server in Demo Mode:**
   - When SMTP credentials (`SMTP_USER`, `SMTP_PASSWORD`) are empty (demo mode), `email_service.py` logs the email to console and returns `EmailSendResult(False, "Chưa cấu hình tài khoản SMTP")`. Production environments require SMTP credentials set in environment variables.

---

## 4. Conclusion

1. **Backend Integration Plan:**
   - Add `send_admin_role_granted_email(...)` to `backend/app/services/email_service.py` with HTML/plain-text templates explaining admin privileges, capabilities, and security recommendations.
   - Integrate the email call into `PUT /admin/users/{user_id}/roles` in `backend/app/api/routes/admin_users.py` directly following `await db.commit()`, wrapped in `try...except Exception:`.
   - Add pytest tests verifying dispatch, recipient matching, content assertion, and DB resilience when email sending fails.
2. **Frontend Integration Plan:**
   - Listen to `DataSyncController` role update signals in `AppShell` or check `/auth/me` on sync.
   - Display an in-app banner/dialog notifying the user of their admin promotion and providing a one-click reload button.
   - Add a Flutter widget test in `frontend/test/admin_role_promotion_notification_test.dart` verifying the prompt display and navigation update.

---

## 5. Verification Method

To independently verify all findings and test suites:

### 5.1 Run Email Template Unit Tests
```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
.venv/bin/python -m pytest tests/test_email_service_templates.py -v
```
*Expected Result:* 8 passed in ~0.5s.

### 5.2 Run Full Frontend Widget Test Suite
```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend
flutter test --no-pub
```
*Expected Result:* 290 passed in ~43s.

### 5.3 Run Targeted Role and Admin Widget Tests
```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend
flutter test test/admin_add_new_admin_flow_test.dart test/root_role_update_test.dart
```
*Expected Result:* All tests passed.

### 5.4 Run Lint and Security Audits
```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho
python3 -m ruff check backend/ ai/
python3 scripts/check_no_secrets.py
cd frontend && flutter analyze
```
*Expected Result:* 0 lint errors, 0 secret leaks, 0 analyze issues.

### 5.5 Invalidation Conditions
- If `PUT /admin/users/{user_id}/roles` throws an unhandled exception and rolls back the database transaction when email sending fails, the resilience requirement is violated.
- If email is sent to an address other than `user.email`, the recipient accuracy requirement is violated.
- If the frontend forces a hard logout without notifying the user that their role was upgraded to admin, the UI notification requirement is violated.
