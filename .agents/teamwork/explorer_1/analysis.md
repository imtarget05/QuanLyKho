# Báo Cáo Phân Tích Kỹ Thuật: Frontend QuanLyKho & Cơ Chế Phát Hiện Cập Nhật Quyền Admin (R1)

- **Người thực hiện**: Explorer 1 (Frontend Explorer)
- **Mục tiêu**: Phân tích toàn diện kiến trúc frontend, luồng xác thực/vai trò, cơ chế ẩn/hiện quyền admin, và đề xuất kiến trúc phát hiện & làm mới giao diện khi người dùng được cấp quyền Admin theo Yêu cầu R1.
- **Ngày khảo sát**: 2026-11-02
- **Trạng thái**: Hoàn tất khảo sát (Read-Only)

---

## 1. Kiến Trúc Frontend & Vị Trí Tập Tin

### 1.1. Công nghệ & Nền tảng
- **Framework**: **Flutter** (Dart SDK `>=3.4.0 <4.0.0`). Ứng dụng hỗ trợ đa nền tảng, trong đó mục tiêu chính là **Flutter Web** (deploy qua Cloudflare Workers tại `PUBLIC_WEB_ORIGIN = "https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev"`) cùng mobile (Android/iOS) và Desktop.
- **Quản lý trạng thái (State Management)**: `provider: ^6.1.2` (`ChangeNotifierProvider`, `Consumer`) kết hợp mô hình `InheritedWidget` (`SessionScope`, `RepositoryScope`, `SyncScope`).
- **Lưu trữ phiên & bảo mật**: `flutter_secure_storage: ^9.2.2` (lưu JWT `access_token` và `refresh_token`), `shared_preferences: ^2.3.0` (cấu hình local UI, offline outbox).
- **Giao thức mạng**: `http: ^1.2.0`, tích hợp Server-Sent Events (SSE) stream (`text/event-stream`).

### 1.2. Cấu trúc thư mục & các tập tin trọng yếu
```text
frontend/
├── lib/
│   ├── main.dart                                   # Điểm khởi chạy, MultiProvider, SessionBridge, _AuthGate, _LiveCommerceGate
│   └── src/
│       ├── app/
│       │   ├── app_shell.dart                      # Shell responsive (bottom nav / rail / sidebar), SessionScope, RepositoryScope, SyncScope
│       │   └── theme_mode_controller.dart          # Điều khiển Dark/Light mode
│       ├── core/
│       │   ├── util/
│       │   │   ├── role_visibility.dart            # Logic client-side RBAC: kiểm tra quyền admin, ẩn/hiện tab, nhãn vai trò
│       │   │   ├── web_helpers.dart / _web / _stub # Tiện ích Web: forceAppUpdate() (window.location.reload), PWA install
│       │   │   └── error_text.dart                 # Format lỗi người dùng
│       │   ├── sync/
│       │   │   └── data_sync_controller.dart       # SSE listener & Lifecycle resume & Heartbeat poller
│       │   └── widgets/
│       │       └── user_avatar.dart, app_toast.dart
│       ├── data/
│       │   ├── models/
│       │   │   └── dtos.dart                       # AppUser, RoleDto, EmployeeUserDto
│       │   └── repositories/
│       │       ├── bankops_repository.dart         # Abstract interface
│       │       ├── http_bankops_repository.dart    # Triển khai HTTP + SSE client (/approvals/stream)
│       │       └── fake_repository.dart            # In-memory mock cho reviewer sandbox / test
│       └── features/
│           ├── auth/
│           │   ├── auth_service.dart               # ChangeNotifier trung tâm: đăng nhập, token, autoLogin, updateProfile
│           │   └── login_screen.dart
│           ├── admin/
│           │   └── employee_management_screen.dart # Màn hình Quản trị nhân viên & Cấp phát IAM (Tab 9)
│           └── commerce/
│               ├── commerce_workspace.dart         # Workspace Vận hành ERP/POS chính của ứng dụng
│               ├── commerce_settings_view.dart     # Cài đặt hệ thống, nơi nhúng Employee Management Card
│               └── commerce_api.dart               # HTTP client cho phân hệ commerce
```

---

## 2. Quản Lý Xác Thực, Danh Tính & Vai Trò Người Dùng (Auth & Role Storage)

### 2.1. Cấu trúc lưu trữ dữ liệu người dùng (`AppUser`)
Trong `frontend/lib/src/data/models/dtos.dart` (dòng 5–35):
- `AppUser` là một Immutable Value Object gồm các trường:
  - `id`: `String` (UUID định danh người dùng trong database `iam_users`).
  - `username`: `String`.
  - `displayName`: `String`.
  - `roles`: `List<String>` — danh sách vai trò (ví dụ: `['staff']`, `['admin']`, `['inventory_manager']`, `['root_admin']`).
  - `capabilities`: `List<String>` — danh sách quyền chức năng (ví dụ: `['iam:admin', 'admin:user_management', 'inventory:view_balances']`).
  - `email`, `phoneNumber`, `branch`, `employeeCode`, `avatarUrl`.

### 2.2. Vòng đời phiên làm việc trong `AuthService` (`frontend/lib/src/features/auth/auth_service.dart`)
1. **Lưu trữ Client**:
   - `_user` (`AppUser?`): đối tượng người dùng hiện tại đang lưu trong RAM của `AuthService`.
   - `_memoryToken` (`String?`): Access token lưu trong RAM để tối ưu tốc độ gọi API.
   - `_storage` (`FlutterSecureStorage`): Lưu `access_token` và `refresh_token` trên bộ nhớ an toàn của thiết bị/trình duyệt.
2. **Khởi động & Auto-Login**:
   - Khi ứng dụng mở, `main.dart` gọi `AuthService()..tryAutoLogin()`.
   - `tryAutoLogin()` (dòng 289–328) đọc `access_token` từ storage, gọi `GET {baseUrl}/auth/me` với header `Authorization: Bearer <token>`.
   - Nếu trả về `200 OK`: `_user = _userFromJson(json.decode(resp.body))`, `notifyListeners()` thông báo cho widget tree.
   - Nếu trả về `401` hoặc lỗi: gọi `_clearLocal()` xóa storage và đưa `_user = null` (quay về `LoginScreen`).
3. **Cơ chế phân phối vào Widget Tree**:
   - `TeaInventoryApp` cấu hình `MultiProvider` với `ChangeNotifierProvider(create: (_) => AuthService()..tryAutoLogin())`.
   - `SessionBridge` (trong `main.dart`, dòng 61–86) bọc `TeaInventoryApp.builder` bằng `Consumer<AuthService>`.
   - `SessionBridge` dựng `SessionScope(user: auth.user, onSignOut: auth.signOut, child: ...)`.
   - Toàn bộ cây widget con truy cập thông tin người dùng tức thì qua `SessionScope.maybeOf(context)?.user` hoặc `context.watch<AuthService>().user`. Khi `AuthService` gọi `notifyListeners()`, toàn bộ UI tự động re-render đồng bộ.

---

## 3. Các Vị Trí Gated & Hiển Thị Đặc Quyền Admin Trên Giao Diện

Client phân quyền hiển thị (UI Gating) thông qua lớp tiện ích `RoleVisibility` (`frontend/lib/src/core/util/role_visibility.dart`).

### 3.1. Quy tắc nhận diện Admin trong `RoleVisibility`
- `RoleVisibility.isAdmin(Set<String> roles)` (dòng 62–67):
  ```dart
  static bool isAdmin(Set<String> roles) =>
      roles.contains('admin') ||
      roles.contains('root_admin') ||
      roles.contains('system_admin') ||
      roles.contains('manager') ||
      roles.contains('owner');
  ```
- `RoleVisibility.canManageEmployees(AppUser? user)` (dòng 92–114):
  Kiểm tra xem user có vai trò Admin (`admin`, `root_admin`, `system_admin`, `owner`) hoặc có capability `iam:admin` / `admin:user_management`.
- `RoleVisibility.userRoleLabel(AppUser? user)` (dòng 199–242):
  - Người dùng thường (`staff`): hiển thị nhãn `"Nhân Viên Pha Chế / Quầy"`.
  - Người dùng có quyền Admin: hiển thị nhãn `"Chủ Quán (Admin)"`.

### 3.2. Chi tiết các thành phần UI bị ẩn/hiện theo quyền Admin

| Phân hệ / Màn hình | Vị trí tập tin & Dòng mã | Hành vi khi là Staff (Chưa có Admin) | Hành vi khi được nâng quyền Admin |
| :--- | :--- | :--- | :--- |
| **Workspace Sidebar Navigation** | `commerce_workspace.dart:471–478` | Chỉ hiển thị Tổng quan, Bán hàng, Nhập hàng, Kho, Công nợ, Cài đặt. **Ẩn Tab 5 (Báo cáo)** và **Tab 6 (Duyệt)**. | **Tự động xuất hiện Tab Báo cáo (Reports)** và **Tab Duyệt (Approvals)**. |
| **Chỉ số Tài chính & Lãi lỗ (Overview KPIs)** | `commerce_workspace.dart:1010–1130` | Ẩn toàn bộ doanh thu, lợi nhuận ròng, giá trị tài sản kho, biểu đồ tài chính. | Hiển thị đầy đủ doanh thu thực, chi phí vốn (COGS), biên lợi nhuận, biểu đồ dòng tiền. |
| **Báo cáo Phân tích Chuyên sâu** | `commerce_workspace.dart:196–198` (`CommerceReportsPage`) | Bị chặn, trả về `SizedBox.shrink()` hoặc rơi về trang Overview. | Mở khóa toàn bộ báo cáo doanh số, đối soát ca, xuất file Excel/PDF. |
| **Quản trị Nhân sự & Phân quyền (RBAC)** | `commerce_settings_view.dart:146–149`, `484–542` | Thẻ `"Quản trị Nhân sự & Phân quyền (RBAC)"` trong Settings **bị ẩn hoàn toàn**. | Thẻ xuất hiện với nút `[Quản lý nhân viên]`, mở `EmployeeManagementScreen`. |
| **Màn hình IAM (AppShell Tab 9)** | `app_shell.dart:480–513` (`EmployeeManagementScreen`) | Bị chặn điều hướng, hiện màn hình từ chối: *"Chỉ Quản Trị Viên mới có quyền truy cập..."*. | Mở khóa phân hệ tạo tài khoản nhân viên, phân quyền vai trò, khóa tài khoản, revoke session. |
| **Hộp thư Phê duyệt (Approvals)** | `app_shell.dart:380–410` (`ApprovalsScreen`) | Chặn với nhân viên không có quyền duyệt. | Mở quyền phê duyệt kiểm kê lệch, duyệt phiếu điều chỉnh quỹ và xuất kho. |
| **Quản lý Giá & Danh mục Kho** | `inventory_screen.dart` / `commerce_workspace.dart:149` | Ẩn giá vốn, không cho sửa giá bán hoặc xóa mặt hàng. | Cho phép thêm mới SKU, sửa giá vốn/giá bán, kích hoạt/vô hiệu hóa sản phẩm. |
| **Huy hiệu Vai trò (Profile Badge)** | TopBar / Sidebar Profile Tile | Hiển thị: `"Nhân Viên Pha Chế / Quầy"`. | Đổi ngay thành: `"Chủ Quán (Admin)"`. |

---

## 4. Phân Tích Cơ Chế Phát Hiện Cập Nhật Quyền Từ Phía Backend

### 4.1. Hành vi của Backend khi Admin thực hiện đổi vai trò
Tại endpoint `PUT /api/v1/admin/users/{user_id}/roles` (`backend/app/api/routes/admin_users.py`, dòng 633–654):
```python
    for role_code in after - before:
        db.add(UserRole(user_id=u_uuid, role_code=role_code))

    # Invalidate token version so user gets refreshed permissions
    user.auth_version = getattr(user, "auth_version", 1) + 1

    await _audit(...)
    await _outbox(db, event_type="user.roles_updated", ...)
    await db.commit()
```
**Hệ quả trực tiếp trên hệ thống**:
1. Cột `iam_users.auth_version` của người dùng bị tăng thêm 1.
2. Token JWT hiện tại mà trình duyệt của User đang cầm mang `auth_version` cũ.
3. Khi User gửi bất kỳ request nào có token cũ lên server, dependency `get_current_user` (`backend/app/api/routes/auth_utils.py`, dòng 491–498) kiểm tra:
   ```python
   token_auth_version = payload.get("auth_version")
   if token_auth_version is not None and getattr(user, "auth_version", 1) != token_auth_version:
       raise HTTPException(
           status_code=status.HTTP_401_UNAUTHORIZED,
           detail="Phiên đăng nhập đã bị thu hồi.",
       )
   ```
4. **Vấn đề cốt lõi hiện tại (Gotcha P0)**:
   - Trình duyệt User nhận lỗi `401 UNAUTHORIZED`.
   - Nếu client không có cơ chế phân biệt mà chỉ coi 401 là logout, User sẽ bị văng ra màn hình đăng nhập (`LoginScreen`) một cách đột ngột mà không hiểu vì sao, hoặc gặp lỗi kết nối màn hình mà không nhận được quyền Admin.
   - Người dùng phải tự phán đoán và gõ lại mật khẩu để đăng nhập lại — điều này **vi phạm trực tiếp Acceptance Criteria R1**.

### 4.2. Khảo sát các kênh phát hiện (Detection Channels)

| Kênh phát hiện | Hiện trạng trong codebase | Đánh giá tính khả thi & độ tin cậy |
| :--- | :--- | :--- |
| **WebSocket** | Không có triển khai WebSocket nào cho client trong backend/frontend. | Không khả thi (không có hạ tầng có sẵn). |
| **Server-Sent Events (SSE)** | Backend có `/approvals/stream` (`approvals.py:183`). Tuy nhiên: endpoint này yêu cầu capability `approval:view_inbox` mà tài khoản `staff` chưa có (trả 403 Forbidden). | Không nên phụ thuộc riêng vào SSE này vì staff bị chặn kết nối từ đầu. |
| **Polling / Role Status Heartbeat** | Frontend đã có `_startOfflinePing` (mỗi 30s gọi `/health/live` trong `app_shell.dart`) và `DataSyncController` (heartbeat mỗi 60s). | **Cực kỳ khả thi và ổn định cao**. Có thể bổ sung kiểm tra vai trò định kỳ (mỗi 10–15s cho tài khoản non-admin) hoặc gắn vào heartbeat sẵn có. |
| **Bắt lỗi 401 có ngữ cảnh (Token Refresh / Re-auth)** | Khi quyền thay đổi, backend trả 401 do `auth_version` tăng. Nếu client intercept 401 và thử refresh token hoặc kiểm tra trạng thái quyền qua endpoint check nhẹ. | **Cần thiết phải phối hợp**: Giúp phát hiện thay đổi ngay lập tức ở request kế tiếp thay vì đợi hết chu kỳ poll. |
| **Lifecycle Resumed (Chuyển tab)** | `DataSyncController.didChangeAppLifecycleState` đã có sẵn cơ chế bắt sự kiện khi người dùng quay lại tab trình duyệt. | Kích hoạt kiểm tra ngay khi người dùng mở lại tab ứng dụng. |

---

## 5. Đề Xuất Kiến Trúc Khắc Phục Hoàn Chỉnh Cho Yêu Cầu R1

Để đạt chuẩn 100% Acceptance Criteria của R1:
1. Giao diện tự động phát hiện khi quyền đổi sang admin.
2. Hiển thị thông báo yêu cầu tải lại hoặc tự động refresh.
3. Người dùng không cần tự phán đoán hay reload thủ công.
4. Mọi đặc quyền admin và giao diện hoạt động chính xác sau khi làm mới.

### 5.1. Mô hình Phối Hợp 3 Lớp (Tri-Layer Detection & Auto-Refresh)

```text
[Backend: Admin gán quyền admin]
        │
        ├─► Database: user_roles thêm 'admin', auth_version = auth_version + 1
        │
        ▼
[Client: 3 Kênh Phát Hiện Tự Động]
  ├── Kênh 1: Polling Timer (Mỗi 10s đối với tài khoản chưa phải Admin)
  ├── Kênh 2: Window Focus / Lifecycle Resume (Người dùng click lại vào tab)
  └── Kênh 3: Interceptor bắt 401 khi auth_version thay đổi
        │
        ▼
[AuthService: Kiểm tra & Phát hiện Thăng quyền]
  wasAdmin == false && nowAdmin == true
        │
        ▼
[Hiển thị Banner Thông Báo Nổi Bật Trên Toàn Ứng Dụng]
  "🎉 Tài khoản của bạn vừa được cấp quyền Quản Trị Viên (Admin)!"
  [Làm mới ngay] (Kèm bộ đếm tự động làm mới sau 5 giây)
        │
        ▼
[Làm mới Phiên & Kích hoạt Đặc quyền]
  1. Cập nhật AuthService.user với danh sách roles mới (chứa 'admin')
  2. Cập nhật access_token mới từ backend (hoặc reload session)
  3. Gọi AuthService.notifyListeners() -> SessionScope re-render
  4. Mở khóa toàn bộ Sidebar, Báo cáo tài chính, Tab Nhân sự, Phê duyệt
```

### 5.2. Các thay đổi cụ thể đề xuất cho đội ngũ Implementer

#### Thay đổi 1: Bổ sung Trạng thái & Cơ chế Kiểm tra Quyền trong `AuthService` (`frontend/lib/src/features/auth/auth_service.dart`)
- **Thuộc tính mới**:
  ```dart
  bool _adminRolePromoted = false;
  bool get adminRolePromoted => _adminRolePromoted;
  Timer? _roleCheckTimer;
  ```
- **Phương thức `checkUserRoleUpdate()`**:
  - Chỉ kích hoạt khi `_user != null` và `!RoleVisibility.isAdmin(RoleVisibility.rolesOf(_user))`.
  - Gửi request kiểm tra tới backend (ví dụ: `GET /auth/me` hoặc endpoint role check).
  - Nếu backend trả về thông tin user có `roles.contains('admin')`:
    - Ghi nhận `_adminRolePromoted = true;`
    - Cập nhật `_user` với vai trò admin và capabilities tương ứng.
    - Gọi `notifyListeners()`.
- **Phương thức `startRolePromotionWatcher()`**:
  - Khởi động timer định kỳ mỗi 10–15 giây để gọi `checkUserRoleUpdate()`. Khi `_user` đã là admin, tự động hủy timer để tiết kiệm tài nguyên.
- **Phương thức `applyAdminPromotionAndRefresh()`**:
  - Cập nhật phiên làm việc, xóa cờ `_adminRolePromoted = false`.
  - Trên Flutter Web: gọi `WebHelpers.forceAppUpdate()` hoặc `html.window.location.reload()`.
  - Trên Mobile/Desktop: gọi `notifyListeners()` và tải lại toàn bộ store dữ liệu (`onRefresh`).

#### Thay đổi 2: Hiển thị Banner Thông Báo Đổi Quyền Nổi Bật (`_AdminPromotionBanner`)
Tạo widget thông báo tại vị trí đầu của toàn bộ ứng dụng (trong `SessionBridge` hoặc `_LiveCommerceGate` / `AppShell`):
- Giao diện thiết kế theo phong cách Emerald/Gold cao cấp:
  - Icon: `Icons.admin_panel_settings_rounded`, màu vàng gold (`#F59E0B`).
  - Tiêu đề: **"Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)"**.
  - Nội dung: *"Các quyền hạn và phân hệ quản trị đã sẵn sàng. Vui lòng làm mới để áp dụng ngay."*
  - Nút bấm chính: `[Làm mới ngay]` (Key: `btn-admin-promoted-refresh`), khi bấm lập tức làm mới giao diện và nạp quyền.
  - Tự động làm mới đếm ngược: Tự động kích hoạt sau 5 giây nếu người dùng không tương tác, tránh việc người dùng phải thao tác tay.

#### Thay đổi 3: Phối hợp Hợp đồng với Backend (Backend Handoff Contract)
Để quá trình làm mới không bị chặn bởi 401 khi `auth_version` tăng:
- Khi admin gọi `PUT /admin/users/{user_id}/roles`:
  - Khuyến nghị Backend: Cho phép `POST /auth/refresh` cấp cặp token mới với `auth_version` mới nếu người dùng vẫn `active` và chỉ vừa được cập nhật vai trò, HOẶC cung cấp endpoint `GET /api/v1/auth/me` xử lý mượt mà khi đổi quyền.
  - Nhờ đó, client vừa có token mới hợp lệ, vừa nạp quyền Admin mà không bị văng ra màn hình đăng nhập.

---

## 6. Kết Luận
1. Frontend QuanLyKho là ứng dụng Flutter Web/Multi-platform với kiến trúc Clean Architecture rất rõ ràng. Logic phân quyền client tập trung ở `RoleVisibility` và phân bổ vào `CommerceWorkspace`, `AppShell` và `CommerceSettingsView`.
2. Toàn bộ hạ tầng hiển thị quyền Admin (báo cáo tài chính, tab IAM, menu phê duyệt, bảng giá) đã có sẵn nhưng đang bị khóa đối với tài khoản `staff`.
3. Giải pháp polling 10–15s kết hợp bắt sự kiện chuyển tab và banner thông báo `_AdminPromotionBanner` kèm auto-refresh là phương án sạch nhất, không đòi hỏi sửa đổi hạ tầng WebSocket phức tạp, đảm bảo tương thích 100% với Web/Mobile, đáp ứng hoàn hảo yêu cầu R1 và không làm ảnh hưởng đến bất kỳ test suite hiện tại nào.
