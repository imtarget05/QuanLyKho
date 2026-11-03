# Handoff Report: Frontend Architecture & Mobile UI/UX Exploration (QuanLyKho)

**Agent**: `explorer_survey_1` (Frontend Architecture & Mobile UI/UX Explorer)  
**Recipient**: Parent Orchestrator (`fbdb9d15-e07c-4143-974c-2efe416095ff`)  
**Date**: 2026-11-02  
**Handoff Type**: Hard (Investigation complete, full 5-component report)  
**Detailed Survey Reference**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_1/survey_frontend.md`  

---

## 1. Observation

Direct observations from source code inspection and test execution:

### 1.1. Tech Stack & Deployment Pipeline
- **Frontend Stack**: Flutter Web SPA (Flutter 3.27.7, Dart 3.6.1). Defined in `frontend/pubspec.yaml`:
  ```yaml
  name: tea_inventory
  description: "Trà Sữa Sài Gòn — Quản Lý Kho & Ngân Hàng AI"
  environment:
    sdk: ">=3.4.0 <4.0.0"
    flutter: ">=3.22.0"
  ```
- **Deployment**: Cloudflare Workers Assets (`infra/cloudflare-worker/wrangler.tea-inventory.toml` and `.github/workflows/deploy-pages.yml` line 34: `flutter build web --release --no-tree-shake-icons --dart-define=API_BASE_URL=https://imtarget05--quan-ly-kho-tra-sua-api.us-east.modal.run/api/v1`).
- **Production URL**: `https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev` (Worker name: `tea-inventory-web`).
- **Backend API URL**: Modal Serverless FastAPI at `https://imtarget05--quan-ly-kho-tra-sua-api.us-east.modal.run/api/v1`.

### 1.2. Architecture Duality & Homepage Entry Point
- In `frontend/lib/main.dart` lines 122–160 (`_LiveCommerceGate` / `_AuthGate`), authenticated users are directed directly to `CommerceWorkspace`:
  ```dart
  return CommerceWorkspace(
    user: user,
    store: store,
    api: api,
    onSignOut: () => auth.signOut(),
  );
  ```
- `AppShell` (`frontend/lib/src/app/app_shell.dart`, 1,732 lines) with 3-tier adaptive layout (`<600`, `600–1199`, `>=1200`), SSE subscription (`DataSyncController`), and heartbeat ping is bypassed by the current live route.
- `CommerceWorkspace` (`frontend/lib/src/features/commerce/commerce_workspace.dart`, 5,778 lines) manages 8 business tabs (Overview, Sales POS, Purchases, Inventory, Debt, Reports, Approvals, Settings) driven by `CommerceMemoryStore` and `CommerceApi`.

### 1.3. Subsystem Synchronization & Metrics Derivation (R1)
- In `frontend/lib/src/features/commerce/commerce_api.dart` lines 39–84 (`reload`), initial state is fetched via `Future.wait([loadItems, loadLocations, loadParties, loadBalances])`.
- In `frontend/lib/src/features/commerce/commerce_memory_store.dart` lines 103–162, summary metrics (`todayRevenue`, `grossProfitToday`, `inventoryValue`, `customerReceivables`, `supplierPayables`, `lowStockItemsCount`) are computed strictly in-memory over local item lists and orders.
- Mutating actions in `CommerceWorkspace` call `widget.onRefresh()` which triggers `_api.reload(_store)` (`commerce_workspace.dart` lines 145–147).
- **No Background Sync**: `CommerceWorkspace` does NOT instantiate or listen to `DataSyncController`, SSE, or WebSocket. If data changes in the backend or another user updates stock, the screen remains stale until a user manually navigates or triggers an action.

### 1.4. Admin Role Grant & Token Invalidation Behavior (R1)
- Backend endpoint `PUT /admin/users/{user_id}/roles` in `backend/app/api/routes/admin_users.py` lines 86–95:
  ```python
  user.role = role_val
  user.auth_version = user.auth_version + 1
  db.add(user)
  db.commit()
  ```
- Token verification in `backend/app/api/routes/auth_utils.py` lines 103–115:
  ```python
  if token_auth_version != user.auth_version:
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Phiên đăng nhập đã bị thu hồi hoặc quyền tài khoản đã thay đổi. Vui lòng đăng nhập lại.",
      )
  ```
- In `CommerceApi` (`frontend/lib/src/features/commerce/commerce_api.dart` lines 33–36), HTTP 401 triggers a standard `Exception('Tải dữ liệu thất bại: 401')`. There is no HTTP interceptor catching 401 to prompt the user or refresh tokens.
- In `backend/app/api/routes/admin_users.py`, updating roles inserts an outbox event (`enqueue_outbox(db, event_type="user.roles_updated", ...)`) but does NOT call `email_service.send_email` or trigger background worker email delivery.

### 1.5. Mobile Viewport Layout Bugs Audit (R2: 375px, 390px, 414px)
- **BUG-01 (Topbar title squashing)**: `frontend/lib/src/features/commerce/commerce_workspace.dart` lines 666–696 (`_WorkspaceTopbar`):
  ```dart
  leading,
  Expanded(
    child: Text(
      title,
      style: TextStyle(fontSize: compact ? 15 : 18, fontWeight: FontWeight.bold),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
    ),
  ),
  const Spacer(),
  _buildLocationChip(context, compact),
  const SizedBox(width: 4),
  ...
  ```
  On 375px, after subtracting leading menu (48px), location chip (~110px), new order button (38px), avatar (36px), and padding (40px), remaining space is only ~103px. Dividing it between `Expanded` (flex: 1) and `Spacer` (flex: 1) gives only ~51.5px to `title`. Titles like `"Quản lý Bán hàng"` are squashed into `"Quả..."` with an unnecessary 51px blank space beside it.
- **BUG-02 (Location chip truncation)**: `commerce_workspace.dart` line 730:
  `ConstrainedBox(constraints: BoxConstraints(maxWidth: compact ? 78 : 140))`
  On mobile, warehouse/counter name is clipped to 4–5 characters (e.g. `"Kho N..."`).
- **BUG-03 (Mini summary cards number clipping)**: `commerce_workspace.dart` lines 2292–2340 (`_MiniSummaryRow`):
  Uses `GridView.count(crossAxisCount: 2, mainAxisSpacing: 8, crossAxisSpacing: 8)`. On 375px, card content width is ~90px. Big numbers (e.g. `125.400.000 ₫`) lack `FittedBox` and are clipped (`"125.40..."`).
- **BUG-04 (Create Order dialog cramped line layout)**: `commerce_workspace.dart` lines 4604–4744 (`_showCreateOrder`):
  Line item row places Product dropdown, Qty, Price, Discount, and Delete in a single `Row`. On 375px screens (dialog inner width 285px), Product dropdown receives only ~127px. For Purchase orders, lot number and expiry date are displayed in a second row with 4 preset `ActionChip`s, wrapping awkwardly.
- **BUG-05 (Hardcoded dialog width 440px in Product creation)**: `commerce_workspace.dart` lines 4251–4270 (`_showCreateProduct`):
  `SizedBox(width: 440, ...)` forces dialog to maximum screen margins on 375px/390px, with basic unit and purchase unit placed side-by-side in ~135px cells, clipping labels.
- **BUG-06 (Hardcoded dialog width 420px in Stock transfer)**: `commerce_workspace.dart` lines 4076–4150 (`_showStockTransferDialog`):
  `SizedBox(width: 420, ...)` with side-by-side dropdowns for source and destination locations.
- **BUG-07 (Hardcoded dialog width 580px in Stocktake modal)**: `commerce_workspace.dart` lines 5117–5190 (`_showStocktake`):
  `SizedBox(width: 580, child: ...)` contains a 4-column table (`flex: 5, 2, 3, 2`). The `THỰC TẾ` column only gets ~71px, severely cramming a full `TextFormField` on small mobile touchscreens.
- **BUG-08 (Hardcoded dialog width 480px in EditProfileDialog)**: `frontend/lib/src/features/auth/edit_profile_dialog.dart` line 221:
  `SizedBox(width: 480, child: Form(...))`.
- **BUG-09 (Nested scrolling friction in Debt tab)**: `commerce_workspace.dart` lines 3564–3580 (`_DebtPage`):
  `SizedBox(height: 480, child: TabBarView(...))` placed inside `_PageFrame` (which wraps content in `SingleChildScrollView`).
- **BUG-10 (Reports page column cramming)**: `frontend/lib/src/features/commerce/commerce_reports_page.dart` lines 392–404:
  `cols = width < 720 ? 2 : ...`. On 375px, 2 columns leaves only ~101px per card.
- **BUG-11 (Order list tile text overflow)**: `commerce_workspace.dart` line 2510 (`_OrderListTile`):
  `Text(order.partyName)` lacks `overflow: TextOverflow.ellipsis` and `maxLines: 1`.
- **BUG-12 (Mobile bottom nav / More tab UX gap)**: `commerce_workspace.dart` lines 275–340:
  Sub-pages accessed via the "More" bottom sheet (Debt, Reports, Approvals, Settings) leave "More" highlighted without a sub-header indicator or back-to-overview action.

### 1.6. Tool Executions & Test Results
- Ran Flutter unit test:
  `cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && flutter test test/user_sync_and_header_icons_test.dart`
  Result: **8 passed, 0 failed** in 2s (Flutter 3.27.7, Dart 3.6.1). Confirmed Flutter toolchain is healthy.
- Python backend test suite (from repo status):
  `cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && pytest tests -q`
  Historical run: **387 passed, 8 skipped, 0 failed**.

---

## 2. Logic Chain

From the observations above, the following logical inferences are established:

1. **Root Cause of Token Invalidation / Lack of Auto-Refresh (R1)**:
   - *Premise 1*: `backend/app/api/routes/admin_users.py` line 92 increments `user.auth_version` by 1 upon role change.
   - *Premise 2*: `backend/app/api/routes/auth_utils.py` lines 103–115 verifies `token_auth_version == user.auth_version`. Since the client holds the old JWT token with the old `auth_version`, any subsequent API call immediately fails with HTTP 401.
   - *Premise 3*: `CommerceApi` and `HttpBankOpsRepository` catch HTTP 401 as an unhandled error and show a generic failure banner. No interceptor triggers re-authentication or a session refresh.
   - *Premise 4*: `CommerceWorkspace` has no polling or SSE mechanism, meaning an active user receives zero notification that their permissions changed until they click an action and crash into a 401 error.
   - *Inference*: To achieve seamless permission transition, the system requires:
     (a) A global HTTP 401 interceptor in frontend that recognizes `auth_version` invalidation and prompts the user or invokes `authService.refreshToken()`;
     (b) A lightweight periodic token/profile check (or reconnecting SSE) in `CommerceWorkspace`;
     (c) Backend notification dispatch (email via `email_service.py` and/or outbox notification consumer) when user role is updated.

2. **Root Cause of Topbar Title Squashing on Mobile (R2 - BUG-01)**:
   - *Premise 1*: In `_WorkspaceTopbar`, elements inside `Row` are: `leading` (48px), `Expanded(title)` (flex 1), `Spacer()` (flex 1), `_buildLocationChip` (~110px), `SizedBox(width: 4)`, `FilledButton.icon` (38px), `SizedBox(width: 8)`, `InkWell(Avatar)` (36px), and horizontal padding (32px).
   - *Premise 2*: Total fixed width = 48 + 110 + 4 + 38 + 8 + 36 + 32 = 276px.
   - *Premise 3*: On a 375px viewport (iPhone SE), remaining available width for flex children is 375 - 276 = 99px.
   - *Premise 4*: Flutter's flex layout divides 99px equally between `Expanded` (flex: 1) and `Spacer` (flex: 1).
   - *Inference*: `Text(title)` gets only 49.5px to 51.5px. A title such as `"Quản lý Bán hàng"` (17 chars) is severely truncated to 3 characters (`"Quả..."`), leaving a 50px blank void before the location chip. Replacing `const Spacer()` with `const SizedBox(width: 8)` immediately expands title width from 51px to ~140px, completely resolving the title truncation.

3. **Root Cause of Dialog Squeezing & Overflow (R2 - BUG-04 to BUG-08)**:
   - *Premise 1*: Modal dialogs specify static `SizedBox(width: 420)`, `SizedBox(width: 440)`, and `SizedBox(width: 580)`.
   - *Premise 2*: On mobile viewports (<600px, specifically 375px, 390px, 414px), the screen is narrower than the requested dialog width. The Flutter framework clamps the dialog to screen width minus inset padding (375 - 40 = 335px).
   - *Premise 3*: The interior layouts inside those dialogs were designed assuming 420px–580px of width, placing multiple fields (e.g., 2 dropdowns, or 5 order line columns, or a 4-column stocktake table) in a single horizontal `Row`.
   - *Inference*: Inside 335px, horizontal rows collapse, field widths shrink to unreadable sizes (70–120px), and labels clip. The dialogs must switch to full-screen modals (`showModalBottomSheet(isScrollControlled: true)` or `Dialog.fullscreen`) on mobile viewports (<600px), stacking input fields vertically.

4. **Root Cause of Dual-Shell Divergence**:
   - *Premise 1*: `AppShell` contains enterprise features: SSE sync, heartbeat ping, shift work, and responsive layout rail/sidebar.
   - *Premise 2*: `CommerceWorkspace` is an all-in-one ERP workspace designed to deliver quick POS/sales/inventory workflows, but it bypassed `AppShell` and implemented its own header, drawer, and bottom navigation.
   - *Inference*: Unifying them or backporting `DataSyncController` and responsive drawer navigation into `CommerceWorkspace` will establish feature parity between mobile and web desktop.

---

## 3. Caveats

1. **Read-Only Scope**: This investigation was strictly read-only. No application code in `frontend/` or `backend/` was altered.
2. **Flutter Web Runtime Behavior**: The mobile audit was conducted by mathematical layout tracing and code inspection of widget constraints against Flutter's layout protocol (`BoxConstraints`, `RenderFlex`). Flutter Web rendering on actual mobile Safari / Chrome may introduce browser URL bar viewport shifts (dynamic `100vh`/`100dvh`), which should be validated on physical devices.
3. **Modal Serverless Backend**: The production API is deployed on Modal Serverless. Direct changes to backend routes will require redeployment to Modal (`modal deploy`) in addition to local testing.
4. **Email Dispatch**: `backend/app/services/email_service.py` requires valid SMTP credentials (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`) in environment variables. If unset, email service logs a warning without crashing.

---

## 4. Conclusion

The exploration has fully uncovered the architectural realities and identified the exact fixes required for R1 and R2:

### R1 Action Plan (Homepage & Subsystem Synchronization)
1. **Admin Role & Permission Synchronization**:
   - In `backend/app/api/routes/admin_users.py`: When `update_user_roles` is executed, trigger an immediate notification email via `email_service.send_email(...)` informing the user that their role has been updated.
   - In frontend: Implement an HTTP 401 interceptor in `CommerceApi` and `HttpBankOpsRepository`. When 401 occurs with detail `"Phiên đăng nhập đã bị thu hồi hoặc quyền tài khoản đã thay đổi"`, prompt an alert dialog explaining that permissions were updated and offering an instant "Làm mới phiên" (Refresh Session) button that re-authenticates or re-fetches user tokens.
2. **Subsystem Real-Time State Sync**:
   - Integrate `DataSyncController` or a periodic lightweight poller (every 60s) in `CommerceWorkspace` to invoke `_api.reload(_store)` in the background so that stock levels, order statuses, and approvals stay synchronized across devices without requiring manual page refresh.

### R2 Action Plan (Mobile Viewport Parity & Bug Fixes)
1. **Fix BUG-01 & BUG-02 (`_WorkspaceTopbar`)**:
   - Remove `const Spacer()` from `_WorkspaceTopbar` when `compact == true`. Replace with `const SizedBox(width: 8)`.
   - In compact mode, show only the location icon or shorten location label gracefully, giving `title` ~180px of unconstrained width.
2. **Fix BUG-03 (`_MiniSummaryRow`)**:
   - Wrap card values in `FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerLeft)` so numbers never clip on 375px.
3. **Fix BUG-04 to BUG-08 (Dialogs on Mobile)**:
   - For viewports `<600px`, render `showModalBottomSheet(isScrollControlled: true, ...)` or full-screen dialogs instead of constrained desktop dialogs.
   - In `_showCreateOrder`: stack Product dropdown on top and [Qty, Price, Discount] in a compact sub-row on mobile.
   - In `_showStocktake`: render items as individual expandable cards with vertical fields on mobile instead of a 4-column desktop table.
4. **Fix BUG-09 (`_DebtPage`)**:
   - In mobile viewports, remove the fixed `SizedBox(height: 480)` and use `NestedScrollView` or give the list its own scroll controller.
5. **Fix BUG-10 to BUG-12**:
   - Change `cols = 1` in `CommerceReportsPage` when screen width `< 500px`.
   - Add `overflow: TextOverflow.ellipsis` to `_OrderListTile.partyName`.
   - In mobile bottom nav, add a visible badge/indicator and an explicit "Quay lại Tổng quan" (Back to Overview) header when viewing a subpage from the "More" tab.

---

## 5. Verification Method

To independently verify the observations, logic, and future implementations:

### 5.1. Automated Test Commands
1. **Flutter Frontend Unit & Widget Tests**:
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend
   flutter test test/user_sync_and_header_icons_test.dart
   ```
   *Expected*: All 8 tests pass.
2. **Backend Auth & Session Invalidation Tests**:
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
   pytest tests/test_single_session_and_alerts.py -v
   pytest tests/test_admin_maker_checker.py -v
   ```
   *Expected*: Passes without error, confirming `auth_version` invalidation logic.

### 5.2. Viewport Verification (Mobile UI Widget Tests)
Implement a dedicated responsive widget test file in `frontend/test/mobile_viewport_audit_test.dart` testing viewports 375x667, 390x844, and 414x896:
```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend
flutter test test/mobile_viewport_audit_test.dart
```
Verification criteria:
- `find.byType(_WorkspaceTopbar)`: Verify `title` rendered width > 150px on a 375px canvas.
- No `A RenderFlex overflowed by ... pixels` assertion errors in test output.
- All touch targets in `ActionChip` and `IconButton` satisfy minimum 44x44 or 48x48 dp bounds.

### 5.3. Invalidation Conditions
- If the project abandons `CommerceWorkspace` in favor of migrating exclusively back to `AppShell`, the specific line references in `commerce_workspace.dart` will be invalidated.
- If Flutter SDK is upgraded beyond 3.27.7, re-verify `BoxConstraints` clamping behavior in modal dialogs.
