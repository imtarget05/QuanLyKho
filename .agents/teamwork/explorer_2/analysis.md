# Phân Tích Kỹ Thuật Backend & Dịch Vụ Email (Explorer 2 Analysis)

**Dự án**: QuanLyKho (Quản Lý Kho Trà Sữa)  
**Ngày thực hiện**: 2026-11-02  
**Agent**: Explorer 2 (Backend & Email Explorer)  
**Mục tiêu**: Điều tra kiến trúc backend, mô hình IAM, endpoint cập nhật vai trò, cơ chế xác thực JWT, hạ tầng SMTP/Email hiện có, và đề xuất phương án kỹ thuật toàn diện cho Yêu cầu R1 (phát hiện thay đổi quyền & làm mới giao diện) và R2 (gửi email thông báo cấp quyền admin).

---

## 1. Mô hình Dữ Liệu Phân Quyền & IAM (Identity & Access Management)

### 1.1. Các bảng cơ sở dữ liệu (`backend/app/models/iam.py`)

Hệ thống IAM của QuanLyKho được thiết kế theo chuẩn RBAC (Role-Based Access Control) kết hợp Capability-Based Security và Scoped Grants (chi nhánh/địa điểm):

1. **`iam_users` (Model `User`, dòng 44–68)**:
   - `id`: `UUID(as_uuid=True)`, khóa chính.
   - `username`: `String(64)`, duy nhất, đánh chỉ mục.
   - `password_hash`: `String(256)`, mã hóa mật khẩu bcrypt/argon2.
   - `pin_hash`: `String(256)`, mã hóa mã PIN phê duyệt 6 số (chỉ cấp sẵn trong demo mode).
   - `status`: `Enum(UserStatus)` với các giá trị `active`, `inactive`, `locked` (mặc định: `active`).
   - `display_name_demo`: `String(256)`, họ và tên hiển thị của nhân viên.
   - `email`: `String(256)`, có thể rỗng (`nullable=True`), dùng để gửi thư mời, cảnh báo bảo mật và thông báo cấp quyền.
   - `phone_number`: `String(32)`, số điện thoại.
   - `branch_id`: `UUID`, khóa ngoại liên kết `org_branches.id`.
   - `avatar_url`: `String(2048)`, đường dẫn ảnh đại diện.
   - `must_change_password`: `Boolean`, cờ bắt buộc đổi mật khẩu khi đăng nhập bằng mật khẩu tạm thời.
   - `invite_token_hash`: `String(128)`, băm SHA-256 của token thư mời.
   - `invite_expires_at`: `DateTime(timezone=True)`, thời hạn của thư mời (thường là 7 ngày).
   - `auth_version`: `Integer`, số nguyên tăng dần (mặc định: `1`). Được dùng làm phiên bản thu hồi phiên (session revocation token version) trong JWT payload.

2. **`iam_roles` (Model `Role`, dòng 97–106)**:
   - `code`: `String(64)`, khóa chính (ví dụ: `admin`, `system_admin`, `root_admin`, `inventory_manager`, `approver`, `staff`, `auditor`, `cash_sim_operator`).
   - `name`: `String(128)`, tên vai trò hiển thị.
   - `description`: `String(512)`, mô tả quyền hạn của vai trò.

3. **`iam_capabilities` (Model `Capability`, dòng 108–117)**:
   - `code`: `String(64)`, khóa chính (ví dụ: `iam:admin`, `admin:user_management`, `inventory:approve_request`, `inventory:create_request`, `cash:manage_box`, `cash:post_adjustment`, `integration:manage`, `audit:view`).
   - `name`: `String(128)`, tên quyền hạn.
   - `description`: `String(512)`, mô tả quyền hạn chi tiết.

4. **`iam_user_roles` (Model `UserRole`, dòng 119–128)**:
   - `user_id`: `UUID`, khóa chính liên kết `iam_users.id`.
   - `role_code`: `String(64)`, khóa chính liên kết `iam_roles.code`.
   - Quan hệ nhiều-nhiều (N-N) giữa người dùng và vai trò.

5. **`iam_role_capabilities` (Model `RoleCapability`, dòng 129–133)**:
   - `role_code`: `String(64)`, khóa chính.
   - `capability_code`: `String(64)`, khóa chính.
   - Quan hệ nhiều-nhiều (N-N) xác định vai trò sở hữu các quyền hạn hạt nhân (capabilities) nào.

6. **`iam_scope_grants` (Model `ScopeGrant`, dòng 69–96)**:
   - `id`: `UUID`, khóa chính.
   - `user_id`: `UUID`, liên kết `iam_users.id`.
   - `branch_id`: `UUID`, giới hạn chi nhánh dữ liệu.
   - `location_id`: `UUID`, giới hạn kho/điểm lưu trữ.
   - `valid_from`, `valid_to`: Thời hạn hiệu lực của phân quyền.

---

## 2. Điểm Kích Hoạt & Endpoint Cập Nhật Quyền (`PUT /admin/users/{user_id}/roles`)

### 2.1. Vị trí mã nguồn
- Tệp tin: `backend/app/api/routes/admin_users.py`
- Hàm: `update_user_roles()` tại các dòng 594–656.
- HTTP Method & Path: `PUT /admin/users/{user_id}/roles` (đồng thời được mount tại `/api/v1/admin/users/{user_id}/roles`).
- Router prefix: `@router.put("/users/{user_id}/roles")` bên trong `APIRouter(prefix="/admin", tags=["Admin IAM"])`.

### 2.2. Phân tích luồng xử lý hiện tại của `update_user_roles`
1. **Phân quyền truy cập (RBAC Guard)**:
   - `current_user: User = Depends(require_any_capability(*_ADMIN_CAPS))` (dòng 598), với `_ADMIN_CAPS = ("iam:admin", "admin:user_management")`.
   - Người gọi bắt buộc phải sở hữu quyền quản trị viên.

2. **Xác thực dữ liệu đầu vào**:
   - Schema `UpdateRolesRequest`: `roles: list[str]`.
   - Hàm `_validated_roles(db, body.roles)` (dòng 107–116): Kiểm tra danh sách vai trò gửi lên, loại bỏ khoảng trắng, chuẩn hóa chữ thường, đối chiếu với bảng `iam_roles`. Ném lỗi `AppError(422, "EMPTY_ROLES")` nếu rỗng, hoặc `AppError(422, "INVALID_ROLES")` nếu có vai trò không tồn tại trong danh mục.

3. **Kiểm tra bất biến an ninh (Security Invariants)**:
   - `_require_root_for_role_change(db, current_user, before, after)`: Không cho phép gán hoặc gỡ vai trò `root_admin` nếu người thực hiện không có quyền `iam:root`.
   - **Tự sửa đổi quyền của chính mình (Self-modification Guard)** (dòng 618–626):
     * Nếu `current_user.id == user.id`: Chặn tự nâng quyền (`after - before` => `AppError(403, "CANNOT_ESCALATE_SELF")`).
     * Chặn tự tước quyền admin của bản thân nếu sau khi cập nhật không còn giữ quyền `_ADMIN_CAPS` (`AppError(400, "CANNOT_DEMOTE_SELF")`).

4. **Cập nhật dữ liệu bằng kỹ thuật Set Difference**:
   - `before = set(existing_roles)` (danh sách role cũ).
   - `after = set(cleaned_roles)` (danh sách role mới).
   - Xóa các role thuộc `before - after` khỏi `iam_user_roles`.
   - Thêm các role thuộc `after - before` vào `iam_user_roles`.

5. **Tăng phiên bản xác thực (Auth Version Bump)**:
   - Dòng 636: `user.auth_version = getattr(user, "auth_version", 1) + 1`.
   - Mục đích: Vô hiệu hóa token truy cập hiện tại để người dùng bắt buộc phải nhận lại bộ quyền mới.

6. **Ghi nhật ký kiểm toán & Outbox**:
   - `_audit(db, actor_id=current_user.id, action="IAM_USER_ROLES_UPDATED", ...)`
   - `_outbox(db, event_type="user.roles_updated", aggregate_id=str(user.id), payload={"username": user.username, "roles": cleaned_roles})`

7. **Commit Transaction**:
   - Dòng 652: `await db.commit()`.
   - Dòng 653: `await db.refresh(user)`.
   - Dòng 655: Trả về kết quả `{"user": await _user_to_dict(db, user), "message": "Cập nhật vai trò thành công."}`.

---

## 3. Cơ Chế Xác Thực & Nhận Diện Quyền Hiện Tại Của Client

### 3.1. Truy xuất thông tin người dùng (`GET /auth/me` hoặc `GET /me`)
- Tệp tin: `backend/app/api/routes/auth.py`, dòng 517–548.
- Trả về:
  ```json
  {
    "id": "uuid-string",
    "username": "tan_admin",
    "display_name": "Mai Nguyễn Bình Tân",
    "email": "tan@example.com",
    "phone_number": "0901234567",
    "branch": "Chi nhánh Bến Thành",
    "avatar_url": null,
    "roles": ["admin"],
    "capabilities": ["iam:admin", "admin:user_management", "inventory:approve_request", "inventory:create_request", "cash:manage_box", "cash:post_adjustment", "integration:manage"]
  }
  ```
- Kiểm tra danh sách `admin_emails` (dòng 526–536): Nếu email người dùng nằm trong danh sách superadmin (`settings.admin_emails`), hệ thống tự động bổ sung quyền admin và capability tương ứng.

### 3.2. Cấu trúc JWT Token & Sự cố Token Stale
- Khi người dùng đăng nhập (`/auth/login` hoặc `/auth/refresh`), token được tạo bằng `create_access_token()` (`backend/app/api/routes/auth_utils.py` dòng 373–381) với payload chứa:
  ```python
  {
      "sub": str(user.id),
      "username": user.username,
      "roles": roles,
      "caps": capabilities,
      "auth_version": user.auth_version,
      "branch_id": str(user.branch_id),
      "exp": expire,
      "type": "access"
  }
  ```
- Hàm kiểm tra quyền `require_capability` (`backend/app/api/routes/auth_utils.py` dòng 608–624): Đọc `caps` **trực tiếp từ JWT token payload** (`payload.get("caps")`).
- **Hệ quả quan trọng**:
  * Khi người dùng được cấp quyền admin mới trong cơ sở dữ liệu, **token cũ đang nằm ở bộ nhớ trình duyệt vẫn mang `roles: ["staff"]` và thiếu các quyền admin**.
  * Khi `user.auth_version` được tăng lên 1, hàm `get_current_user()` (dòng 492–498) kiểm tra:
    ```python
    token_auth_version = payload.get("auth_version")
    if token_auth_version is not None and getattr(user, "auth_version", 1) != token_auth_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã bị thu hồi.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    ```
  * Cả token truy cập (access token) và refresh token cũ (dòng 474–476 trong `auth.py`) sẽ bị máy chủ từ chối với mã lỗi HTTP 401.

---

## 4. Hiện Trạng Dịch Vụ Email & SMTP Trong Ứng Dụng

### 4.1. Cấu hình SMTP (`backend/app/config.py`, dòng 145–171)
Hệ thống đã có đầy đủ các biến cấu hình SMTP chuẩn:
- `smtp_host`: Mặc định `os.environ.get("SMTP_HOST") or "smtp.gmail.com"`.
- `smtp_port`: Mặc định `int(os.environ.get("SMTP_PORT") or 587)`.
- `smtp_user`: `os.environ.get("SMTP_USER") or ""`.
- `smtp_password`: `os.environ.get("SMTP_PASSWORD") or ""`.
- `smtp_from_name`: `os.environ.get("SMTP_FROM_NAME") or "Ban Quản Trị Hệ Thống"`.
- `admin_alert_email`: `os.environ.get("ADMIN_ALERT_EMAIL") or "tanmainguyenbinh@gmail.com"`.
- `admin_emails`: Danh sách email quản trị viên cấp cao.

### 4.2. Khối dịch vụ `backend/app/services/email_service.py` (854 dòng)
Mã nguồn đã xây dựng sẵn nền tảng gửi thư điện tử giao dịch chuẩn doanh nghiệp:
1. **`_send_smtp_sync(...)` (dòng 119–160)**:
   - Gửi thư đồng bộ chạy an toàn trong luồng phụ (`asyncio.to_thread`).
   - Hỗ trợ cả STARTTLS (port 587) và SSL (port 465).
   - Thiết lập `timeout=12` giây ngăn ngừa nghẽn luồng mạng.
   - Nội dung định dạng MIME đa phần (`MIMEMultipart("alternative")`) gồm cả HTML chuyên nghiệp và Plain Text dự phòng chống bộ lọc spam.
   - Bắt mọi ngoại lệ mạng/xác thực SMTP (`try...except Exception as exc`) và trả về `tuple[bool, str]` thay vì làm nổ tiến trình.
2. **`EmailSendResult` (dòng 101–117)**:
   - Lớp đóng gói kết quả gồm cờ `success: bool` và thông điệp `message: str`, hỗ trợ đánh giá điều kiện boolean `if res: ...`.
3. **`is_valid_email(value: str | None) -> bool` (dòng 19–22)**:
   - Kiểm tra định dạng regex email thực dụng (`^[^@\s]+@[^@\s]+\.[^@\s]{2,}$`).
4. **Các phương thức nghiệp vụ đã có**:
   - `send_password_reset_email(to_email, username, otp)`: Gửi OTP đặt lại mật khẩu.
   - `send_invite_email(...)`: Gửi thư mời kích hoạt tài khoản kèm token 7 ngày.
   - `send_activation_confirmation_email(...)`: Xác nhận kích hoạt tài khoản thành công.
   - `send_security_alert_email(...)`: Cảnh báo dò quét mật khẩu (brute-force).
   - `check_smtp_health()`: Thăm dò kết nối máy chủ SMTP (được gọi từ endpoint `GET /admin/smtp-status`).

---

## 5. Đề Xuất Phương Án Kỹ Thuật Cho Yêu Cầu R2: Gửi Email Khi Cấp Quyền Admin

### 5.1. Điều kiện kích hoạt (Trigger Condition)
Trong hàm `update_user_roles` (`backend/app/api/routes/admin_users.py`):
```python
before = set(existing_roles)
after = set(cleaned_roles)
# Phát hiện vai trò admin được cấp mới (chưa có trong before nhưng có trong after)
admin_promoted = "admin" in (after - before)
```
*(Lưu ý: Có thể mở rộng bao gồm cả các vai trò quản trị tương đương như `{"admin", "system_admin", "root_admin"}.intersection(after - before))`.*

### 5.2. Hàm dịch vụ mới trong `backend/app/services/email_service.py`
Xây dựng hàm `send_admin_role_granted_email()` và 2 hàm dựng template HTML/Plain text tương ứng:

```python
_ADMIN_PRIVILEGE_LABELS = [
    ("iam:admin", "Quản trị phân quyền người dùng và kiểm soát phiên (IAM & Session Management)"),
    ("admin:user_management", "Khởi tạo, kích hoạt, khóa và phân bổ nhân sự toàn hệ thống"),
    ("inventory:approve_request", "Phê duyệt các yêu cầu nhập, xuất, chuyển kho và điều chỉnh tồn kho"),
    ("cash:manage_box", "Quản lý danh mục két tiền và phân bổ điểm thu ngân chi nhánh"),
    ("cash:post_adjustment", "Thực hiện và phê duyệt các bút toán điều chỉnh sổ quỹ tiền mặt"),
    ("integration:manage", "Quản trị kết nối và cấu hình tích hợp dữ liệu (Google Sheets / Webhooks)"),
]

def _build_admin_role_granted_html(
    username: str,
    display_name: str | None,
    granted_roles: list[str],
    granted_privileges: list[str],
    actor_name: str | None,
    assigned_at_str: str,
    app_url: str,
) -> str:
    # Template HTML chuẩn enterprise, tương thích giao diện dark header #0F172A,
    # tông màu chủ đạo Royal Blue (#2563EB) và Amber/Green điểm nhấn.
    # Escape toàn bộ các trường đầu vào ngăn chặn triệt để XSS.
    ...

def _build_admin_role_granted_plain(...) -> str:
    # Phiên bản text thuần túy
    ...

async def send_admin_role_granted_email(
    to_email: str,
    username: str,
    display_name: str | None = None,
    granted_roles: list[str] | None = None,
    actor_name: str | None = None,
) -> EmailSendResult:
    clean_email = (to_email or "").strip().lower()
    if not is_valid_email(clean_email):
        logger.warning("Bỏ qua gửi email cấp quyền admin: email không hợp lệ cho user '%s': %s", username, to_email)
        return EmailSendResult(False, f"Email '{to_email}' không có định dạng hợp lệ")

    smtp_user = settings.smtp_user.strip()
    smtp_pass = settings.smtp_password.strip()
    if not smtp_user or not smtp_pass:
        logger.info(
            "[EmailService (Demo mode)] SMTP chưa cấu hình. Bỏ qua gửi email cấp quyền Admin cho user '%s' (%s)",
            username, clean_email,
        )
        return EmailSendResult(False, "Chưa cấu hình tài khoản SMTP")

    # Soạn thảo nội dung và gọi _send_smtp_sync qua asyncio.to_thread
    ...
```

### 5.3. Đảm bảo tính toàn vẹn và an toàn của Giao Dịch Cơ Sở Dữ Liệu (Transaction Safety Invariant)
**Nguyên tắc tối thượng**: Sự cố gửi email (máy chủ SMTP sập, timeout mạng, sai mật khẩu ứng dụng, địa chỉ nhận từ chối) **tuyệt đối không được làm rollback hoặc ném lỗi 500** khiến giao dịch phân quyền trong cơ sở dữ liệu bị hủy.

Mô hình thực thi chuẩn trong `update_user_roles`:
```python
    # 1. Thực hiện toàn bộ cập nhật DB (UserRole, auth_version, audit, outbox)
    await db.commit()
    await db.refresh(user)

    # 2. GỬI EMAIL THÔNG BÁO SAU KHI TRANSACTION ĐÃ COMMIT HOÀN TẤT
    admin_email_sent = False
    delivery_msg = ""
    clean_email = (user.email or "").strip().lower()

    if admin_promoted and clean_email:
        try:
            actor_display = current_user.display_name_demo or current_user.username
            res = await send_admin_role_granted_email(
                to_email=clean_email,
                username=user.username,
                display_name=user.display_name_demo,
                granted_roles=cleaned_roles,
                actor_name=actor_display,
            )
            admin_email_sent = bool(res)
            delivery_msg = getattr(res, "message", "Đã gửi email thông báo")
        except Exception as exc:  # noqa: BLE001 - Email không bao giờ làm fail phân quyền
            logger.warning("Lỗi gửi email cấp quyền admin cho %s: %s", user.username, exc)
            admin_email_sent = False
            delivery_msg = str(exc)

    return {
        "user": await _user_to_dict(db, user),
        "admin_email_sent": admin_email_sent,
        "email_delivery_message": delivery_msg,
        "message": "Cập nhật vai trò thành công.",
    }
```

---

## 6. Đề Xuất Phương Án Kỹ Thuật Cho Yêu Cầu R1: Hỗ Trợ Frontend Phát Hiện Đổi Quyền

### 6.1. Thách thức hiện tại
- Khi người dùng đang mở ứng dụng, nếu một quản trị viên khác cập nhật quyền của họ thành `admin`:
  * Người dùng không hề biết quyền của mình đã được nâng cấp.
  * Khi người dùng bấm vào một chức năng hoặc gửi một yêu cầu, token cũ bị từ chối với lỗi `HTTP 401: Phiên đăng nhập đã bị thu hồi`.
  * Trình duyệt không biết đó là do được cấp quyền hay do bị đuổi khỏi hệ thống, dẫn đến trải nghiệm bị gián đoạn hoặc bắt buộc đăng nhập lại từ đầu.

### 6.2. Giải pháp 3 lớp kết hợp giữa Backend và Frontend

#### Lớp 1: Phát sóng sự kiện thời gian thực qua Bus SSE (`backend/app/services/approval_events.py`)
- Backend đã có sẵn `approval_event_bus` phục vụ kết nối SSE tại `/approvals/stream`.
- Frontend (`HttpBankOpsRepository._runSseLoop()` và `DataSyncController`) **đang duy trì một kết nối SSE mở liên tục**.
- **Đề xuất Backend**: Ngay sau khi commit cập nhật vai trò trong `admin_users.py`, phát một sự kiện thời gian thực:
  ```python
  await approval_event_bus.publish(
      "role_updated",
      {
          "action": "role_updated",
          "user_id": str(user.id),
          "username": user.username,
          "roles": cleaned_roles,
          "is_admin": "admin" in cleaned_roles,
          "auth_version": user.auth_version,
          "message": f"Quyền hạn của tài khoản @{user.username} đã được cập nhật thành: {', '.join(cleaned_roles)}.",
      }
  )
  ```
- **Xử lý phía Frontend**:
  * Khi `DataSyncController` nhận được sự kiện với `event.raw['data']['user_id'] == current_user.id` và `is_admin == true`:
  * Kích hoạt một thông báo trên màn hình (Toast / Dialog / Banner):
    > *"Quyền Quản Trị Viên (Admin) của bạn vừa được cấp mới. Hệ thống sẽ tự động làm mới giao diện sau 3 giây hoặc bấm 'Làm mới ngay'."*
  * Tự động gọi hàm làm mới phiên / làm mới trang (`window.location.reload()` hoặc nạp lại thông tin người dùng).

#### Lớp 2: Chuẩn hóa mã lỗi HTTP 401 khi `auth_version` thay đổi (`backend/app/api/routes/auth_utils.py`)
- Thay vì ném thông điệp chuỗi chung chung `"Phiên đăng nhập đã bị thu hồi."`, cấu trúc lại mã lỗi:
  ```python
  raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail={
          "code": "AUTH_VERSION_CHANGED",
          "reason": "ROLE_OR_SESSION_UPDATED",
          "message": "Phân quyền hoặc phiên làm việc của bạn đã thay đổi. Vui lòng làm mới giao diện.",
      },
      headers={"WWW-Authenticate": "Bearer"},
  )
  ```
- Nhờ mã lỗi `AUTH_VERSION_CHANGED`, interceptor của HTTP client phía frontend sẽ phân biệt được: đây là cập nhật phiên/quyền chứ không phải nhập sai mật khẩu hay mất mạng, từ đó kích hoạt luồng reload êm đẹp.

#### Lớp 3: Cập nhật hiển thị giao diện Admin sau khi làm mới
- Sau khi giao diện được tải lại, `AuthService` nạp lại thông tin từ `GET /auth/me`.
- `AppUser.roles` nhận giá trị mới `["admin", ...]`.
- `RoleVisibility.isAdminUser(user)` lập tức trả về `true`.
- Tab số 9 (`Quản trị nhân sự` / `Employee Management`) và các nút duyệt/quản trị được mở khóa và hiển thị đầy đủ trên thanh điều hướng `AppShell`.

---

## 7. Kế Hoạch Kiểm Thử Tự Động (Testing Strategy)

1. **Unit Test cho Email Service (`backend/tests/test_email_service_templates.py`)**:
   - `test_build_admin_role_granted_html_structure`: Kiểm tra nội dung email hiển thị đúng tên vai trò, danh sách quyền hạn được cấp, thời gian, tên người cấp, link truy cập.
   - `test_build_admin_role_granted_html_escapes_xss`: Đảm bảo toàn bộ thẻ HTML trong username/display_name bị escape an toàn.
   - `test_build_admin_role_granted_plain`: Kiểm tra bản plain text có đầy đủ nội dung.
   - `test_send_admin_role_granted_email_unconfigured_smtp`: Kiểm tra hành vi demo mode khi chưa cấu hình SMTP (trả về False an toàn, không ném exception).

2. **Integration Test cho Endpoint Cập Nhật Quyền (`backend/tests/test_admin_user_role_notification.py`)**:
   - Sử dụng `monkeypatch` mock `_send_smtp_sync` tương tự như `test_admin_provision_specific_user.py`.
   - **Case 1 (Thành công)**: Admin cấp quyền `["admin"]` cho nhân viên có email thật -> Kiểm tra DB cập nhật thành công, `_send_smtp_sync` được gọi đúng người nhận và tiêu đề, API trả về 200 kèm `admin_email_sent=True`.
   - **Case 2 (SMTP lỗi / Timeout)**: Mock `_send_smtp_sync` ném ngoại lệ hoặc trả về lỗi kết nối -> Kiểm tra DB vẫn commit thành công vai trò `admin`, API vẫn trả về 200 và không bị gián đoạn giao dịch (`admin_email_sent=False`).
   - **Case 3 (Nhân viên không có email)**: Cập nhật quyền admin cho nhân viên có `email=None` -> API hoàn tất thành công 200, an toàn bỏ qua bước gửi thư.
   - **Case 4 (Sự kiện SSE được phát sóng)**: Xác thực sự kiện `role_updated` được phát qua `approval_event_bus` với đúng `user_id` và cờ `is_admin=True`.

---

## 8. Kết Luận Đánh Giá Kỹ Thuật

| Hạng mục | Hiện trạng | Đánh giá & Khả thi |
|---|---|---|
| **Mô hình IAM & Phân quyền** | Có sẵn bảng `iam_user_roles`, `iam_roles`, `iam_capabilities`. | Rất tốt, chuẩn Clean Architecture & RBAC. |
| **Endpoint Cập nhật Quyền** | `PUT /admin/users/{user_id}/roles` đã hoàn thiện đầy đủ guard, audit, outbox. | Điểm cắm (hook point) lý tưởng cho cả R1 (SSE) và R2 (Email). |
| **Hạ tầng SMTP** | Đã có `config.py` và `email_service.py` hoàn chỉnh, hỗ trợ STARTTLS/SSL, async thread, timeout 12s. | Tái sử dụng 100% hạ tầng hiện có, chỉ cần bổ sung template và hàm nghiệp vụ `send_admin_role_granted_email`. |
| **An toàn Giao dịch** | Mô hình commit trước, bắt ngoại lệ gửi email sau. | Đạt độ tin cậy cấp doanh nghiệp (fail-safe / resilient). |
| **Phát hiện đổi quyền (R1)** | Đã có sẵn bus SSE `approval_event_bus` kết nối với `DataSyncController` của Flutter. | Có thể phát sự kiện tức thời (real-time) với độ trễ < 100ms. |
