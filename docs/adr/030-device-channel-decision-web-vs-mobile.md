# ADR 030: Device Channel Architecture Decision (Web PWA vs Mobile Native vs Hybrid)

## 1. Status
**Accepted** (2026-10-26)

## 2. Context & Problem Statement
Hệ thống **Quản Lý Kho Trà Sữa (QuanLyKho)** phục vụ hoạt động quản lý chuỗi cửa hàng F&B phân tán, bao gồm nhiều nhóm người dùng với điều kiện làm việc và thiết bị đặc thù:

1. **Nhân viên quầy / Pha chế (Barista / Floor Staff):** Làm việc trực tiếp tại quầy pha chế, kho nguyên liệu hoặc bàn kiểm kê; cần thao tác nhanh bằng một tay, quét mã vạch qua camera, ghi nhận hao hụt/đổ vỡ ngay tại chỗ và kiểm kê cuối ca trong môi trường có thể mất sóng Wi-Fi (kho lạnh, tầng hầm).
2. **Quản lý ca / Cửa hàng trưởng (Store Manager / Shift Leader):** Làm việc cả tại quầy (tablet) và văn phòng cửa hàng (laptop/desktop); phụ trách mở/đóng ca, duyệt phiếu nhập kho, điều chỉnh số liệu lệch kiểm kê, bàn giao ca.
3. **Bộ phận Kế toán / Kiểm toán / Chủ chuỗi (HQ Finance & Audit / Owners):** Làm việc trên màn hình lớn (PC/Mac/Web Browser); phân tích báo cáo XNT, đối soát sổ cái, quản trị IAM/nhân sự, giám sát cảnh báo gian lận.

**Vấn đề:** Lựa chọn chiến lược phân phối nền tảng ứng dụng: Web PWA (Progressive Web App), Native Mobile App (Android APK / iOS IPA), hay Mô hình Lai (Hybrid).

---

## 3. Decision Drivers
1. **Khả năng Offline-First:** Quầy kiểm kê và kho lạnh thường xuyên gặp sự cố mất kết nối mạng hoặc chập chờn. Việc chốt ca và nhập số lượng không được phép bị ngắt quãng.
2. **Tốc độ Triển khai và Chi phí Vận hành:** Chuỗi F&B tuyển dụng nhiều nhân sự thời vụ; quy trình cài đặt ứng dụng phải đơn giản (không bắt buộc duyệt App Store dài ngày cho các bản cập nhật nội bộ khẩn cấp).
3. **Phần cứng & Ngoại vi:** Hỗ trợ camera quét mã vạch, máy in nhiệt hóa đơn (ESC/POS Bluetooth/LAN) và màn hình cảm ứng POS.
4. **Bảo mật & Phân quyền RBAC:** Tuân thủ phân quyền Maker-Checker, hạn chế rủi ro lộ dữ liệu tài chính ra thiết bị cá nhân của nhân viên.
5. **Thông báo đẩy (Push Notifications):** Đảm bảo quản lý nhận được thông báo tức thời khi có phiếu cần duyệt hoặc cảnh báo cận hạn/hết tồn kho.

---

## 4. Evaluated Options

### Option A: Web PWA Duy Nhất (Single Responsive Web App)
- **Ưu điểm:** Một codebase duy nhất; cập nhật tức thì qua Cloudflare Pages / Edge; không tốn phí duy trì tài khoản Apple Developer ($99/năm) hoặc kiểm duyệt chợ ứng dụng; tương thích mọi hệ điều hành (Windows POS, macOS, Android, iOS).
- **Nhược điểm:** Push Notification trên iOS Web Safari hạn chế và kém ổn định (yêu cầu iOS 16.4+ và phải thêm vào Home Screen qua Add to Home Screen); khả năng kết nối Bluetooth ngoại vi (máy in tem/in nhiệt) qua Web Bluetooth bị hạn chế trên Safari/iOS.

### Option B: Native Mobile App Duy Nhất (Flutter Android/iOS)
- **Ưu điểm:** Tận dụng 100% camera barcode hardware acceleration, nền tảng lưu trữ SQLite cục bộ và push notification (FCM/APNs) tối ưu; trải nghiệm mượt mà trên smartphone của nhân viên.
- **Nhược điểm:** Màn hình quản trị lớn (báo cáo XNT nhiều cột, phân tích đối soát BankOps) trên điện thoại rất chật chội; nhân viên văn phòng và kiểm toán không muốn dùng điện thoại để xem báo cáo tài chính hàng nghìn dòng.

### Option C: Mô hình Lai Hợp Nhất (Unified Hybrid Architecture - SELECTED)
- **Kiến trúc Flutter Đa Nền Tảng (Single Flutter Codebase targeting Web & Android/iOS):**
  - **Kênh Web (PWA):** Được build và tối ưu cho Desktop & Máy POS cảm ứng (1080p, tỉ lệ ngang/responsive). Phục vụ Chủ quán, Kế toán, Kiểm toán viên và Quản lý ca trực. Triển khai qua Cloudflare Pages CDN.
  - **Kênh Mobile / Tablet (APK / Native):** Được đóng gói phục vụ kiểm kê quầy và quét kho. Tận dụng `StocktakeOutbox` đồng bộ nền offline và FCM background notifications.

---

## 5. Decision Outcome
Chọn **Option C: Unified Hybrid Architecture**.

### Quy chuẩn Phân kênh theo Vai trò & Thiết bị:

| Nhóm Người dùng | Thiết bị Mục tiêu | Kênh Khuyến nghị | Tính năng Trọng tâm |
|:---|:---|:---|:---|
| **Pha chế / Nhân viên quầy** | Smartphone (Android/iOS) hoặc Tablet 8" | Mobile Native / PWA Home Screen | Kiểm ca 3 bước, quét mã lô, báo hỏng, offline outbox |
| **Quản lý ca trực** | Tablet quầy (iPad / Android Tab) hoặc Laptop | PWA hoặc Mobile Tablet | Duyệt phiếu nhanh, mở/chốt ca, nhận push duyệt phiếu |
| **Kế toán / Kiểm toán viên** | Máy tính để bàn (Chrome / Edge / Firefox) | Web PWA | Báo cáo XNT, đối soát movement, kiểm toán IAM |

---

## 6. Implementation & Operational Guidelines
1. **Responsive Shell:** `AppShell` sử dụng responsive layout (`RoleVisibility.visibleTabs`), tự động chuyển đổi giữa thanh điều hướng đáy (BottomNavigationBar trên Mobile) và NavigationRail (trên Tablet/Desktop).
2. **Push Strategy:**
   - Quản lý ca & Cửa hàng trưởng: Đăng ký FCM token trên thiết bị tablet/mobile để nhận push native tức thì khi có yêu cầu duyệt phiếu.
   - Trình duyệt Web: Dự phòng bằng Server-Sent Events (SSE) `/activity/events_stream` khi tab trình duyệt đang mở.
3. **Offline Sync Contract:** Dữ liệu kiểm kê lưu trong `SharedPreferences` / Hive cục bộ và gửi qua `/api/v1/inventory/shifts/stocktakes` với cơ chế idempotency key và If-Match ETag.
