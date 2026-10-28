# Audit & Plan — Multi-module UI Redesign (VKHO-inspired) cho QuanLyKho

**Trạng thái:** Audit + plan (không sửa code). Tài liệu handoff cho lượt triển khai kế tiếp.
**Ngày:** 2026-10-26
**Phạm vi:** Frontend Flutter (web adaptive) + backend FastAPI contract + RBAC + ledger invariants. Không thay đổi PRD/MVP.
**Tham chiếu:** `docs/PLAN_UI_REDESIGN_VKHO_INSPIRED.md`, `AGENTS.md`, `docs/00-decisions.md`, `docs/01-prd.md`, `docs/02-roadmap.md`, `docs/SRS_QUAN_LY_KHO_TRA_SUA.md`, `docs/acceptance/2026-10-26-milk-tea-baseline.md`.

## 1. Kết luận audit nhanh

- **Backend hiện tại đã đủ để hỗ trợ shell mới mà không cần API mới**: inventory, requests, approvals, cash_sim, reports, activity, notifications, dashboard, integrations, ETL, admin_users, auth, demo. Không cần thay đổi schema/ledger.
- **Frontend hiện tại là một Flutter app adaptive với 10 index tab** (`AppShell` index 0–9; tab 5 Tích hợp/ETL đang ẩn). Điều hướng đã có bottom bar + More sheet trên màn hình hẹp, sidebar/rail có nhóm mục trên màn hình lớn, top bar ở màn hình không-wide. Chưa có menu con đa cấp, breadcrumb hoạt động trong app shell, hoặc routing theo URL cho từng tab.
- **Landing công khai đã tồn tại** tại `frontend/lib/src/features/landing/landing_screen.dart` và được chọn bởi `_AuthGate` trong `frontend/lib/main.dart`. Trang có hero, phần năng lực cốt lõi, footer và CTA đăng nhập. CTA “Trải nghiệm demo” hiện gọi cùng callback với “Đăng nhập”, nên chưa mở một luồng demo riêng. Đăng ký hiện là dialog mở từ trang đăng nhập; chấp nhận lời mời là màn hình riêng.
- **VKHO chỉ dùng làm cảm hứng về cấu trúc thông tin** (sidebar nhóm nghiệp vụ, header search/notify/profile, breadcrumb). Không sao chép thương hiệu/câu chữ/hình ảnh.
- **MVP thực tế là kho trà sữa + ca làm việc**, không phải bán lẻ đa phân hệ. Các module đề xuất (bán hàng, sửa chữa, trả hàng, chi nhánh, khách hàng, nhà cung cấp) **chưa tồn tại** trong code/DB và **không được thêm** trừ khi PRD/SRS được cập nhật có chủ đích.
- **Core invariants phải giữ nguyên**: ledger-first inventory, UOM conversion, MAC valuation, maker≠checker, idempotency, audit append-only, SSE replay.

## 2. Current-state matrix — Frontend Flutter

Nguồn: `frontend/lib/src/features/**`, `frontend/lib/src/app/app_shell.dart`, `frontend/lib/src/core/util/role_visibility.dart`.

| # | Màn hình (file) | Route/tab index | Backend backing | Trạng thái | Ghi chú redesign |
|---|---|---|---|---|---|
| 0 | `dashboard/dashboard_screen.dart` | 0 Tổng quan | `/dashboard/*` | Hoạt động | Giữ, nâng cấp layout responsive + KPI cards |
| 1 | `inventory/inventory_screen.dart` | 1 Kho | `/inventory/items,locations,balances,movements` | Hoạt động | Giữ, thêm empty/loading/error states |
| 1b | `inventory/shift_stocktake_desk.dart` | (sub) | `/inventory/stocktakes` | Hoạt động | Giữ trong Kho |
| 1c | `inventory/import_items_dialog.dart` | (sub) | `/inventory/items` | Hoạt động | Giữ |
| 2 | `cash/cash_screen.dart` | 2 Ca làm việc | `/cash-sim/*` | Hoạt động | Giữ; adjustment dialog theo capability |
| 2b | `cash/cash_adjustment.dart` | (sub) | `/cash-sim/journals` | Hoạt động | Giữ |
| 3 | `requests/requests_screen.dart` | 3 Yêu cầu | `/inventory/requests` | Hoạt động | Giữ; timeline sub-component |
| 3b | `requests/request_timeline.dart` | (sub) | `/inventory/requests/{id}` | Hoạt động | Giữ |
| 4 | `approvals/approvals_screen.dart` | 4 Duyệt | `/approvals/*` | Hoạt động | Giữ; SSE replay |
| 5 | `integrations/integrations_screen.dart` + `import_screen.dart` | 5 Tích hợp/ETL (ẩn pilot) | `/integrations/*` | Ẩn UI (`hiddenPilotTabs={5}`) | Giữ ẩn; backend giữ rollback |
| 5b | `etl/etl_studio_screen.dart`, `etl_run_screen.dart`, `etl_review_screen.dart` | (sub của 5) | `/etl/*` | Ẩn UI | Giữ ẩn |
| 6 | `activity/activity_screen.dart`, `activity_center.dart` | 6 Hoạt động | `/activity/*`, `/audit-events` | Hoạt động | Giữ |
| 7 | `reports/reports_screen.dart` (+ `reports_filter.dart`) | 7 Báo cáo | `/reports/*` | Hoạt động | Giữ; filter responsive |
| 8 | `settings/settings_screen.dart` | 8 Cài đặt | `/auth/*` (profile) | Hoạt động | Giữ |
| 9 | `admin/employee_management_screen.dart` | 9 Quản trị nhân viên | `/admin/users/*` | Theo capability | Giữ; role-aware |
| — | `landing/landing_screen.dart` | Public (AuthGate khi chưa đăng nhập) | Không có API riêng | Hoạt động | Tái sử dụng khung hero/features; làm rõ CTA demo vì hiện dẫn vào login |
| — | `auth/login_screen.dart`, `accept_invite_screen.dart`, `auth/widgets/register_dialog.dart` | Auth flow | `/auth/login, /auth/accept-invite, /auth/register` | Hoạt động theo flow hiện có | Giữ auth; đăng ký là dialog, invite là màn hình riêng |
| — | `ai/ai_assistant_dialog.dart`, `ai_voucher_audit.dart` | Modal | `/ai/*` | Hoạt động (P3 gap G11) | Giữ như enhancement, không phải core module |

**Navigation model hiện tại:** `RoleVisibility.visibleTabs()` trả list index; `hiddenPilotTabs={5}`; auditor-only ẩn tab 3/4. `_navRail` trong `app_shell.dart` hiển thị sidebar rộng 256 px trên màn hình wide, rail 88 px ở màn hình medium, có các section header tĩnh; màn hình compact dùng bottom bar + More sheet. Đây là nhóm mục phẳng, chưa phải menu cha/con có thể thu gọn. Chưa thấy breadcrumb được gắn vào app shell hoặc router duy trì URL theo tab. Landing công khai có trong `_AuthGate`, không phải route URL riêng.

**Auth/RBAC client:** `RoleVisibility` là allowlist fail-open cho role lạ; backend là nguồn chuẩn. Capabilities: `iam:admin`, `etl:admin/design/run`, `cash:post_adjustment`. Vai trò seed: admin/staff/approver/auditor (backend) vs maker/checker/auditor (HTTP fallback).
## 3. Current-state matrix — Backend routes (không đổi)

| Route module | File | Endpoints chính | Module redesign tương ứng | Ghi chú |
|---|---|---|---|---|
| auth | `auth.py`, `auth_google.py`, `auth_utils.py` | login, invite, profile, google | Auth/demo landing | Giữ contract |
| dashboard | `dashboard.py` | KPI/overview | Tổng quan | Giữ |
| inventory | `inventory.py` (3450 LOC) | items, locations, balances, movements, requests, stocktakes, costing | Danh mục & kho, Nhập/Xuất, Kiểm kê, Sổ biến động, Giá vốn | Giữ; ledger-first |
| approvals | `approvals.py` | approve/reject | Duyệt | Giữ; maker≠checker |
| cash_sim | `cash_sim.py` | balances, journals, adjustments | Sổ quỹ (simulated) | Giữ; chỉ VND mô phỏng |
| reports | `reports.py` | aggregation | Báo cáo & đối soát | Giữ |
| activity | `activity.py` | audit events | Hoạt động | Giữ; append-only |
| notifications | `notifications.py` | notify | Header notifications | Giữ |
| events | `events.py` | SSE | Realtime | Giữ |
| integrations | `integrations.py` | staging import/export | Tích hợp | Giữ ẩn |
| etl | `etl.py` | pipeline design/run/review | ETL Studio | Giữ ẩn |
| admin_users | `admin_users.py` | IAM | Quản trị nhân viên | Giữ |
| reconciliations | `reconciliations.py` | recon | Đối soát | Giữ |
| intake | `intake.py` | intake | Nhập hàng (partial) | Giữ |
| demo | `demo.py` | demo | Demo landing (nếu bật) | Kiểm tra an toàn trước khi expose |
| ai, ai_forecasting | `ai*.py` | LLM assist | Enhancement (P3 gap G11) | Giữ optional |
| sync_requests | `sync_requests.py` | offline sync | Offline (P2) | Giữ |
| health | `health.py` | health | Infra | Giữ |

**Kết luận:** Không cần endpoint mới cho Phase 1 (shell/nav/auth landing). Mọi module đề xuất trong plan đều map được vào route hiện có; module "chưa hỗ trợ" (bán hàng, sửa chữa, trả hàng, chi nhánh, khách hàng, nhà cung cấp) **không có backend** → không được thêm menu/claim.

## 4. Gap analysis — Proposed modules vs current MVP

| Module đề xuất (plan) | Trạng thái backend | Trạng thái UI | Quyết định |
|---|---|---|---|
| 1 Tổng quan | Có (`/dashboard`) | Có | Giữ, nâng cấp |
| 2 Danh mục & kho | Có (`/inventory/items,locations`) | Có (tab Kho) | Giữ |
| 3 Nhập hàng | Có (`/intake`, `/inventory/requests` type ISSUE/TRANSFER/ADJUSTMENT) | Có (Yêu cầu) | Giữ; không thêm "nhà cung cấp" entity (chưa có) |
| 4 Xuất hàng | Có (request types) | Có (Yêu cầu) | Giữ; không thêm "khách hàng" entity (chưa có) |
| 5 Kiểm kê & điều chỉnh | Có (`/inventory/stocktakes`, adjustment) | Có (sub-desk) | Giữ |
| 6 Sổ biến động tồn | Có (`/inventory/movements`) | Có (trong Kho) | Giữ; tách thành view riêng nếu cần |
| 7 Giá vốn (MAC) | Có (costing trong inventory) | Partial | Giữ; tuân quyền truy cập |
| 8 Báo cáo & đối soát | Có (`/reports`, `/reconciliations`) | Có | Giữ |
| 9 Sổ quỹ | Có (`/cash-sim`) | Có (Ca làm việc) | Giữ; chỉ mô phỏng |
| 10 Hoạt động & audit | Có (`/activity`, audit-events) | Có | Giữ |
| 11 Quản trị người dùng | Có (`/admin/users`) | Có (tab 9) | Giữ; capability-gated |
| 12 Tích hợp/ETL | Có (ẩn) | Ẩn pilot | Giữ ẩn |
| 13 AI assist | Có (optional) | Modal | Giữ optional (G11) |
| — Bán hàng / Sửa chữa / Trả hàng / Chi nhánh / Khách hàng / Nhà cung cấp | **Không có** | **Không có** | **Không thêm** cho đến khi PRD/SRS cập nhật + backend/model/migration được phê duyệt |

**Kết luận gap:** Landing và responsive navigation đã có nền tảng đáng tái sử dụng. Khoảng trống chính là **CTA/demo chưa có hành vi riêng; điều hướng chưa có menu con/breadcrumb/URL state; và shell chưa được chuẩn hóa theo sitemap mới**. Đây là enhancement, không phải bằng chứng cho thấy backend cần viết lại. Cần kiểm tra các thay đổi đang có trong working tree trước khi tiếp tục: hiện có chỉnh sửa `frontend/lib/src/core/i18n/app_i18n.dart` và các file chưa track dưới `frontend/lib/src/app/widgets/` cùng `frontend/test/sidebar_breadcrumb_test.dart`; không ghi đè hoặc quy chúng thành thay đổi của audit này.

## 5. Phase 1 scope — Shell, Navigation, Auth/Demo Landing

**Mục tiêu:** Có khung quản trị nhất quán (sidebar đa cấp thu gọn/mở rộng, header search/notify/profile, breadcrumb, route-level content) + hành trình công khai (landing/login/register/demo nếu backend hỗ trợ) + responsive 360/768/1280, **không thay đổi API/ledger**.

### 5.1 In scope (Phase 1)

1. **Public landing**: cải tiến `LandingScreen` hiện có; giữ CTA đăng nhập. Chỉ đổi CTA demo thành luồng thật sau khi xác minh demo endpoint/session an toàn. Đăng ký tiếp tục dùng flow hiện có trừ khi có yêu cầu sản phẩm cho route riêng.
2. **Auth routes**: login, accept-invite, (register nếu backend có). Giữ JWT flow hiện tại.
3. **App shell nâng cấp**: mở rộng sidebar/rail hiện có thành điều hướng có nhóm rõ ràng (menu con chỉ khi cần), header (search, notifications, profile menu), breadcrumb và trạng thái tab; chỉ thêm URL routing nếu phù hợp cấu trúc Flutter hiện có. Giữ 10 index tab hiện có, nhóm theo nghiệp vụ:
   - Tổng quan
   - Kho & kiểm kê (Kho, Kiểm kê, Sổ biến động, Giá vốn)
   - Giao dịch (Yêu cầu, Duyệt)
   - Quỹ (Ca làm việc)
   - Báo cáo & đối soát
   - Hoạt động
   - Cài đặt
   - Quản trị (nhân viên) — capability-gated
   - Tích hợp/ETL — ẩn pilot (giữ rollback)
4. **Role-aware visibility**: tái sử dụng `RoleVisibility`; không thay đổi logic quyền; backend vẫn là nguồn chuẩn.
5. **Responsive**: 360/768/1280; bảng dữ liệu có horizontal scroll / card fallback trên mobile; không tràn ngang ngoài chủ đích.
6. **States**: empty/loading/error/success + permission-denied cho mọi route.
7. **Keyboard accessibility**: sidebar điều hướng bằng bàn phím, focus visible, ARIA labels (web).

### 5.2 Out of scope (Phase 1)

- Module mới (bán hàng, sửa chữa, trả hàng, chi nhánh, khách hàng, nhà cung cấp) — cần PRD/SRS update.
- Thay đổi API/DB/migration.
- Thay đổi ledger/UOM/MAC logic.
- Offline write (P2, giữ sync_requests).
- AI quyết định phê duyệt (ngoài phạm vi MVP).

### 5.3 Acceptance criteria (Phase 1)

- [ ] Hành trình công khai → đăng nhập → vào app hoàn tất; lỗi/thành công có thông báo; quyền truy cập rõ.
- [ ] Tất cả mục điều hướng đã bật trỏ tới trang hoạt động hoặc trạng thái "chưa hỗ trợ" được thiết kế chủ động; không có link chết.
- [ ] Sidebar đa cấp hoạt động bằng chuột + bàn phím, thu gọn/mở rộng, giữ chỉ báo route hiện hành; header + breadcrumb nhất quán.
- [ ] Layout kiểm tra ở 360, 768, 1280 px; không mất thao tác cốt lõi; không tràn ngang ngoài chủ đích.
- [ ] Giao diện role-aware khớp quyền server; kiểm tra trực tiếp API/route vẫn chặn đúng thao tác trái quyền.
- [ ] Phiếu nháp không đổi tồn; chỉ luồng hoàn tất hợp lệ ghi một lần movement; retry không nhân đôi (invariant giữ nguyên).
- [ ] Balance sau giao dịch khớp ledger; đồng thời cập nhật movement/balance/audit/outbox nguyên tử.
- [ ] Quy đổi đơn vị dùng hệ số chụp trên dòng chứng từ; MAC đúng công thức.
- [ ] Báo cáo có lọc/phân trang và số khớp nguồn chuẩn; empty/loading/error + demo phân biệt.
- [ ] QA theo quy trình repo; cập nhật acceptance evidence + docs trước phát hành.

### 5.4 Rủi ro & giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| Phá vỡ navigation hiện có (10 tab index) | Giữ index mapping; chỉ đổi presentation layer; thêm integration test route |
| Role visibility regression | Tái sử dụng `RoleVisibility`; thêm unit test cho visibleTabs |
| Public landing claim sai năng lực | Chỉ expose CTA cho nhánh backend hỗ trợ; gate demo bằng `/demo` + kiểm tra an toàn |
| Responsive regression | Visual regression ở 360/768/1280; manual UAT |
| Drift giữa client menu và server RBAC | Client chỉ ẩn/hiện; server vẫn enforce (invariant #12) |

## 6. Branch sync strategy (trước khi implement)

**Trạng thái lúc audit:** đang ở branch `feat/ui-shell-redesign-phase1`. Working tree đã có thay đổi chưa commit ở frontend (`app_i18n.dart`, `frontend/lib/src/app/widgets/`, `frontend/test/sidebar_breadcrumb_test.dart`). Đây là trạng thái quan sát được tại thời điểm audit; cần giữ nguyên và đọc diff trước khi sửa cùng khu vực.

**Khuyến nghị:** không checkout/rebase/merge trong bước audit. Trước khi triển khai, xem diff của các file frontend chưa commit để tránh ghi đè công việc đang dở; chỉ sync branch nếu workflow hiện hành yêu cầu.

## 7. Deliverables đã có / sẽ có

- `docs/PLAN_UI_REDESIGN_VKHO_INSPIRED.md` (đã có) — định hướng UX/UI.
- `docs/AUDIT_UI_REDESIGN_CURRENT_STATE.md` (tài liệu này) — audit + plan Phase 1.
- (Kế tiếp) `docs/acceptance/...-ui-redesign-phase1.md` — bằng chứng QA.
- (Kế tiếp) Cập nhật `docs/13-backlog.md` với Phase 1 tickets (không sửa gap-register).

## 8. Chỉ dẫn cho lượt triển khai kế tiếp

Đọc `AGENTS.md`, tài liệu này, `docs/PLAN_UI_REDESIGN_VKHO_INSPIRED.md`, PRD/SRS/decisions/roadmap/architecture/database/workflows/API/QA/acceptance mới nhất. Kiểm tra `git status` và giữ nguyên thay đổi có sẵn. Audit lại frontend routes/screens/components, backend routes/schemas/services/models/migrations, auth/RBAC, tests và UI acceptance evidence trước khi sửa. Lập ma trận có đường dẫn/bằng chứng, xác định gaps, đối chiếu mâu thuẫn với MVP ca trà sữa. Không giả định tính năng đã tồn tại từ tên trường; không thêm module ngoài phạm vi đã được chấp thuận. Sau audit, đề xuất lát cắt đầu tiên nhỏ, giữ API/kiến trúc đang chạy, kèm acceptance và rủi ro trước khi triển khai. Khi triển khai được yêu cầu, sửa theo convention repo, chỉ thêm/sửa test phù hợp thay đổi và báo cáo chính xác phần đã kiểm chứng cùng phần còn thiếu bằng chứng. Dùng vkho.vn làm cảm hứng về cấu trúc thông tin; thiết kế nhận diện, nội dung và hình ảnh riêng cho QuanLyKho.

