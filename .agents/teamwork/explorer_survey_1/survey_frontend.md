# Báo Cáo Khảo Sát Kiến Trúc Frontend & Kiểm Toán Mobile UI/UX (QuanLyKho)

**Tác giả**: Explorer Agent (Frontend Architecture & Mobile UI Explorer)  
**Dự án**: Quản Lý Kho & Ngân Hàng AI (`QuanLyKho`)  
**Ngày thực hiện**: 2026-11-02  
**Mục tiêu**: Khảo sát sâu toàn bộ kiến trúc frontend, luồng điều hướng trang chủ, cơ chế đồng bộ số liệu / trạng thái giữa các phân hệ (R1), và kiểm toán tính tương thích trên các kích thước màn hình di động chuẩn (375px, 390px, 414px) cùng các lỗi thành phần UI cần khắc phục (R2).

---

## 1. Tổng Quan Kiến Trúc Frontend & Hạ Tầng Triển Khai

### 1.1. Công nghệ Frontend (Tech Stack)
- **Framework chính**: **Flutter Web & Multiplatform** (Flutter SDK 3.27.7+ / Dart SDK `>=3.4.0 <4.0.0`), kiến trúc **Single Page Application (SPA)**.
  - Sử dụng cơ chế Web Renderer hiện đại (CanvasKit / Skia / Wasm / HTML engine), hỗ trợ `flutter_bootstrap.js` và PWA Service Worker với cơ chế phát hiện phiên bản mới qua `version.json`.
  - Toàn bộ frontend nằm trong thư mục `/frontend`, cấu hình tại `pubspec.yaml`.
- **Quản lý trạng thái (State Management)**:
  - `Provider` (`MultiProvider` tại `main.dart`): `AuthService`, `LocaleController` (đa ngôn ngữ vi/en), `AppUiSettingsController` (giao diện, theme mode, màu sắc, mật độ hiển thị).
  - `CommerceMemoryStore` (kế thừa `ChangeNotifier`): Lưu trữ và dẫn xuất (derive) toàn bộ dữ liệu nghiệp vụ thương mại, tồn kho, đơn hàng, đối tác, công nợ, kiểm kê.
  - `SessionScope` & `RepositoryScope` (`InheritedWidget`): Cung cấp thông tin phiên đăng nhập (`AppUser`) và đối tượng repository (`BankOpsRepository`) xuyên suốt cây widget.
- **Thư viện bổ trợ**:
  - Biểu đồ: `fl_chart` (^0.68.0) cho BarChart, LineChart, DonutChart.
  - Xuất báo cáo & In ấn: `printing` (^5.14.3), `pdf` (^3.12.0), `excel` (^4.0.6), `csv_export.dart`.
  - Quản lý bộ nhớ bảo mật: `flutter_secure_storage` (^9.2.2), `shared_preferences` (^2.3.0).
  - Mã QR: `qr_flutter` (^4.1.0).

### 1.2. Hạ tầng & Đường Ống Triển Khai (Deployment Pipeline)
- **Triển khai Production**:
  - Tự động hóa qua GitHub Actions (`.github/workflows/deploy-pages.yml`).
  - Biên dịch: `flutter build web --release --no-tree-shake-icons --dart-define=API_BASE_URL=...`.
  - Lưu trữ & CDN: **Cloudflare Workers Assets** (cấu hình `infra/cloudflare-worker/wrangler.tea-inventory.toml`).
  - Production URL: `https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev`.
- **Môi trường Local Dev**:
  - Container `frontend-web` trong `docker-compose.yml` sử dụng `nginx:alpine` phục vụ thư mục build `./frontend/dist` tại cổng `8080` (`http://localhost:8080`), cấu hình SPA fallback tại `frontend/nginx.conf`.
- **Kết nối Backend API**:
  - Backend là FastAPI Python (tại `backend/app`), triển khai production trên nền tảng **Modal Serverless**:
    `https://imtarget05--quan-ly-kho-tra-sua-api.us-east.modal.run/api/v1`.
  - Môi trường dev nội bộ: `http://localhost:8000/api/v1` (hoặc `http://10.0.2.2:8000/api/v1` trên Android Emulator).

---

## 2. Yêu Cầu R1: Khảo Sát Kiến Trúc Trang Chủ & Đồng Bộ Hóa Phân Hệ

### 2.1. Hiện Tượng Hai Tầng Vỏ Giao Diện (Architecture Duality)
Codebase hiện tồn tại song song 2 hệ thống vỏ giao diện:
1. **`AppShell` (`frontend/lib/src/app/app_shell.dart` - 1.732 dòng)**:
   - Được thiết kế theo chuẩn 3-tier layout (`<600` bottom nav, `600–1199` navigation rail, `>=1200` desktop sidebar + topbar).
   - Quản lý các tab: Tổng quan (`DashboardScreen`), Kho (`InventoryScreen`), Ca làm việc (`InventoryScreen` mode shift), Yêu cầu (`RequestsScreen`), Duyệt (`ApprovalsScreen`), Hoạt động (`ActivityScreen`), Báo cáo (`ReportsScreen`), Cài đặt (`SettingsScreen`), Nhân viên (`EmployeeManagementScreen`).
   - Tích hợp `DataSyncController` lắng nghe Server-Sent Events (`SSE`), bộ đếm heartbeat ping 30s/60s, và xử lý Offline Outbox.
2. **`CommerceWorkspace` (`frontend/lib/src/features/commerce/commerce_workspace.dart` - 5.778 dòng)**:
   - Là không gian làm việc ERP hoàn chỉnh (Optimate x NexUp ERP) được nạp trực tiếp sau khi đăng nhập thành công tại `main.dart` (`_LiveCommerceGate` / `_AuthGate`).
   - Quản lý 8 phân hệ chính:
     - Tab 0: **Tổng quan** (`_OverviewPage`) — KPI doanh thu, lợi nhuận gộp, số đơn, giá trị kho, tỷ suất lợi nhuận, cảnh báo tồn, công nợ thu/trả, biểu đồ doanh thu 12 tháng, Top sản phẩm/khách hàng, đơn hàng gần đây.
     - Tab 1: **Bán hàng / POS** (`_OrderListPage` kind='sale') — Lập đơn bán hàng, quản lý báo giá, danh bạ khách hàng, in hóa đơn A4/K80.
     - Tab 2: **Nhập hàng / Mua hàng** (`_OrderListPage` kind='purchase') — Lập phiếu mua, quản lý nhà cung cấp, quản lý số lô (lot number) & hạn sử dụng (expiry date).
     - Tab 3: **Kho hàng** (`_InventoryPage`) — Danh mục sản phẩm, chuyển kho nội bộ, kiểm kê kho (`_showStocktake`), lịch sử biến động kho (`_InventoryHistoryPage`).
     - Tab 4: **Sổ nợ** (`_DebtPage`) — Công nợ khách hàng (phải thu), công nợ NCC (phải trả), ghi nhận thanh toán (`_showPayment`).
     - Tab 5: **Báo cáo** (`CommerceReportsPage`) — P&L tổng hợp, báo cáo xuất nhập tồn NVL & TP, biểu đồ đa trục, xuất file Excel/CSV.
     - Tab 6: **Phê duyệt** (`_ApprovalPage`) — Kiểm soát kép (Dual Control), phê duyệt phiếu bán/phiếu nhập/kiểm kê.
     - Tab 7: **Cài đặt** (`CommerceSettingsView`) — Hồ sơ tài khoản, chỉnh sửa profile, đổi mật khẩu, avatar, đổi theme/ngôn ngữ, quản lý nhân viên RBAC (`EmployeeManagementScreen`), cấu hình in ấn.

### 2.2. Cơ Chế Điều Hướng Phân Hệ (Navigation Flow)
- **Desktop (Chiều rộng $\ge 700\text{px}$)**:
  - Sử dụng Sidebar cố định bên trái (`_WorkspaceSidebar`, chiều rộng 232px).
  - Tích hợp icon, nhãn song ngữ (`AppI18n`), badge đếm phê duyệt chờ duyệt, và thông tin tài khoản người dùng ở góc dưới.
- **Mobile (Chiều rộng $< 700\text{px}$)**:
  - Sử dụng `NavigationBar` Material 3 cố định ở đáy màn hình với 5 nút:
    1. Tổng quan (`Icons.dashboard_outlined`) $\to$ Tab 0.
    2. Bán hàng (`Icons.storefront_outlined`) $\to$ Tab 1.
    3. Nhập hàng (`Icons.shopping_bag_outlined`) $\to$ Tab 2.
    4. Kho hàng (`Icons.inventory_2_outlined`) $\to$ Tab 3.
    5. Thêm (`Icons.more_horiz_outlined`) $\to$ Mở `showModalBottomSheet`.
  - Trong `ModalBottomSheet`, người dùng truy cập tiếp: Sổ nợ (Tab 4), Báo cáo (Tab 5), Phê duyệt (Tab 6), Cài đặt (Tab 7), Thông tin tài khoản và Nút Đăng xuất.

### 2.3. Cơ Chế Đồng Bộ Trạng Thái & Lấy Số Liệu Từ Phân Hệ
- **Khi khởi tạo / chuyển kho**:
  - `_LiveCommerceGateState._reload()` gọi `_api.reload(_store)` (`frontend/lib/src/features/commerce/commerce_api.dart`).
  - Gửi song song 3 API: `GET /inventory/items`, `GET /inventory/locations`, `GET /commerce/parties`.
  - Sau đó phân trang lấy toàn bộ số dư tồn kho: `GET /inventory/balances?limit=100&cursor=...`.
  - Đổ toàn bộ dữ liệu vào `CommerceMemoryStore` và gọi `notifyListeners()`.
- **Khi phát sinh giao dịch trong phân hệ**:
  - Sau mỗi thao tác ghi dữ liệu (tạo đơn bán/mua, duyệt phiếu, trả nợ, cân kho), frontend gọi `await widget.onRefresh?.call()`, kích hoạt lại chu trình `_api.reload(_store)` để làm mới số liệu toàn cục.
- **Khoảng Trống Đồng Bộ (Synchronization Gaps)**:
  1. `CommerceWorkspace` **hoàn toàn không kết nối** với `DataSyncController` hoặc Server-Sent Events (`SSE`).
  2. Không có Timer polling định kỳ ngầm trên trang chủ. Nếu một nhân viên khác lập đơn hoặc thủ kho duyệt phiếu ở máy khác, trang chủ sẽ giữ nguyên snapshot cũ cho đến khi người dùng tự tay thao tác hoặc tải lại trang.

### 2.4. Phân Tích Luồng Cập Nhật Quyền Admin & Lỗ Hổng Đồng Bộ Giao Diện
- **Cơ chế phía Backend (`backend/app/api/routes/admin_users.py`)**:
  - Khi một admin cập nhật quyền cho người dùng qua `PUT /admin/users/{user_id}/roles`:
    ```python
    user.auth_version = getattr(user, "auth_version", 1) + 1
    ```
  - Backend tăng `auth_version` của người dùng để thực thi thu hồi phiên cũ (single session / RBAC invalidation).
  - Khi người dùng này gửi request tiếp theo, backend kiểm tra trong `backend/app/api/routes/auth_utils.py`:
    ```python
    if token_auth_version is not None and getattr(user, "auth_version", 1) != token_auth_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã bị thu hồi hoặc quyền tài khoản đã thay đổi. Vui lòng đăng nhập lại.",
        )
    ```
- **Hành vi hiện tại phía Frontend**:
  - Khi token bị từ chối 401 do `auth_version` lệch, `CommerceApi` và `HttpBankOpsRepository` chỉ ném ngoại lệ (`StateError` hoặc `ApiException`).
  - Frontend hiện tại **chưa có bộ đón nhận (interceptor) 401** để nhận biết nguyên nhân do "quyền tài khoản đã thay đổi".
  - Người dùng đang làm việc bình thường đột nhiên gặp thông báo lỗi màu đỏ hoặc màn hình "Không tải được dữ liệu cửa hàng".
  - Nếu người dùng tự F5 trình duyệt, hàm `tryAutoLogin()` gửi lại token cũ bị 401 nên tự động xóa phiên và đá người dùng ra màn hình đăng nhập (`LoginScreen`), buộc người dùng phải nhập lại tài khoản/mật khẩu mới nhận được quyền admin mới.
- **Yêu cầu cần giải quyết cho R1**:
  - Cần cơ chế phát hiện thay đổi quyền tài khoản (qua interceptor 401 kiểm tra message/code, hoặc polling định kỳ `/auth/me`).
  - Khi phát hiện quyền admin mới được cấp: hiển thị Banner / Dialog thông báo rõ ràng: *"Quyền tài khoản của bạn đã được nâng cấp thành Quản Trị Viên (Admin). Đang làm mới giao diện..."*.
  - Tự động gọi refresh token / silent re-auth hoặc tự động nạp lại giao diện để áp dụng quyền admin mới mà không yêu cầu người dùng phải tự phán đoán hay đăng nhập lại thủ công từ đầu.

---

## 3. Yêu Cầu R2: Kiểm Toán Giao Diện Mobile (375px, 390px, 414px) & Danh Sách Lỗi

Qua khảo sát mã nguồn và đối chiếu với 3 kích thước màn hình di động chuẩn:
- **375px**: iPhone SE (Gen 2/3), iPhone 8/7/6s.
- **390px**: iPhone 12 / 13 / 14 / 15 / 16 tiêu chuẩn và dòng Pro.
- **414px**: iPhone 8 Plus, iPhone XR, iPhone 11.

Chúng tôi xác định các vị trí lỗi vỡ bố cục, tràn pixel ngang, cắt chữ và xung đột tương tác như sau:

| Mã Lỗi | Thành phần UI / Tệp tin | Vị trí dòng | Hiện tượng lỗi & Hậu quả trên Mobile (375px / 390px) | Mức độ nghiêm trọng |
|---|---|---|---|---|
| **BUG-01** | `_WorkspaceTopbar` (`commerce_workspace.dart`) | L.666–696 | **Tiêu đề trang bị chèn ép còn ~51px**: Trong `Row`, tiêu đề được bọc trong `Expanded(flex: 1)` nhưng ngay sau đó lại có `const Spacer()` (cũng flex 1), cạnh chip kho (~110px), nút tạo (+40px) và avatar (+40px). Trên màn 375px, không gian cho tiêu đề bị ép xuống chỉ còn 51.5px khiến chữ tiếng Việt như "Quản lý bán hàng", "Quản lý mua hàng" bị cắt cụt thành "Quả...", trong khi để trống một khoảng 51px vô nghĩa giữa tiêu đề và chip kho. | **P0 (Critical UI)** |
| **BUG-02** | `_WorkspaceTopbar` chip kho (`commerce_workspace.dart`) | L.728–730 | **Tên kho/quầy bị cắt cụt**: `ConstrainedBox(maxWidth: compact ? 78 : 140)` giới hạn tên kho tối đa 78px. Trên mobile, các tên kho như "Kho Nguyên Vật Liệu", "Quầy Pha Chế 1" chỉ hiện được 4–5 chữ cái ("Kho N..."), gây khó khăn khi chọn kho. | **P1 (High UX)** |
| **BUG-03** | `_MiniSummaryRow` (`commerce_workspace.dart`) | L.2292–2340 | **Cắt cụt số tiền trên thẻ tóm tắt**: `GridView.count(crossAxisCount: 2)` trên màn 375px khiến chiều rộng nội dung thẻ chỉ còn 90px. Do không dùng `FittedBox` (khác với `_MetricCard`), số tiền lớn (ví dụ: `125.400.000 ₫`) bị cắt thành `125.40...` gây hiểu lầm số liệu tài chính. | **P1 (High UX)** |
| **BUG-04** | `_showCreateOrder` (`commerce_workspace.dart`) | L.4604–4744 | **Tràn layout hàng sản phẩm trong Dialog đơn hàng**: Dòng sản phẩm trong dialog gồm: Dropdown chọn sản phẩm (flex 5), ô số lượng (110px), nút xóa (40px). Trên màn 375px với dialog padding, ô dropdown chỉ còn lại 127px để hiển thị cả mã SKU lẫn tên sản phẩm. Hơn nữa, với phiếu mua, hàng số lô & hạn dùng đặt 2 ô cạnh nhau kèm 4 `ActionChip` (+30n, +90n, +6th, +1năm) khiến các chip bị đẩy vỡ hàng hoặc tràn khung. | **P1 (High UX)** |
| **BUG-05** | `_showCreateProduct` (`commerce_workspace.dart`) | L.4251–4270 | **Hardcoded width 440px trên dialog thêm sản phẩm**: Dialog đặt cứng `SizedBox(width: 440)`. Khi hiển thị trên màn 375px (chiều rộng tối đa của dialog chỉ ~327px), các hàng ngang như `_FormInput('Đơn vị cơ bản (xuất/bán)', unit)` và `_FormInput('Đơn vị nhập (vd: Thùng)', purchaseUnit)` bị ép xuống 135px/ô, làm nhãn dài bị đè lấn hoặc tràn viền khung text. | **P1 (High UX)** |
| **BUG-06** | `_showStockTransferDialog` (`commerce_workspace.dart`) | L.4076–4150 | **Hardcoded width 420px trên dialog chuyển kho**: Đặt cứng `width: 420`. Hàng chọn "Từ kho nguồn" và "Đến kho đích" đặt song song 2 `Expanded` (~135px/ô) làm tên kho bị cắt ngắn nghiêm trọng trên mobile. | **P2 (Medium)** |
| **BUG-07** | `_showStocktake` (`commerce_workspace.dart`) | L.5117–5190 | **Hardcoded width 580px & Bảng kiểm kê bị ép nát**: Dialog đặt cứng `width: 580`. Hàng tiêu đề và dữ liệu chia tỉ lệ `flex: 5, 2, 3, 2` cho 4 cột (SẢN PHẨM, HỆ THỐNG, THỰC TẾ, LỆCH). Cột THỰC TẾ chỉ nhận ~71px nhưng lại chứa cả một `TextFormField` viền đầy đủ, gây khó khăn cực lớn khi chạm gõ số lượng thực tế trên màn hình cảm ứng nhỏ. | **P1 (High UX)** |
| **BUG-08** | `EditProfileDialog` (`edit_profile_dialog.dart`) | L.221 | **Hardcoded width 480px trên dialog sửa hồ sơ**: Đặt cứng `width: 480` trong `AlertDialog` thay vì bọc theo `MediaQuery` hoặc `constraints.maxWidth`, gây ép layout trên thiết bị 375px. | **P2 (Medium)** |
| **BUG-09** | `_DebtPage` (`commerce_workspace.dart`) | L.3564 | **Xung đột cuộn lồng nhau (Nested Scroll Conflict)**: `TabBarView` chứa `_DebtList` được bọc trong `SizedBox(height: 480)` cố định, nằm bên trong một `SingleChildScrollView` ngoài (`_PageFrame`). Trên thiết bị di động, thao tác vuốt cảm ứng bị "kẹt" giữa cuộn danh sách hóa đơn bên trong và cuộn toàn trang bên ngoài. | **P1 (High UX)** |
| **BUG-10** | `CommerceReportsPage` (`commerce_reports_page.dart`) | L.392–404 | **Cắt cụt nhãn KPI tài chính**: Thiết lập `cols = 2` trên màn hình `<720px`. Trên màn 375px, mỗi thẻ chỉ rộng 165px, trừ padding và icon chỉ còn ~101px cho chữ, khiến các mục như "Tổng giá vốn (COGS)" và subtitle chi tiết công nợ bị cắt cụt bằng dấu chấm lửng. | **P2 (Medium)** |
| **BUG-11** | `_OrderListTile` (`commerce_workspace.dart`) | L.2510 | **Thiếu thuộc tính chống tràn tên khách hàng/NCC**: `Text(order.partyName)` không có `maxLines: 1` và `overflow: TextOverflow.ellipsis`. Khi tên đối tác dài (ví dụ: công ty đối tác trà sữa), thẻ bị đẩy dọc bất thường làm mất cân đối danh sách. | **P2 (Medium)** |
| **BUG-12** | Mobile Bottom Nav & More Sheet | L.275–340 | **Mất dấu trạng thái khi ở tab phụ (More subpages)**: Khi người dùng chọn Sổ nợ, Báo cáo, Phê duyệt hoặc Cài đặt từ nút "Thêm", `NavigationBar` luôn highlight biểu tượng More (vị trí 4) mà không có chỉ báo cụ thể tab phụ nào đang mở, đồng thời thiếu nút quay lại nhanh về trang Tổng quan nếu không mở lại sheet. | **P2 (Medium)** |

---

## 4. Bản Đồ Các Thành Phần Cần Cải Tổ (Refactoring Map)

Để đạt được sự đồng bộ hoàn hảo giữa Web Desktop và Mobile Viewport, đồng thời xử lý triệt để yêu cầu cập nhật quyền admin (R1, R2), các thành phần sau cần được cập nhật:

```
frontend/lib/
├── main.dart
│   └── Cập nhật _LiveCommerceGate để truyền callback kiểm tra quyền hoặc quản lý SessionBridge lặp lại.
├── src/features/auth/
│   └── auth_service.dart
│       ├── Bổ sung hàm `refreshSession()` hoặc `pollUserPermissions()` để định kỳ gọi GET /auth/me kiểm tra vai trò.
│       └── Bổ sung cơ chế xử lý khi token bị từ chối 401 do auth_version: hiển thị thông báo nâng quyền thay vì silent error.
├── src/features/commerce/
│   ├── commerce_api.dart
│   │   └── Intercept lỗi HTTP 401: nhận diện mã lỗi hoặc nội dung "quyền tài khoản đã thay đổi" và kích hoạt sự kiện role_changed.
│   ├── commerce_workspace.dart
│   │   ├── [Topbar] Gỡ bỏ Spacer() dư thừa trên mobile, mở rộng maxWidth cho title và location chip.
│   │   ├── [MiniSummary] Bọc FittedBox(fit: BoxFit.scaleDown) quanh Text(e.$2) để chống cụt số tiền.
│   │   ├── [OrderListTile] Thêm maxLines: 1 và ellipsis cho partyName.
│   │   ├── [Dialogs] Thay thế hardcoded width (420, 440, 580) bằng `constraints.maxWidth < 600 ? double.infinity : width`.
│   │   ├── [CreateOrder] Chuyển layout hàng sản phẩm và chip hạn dùng sang dạng khối dọc (Column/Wrap linh hoạt) trên mobile.
│   │   ├── [Stocktake] Thiết kế lại giao diện bảng kiểm kê trên mobile dạng thẻ card theo từng sản phẩm thay vì ép 4 cột trong 1 hàng.
│   │   └── [DebtPage] Thay thế SizedBox(height: 480) bằng `NeverScrollableScrollPhysics` hoặc cấu trúc cuộn hợp nhất.
│   ├── commerce_reports_page.dart
│   │   └── Điều chỉnh `cols = 1` trên màn hình `<420px` cho các thẻ KPI báo cáo doanh thu & giá vốn.
│   └── commerce_settings_view.dart
│       └── Đảm bảo hiển thị tức thì mục "Quản lý nhân viên & Phân quyền (RBAC)" ngay khi tài khoản được cấp quyền admin.
└── src/features/settings/widgets/
    └── edit_profile_dialog.dart
        └── Thay thế SizedBox(width: 480) bằng ConstrainedBox responsive.
```

---

## 5. Kết Luận & Đề Xuất Cho Đội Ngũ Triển Khai (Next Steps)

1. **Về R1 (Cập nhật quyền admin & làm mới giao diện)**:
   - Backend đã có cơ chế tăng `auth_version` và gửi cảnh báo an ninh (`send_security_alert_email`).
   - Cần bổ sung vào `backend/app/api/routes/admin_users.py` hàm gửi email trực tiếp đến địa chỉ của người dùng được gán admin (`send_admin_role_granted_email`).
   - Phía frontend Flutter, tại `AuthService` và `CommerceApi`, cần xây dựng cơ chế tự động thăm dò (heartbeat poll) hoặc xử lý khi gặp 401 do thay đổi quyền: tự động hiển thị thông báo Dialog/Banner "Tài khoản của bạn đã được nâng cấp quyền Admin. Đang áp dụng quyền mới..." và làm mới session mà không cần người dùng can thiệp thủ công.
2. **Về R2 (Khắc phục lỗi hiển thị & đồng bộ Mobile Viewport)**:
   - Áp dụng các bản vá bố cục cho `BUG-01` đến `BUG-12` theo danh sách trên.
   - Thêm bộ kiểm thử widget test (`test/mobile_viewport_parity_test.dart`) kiểm tra không có lỗi tràn pixel (`RenderFlex overflow`) và không bị mất nút thao tác trên kích thước `375x667`, `390x844` và `414x896`.
