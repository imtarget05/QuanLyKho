# Handoff Report — Explorer 2 (Backend & Email Explorer)

## 1. Observation

1. **User & IAM Models**:
   - File `backend/app/models/iam.py`:
     - Lines 44–68: `User` model (`iam_users`) contains `id` (UUID), `username`, `password_hash`, `pin_hash`, `status` (UserStatus), `display_name_demo`, `email` (nullable), `branch_id`, and `auth_version` (Integer, default 1).
     - Lines 97–106: `Role` model (`iam_roles`) with `code` primary key.
     - Lines 108–117: `Capability` model (`iam_capabilities`) with `code` primary key.
     - Lines 119–128: `UserRole` model (`iam_user_roles`) with composite primary key `(user_id, role_code)`.
     - Lines 129–133: `RoleCapability` model (`iam_role_capabilities`) with composite primary key `(role_code, capability_code)`.

2. **Role Update Endpoint**:
   - File `backend/app/api/routes/admin_users.py`:
     - Lines 50, 52: `@router = APIRouter(prefix="/admin", tags=["Admin IAM"])`, `_ADMIN_CAPS = ("iam:admin", "admin:user_management")`.
     - Lines 594–656: `PUT /admin/users/{user_id}/roles` (function `update_user_roles`).
     - Line 610: Validates input roles via `_validated_roles(db, body.roles)`.
     - Line 618–626: Guard prevents admin from self-escalating roles or stripping own admin capability.
     - Lines 629–633: Applies set difference on `UserRole` table (`before - after` deleted, `after - before` added).
     - Line 636: `user.auth_version = getattr(user, "auth_version", 1) + 1` (bumps version).
     - Lines 638–650: Logs `AuditEvent` and queues `OutboxEvent`.
     - Lines 652–653: `await db.commit()`, `await db.refresh(user)`.
     - Line 655: Returns `{"user": await _user_to_dict(db, user), "message": "Cập nhật vai trò thành công."}`.

3. **Authentication, Profile & Token Inspection**:
   - File `backend/app/api/routes/auth.py`:
     - Lines 517–548: `GET /auth/me` returns `roles` and `capabilities` retrieved from database via `get_user_roles(db, current_user.id)` and `get_user_capabilities(db, current_user.id)`.
   - File `backend/app/api/routes/auth_utils.py`:
     - Lines 373–381: `create_access_token` encodes JWT with claims `sub`, `username`, `roles`, `caps`, `auth_version`, `branch_id`.
     - Lines 491–499: `get_current_user` compares `payload.get("auth_version")` with `user.auth_version`. If mismatched, raises `HTTPException(401, detail="Phiên đăng nhập đã bị thu hồi.")`.
     - Lines 608–632: `get_current_user_with_capabilities` reads `caps` directly from token claims (`payload.get("caps")`).
   - File `backend/app/api/routes/auth.py`:
     - Lines 474–476: `POST /auth/refresh` checks `token_auth_version == user.auth_version`. If mismatched, raises 401 `invalid`.

4. **Existing Email Service & SMTP Configuration**:
   - File `backend/app/config.py`:
     - Lines 145–171: Settings `smtp_host` (default `"smtp.gmail.com"`), `smtp_port` (default `587`), `smtp_user`, `smtp_password`, `smtp_from_name` (default `"Ban Quản Trị Hệ Thống"`), `admin_alert_email`, `admin_emails`.
   - File `backend/app/services/email_service.py` (854 lines):
     - Lines 19–22: `is_valid_email(value: str | None) -> bool`.
     - Lines 101–117: `EmailSendResult` with boolean evaluation (`.ok`, `.success`, `.message`).
     - Lines 119–160: `_send_smtp_sync(...)` handles STARTTLS on 587, SSL on 465, 12-second timeout, UTF-8 multipart HTML/plain text, returns `tuple[bool, str]`.
     - Lines 417–491: `send_invite_email(...)` provides enterprise template with safe escaping and demo mode fallback when unconfigured.
     - Lines 824–853: `check_smtp_health()` verifies SMTP connectivity.

5. **Existing Real-Time SSE Infrastructure**:
   - File `backend/app/services/approval_events.py`:
     - Lines 19–176: `ApprovalEventBus` with in-memory asyncio queues and optional Redis distributed Pub/Sub backplane.
     - Lines 179–198: Broadcast helpers (`publish`, `broadcast_approval_event`).
   - File `backend/app/api/routes/approvals.py`:
     - Lines 189–228: Endpoint `GET /approvals/stream` delivers real-time SSE stream.
   - File `frontend/lib/src/data/repositories/http_bankops_repository.dart`:
     - Lines 50–84: Connects to `/approvals/stream` and populates `approvalNotifications` stream.
   - File `frontend/lib/src/core/sync/data_sync_controller.dart`:
     - Lines 68–78: Binds repository and listens to `approvalNotifications`.

6. **Current Test Suite Results**:
   - Command: `DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" poetry run pytest tests/test_email_service_templates.py -v`
   - Result: 8 passed in 0.49s.

## 2. Logic Chain

1. **Email Notification Trigger Point**:
   - From Observation 2 (`admin_users.py:594`), `update_user_roles` calculates `before = set(existing_roles)` and `after = set(cleaned_roles)`.
   - When `"admin" in (after - before)` (or an admin role is added), this constitutes the exact moment a user is granted admin privileges.
   - Therefore, the notification email should be triggered within `update_user_roles`.

2. **Transaction Safety Guarantee**:
   - In Observation 2 (`admin_users.py:652`), `await db.commit()` commits the role changes to PostgreSQL.
   - In Observation 4 (`email_service.py:119`), SMTP sending involves network calls and an external server with a 12-second timeout.
   - If email sending is invoked *before* `commit()`, any network failure, timeout, or invalid SMTP credential would either hang the DB transaction or cause a rollback.
   - Conversely, by executing email dispatch *strictly after* `await db.commit()`, and enclosing it in a `try...except Exception as exc:` block:
     * The database update remains 100% committed and intact.
     * Any SMTP error is caught, logged (`logger.warning`), and the HTTP API response still completes with HTTP 200 and updated user data.
     * This fulfills Acceptance Criteria: *"Luồng cập nhật quyền trong cơ sở dữ liệu hoạt động ổn định và an toàn kể cả khi quá trình gửi email gặp sự cố"*.

3. **Email Content & Formatting**:
   - From Observation 1 (`iam.py:108`) and `seed.py:126–168`, admin capabilities include `admin:user_management`, `iam:admin`, `inventory:approve_request`, `cash:manage_box`, `cash:post_adjustment`, and `integration:manage`.
   - From Observation 4 (`email_service.py:417`), existing email templates follow an enterprise design (Dark header `#0F172A`, Royal Blue `#2563EB`, responsive table, XSS escaping).
   - Adding `send_admin_role_granted_email()` with HTML and plain-text versions specifying the newly granted role and privilege summary meets Requirement R2.

4. **Frontend Role Change Detection (Requirement R1)**:
   - From Observation 2 (`admin_users.py:636`), updating roles increments `user.auth_version`.
   - From Observation 3 (`auth_utils.py:494`), a mismatched `auth_version` causes `get_current_user` to reject old tokens with HTTP 401.
   - Furthermore, `get_current_user_with_capabilities` reads capabilities directly from JWT claims. Hence, client-side capabilities cannot be updated without a refreshed session.
   - From Observation 5 (`approval_events.py` & `http_bankops_repository.dart`), the frontend already keeps an active SSE connection to `/approvals/stream` managed by `DataSyncController`.
   - By publishing a `role_updated` event through `approval_event_bus` upon committing `update_user_roles`:
     * The client receives a push notification immediately (< 100ms).
     * `DataSyncController` identifies `event.user_id == current_user.id` and `is_admin == true`.
     * The UI can display a reload dialog/toast or trigger an automatic session refresh.
   - In addition, updating the HTTP 401 error envelope in `auth_utils.py` to return `{"code": "AUTH_VERSION_CHANGED", "reason": "ROLE_OR_SESSION_UPDATED"}` provides a resilient fallback if SSE is disconnected.

## 3. Caveats

1. **No Code Modifications**: Per instructions, this investigation is strictly read-only. No application code has been modified in this turn.
2. **SMTP Credential Availability**: In local/dev environments where `SMTP_USER` and `SMTP_PASSWORD` are empty, `email_service` safely runs in demo mode (logging to stdout/logger). Production deployment requires real SMTP credentials (e.g. Gmail App Password or SendGrid/Postmark) set in environment variables.
3. **Users without Email**: Some legacy or demo users may have `email = None`. The email sending service must check `if not is_valid_email(clean_email): return EmailSendResult(False, ...)` to gracefully skip without errors.

## 4. Conclusion

1. **Requirement R2 (Email on Admin Role Grant)**:
   - Add `send_admin_role_granted_email(...)` to `backend/app/services/email_service.py` with enterprise HTML and plain-text templates detailing the admin role, granted capabilities, assigned timestamp, and acting admin.
   - Call this function in `update_user_roles` (`backend/app/api/routes/admin_users.py`) **after** `await db.commit()`, wrapped in an isolated `try...except Exception` block.
   - Include optional delivery metadata (`admin_email_sent`, `email_delivery_message`) in the response envelope, matching the existing `create_user` convention.

2. **Requirement R1 (Frontend Role Change Detection)**:
   - Publish a `role_updated` event via `approval_event_bus.publish(...)` right after database commit in `update_user_roles`.
   - Refine the 401 exception in `auth_utils.py` to include structured detail `{"code": "AUTH_VERSION_CHANGED", "reason": "ROLE_OR_SESSION_UPDATED"}`.
   - Frontend `DataSyncController` catches the SSE event, matches `current_user.id`, and prompts the user to reload or triggers an automatic refresh.

## 5. Verification Method

1. **Unit Tests (Email Templates & Logic)**:
   - Command:
     ```bash
     cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" poetry run pytest tests/test_email_service_templates.py -v
     ```
   - Verify template generation, XSS escaping, and plain-text parity.

2. **Integration Test (Role Update & Email Mock)**:
   - Add a test in `backend/tests/test_admin_user_role_notification.py` mocking `_send_smtp_sync`:
     - Test that promoting a user to admin calls `_send_smtp_sync` with the target user's email, subject, and privilege details.
     - Test that when `_send_smtp_sync` raises an exception (simulating SMTP down), the database transaction still succeeds, the user's role is updated to admin, and the endpoint returns HTTP 200.
     - Test that the SSE event bus receives `role_updated` with `is_admin=True`.
