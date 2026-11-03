# Progress Tracking — Milestone M1

Last visited: 2026-11-02T15:10:00Z
Status: In Progress

## Tasks
- [ ] Read mandatory docs: ORIGINAL_REQUEST.md, PROJECT.md, survey_frontend.md, handoff.md, AGENTS.md
- [ ] Inspect existing code:
  - backend/app/api/routes/admin_users.py and email_service
  - frontend/lib/src/features/commerce/commerce_workspace.dart
  - frontend/lib/src/features/commerce/commerce_api.dart
  - frontend/lib/src/features/commerce/commerce_memory_store.dart
- [ ] Step 1: Backend - Admin role change email notification (`backend/app/api/routes/admin_users.py`)
- [ ] Step 2: Backend test - `backend/tests/test_admin_role_email_notification.py` & run pytest
- [ ] Step 3: Frontend - Overview tab redesign with 6 operational KPI cards & 7 subsystem launch tiles (`commerce_workspace.dart`)
- [ ] Step 4: Frontend - Silent background data reload (every 60s / resume >30s) in `commerce_workspace.dart` and `commerce_api.dart`
- [ ] Step 5: Frontend - 401 Session revoked detection & session refresh dialog (`commerce_api.dart`, `commerce_workspace.dart`)
- [ ] Step 6: Frontend test - `frontend/test/homepage_subsystem_sync_test.dart` & run flutter test
- [ ] Step 7: Final verification & handoff report
