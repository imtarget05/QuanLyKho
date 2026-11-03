# Handoff Report — Reviewer 2 (Architecture & Systems Reviewer)

**Working Directory:** `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/reviewer_m1_2/`  
**Target Milestone:** Milestone 1 (Backend Admin Grant Email & Resilience)  
**Parent Orchestrator:** `eb3ef222-d19e-45a6-a876-1ab4961ac627`  
**Verdict:** **APPROVE**

---

## 1. Observation

1. **Database Commit vs. Email Dispatch Order (`backend/app/api/routes/admin_users.py`)**:
   - Lines 658–664:
     ```python
     is_newly_admin = bool(
         (after & {"admin", "system_admin", "root_admin"})
         and not (before & {"admin", "system_admin", "root_admin"})
     )

     await db.commit()
     await db.refresh(user)
     ```
   - Lines 686–705:
     ```python
     if is_newly_admin:
         if user.email:
             try:
                 await send_admin_role_granted_email(
                     to_email=user.email,
                     username=user.username,
                     display_name=getattr(user, "display_name_demo", None) or getattr(user, "display_name", None),
                     new_roles=cleaned_roles,
                     granted_by_username=current_user.username if current_user else None,
                 )
             except Exception as exc:
                 logger.warning(
                     "Không thể gửi email thông báo cấp quyền admin tới %s (user: %s): %s",
                     user.email,
                     user.username,
                     exc,
                     exc_info=True,
                 )
         else:
             logger.info("Bỏ qua gửi email cấp quyền admin vì user '%s' không có email.", user.username)
     ```
   - Line 707:
     ```python
     return {"user": await _user_to_dict(db, user), "message": "Cập nhật vai trò thành công."}
     ```
   - Observation: `await db.commit()` strictly precedes email execution. The email call is wrapped in a dedicated `try ... except Exception:` block. Any exception during dispatch is logged as a warning; the route proceeds to return `HTTP 200` with the committed user data.

2. **Email Service Implementation & Templates (`backend/app/services/email_service.py`)**:
   - Lines 686–713:
     ```python
     def _build_admin_role_granted_html(...) -> str:
         raw_full_name = (display_name or "").strip() or username
         full_name = html.escape(raw_full_name)
         safe_username = html.escape(username)
         safe_email = html.escape(to_email if to_email else "Email đăng ký của bạn")
         safe_time = html.escape(granted_at_str)
         safe_app_url = html.escape(app_url)

         role_labels = [_ROLE_TITLES.get(r.lower(), r) for r in (new_roles or [])]
         role_desc = html.escape(", ".join(role_labels) if role_labels else "Quản Trị Viên (Admin)")
     ```
   - All user-supplied inputs (`username`, `display_name`, `to_email`, `granted_by_username`, `app_url`) are sanitized with `html.escape`.
   - Lines 919–931: Email format validation via `is_valid_email` (which requires matching `^[^@\s]+@[^@\s]+\.[^@\s]{2,}$`), returning `EmailSendResult(False, ...)` on malformed or empty email.
   - Lines 966–977: Synchronous SMTP execution is offloaded to a thread pool via `await asyncio.to_thread(_send_smtp_sync, ...)`.
   - Lines 146–154: `_send_smtp_sync` configures `timeout=12` and catches `Exception` returning `(False, str(exc))`.

3. **Security Invariant Enforcement (`backend/app/api/routes/admin_users.py`)**:
   - Lines 616–621: Roles validated against catalog table `Role.code` via `_validated_roles(db, body.roles)`. Root modifications require actor to hold `iam:root`.
   - Lines 624–632: Self-modification checks:
     ```python
     if current_user.id == user.id:
         if after - before:
             raise AppError(403, "CANNOT_ESCALATE_SELF", "Không thể tự cấp thêm vai trò cho chính mình.")
         retained_caps = set((await db.execute(
             select(RoleCapability.capability_code).where(RoleCapability.role_code.in_(after))
         )).scalars().all())
         if not retained_caps.intersection(_ADMIN_CAPS):
             raise AppError(400, "CANNOT_DEMOTE_SELF", "Quản trị viên không thể tự gỡ vai trò admin của chính mình.")
     ```

4. **Independent Test Execution Results**:
   - Command 1:
     ```bash
     cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
     .venv/bin/python -m pytest tests/test_admin_user_role_notification.py tests/test_email_service_templates.py -v
     ```
     Result: **19 passed, 3 warnings in 15.80s**
   - Command 2:
     ```bash
     cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
     .venv/bin/python -m pytest tests/test_iam_admin.py -q
     ```
     Result: **11 passed, 3 warnings in 15.88s**
   - Command 3:
     ```bash
     cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
     .venv/bin/python -m pytest tests/test_admin_role_email_notification.py -v
     ```
     Result: **2 passed, 3 warnings in 7.99s**
   - Command 4:
     ```bash
     cd /Users/mainguyenbinhtan/Downloads/QuanLyKho && \
     ./backend/.venv/bin/ruff check backend/app/services/email_service.py backend/app/api/routes/admin_users.py backend/tests/test_admin_user_role_notification.py
     ```
     Result: **All checks passed!** (0 violations)

5. **Integrity Violation Check**:
   - No hardcoded test conditions or expected outputs embedded in source code.
   - No mock facades or shortcut bypasses in application routes.
   - Genuinely independent verification against local PostgreSQL 16 database.

---

## 2. Logic Chain

1. **Transaction Boundary & Resilience**:
   - From Observation 1, `await db.commit()` is executed on line 663 and confirmed before entering lines 666–705.
   - Because PostgreSQL commits atomically, any subsequent failure inside Python cannot undo or roll back the committed transaction.
   - Furthermore, lines 686–703 enclose the async dispatch of `send_admin_role_granted_email` in `try ... except Exception as exc:`.
   - Even under complete SMTP timeout or disconnection (tested via `mock_send_email.side_effect = RuntimeError(...)`), the API endpoint does not return 500; it logs a warning and returns `HTTP 200` with the updated user data.
   - Subsequent database reads verify that the `admin` role is permanently retained in PostgreSQL. This directly fulfills Acceptance Criteria R2.

2. **Trigger Precision & Idempotency**:
   - `is_newly_admin` checks `(after & {"admin", "system_admin", "root_admin"}) and not (before & {"admin", "system_admin", "root_admin"})`.
   - Case A (Normal grant): Staff -> Admin: `before` has no admin, `after` has admin -> Triggers email.
   - Case B (Role update for existing admin): Admin -> Admin + Approver: `before` already has admin -> Does NOT re-trigger email.
   - Case C (Demotion): Admin -> Staff: `after` has no admin -> Does NOT trigger email.
   - Case D (Non-admin change): Staff -> Approver: Neither has admin -> Does NOT trigger email.
   - Case E (Missing email): User has `email = None` or `""` -> `if user.email:` safely branches to log info and skips dispatch without error.

3. **Injection & Security Immunity**:
   - From Observation 2, `_build_admin_role_granted_html` sanitizes every interpolated string using `html.escape`. Malicious payloads (e.g. `<script>`, `<img onerror=...>`, `<style>`) are converted to HTML entities, neutralizing XSS.
   - `is_valid_email` enforces standard email formatting matching `_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")`. Since whitespace (including `\r` and `\n`) is disallowed, CRLF header injection in `to_email` is rejected.
   - From Observation 3, IAM self-escalation is blocked via `CANNOT_ESCALATE_SELF` (403), and self-demotion stripping admin privileges is blocked via `CANNOT_DEMOTE_SELF` (400).

---

## 3. Caveats

- **Dual Email Triggering during Admin Promotion**:
  In `update_user_roles` (lines 666–684), `email_service.send_email(...)` is called for any role update if `user.email` is present, followed by `send_admin_role_granted_email(...)` if `is_newly_admin`. When an admin role is granted, two emails are queued: a generic role update notice and the specialized admin privilege notice. Both are properly error-handled and non-fatal, but in a future refactor, the generic email can be bypassed if `is_newly_admin` is True to avoid redundant notifications.
- **Synchronous Await in Request Cycle**:
  `send_admin_role_granted_email` is executed in a worker thread (`asyncio.to_thread`), preventing event-loop starvation. However, the client request awaits completion before returning HTTP 200. If an unconfigured SMTP host hangs until the 12-second timeout, the individual HTTP request will experience latency up to 12s. For production scale, offloading email dispatch to an asynchronous Outbox worker / Celery task is recommended. For Milestone 1, the current pattern satisfies all specified constraints.

---

## 4. Conclusion

**Verdict: APPROVE**

Milestone 1 satisfies all functional requirements, security invariants, transaction boundary guarantees, and test acceptance criteria without integrity violations:
- Commit boundary is strictly enforced prior to email dispatch.
- Zero database rollback under email failure.
- API remains fully resilient (HTTP 200) under SMTP timeouts and network drops.
- Anti-XSS and role transition safeguards are verified.
- Test suites pass 100% (32 passed, 0 failed, 0 linter errors).

---

## 5. Verification Method

To independently re-verify all observations:

1. **Test Admin Role Notifications and Templates (19 tests)**:
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
   DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
   .venv/bin/python -m pytest tests/test_admin_user_role_notification.py tests/test_email_service_templates.py -v
   ```

2. **Test IAM Admin Invariants & Security (11 tests)**:
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
   DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
   .venv/bin/python -m pytest tests/test_iam_admin.py -q
   ```

3. **Test Role Email Outbox Resilience (2 tests)**:
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
   DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
   .venv/bin/python -m pytest tests/test_admin_role_email_notification.py -v
   ```

4. **Verify Ruff Lint Compliance**:
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho
   ./backend/.venv/bin/ruff check backend/app/services/email_service.py backend/app/api/routes/admin_users.py backend/tests/test_admin_user_role_notification.py
   ```

### Invalidation Conditions:
- If `PUT /admin/users/{user_id}/roles` fails with HTTP 500 when `send_admin_role_granted_email` throws an exception, resilience is invalidated.
- If the role in PostgreSQL reverts to non-admin upon email failure, transaction finality is invalidated.
- If raw `<script>` tags are unescaped in HTML email templates, XSS protection is invalidated.
