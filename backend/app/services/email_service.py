"""Email notification service for Quản Lý Kho Trà Sữa."""
import asyncio
import html
import logging
import re
import smtplib
from datetime import UTC, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger("khotrasua.email")

# Regex email thực dụng: local@domain.tld (≥2 ký tự TLD), không chứa space.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def is_valid_email(value: str | None) -> bool:
    """Chỉ chấp nhận email thật có format hợp lệ (dùng cho invite & reset)."""
    if not value:
        return False
    val = value.strip().lower()
    if ".." in val or val.startswith(".") or "@." in val or ".@" in val:
        return False
    return bool(_EMAIL_RE.match(val))


def _build_otp_html(username: str, otp: str) -> str:
    safe_user = html.escape(username)
    safe_otp = html.escape(otp)
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mã xác thực khôi phục mật khẩu - Quản Lý Kho Trà Sữa</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f4f6f8; padding: 40px 20px;">
    <tr>
      <td align="center">
        <table width="100%" max-width="580" style="max-width: 580px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); border: 1px solid #e2e8f0;">
          <!-- Header -->
          <tr>
            <td style="background-color: #0A2540; padding: 28px 32px; text-align: left;">
              <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <span style="color: #ffffff; font-size: 22px; font-weight: 800; letter-spacing: 0.5px;">Quản Lý Kho Trà Sữa</span>
                    <span style="color: #FDE68A; font-size: 13px; font-weight: 600; margin-left: 8px; padding: 3px 8px; background: rgba(255,255,255,0.12); border-radius: 4px;">NHẬP · XUẤT · TỒN</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding: 36px 32px 24px 32px;">
              <h2 style="margin: 0 0 16px 0; font-size: 19px; font-weight: 700; color: #0f172a;">Yêu Cầu Khôi Phục Mật Khẩu</h2>
              <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #475569;">
                Xin chào <strong>{safe_user}</strong>,
              </p>
              <p style="margin: 0 0 24px 0; font-size: 14px; line-height: 1.6; color: #475569;">
                Hệ thống Quản Lý Kho Trà Sữa vừa nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn. Vui lòng sử dụng mã xác thực OTP dùng một lần dưới đây để hoàn tất:
              </p>

              <!-- OTP Code Display -->
              <div style="background-color: #f8fafc; border: 2px dashed #0A2540; border-radius: 8px; padding: 20px; text-align: center; margin-bottom: 24px;">
                <span style="display: block; font-size: 12px; font-weight: 600; text-transform: uppercase; color: #64748b; margin-bottom: 6px; letter-spacing: 1px;">MÃ XÁC THỰC OTP</span>
                <span style="font-family: 'SF Mono', Consolas, Monaco, monospace; font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #0A2540;">{safe_otp}</span>
                <span style="display: block; font-size: 12px; color: #dc2626; margin-top: 8px; font-weight: 600;">Hiệu lực trong vòng 15 phút (900 giây)</span>
              </div>

              <!-- Security Notice -->
              <div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 4px; margin-bottom: 24px;">
                <p style="margin: 0; font-size: 12.5px; line-height: 1.5; color: #92400e;">
                  <strong>Lưu ý bảo mật:</strong> Không chia sẻ mã OTP này cho bất kỳ ai. Nếu bạn không thực hiện yêu cầu này, vui lòng bỏ qua email và thông báo ngay cho quản lý cửa hàng.
                </p>
              </div>

              <p style="margin: 0; font-size: 13px; line-height: 1.5; color: #64748b;">
                Trân trọng,<br>
                <strong>Ban Vận Hành Quản Lý Kho Trà Sữa</strong>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 20px 32px; text-align: center;">
              <p style="margin: 0; font-size: 11.5px; color: #94a3b8; line-height: 1.4;">
                Đây là email tự động từ hệ thống Quản Lý Kho Trà Sữa. Vui lòng không trả lời trực tiếp email này.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


class EmailSendResult:
    """Wrapper cho kết quả gửi email, hỗ trợ evaluate như boolean và cung cấp thông điệp chi tiết."""

    def __init__(self, success: bool, message: str = ""):
        self.success = bool(success)
        self.message = str(message)

    @property
    def ok(self) -> bool:
        return self.success

    def __bool__(self) -> bool:
        return self.success

    def __repr__(self) -> str:
        return f"<EmailSendResult success={self.success} message={self.message!r}>"


def _send_smtp_sync(
    host: str,
    port: int,
    user: str,
    password: str,
    to_email: str,
    subject: str,
    html_content: str,
    plain_text_content: str | None = None,
    from_name: str = "Quản Lý Kho Trà Sữa",
) -> tuple[bool, str]:
    """Synchronous SMTP email sender designed to run inside asyncio.to_thread."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{user}>"
        msg["To"] = to_email

        if plain_text_content:
            part_plain = MIMEText(plain_text_content, "plain", "utf-8")
            msg.attach(part_plain)

        part_html = MIMEText(html_content, "html", "utf-8")
        msg.attach(part_html)

        # Support STARTTLS (port 587) and SSL (port 465)
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=12) as server:
                server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=12) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)

        logger.info("Successfully sent email to %s (subject: %s) via %s:%d", to_email, subject, host, port)
        return True, "Gửi email thành công"
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False, str(exc)


async def send_password_reset_email(to_email: str, username: str, otp: str) -> bool:
    """Send a password recovery OTP email asynchronously.
    
    If SMTP credentials are not configured, logs a helpful warning and returns False without raising error.
    """
    clean_email = to_email.strip()
    if not clean_email or "@" not in clean_email:
        logger.warning("Invalid recipient email: %s", to_email)
        return False

    smtp_user = settings.smtp_user.strip()
    smtp_pass = settings.smtp_password.strip()

    if not smtp_user or not smtp_pass:
        logger.info(
            "[EmailService (Demo mode)] SMTP not configured. OTP for user '%s' (%s) is %s",
            username,
            clean_email,
            otp,
        )
        return False

    subject = f"[{settings.smtp_from_name}] Mã xác thực OTP khôi phục mật khẩu: {otp}"
    html_body = _build_otp_html(username=username, otp=otp)
    plain_body = f"Xin chào {username},\n\nMã xác thực OTP của bạn là: {otp}\nHiệu lực trong 15 phút.\n"

    ok, _ = await asyncio.to_thread(
        _send_smtp_sync,
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=smtp_user,
        password=smtp_pass,
        to_email=clean_email,
        subject=subject,
        html_content=html_body,
        plain_text_content=plain_body,
        from_name=settings.smtp_from_name,
    )
    return ok


_ROLE_TITLES = {
    "admin": "Chủ Quán / Quản Trị Viên (Administrator)",
    "system_admin": "Quản Trị Viên Hệ Thống (System Administrator)",
    "root_admin": "Quản Trị Viên Cấp Cao (Root Administrator)",
    "superadmin": "Tổng Quản Trị Hệ Thống (Super Administrator)",
    "manager": "Quản Lý Cửa Hàng / Trưởng Ca (Store Manager)",
    "staff": "Nhân Viên Vận Hành / Pha Chế (Store Staff)",
    "auditor": "Kiểm Toán Viên Độc Lập (Auditor)",
    "supervisor": "Kiểm Soát Viên (Supervisor)",
}


def _build_invite_html(
    username: str,
    invite_link: str,
    expires_label: str,
    to_email: str = "",
    display_name: str | None = None,
    roles: list[str] | None = None,
    token: str | None = None,
    inviter_name: str | None = None,
) -> str:
    """HTML nội dung email mời kích hoạt tài khoản chuẩn doanh nghiệp cấp cao."""
    raw_full_name = (display_name or "").strip() or username
    full_name = html.escape(raw_full_name)
    safe_username = html.escape(username)
    safe_expires = html.escape(expires_label)
    safe_to_email = html.escape(to_email if to_email else "Email đăng ký của bạn")
    safe_invite_link = html.escape(invite_link)

    role_labels = [_ROLE_TITLES.get(r.lower(), r) for r in (roles or [])]
    role_desc = html.escape(", ".join(role_labels) if role_labels else "Quản Trị Viên Hệ Thống (Administrator)")

    inviter_intro = (
        f"Quản trị viên <strong>{html.escape(inviter_name.strip())}</strong>"
        if inviter_name and inviter_name.strip()
        else "Ban Quản Trị Hệ Thống"
    )

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lời mời kích hoạt tài khoản - Hệ Thống Quản Trị Doanh Nghiệp</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B; -webkit-font-smoothing: antialiased;">
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #F1F5F9; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 600px; background-color: #FFFFFF; border-radius: 14px; overflow: hidden; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08); border: 1px solid #E2E8F0;">
          
          <!-- Top Brand Header (Deep Slate / Navy) -->
          <tr>
            <td style="background-color: #0F172A; padding: 28px 36px; border-bottom: 3px solid #2563EB;">
              <table role="presentation" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="background-color: #2563EB; width: 36px; height: 36px; border-radius: 8px; text-align: center; vertical-align: middle;">
                    <span style="color: #FFFFFF; font-size: 18px; line-height: 36px; font-weight: 800;">⚡</span>
                  </td>
                  <td style="padding-left: 14px;">
                    <span style="color: #FFFFFF; font-size: 18px; font-weight: 800; letter-spacing: 0.5px; display: block;">HỆ THỐNG QUẢN TRỊ DOANH NGHIỆP</span>
                    <span style="color: #94A3B8; font-size: 11px; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase;">ENTERPRISE OPERATIONS SYSTEM</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Content Body -->
          <tr>
            <td style="padding: 32px 36px 24px 36px;">
              <h1 style="margin: 0 0 16px 0; font-size: 19px; font-weight: 800; color: #0F172A; line-height: 1.4;">
                Lời Mời Kích Hoạt Tài Khoản Quản Trị
              </h1>
              <p style="margin: 0 0 14px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
                Kính gửi Anh/Chị <strong>{full_name}</strong>,
              </p>
              <p style="margin: 0 0 22px 0; font-size: 14px; line-height: 1.65; color: #475569;">
                {inviter_intro} đã cấp quyền truy cập và mời bạn tham gia làm việc trên <strong>Hệ Thống Quản Trị Doanh Nghiệp</strong>. Vui lòng kiểm tra thông tin tài khoản và kích hoạt theo hướng dẫn dưới đây:
              </p>

              <!-- Account Details Card -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; margin-bottom: 24px; overflow: hidden;">
                <tr>
                  <td style="background-color: #F1F5F9; padding: 12px 18px; border-bottom: 1px solid #E2E8F0;">
                    <span style="font-size: 12px; font-weight: 800; text-transform: uppercase; color: #475569; letter-spacing: 0.8px;">THÔNG TIN TÀI KHOẢN & PHÂN QUYỀN</span>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 16px 18px;">
                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="6">
                      <tr>
                        <td width="38%" style="font-size: 13px; color: #64748B; font-weight: 600;">Họ và tên:</td>
                        <td style="font-size: 13.5px; color: #0F172A; font-weight: 700;">{full_name}</td>
                      </tr>
                      <tr>
                        <td style="font-size: 13px; color: #64748B; font-weight: 600;">Tên đăng nhập:</td>
                        <td style="font-size: 13.5px; color: #2563EB; font-weight: 700; font-family: 'SF Mono', Consolas, monospace;">@{safe_username}</td>
                      </tr>
                      <tr>
                        <td style="font-size: 13px; color: #64748B; font-weight: 600;">Hộp thư nhận:</td>
                        <td style="font-size: 13.5px; color: #0F172A;">{safe_to_email}</td>
                      </tr>
                      <tr>
                        <td style="font-size: 13px; color: #64748B; font-weight: 600;">Vai trò phân quyền:</td>
                        <td style="font-size: 13.5px; color: #059669; font-weight: 700;">{role_desc}</td>
                      </tr>
                      <tr>
                        <td style="font-size: 13px; color: #64748B; font-weight: 600;">Thời hạn kích hoạt:</td>
                        <td style="font-size: 13px; color: #DC2626; font-weight: 600;">7 ngày (Hết hạn: {safe_expires})</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Hero CTA Button -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 8px 0 20px 0;">
                <tr>
                  <td align="center">
                    <a href="{safe_invite_link}" target="_blank" style="display: inline-block; background-color: #2563EB; color: #FFFFFF; font-size: 15px; font-weight: 700; text-decoration: none; padding: 14px 36px; border-radius: 8px; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25); letter-spacing: 0.3px;">
                      Kích Hoạt Tài Khoản Quản Trị
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Enterprise Direct Link Fallback -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-top: 18px; margin-bottom: 24px; background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px 16px;">
                <tr>
                  <td>
                    <p style="margin: 0 0 6px 0; font-size: 12px; color: #64748B; font-weight: 600;">
                      Nếu nút bấm phía trên không hoạt động, sao chép liên kết trực tiếp sau vào trình duyệt:
                    </p>
                    <p style="margin: 0; font-size: 12px; word-break: break-all; line-height: 1.5;">
                      <a href="{safe_invite_link}" style="color: #2563EB; text-decoration: underline; font-family: 'SF Mono', Consolas, Monaco, monospace;">
                        {safe_invite_link}
                      </a>
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin: 24px 0 0 0; font-size: 13.5px; line-height: 1.5; color: #475569;">
                Trân trọng,<br>
                <strong style="color: #0F172A;">Ban Vận Hành & Chuyển Giao Công Nghệ</strong><br>
                <span style="font-size: 12px; color: #64748B;">Hệ Thống Quản Trị Doanh Nghiệp Core Operations</span>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 22px 36px; text-align: center;">
              <p style="margin: 0 0 6px 0; font-size: 11.5px; color: #94A3B8; line-height: 1.4;">
                Đây là thư điện tử được gửi tự động từ Hệ Thống Quản Trị Doanh Nghiệp. Vui lòng không trả lời trực tiếp email này.
              </p>
              <p style="margin: 0; font-size: 11px; color: #CBD5E1;">
                © 2026 Hệ Thống Quản Trị Doanh Nghiệp. All rights reserved. Tiêu chuẩn bảo mật ISO 27001 & Maker-Checker Dual Control.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_invite_plain(
    username: str,
    invite_link: str,
    expires_label: str,
    to_email: str = "",
    display_name: str | None = None,
    roles: list[str] | None = None,
    token: str | None = None,
    inviter_name: str | None = None,
) -> str:
    """Nội dung văn bản thuần (plain text) hỗ trợ bộ lọc email chống spam."""
    full_name = (display_name or "").strip() or username
    role_desc = (
        ", ".join(_ROLE_TITLES.get(r.lower(), r) for r in roles)
        if roles
        else "Quản Trị Viên Hệ Thống (Administrator)"
    )
    inviter_intro = (
        f"Quản trị viên {inviter_name.strip()}"
        if inviter_name and inviter_name.strip()
        else "Ban Quản Trị Hệ Thống"
    )

    return (
        f"=== THƯ MỜI THAM GIA QUẢN TRỊ HỆ THỐNG ===\n"
        f"HỆ THỐNG QUẢN TRỊ DOANH NGHIỆP\n\n"
        f"Kính gửi Anh/Chị {full_name},\n\n"
        f"{inviter_intro} đã cấp quyền truy cập và mời bạn tham gia làm việc trên Hệ Thống Quản Trị Doanh Nghiệp.\n\n"
        f"--- THÔNG TIN TÀI KHOẢN ---\n"
        f"• Họ và tên: {full_name}\n"
        f"• Tên đăng nhập: @{username}\n"
        f"• Email liên kết: {to_email}\n"
        f"• Vai trò phân quyền: {role_desc}\n"
        f"• Thời hạn kích hoạt: 7 ngày (Hết hạn: {expires_label})\n\n"
        f"--- LIÊN KẾT KÍCH HOẠT TÀI KHOẢN ---\n"
        f"{invite_link}\n\n"
        f"Nếu không bấm được nút, vui lòng sao chép liên kết trên vào trình duyệt.\n\n"
        f"Trân trọng,\n"
        f"Ban Vận Hành & Chuyển Giao Công Nghệ\n"
        f"Hệ Thống Quản Trị Doanh Nghiệp Core Operations\n"
        f"© 2026 Hệ Thống Quản Trị Doanh Nghiệp. All rights reserved.\n"
    )


async def send_invite_email(
    to_email: str,
    username: str,
    invite_link: str,
    expires_at,
    display_name: str | None = None,
    roles: list[str] | None = None,
    token: str | None = None,
    inviter_name: str | None = None,
) -> EmailSendResult:
    """Gửi email mời kích hoạt tài khoản (onboarding `invite_email`).

    Yêu cầu email thật (format hợp lệ). Trả về EmailSendResult hỗ trợ evaluate boolean
    và cung cấp thông báo trạng thái/lỗi chi tiết.
    """
    clean_email = (to_email or "").strip().lower()
    if not is_valid_email(clean_email):
        logger.warning("Invite skipped: email không hợp lệ cho user '%s': %s", username, to_email)
        return EmailSendResult(False, f"Email '{to_email}' không có định dạng hợp lệ")

    smtp_user = settings.smtp_user.strip()
    smtp_pass = settings.smtp_password.strip()
    if not smtp_user or not smtp_pass:
        logger.info(
            "[EmailService (Demo mode)] SMTP not configured. Invite for user '%s' (%s) link: %s",
            username, clean_email, invite_link,
        )
        return EmailSendResult(False, "Chưa cấu hình tài khoản SMTP (SMTP_USER hoặc SMTP_PASSWORD)")

    expires_label = (
        expires_at.strftime("%d/%m/%Y %H:%M") if getattr(expires_at, "year", None) else "7 ngày"
    )
    full_name = (display_name or "").strip() or username
    subject = f"[Hệ Thống] Lời mời kích hoạt tài khoản cho {full_name}"

    inviter_display = (inviter_name or "").strip()
    if inviter_display:
        from_name = f"{inviter_display} (Hệ Thống Quản Trị)"
    else:
        from_name = settings.smtp_from_name or "Ban Quản Trị Hệ Thống"

    html_body = _build_invite_html(
        username=username,
        invite_link=invite_link,
        expires_label=expires_label,
        to_email=clean_email,
        display_name=display_name,
        roles=roles,
        token=token,
        inviter_name=inviter_name,
    )
    plain_body = _build_invite_plain(
        username=username,
        invite_link=invite_link,
        expires_label=expires_label,
        to_email=clean_email,
        display_name=display_name,
        roles=roles,
        token=token,
        inviter_name=inviter_name,
    )

    ok, msg = await asyncio.to_thread(
        _send_smtp_sync,
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=smtp_user,
        password=smtp_pass,
        to_email=clean_email,
        subject=subject,
        html_content=html_body,
        plain_text_content=plain_body,
        from_name=from_name,
    )
    return EmailSendResult(ok, msg)


def _build_activation_confirmation_html(
    username: str,
    display_name: str | None = None,
    activated_at_str: str = "",
    app_url: str = "",
) -> str:
    """HTML nội dung email xác nhận kích hoạt tài khoản thành công và đóng luồng."""
    raw_full_name = (display_name or "").strip() or username
    full_name = html.escape(raw_full_name)
    safe_username = html.escape(username)
    safe_time = html.escape(activated_at_str)
    safe_app_url = html.escape(app_url)

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Xác nhận kích hoạt tài khoản thành công - Hệ Thống Quản Trị Doanh Nghiệp</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B; -webkit-font-smoothing: antialiased;">
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #F1F5F9; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 600px; background-color: #FFFFFF; border-radius: 14px; overflow: hidden; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08); border: 1px solid #E2E8F0;">
          
          <!-- Top Brand Header (Deep Slate / Navy) -->
          <tr>
            <td style="background-color: #0F172A; padding: 28px 36px; border-bottom: 3px solid #10B981;">
              <table role="presentation" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="background-color: #10B981; width: 36px; height: 36px; border-radius: 8px; text-align: center; vertical-align: middle;">
                    <span style="color: #FFFFFF; font-size: 18px; line-height: 36px; font-weight: 800;">✓</span>
                  </td>
                  <td style="padding-left: 14px;">
                    <span style="color: #FFFFFF; font-size: 18px; font-weight: 800; letter-spacing: 0.5px; display: block;">HỆ THỐNG QUẢN TRỊ DOANH NGHIỆP</span>
                    <span style="color: #94A3B8; font-size: 11px; font-weight: 600; letter-spacing: 0.8px; text-transform: uppercase;">XÁC NHẬN KÍCH HOẠT THÀNH CÔNG</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Content Body -->
          <tr>
            <td style="padding: 32px 36px 24px 36px;">
              <h1 style="margin: 0 0 16px 0; font-size: 19px; font-weight: 800; color: #0F172A; line-height: 1.4;">
                Tài Khoản Đã Kích Hoạt Thành Công
              </h1>
              <p style="margin: 0 0 14px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
                Kính gửi Anh/Chị <strong>{full_name}</strong>,
              </p>
              <p style="margin: 0 0 20px 0; font-size: 14px; line-height: 1.65; color: #475569;">
                Tài khoản của bạn (<strong>@{safe_username}</strong>) đã hoàn tất kích hoạt và đăng nhập thành công vào Hệ Thống Quản Trị Doanh Nghiệp lúc <strong>{safe_time}</strong>.
              </p>

              <!-- Security Notice / Resource Release -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 10px; margin-bottom: 24px; padding: 16px 18px;">
                <tr>
                  <td>
                    <span style="font-size: 12px; font-weight: 800; text-transform: uppercase; color: #166534; letter-spacing: 0.8px; display: block; margin-bottom: 6px;">
                      🔒 BẢO MẬT & THU HỒI TÀI NGUYÊN HOÀN TẤT
                    </span>
                    <p style="margin: 0; font-size: 13px; line-height: 1.6; color: #15803D;">
                      Toàn bộ liên kết mời và mã token dùng một lần trước đó đã được hệ thống <strong>thu hồi và hủy bỏ vĩnh viễn (Revoked & Released)</strong>. Bạn có thể sử dụng mật khẩu mới vừa thiết lập để đăng nhập cho các phiên làm việc tiếp theo.
                    </p>
                  </td>
                </tr>
              </table>

              <!-- CTA Button -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 8px 0 20px 0;">
                <tr>
                  <td align="center">
                    <a href="{safe_app_url}" target="_blank" style="display: inline-block; background-color: #0F172A; color: #FFFFFF; font-size: 15px; font-weight: 700; text-decoration: none; padding: 14px 36px; border-radius: 8px; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.25); letter-spacing: 0.3px;">
                      Truy Cập Hệ Thống Ngay
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin: 16px 0 0 0; font-size: 12.5px; line-height: 1.5; color: #DC2626;">
                ⚠️ <strong>Cảnh báo an ninh:</strong> Nếu bạn không thực hiện việc kích hoạt tài khoản này, vui lòng thông báo khẩn cấp cho Quản Trị Viên để phong tỏa tài khoản ngay lập tức.
              </p>

              <p style="margin: 24px 0 0 0; font-size: 13.5px; line-height: 1.5; color: #475569;">
                Trân trọng,<br>
                <strong style="color: #0F172A;">Ban Vận Hành & An Ninh Hệ Thống</strong><br>
                <span style="font-size: 12px; color: #64748B;">Hệ Thống Quản Trị Doanh Nghiệp Core Operations</span>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 22px 36px; text-align: center;">
              <p style="margin: 0 0 6px 0; font-size: 11.5px; color: #94A3B8; line-height: 1.4;">
                Đây là thư điện tử được gửi tự động từ Hệ Thống Quản Trị Doanh Nghiệp. Vui lòng không trả lời trực tiếp email này.
              </p>
              <p style="margin: 0; font-size: 11px; color: #CBD5E1;">
                © 2026 Hệ Thống Quản Trị Doanh Nghiệp. All rights reserved. Tiêu chuẩn bảo mật ISO 27001.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_activation_confirmation_plain(
    username: str,
    display_name: str | None = None,
    activated_at_str: str = "",
    app_url: str = "",
) -> str:
    """Nội dung plain-text cho email xác nhận kích hoạt tài khoản."""
    full_name = (display_name or "").strip() or username
    return (
        f"=== XÁC NHẬN KÍCH HOẠT TÀI KHOẢN THÀNH CÔNG ===\n"
        f"HỆ THỐNG QUẢN TRỊ DOANH NGHIỆP\n\n"
        f"Kính gửi Anh/Chị {full_name},\n\n"
        f"Tài khoản của bạn (@{username}) đã hoàn tất kích hoạt và đăng nhập thành công vào Hệ Thống Quản Trị Doanh Nghiệp lúc {activated_at_str}.\n\n"
        f"--- BẢO MẬT & THU HỒI TÀI NGUYÊN ---\n"
        f"Toàn bộ liên kết mời và mã token dùng một lần trước đó đã được hệ thống thu hồi và hủy bỏ vĩnh viễn (Revoked & Released).\n\n"
        f"Truy cập hệ thống: {app_url}\n\n"
        f"Nếu không phải bạn thực hiện, vui lòng liên hệ ngay Quản Trị Viên để khóa tài khoản.\n\n"
        f"Trân trọng,\n"
        f"Ban Vận Hành & An Ninh Hệ Thống\n"
        f"© 2026 Hệ Thống Quản Trị Doanh Nghiệp. All rights reserved.\n"
    )


async def send_activation_confirmation_email(
    to_email: str,
    username: str,
    display_name: str | None = None,
    activated_at: datetime | None = None,
) -> EmailSendResult:
    """Gửi email xác nhận sau khi user kích hoạt tài khoản thành công và đóng luồng tác vụ."""
    clean_email = (to_email or "").strip().lower()
    if not is_valid_email(clean_email):
        return EmailSendResult(False, f"Email '{to_email}' không có định dạng hợp lệ")

    smtp_user = settings.smtp_user.strip()
    smtp_pass = settings.smtp_password.strip()
    if not smtp_user or not smtp_pass:
        return EmailSendResult(False, "Chưa cấu hình tài khoản SMTP (SMTP_USER hoặc SMTP_PASSWORD)")

    now_dt = activated_at or datetime.now(UTC)
    # Định dạng hiển thị giờ UTC+7
    tz_vn = timezone(timedelta(hours=7))
    time_str = now_dt.astimezone(tz_vn).strftime("%H:%M:%S ngày %d/%m/%Y (Giờ Việt Nam)")

    full_name = (display_name or "").strip() or username
    subject = f"[Hệ Thống] Kích hoạt tài khoản thành công - {full_name}"
    from_name = settings.smtp_from_name or "Ban Quản Trị Hệ Thống"
    app_url = settings.frontend_base_url.rstrip("/")

    html_body = _build_activation_confirmation_html(
        username=username,
        display_name=display_name,
        activated_at_str=time_str,
        app_url=app_url,
    )
    plain_body = _build_activation_confirmation_plain(
        username=username,
        display_name=display_name,
        activated_at_str=time_str,
        app_url=app_url,
    )

    ok, msg = await asyncio.to_thread(
        _send_smtp_sync,
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=smtp_user,
        password=smtp_pass,
        to_email=clean_email,
        subject=subject,
        html_content=html_body,
        plain_text_content=plain_body,
        from_name=from_name,
    )
    return EmailSendResult(ok, msg)
 
 
def _build_admin_role_granted_html(
    username: str,
    to_email: str = "",
    display_name: str | None = None,
    new_roles: list[str] | None = None,
    granted_by_username: str | None = None,
    granted_at_str: str = "",
    app_url: str = "",
) -> str:
    """HTML template thông báo cấp quyền Quản Trị Viên (Admin) chuẩn doanh nghiệp."""
    raw_full_name = (display_name or "").strip() or username
    full_name = html.escape(raw_full_name)
    safe_username = html.escape(username)
    safe_email = html.escape(to_email if to_email else "Email đăng ký của bạn")
    safe_time = html.escape(granted_at_str)
    safe_app_url = html.escape(app_url)

    role_labels = [_ROLE_TITLES.get(r.lower(), r) for r in (new_roles or [])]
    role_desc = html.escape(", ".join(role_labels) if role_labels else "Quản Trị Viên (Admin)")

    granter_display = (granted_by_username or "").strip()
    if granter_display:
        granter_intro = f"Quản trị viên <strong>{html.escape(granter_display)}</strong>"
        safe_granter_val = html.escape(granter_display)
    else:
        granter_intro = "Ban Quản Trị Hệ Thống"
        safe_granter_val = "Ban Quản Trị Hệ Thống"

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Thông Báo Cấp Quyền Quản Trị Viên (Admin) - Hệ Thống Quản Trị Doanh Nghiệp</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F1F5F9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B; -webkit-font-smoothing: antialiased;">
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #F1F5F9; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 600px; background-color: #FFFFFF; border-radius: 14px; overflow: hidden; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08); border: 1px solid #E2E8F0;">
          
          <!-- Top Brand Header (Deep Slate / Navy with Royal Blue Accent) -->
          <tr>
            <td style="background-color: #0F172A; padding: 28px 36px; border-bottom: 3px solid #2563EB;">
              <table role="presentation" border="0" cellspacing="0" cellpadding="0" width="100%">
                <tr>
                  <td>
                    <span style="color: #FFFFFF; font-size: 18px; font-weight: 800; letter-spacing: 0.5px; display: block;">HỆ THỐNG QUẢN TRỊ DOANH NGHIỆP</span>
                    <span style="color: #93C5FD; font-size: 12px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase;">THÔNG BÁO CẤP QUYỀN QUẢN TRỊ VIÊN (ADMIN)</span>
                  </td>
                  <td align="right">
                    <span style="background-color: #1E3A8A; color: #DBEAFE; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 6px; letter-spacing: 0.5px; border: 1px solid #3B82F6;">ADMIN PRIVILEGE</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Main Content Body -->
          <tr>
            <td style="padding: 32px 36px 24px 36px;">
              <h1 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 800; color: #0F172A; line-height: 1.4;">
                Tài Khoản Đã Được Cấp Quyền Quản Trị Viên (Admin)
              </h1>
              <p style="margin: 0 0 14px 0; font-size: 14.5px; line-height: 1.6; color: #334155;">
                Kính gửi Anh/Chị <strong>{full_name}</strong>,
              </p>
              <p style="margin: 0 0 20px 0; font-size: 14px; line-height: 1.65; color: #475569;">
                Tài khoản của bạn (<strong>@{safe_username}</strong>) vừa được cập nhật và cấp quyền <strong>Quản Trị Viên (Admin)</strong> trên Hệ Thống Quản Trị Doanh Nghiệp. Quyền quản trị này được thiết lập bởi {granter_intro} vào lúc <strong>{safe_time}</strong>.
              </p>

              <!-- Account & Grant Info Box -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; margin-bottom: 24px; padding: 18px 20px;">
                <tr>
                  <td>
                    <span style="font-size: 12px; font-weight: 800; text-transform: uppercase; color: #0F172A; letter-spacing: 0.8px; display: block; margin-bottom: 12px; border-bottom: 1px solid #E2E8F0; padding-bottom: 6px;">
                      THÔNG TIN CẤP QUYỀN HỆ THỐNG
                    </span>
                    <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="4" style="font-size: 13.5px; color: #334155;">
                      <tr>
                        <td style="width: 38%; color: #64748B; font-weight: 600;">Họ và tên:</td>
                        <td style="font-weight: 700; color: #0F172A;">{full_name}</td>
                      </tr>
                      <tr>
                        <td style="color: #64748B; font-weight: 600;">Tên đăng nhập:</td>
                        <td style="font-family: 'SF Mono', Consolas, Monaco, monospace; font-weight: 700; color: #2563EB;">@{safe_username}</td>
                      </tr>
                      <tr>
                        <td style="color: #64748B; font-weight: 600;">Email liên kết:</td>
                        <td style="color: #0F172A;">{safe_email}</td>
                      </tr>
                      <tr>
                        <td style="color: #64748B; font-weight: 600;">Vai trò phân quyền:</td>
                        <td style="font-weight: 700; color: #1E40AF;">{role_desc}</td>
                      </tr>
                      <tr>
                        <td style="color: #64748B; font-weight: 600;">Người thực hiện:</td>
                        <td style="font-weight: 600; color: #0F172A;">{safe_granter_val}</td>
                      </tr>
                      <tr>
                        <td style="color: #64748B; font-weight: 600;">Thời gian cấp quyền:</td>
                        <td style="color: #475569;">{safe_time}</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Privilege & Capabilities Summary -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; margin-bottom: 24px; padding: 18px 20px;">
                <tr>
                  <td>
                    <span style="font-size: 12px; font-weight: 800; text-transform: uppercase; color: #1E40AF; letter-spacing: 0.8px; display: block; margin-bottom: 10px;">
                      📋 TỔNG HỢP QUYỀN HẠN & PHẠM VI QUẢN TRỊ
                    </span>
                    <ul style="margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.7; color: #1E3A8A;">
                      <li><strong>Quản trị người dùng & Phân quyền (IAM):</strong> Toàn quyền khởi tạo, cấu hình vai trò, phân quyền truy cập và quản lý phạm vi tài khoản.</li>
                      <li><strong>Phê duyệt kho & Kiểm soát vận hành:</strong> Phê duyệt các yêu cầu nhập, xuất kho, điều chỉnh tồn kho và kiểm soát tài sản doanh nghiệp.</li>
                      <li><strong>Quản lý sổ quỹ & Đối soát tài chính:</strong> Giám sát dòng tiền, thiết lập định mức két tiền, phê duyệt thanh toán và đối soát số dư.</li>
                      <li><strong>Cấu hình & Nhật ký kiểm toán:</strong> Truy cập hệ thống báo cáo phân tích số liệu kinh doanh và giám sát nhật ký Audit Trail toàn diện.</li>
                    </ul>
                  </td>
                </tr>
              </table>

              <!-- Security Notice -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #FFFBEB; border-left: 4px solid #F59E0B; border-radius: 4px; margin-bottom: 24px; padding: 14px 16px;">
                <tr>
                  <td>
                    <span style="font-size: 12px; font-weight: 800; text-transform: uppercase; color: #92400E; display: block; margin-bottom: 4px;">
                      🔒 LƯU Ý BẢO MẬT & AN NINH HỆ THỐNG
                    </span>
                    <p style="margin: 0; font-size: 12.5px; line-height: 1.6; color: #78350F;">
                      Vai trò Quản Trị Viên (Admin) có phạm vi ảnh hưởng trực tiếp đến toàn bộ hệ thống. Vui lòng bảo mật thông tin đăng nhập, không cung cấp mật khẩu hoặc mã xác thực (OTP/PIN) cho người khác. Nếu bạn không nhận diện hành vi cấp quyền này, vui lòng thông báo khẩn cấp cho Quản Trị Viên Hệ Thống.
                    </p>
                  </td>
                </tr>
              </table>

              <!-- CTA Button -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 8px 0 20px 0;">
                <tr>
                  <td align="center">
                    <a href="{safe_app_url}" target="_blank" style="display: inline-block; background-color: #2563EB; color: #FFFFFF; font-size: 15px; font-weight: 700; text-decoration: none; padding: 14px 36px; border-radius: 8px; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25); letter-spacing: 0.3px;">
                      Truy Cập Hệ Thống Quản Trị
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin: 24px 0 0 0; font-size: 13.5px; line-height: 1.5; color: #475569;">
                Trân trọng,<br>
                <strong style="color: #0F172A;">Ban Vận Hành & An Ninh Hệ Thống</strong><br>
                <span style="font-size: 12px; color: #64748B;">Hệ Thống Quản Trị Doanh Nghiệp Core Operations</span>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 22px 36px; text-align: center;">
              <p style="margin: 0 0 6px 0; font-size: 11.5px; color: #94A3B8; line-height: 1.4;">
                Đây là thư điện tử được gửi tự động từ Hệ Thống Quản Trị Doanh Nghiệp. Vui lòng không trả lời trực tiếp email này.
              </p>
              <p style="margin: 0; font-size: 11px; color: #CBD5E1;">
                © 2026 Hệ Thống Quản Trị Doanh Nghiệp. All rights reserved. Tiêu chuẩn bảo mật ISO 27001.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_admin_role_granted_plain(
    username: str,
    to_email: str = "",
    display_name: str | None = None,
    new_roles: list[str] | None = None,
    granted_by_username: str | None = None,
    granted_at_str: str = "",
    app_url: str = "",
) -> str:
    """Nội dung văn bản thuần (plain-text) cho email thông báo cấp quyền Quản Trị Viên (Admin)."""
    full_name = (display_name or "").strip() or username
    role_labels = [_ROLE_TITLES.get(r.lower(), r) for r in (new_roles or [])]
    role_desc = ", ".join(role_labels) if role_labels else "Quản Trị Viên (Admin)"
    granter_display = (granted_by_username or "").strip() or "Ban Quản Trị Hệ Thống"

    return (
        f"=== THÔNG BÁO CẤP QUYỀN QUẢN TRỊ VIÊN (ADMIN) ===\n"
        f"HỆ THỐNG QUẢN TRỊ DOANH NGHIỆP\n\n"
        f"Kính gửi Anh/Chị {full_name},\n\n"
        f"Tài khoản của bạn (@{username}) đã được cấp quyền Quản Trị Viên (Admin) trên Hệ Thống Quản Trị Doanh Nghiệp.\n\n"
        f"--- THÔNG TIN CẤP QUYỀN HỆ THỐNG ---\n"
        f"• Họ và tên: {full_name}\n"
        f"• Tên đăng nhập: @{username}\n"
        f"• Email liên kết: {to_email}\n"
        f"• Vai trò phân quyền: {role_desc}\n"
        f"• Người thực hiện: {granter_display}\n"
        f"• Thời gian cấp quyền: {granted_at_str}\n\n"
        f"--- TỔNG HỢP QUYỀN HẠN & PHẠM VI QUẢN TRỊ ---\n"
        f"1. Quản trị người dùng & Phân quyền (IAM): Toàn quyền khởi tạo, cấu hình vai trò, phân quyền truy cập và quản lý phạm vi tài khoản.\n"
        f"2. Phê duyệt kho & Kiểm soát vận hành: Phê duyệt các yêu cầu nhập, xuất kho, điều chỉnh tồn kho và kiểm soát tài sản doanh nghiệp.\n"
        f"3. Quản lý sổ quỹ & Đối soát tài chính: Giám sát dòng tiền, thiết lập định mức két tiền, phê duyệt thanh toán và đối soát số dư.\n"
        f"4. Cấu hình & Nhật ký kiểm toán: Truy cập hệ thống báo cáo phân tích số liệu kinh doanh và giám sát nhật ký Audit Trail toàn diện.\n\n"
        f"--- HƯỚNG DẪN TRUY CẬP ---\n"
        f"Đăng nhập vào hệ thống tại: {app_url}\n\n"
        f"LƯU Ý BẢO MẬT:\n"
        f"Vai trò Quản Trị Viên (Admin) có phạm vi ảnh hưởng trực tiếp đến toàn bộ hệ thống. Vui lòng bảo mật thông tin đăng nhập, không cung cấp mật khẩu hoặc mã xác thực (OTP/PIN) cho người khác. Nếu bạn không nhận diện hành vi cấp quyền này, vui lòng thông báo khẩn cấp cho Quản Trị Viên Hệ Thống.\n\n"
        f"Trân trọng,\n"
        f"Ban Vận Hành & An Ninh Hệ Thống\n"
        f"Hệ Thống Quản Trị Doanh Nghiệp Core Operations\n"
        f"© 2026 Hệ Thống Quản Trị Doanh Nghiệp. All rights reserved.\n"
    )


async def send_admin_role_granted_email(
    to_email: str,
    username: str,
    display_name: str | None,
    new_roles: list[str],
    granted_by_username: str | None = None,
) -> EmailSendResult:
    """Gửi email thông báo trực tiếp khi người dùng được cấp quyền Quản Trị Viên (Admin).

    Gracefully handle demo mode when SMTP credentials are not configured,
    exactly like existing email methods.
    """
    clean_email = (to_email or "").strip().lower()
    if not is_valid_email(clean_email):
        logger.warning("Admin grant email skipped: email không hợp lệ cho user '%s': %s", username, to_email)
        return EmailSendResult(False, f"Email '{to_email}' không có định dạng hợp lệ")

    smtp_user = settings.smtp_user.strip()
    smtp_pass = settings.smtp_password.strip()
    if not smtp_user or not smtp_pass:
        logger.info(
            "[EmailService (Demo mode)] SMTP not configured. Admin role granted email for user '%s' (%s) with roles: %s",
            username, clean_email, new_roles,
        )
        return EmailSendResult(False, "Chưa cấu hình tài khoản SMTP (SMTP_USER hoặc SMTP_PASSWORD)")

    tz_vn = timezone(timedelta(hours=7))
    time_str = datetime.now(UTC).astimezone(tz_vn).strftime("%H:%M:%S ngày %d/%m/%Y (Giờ Việt Nam)")

    full_name = (display_name or "").strip() or username
    subject = f"[Hệ Thống] Thông báo cấp quyền Quản Trị Viên (Admin) cho {full_name}"

    granter_display = (granted_by_username or "").strip()
    if granter_display:
        from_name = f"{granter_display} (Ban Quản Trị Hệ Thống)"
    else:
        from_name = settings.smtp_from_name or "Ban Quản Trị Hệ Thống"

    app_url = settings.frontend_base_url.rstrip("/")

    html_body = _build_admin_role_granted_html(
        username=username,
        to_email=clean_email,
        display_name=display_name,
        new_roles=new_roles,
        granted_by_username=granted_by_username,
        granted_at_str=time_str,
        app_url=app_url,
    )
    plain_body = _build_admin_role_granted_plain(
        username=username,
        to_email=clean_email,
        display_name=display_name,
        new_roles=new_roles,
        granted_by_username=granted_by_username,
        granted_at_str=time_str,
        app_url=app_url,
    )

    ok, msg = await asyncio.to_thread(
        _send_smtp_sync,
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=smtp_user,
        password=smtp_pass,
        to_email=clean_email,
        subject=subject,
        html_content=html_body,
        plain_text_content=plain_body,
        from_name=from_name,
    )
    return EmailSendResult(ok, msg)


async def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    plain_text_content: str | None = None,
    roles: list[str] | None = None,
    username: str | None = None,
    from_name: str | None = None,
    **kwargs,
) -> EmailSendResult:
    """Generic async email dispatcher supporting general role and system updates."""
    clean_email = (to_email or "").strip().lower()
    if not is_valid_email(clean_email):
        logger.warning("Email skipped: email không hợp lệ: %s", to_email)
        return EmailSendResult(False, f"Email '{to_email}' không có định dạng hợp lệ")

    smtp_user = settings.smtp_user.strip()
    smtp_pass = settings.smtp_password.strip()
    if not smtp_user or not smtp_pass:
        logger.info("[EmailService (Demo mode)] SMTP not configured. Skipped email to %s (subject: %s)", clean_email, subject)
        return EmailSendResult(False, "Chưa cấu hình tài khoản SMTP (SMTP_USER hoặc SMTP_PASSWORD)")

    ok, msg = await asyncio.to_thread(
        _send_smtp_sync,
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=smtp_user,
        password=smtp_pass,
        to_email=clean_email,
        subject=subject,
        html_content=html_content,
        plain_text_content=plain_text_content,
        from_name=from_name or settings.smtp_from_name or "Ban Quản Trị Hệ Thống",
    )
    return EmailSendResult(ok, msg)


def _build_security_alert_html(
    title: str,
    message: str,
    time_str: str,
    details: dict[str, str] | None = None,
) -> str:
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    rows_html = ""
    if details:
        for k, v in details.items():
            rows_html += f"""
            <tr>
              <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #475569; width: 35%;">{html.escape(str(k))}</td>
              <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0; color: #0f172a; font-family: monospace;">{html.escape(str(v))}</td>
            </tr>
            """

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>{safe_title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; padding: 30px 15px;">
    <tr>
      <td align="center">
        <table width="100%" max-width="600" style="max-width: 600px; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border: 1px solid #e2e8f0;">
          <tr>
            <td style="background-color: #991b1b; padding: 20px 28px; text-align: left;">
              <span style="color: #ffffff; font-size: 18px; font-weight: 800; letter-spacing: 0.5px;">🚨 CẢNH BÁO AN NINH HỆ THỐNG</span>
            </td>
          </tr>
          <tr>
            <td style="padding: 28px;">
              <h2 style="margin: 0 0 12px 0; font-size: 18px; color: #991b1b;">{safe_title}</h2>
              <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #334155;">{safe_message}</p>
              
              <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 16px 0; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13.5px; border-collapse: collapse;">
                <tbody>
                  {rows_html}
                  <tr>
                    <td style="padding: 8px 12px; font-weight: 600; color: #475569;">Thời gian ghi nhận</td>
                    <td style="padding: 8px 12px; color: #0f172a;">{time_str}</td>
                  </tr>
                </tbody>
              </table>

              <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; border-radius: 4px; margin-top: 20px;">
                <p style="margin: 0; font-size: 12.5px; line-height: 1.5; color: #991b1b;">
                  <strong>Hành động khuyến nghị:</strong> Nếu đây không phải là thao tác hợp lệ của nhân viên, vui lòng truy cập ngay trang quản trị để tạm khóa tài khoản hoặc thu hồi phiên làm việc khẩn cấp.
                </p>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_security_alert_plain(
    title: str,
    message: str,
    time_str: str,
    details: dict[str, str] | None = None,
) -> str:
    lines = [
        "=== [CẢNH BÁO AN NINH HỆ THỐNG] ===",
        title,
        "",
        message,
        "",
        "Chi tiết sự kiện:",
    ]
    if details:
        for k, v in details.items():
            lines.append(f"- {k}: {v}")
    lines.append(f"- Thời gian ghi nhận: {time_str}")
    lines.extend([
        "",
        "Khuyến nghị: Nếu đây không phải thao tác hợp lệ, vui lòng khóa tài khoản hoặc thu hồi phiên làm việc khẩn cấp.",
    ])
    return "\n".join(lines)


async def send_security_alert_email(
    subject: str,
    title: str,
    message: str,
    details: dict[str, str] | None = None,
    to_emails: list[str] | None = None,
) -> EmailSendResult:
    """Gửi email cảnh báo an ninh tới Quản trị viên hệ thống (Admin)."""
    target_emails = to_emails or [settings.admin_alert_email] + getattr(settings, "admin_emails", [])
    valid_recipients = list({e.strip().lower() for e in target_emails if is_valid_email(e)})
    if not valid_recipients:
        logger.warning("Không có email quản trị viên hợp lệ để gửi cảnh báo an ninh")
        return EmailSendResult(False, "Không có email quản trị viên hợp lệ")

    smtp_user = settings.smtp_user.strip()
    smtp_pass = settings.smtp_password.strip()
    if not smtp_user or not smtp_pass:
        logger.info(
            "SECURITY_ALERT (SMTP chưa cấu hình, logged): %s | title=%s | details=%s",
            subject, title, details
        )
        return EmailSendResult(False, "Chưa cấu hình tài khoản SMTP")

    tz_vn = timezone(timedelta(hours=7))
    time_str = datetime.now(UTC).astimezone(tz_vn).strftime("%H:%M:%S ngày %d/%m/%Y (Giờ VN)")
    html_body = _build_security_alert_html(title, message, time_str, details)
    plain_body = _build_security_alert_plain(title, message, time_str, details)
    from_name = f"{settings.smtp_from_name or 'Hệ Thống'} - An Ninh"

    all_ok = True
    last_msg = ""
    for email_addr in valid_recipients:
        ok, msg = await asyncio.to_thread(
            _send_smtp_sync,
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=smtp_user,
            password=smtp_pass,
            to_email=email_addr,
            subject=f"[CẢNH BÁO AN NINH] {subject}",
            html_content=html_body,
            plain_text_content=plain_body,
            from_name=from_name,
        )
        if not ok:
            all_ok = False
            last_msg = msg

    return EmailSendResult(all_ok, last_msg or "Đã gửi email cảnh báo an ninh")


async def check_smtp_health() -> dict:
    """Kiểm tra sức khỏe kết nối tới máy chủ SMTP."""
    smtp_user = settings.smtp_user.strip()
    smtp_pass = settings.smtp_password.strip()
    if not smtp_user or not smtp_pass:
        return {"configured": False, "status": "unconfigured", "message": "SMTP chưa được cấu hình"}

    def _probe() -> tuple[bool, str]:
        try:
            if settings.smtp_port == 465:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=8) as server:
                    server.login(smtp_user, smtp_pass)
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
            return True, "Kết nối và xác thực SMTP thành công"
        except Exception as exc:
            return False, str(exc)

    ok, msg = await asyncio.to_thread(_probe)
    return {
        "configured": True,
        "host": settings.smtp_host,
        "port": settings.smtp_port,
        "user": smtp_user,
        "status": "connected" if ok else "failed",
        "message": msg,
    }

