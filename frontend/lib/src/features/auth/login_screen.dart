import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../app/app_shell.dart';
import '../../core/util/error_text.dart';
import '../../core/widgets/google_logo.dart';
import '../../core/widgets/store_logo.dart';
import '../../data/repositories/bankops_repository.dart';
import 'auth_service.dart';
import 'accept_invite_screen.dart';
import 'widgets/forgot_password_dialog.dart';
import 'widgets/register_dialog.dart';

/// Màn hình đăng nhập Hệ Thống Quản Lý Nhập Xuất Tồn Quán Trà Sữa (MilkTea Ops).
/// Thiết kế Split-screen trên desktop/tablet, phong cách F&B hiện đại.
/// Hỗ trợ đăng nhập nhanh theo ca trực và Google Sign-In SSO.
class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    this.initialUsername,
    this.initialPassword,
    this.showDemoBanner = false,
  });

  /// Pre-fill the username field (e.g. for demo flow).
  final String? initialUsername;

  /// Pre-fill the password field (e.g. for demo flow).
  final String? initialPassword;

  /// When true, shows a top banner indicating this is a demo session.
  final bool showDemoBanner;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _usernameCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _usernameFocus = FocusNode();
  bool _busy = false;
  bool _obscurePassword = true;

  @override
  void dispose() {
    _usernameCtrl.dispose();
    _passwordCtrl.dispose();
    _usernameFocus.dispose();
    super.dispose();
  }

  Future<void> _loginWithPassword([String? presetUser, String? presetPass]) async {
    if (_busy) return;
    if (presetUser != null) {
      _usernameCtrl.text = presetUser;
    }
    if (presetPass != null) {
      _passwordCtrl.text = presetPass;
    }
    setState(() => _busy = true);
    try {
      final ok = await context.read<AuthService>().signInWithPassword(
            username: _usernameCtrl.text.trim(),
            password: _passwordCtrl.text,
          );
      if (!mounted) return;
      if (!ok) {
        final msg = context.read<AuthService>().lastError ??
            'Đăng nhập thất bại. Vui lòng kiểm tra lại thông tin tài khoản.';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: const Color(0xFFB42318),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            content: Row(
              children: [
                const Icon(Icons.error_outline, color: Colors.white, size: 20),
                const SizedBox(width: 8),
                Expanded(child: Text(msg)),
              ],
            ),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loginWithGoogleMock([String? roleName, String? email]) async {
    if (!kDebugMode) return; // Prod (release) không cho phép mock token.
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final token =
          'mock-${email ?? 'staff_morning@milktea.local'}:${roleName ?? 'Nguyễn Thị Mai (Trưởng Ca Sáng)'}';
      final ok = await context.read<AuthService>().signInWithGoogle(customToken: token);
      if (!mounted) return;
      if (!ok) {
        final msg = context.read<AuthService>().lastError ?? 'Đăng nhập Google thất bại.';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: const Color(0xFFDC2626),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            content: Text(msg),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _loginWithGoogle() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final ok = await context.read<AuthService>().signInWithGoogle();
      if (!mounted) return;
      if (!ok) {
        final auth = context.read<AuthService>();
        final msg = auth.lastError;
        if (msg == null ||
            msg.contains('Đã hủy') ||
            msg.toLowerCase().contains('popup_closed') ||
            msg.toLowerCase().contains('closed_by_user')) {
          // Người dùng chủ động tắt popup Google – giữ nguyên trạng thái
          return;
        }

        String userFriendlyMsg = msg;
        if (msg.contains('origin') ||
            msg.contains('invalid_client') ||
            msg.contains('registered origin')) {
          userFriendlyMsg =
              'Google OAuth: Domain Cloudflare chưa được đăng ký trong Authorized JavaScript origins của Google Cloud Console.';
        } else if (msg.contains('Validation failed') ||
            msg.contains('chưa hợp lệ')) {
          userFriendlyMsg =
              'Xác thực tài khoản Google không thành công. Vui lòng thử lại.';
        }

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: const Color(0xFFDC2626),
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 8),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
            content: Row(
              children: [
                const Icon(Icons.error_outline, color: Colors.white, size: 20),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    userFriendlyMsg,
                    style: const TextStyle(color: Colors.white, fontSize: 13),
                  ),
                ),
              ],
            ),
            action: kDebugMode
                ? SnackBarAction(
                    label: 'Thử Google Demo',
                    textColor: const Color(0xFFFDE047),
                    onPressed: () => _loginWithGoogleMock(),
                  )
                : null,
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFFDC2626),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 8),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          content: Row(
            children: [
              const Icon(Icons.error_outline, color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Lỗi xác thực Google: ${friendlyError(e)}',
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                ),
              ),
            ],
          ),
          action: kDebugMode
              ? SnackBarAction(
                  label: 'Thử Google Demo',
                  textColor: const Color(0xFFFDE047),
                  onPressed: () => _loginWithGoogleMock(),
                )
              : null,
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openForgotPassword() async {
    BankOpsRepository? repo;
    try {
      repo = RepositoryScope.of(context);
    } catch (_) {}
    final username = await ForgotPasswordDialog.show(
      context,
      initialUsername: _usernameCtrl.text.trim(),
      repository: repo,
    );
    if (username != null && mounted) {
      _usernameCtrl.text = username;
      _passwordCtrl.clear();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          backgroundColor: Color(0xFF059669),
          behavior: SnackBarBehavior.floating,
          content: Row(
            children: [
              Icon(Icons.check_circle_outline, color: Colors.white, size: 20),
              SizedBox(width: 8),
              Expanded(
                child: Text('Khôi phục mật khẩu thành công! Vui lòng đăng nhập.'),
              ),
            ],
          ),
        ),
      );
    }
  }

  Future<void> _openRegister() async {
    await RegisterDialog.show(context);
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final isDesktop = width >= 900;
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final overlayStyle = SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: isDark ? Brightness.light : Brightness.dark,
      statusBarBrightness: isDark ? Brightness.dark : Brightness.light,
      systemNavigationBarColor: Colors.transparent,
      systemNavigationBarDividerColor: Colors.transparent,
      systemNavigationBarIconBrightness:
          isDark ? Brightness.light : Brightness.dark,
      systemNavigationBarContrastEnforced: false,
      systemStatusBarContrastEnforced: false,
    );

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: overlayStyle,
      child: Scaffold(
        backgroundColor:
            isDark ? const Color(0xFF06140E) : const Color(0xFFF4F7F5),
        body: SafeArea(
          child: Center(
            child: isDesktop
                ? _buildDesktopLayout(context)
                : _buildMobileLayout(context),
          ),
        ),
      ),
    );
  }

  Widget _buildDesktopLayout(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 1100, maxHeight: 760),
      margin: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.12),
            blurRadius: 32,
            offset: const Offset(0, 8),
          ),
        ],
        border: Border.all(
          color: Theme.of(context).colorScheme.outlineVariant.withValues(alpha: 0.5),
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Row(
        children: [
          Expanded(
            flex: 5,
            child: _buildHeroPanel(context),
          ),
          Expanded(
            flex: 6,
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 44, vertical: 32),
              child: _buildLoginForm(context),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMobileLayout(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(20),
              side: BorderSide(
                color: Theme.of(context).colorScheme.outlineVariant.withValues(alpha: 0.6),
              ),
            ),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildBrandHeader(context),
                  const SizedBox(height: 20),
                  _buildLoginForm(context),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBrandHeader(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      children: [
        const StoreLogo(size: 56),
        const SizedBox(height: 14),
        Text(
          'Quản Lý Bán Hàng & Kho',
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w900,
            letterSpacing: -0.5,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Hệ thống quản lý bán hàng, kho hàng và công nợ thực chiến',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
            fontWeight: FontWeight.w500,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  Widget _buildHeroPanel(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(40),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [
            Color(0xFF062319),
            Color(0xFF0D3B2E),
            Color(0xFF0F4C3A),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.white.withValues(alpha: 0.18)),
                ),
                child: const Icon(
                  Icons.emoji_food_beverage_rounded,
                  color: Color(0xFFFDE047),
                  size: 26,
                ),
              ),
              const SizedBox(width: 14),
              const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'MilkTea Ops',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.w900,
                      letterSpacing: -0.5,
                    ),
                  ),
                  Text(
                    'HỆ THỐNG QUẢN LÝ NHẬP XUẤT TỒN',
                    style: TextStyle(
                      color: Color(0xFF86EFAC),
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.1,
                    ),
                  ),
                ],
              ),
            ],
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF059669).withValues(alpha: 0.25),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: const Color(0xFF34D399).withValues(alpha: 0.4)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.eco_rounded, color: Color(0xFF34D399), size: 14),
                    SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        'Vận Hành Theo Ca • Chuẩn F&B',
                        style: TextStyle(
                          color: Color(0xFF86EFAC),
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'Kiểm soát nguyên liệu\n& thất thoát theo ca',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 26,
                  fontWeight: FontWeight.w800,
                  height: 1.25,
                ),
              ),
              const SizedBox(height: 20),
              _buildFeatureItem(
                icon: Icons.schedule_rounded,
                title: 'Kiểm Kê 3 Ca Thời Gian Thực',
                desc: 'Chốt tồn Ca Sáng (07:30 - 15:00), Chiều (15:00 - 23:00) & Ca Lỡ. Công thức chốt tồn tự động.',
              ),
              const SizedBox(height: 14),
              _buildFeatureItem(
                icon: Icons.warning_amber_rounded,
                title: 'Cảnh Báo Tồn An Toàn & Hạn Dùng FEFO',
                desc: 'Tự động đổi màu đỏ khi chạm ngưỡng tối thiểu (Min Stock) & cảnh báo hạn sử dụng lô hàng.',
              ),
              const SizedBox(height: 14),
              _buildFeatureItem(
                icon: Icons.lock_clock_rounded,
                title: 'Chốt Ca Bất Biến & Vết Kiểm Toán',
                desc: 'Khóa ca sau 30 phút, chống sửa đổi số liệu quá khứ, phát hiện hao hụt chênh lệch tức thời.',
              ),
            ],
          ),
          Row(
            children: [
              const Icon(Icons.verified_outlined, color: Color(0xFF86EFAC), size: 16),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  'Hệ thống kiểm soát kho F&B • Phiên bản 2.0',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.65),
                    fontSize: 11.5,
                    fontWeight: FontWeight.w500,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildFeatureItem({
    required IconData icon,
    required String title,
    required String desc,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.all(6),
          margin: const EdgeInsets.only(top: 2),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(icon, color: const Color(0xFFFDE047), size: 16),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                desc,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.75),
                  fontSize: 11.5,
                  height: 1.3,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildLoginForm(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final auth = context.watch<AuthService>();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          'Đăng nhập hệ thống',
          style: theme.textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.w800,
            letterSpacing: -0.3,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Truy cập sổ kiểm kê, nhập xuất kho & chốt ca quầy pha chế',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 20),
        // Banner cảnh báo khi offline session bị discard vì backend sống lại:
        // tài khoản offline chưa tồn tại trên server, cần đăng nhập lại.
        if (auth.needsOfflineRelogin)
          Container(
            key: const Key('login-relogin-banner'),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFFEF3C7),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFF59E0B).withValues(alpha: 0.5)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.warning_amber_rounded,
                    color: Color(0xFFB45309), size: 22),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        auth.offlineReloginMessage ??
                            'Máy chủ đã hoạt động trở lại. Vui lòng đăng nhập lại.',
                        style: const TextStyle(
                          color: Color(0xFF92400E),
                          fontSize: 12.5,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 6),
                      TextButton(
                        key: const Key('login-relogin-btn'),
                        onPressed: () {
                          auth.clearOfflineReloginFlag();
                          _usernameFocus.requestFocus();
                        },
                        style: TextButton.styleFrom(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 4),
                          minimumSize: Size.zero,
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          backgroundColor: const Color(0xFF0F4C3A),
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                        child: const Text(
                          'Đăng nhập lại',
                          style: TextStyle(
                              fontSize: 12.5, fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        if (auth.needsOfflineRelogin) const SizedBox(height: 12),
        TextField(
          key: const Key('login-username-field'),
          controller: _usernameCtrl,
          focusNode: _usernameFocus,
          enabled: !_busy,
          decoration: InputDecoration(
            labelText: 'Tài khoản nhân viên / Quản lý',
            hintText: auth.apiBaseUrl.isEmpty
                ? 'staff_morning / manager_demo'
                : 'Tài khoản nhân viên',
            prefixIcon: const Icon(Icons.person_outline, size: 20),
            filled: true,
            isDense: true,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('login-password-field'),
          controller: _passwordCtrl,
          enabled: !_busy,
          obscureText: _obscurePassword,
          onSubmitted: (_) => _loginWithPassword(),
          decoration: InputDecoration(
            labelText: 'Mật khẩu',
            hintText: auth.apiBaseUrl.isEmpty
                ? 'DemoPass123! hoặc 123456'
                : 'Mật khẩu',
            prefixIcon: const Icon(Icons.lock_outline, size: 20),
            suffixIcon: IconButton(
              icon: Icon(
                _obscurePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                size: 20,
              ),
              onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
            ),
            filled: true,
            isDense: true,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
        const SizedBox(height: 6),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(
            key: const Key('login-forgot-password-btn'),
            onPressed: _busy ? null : _openForgotPassword,
            style: TextButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Text(
              'Quên mật khẩu?',
              style: TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
                color: Color(0xFF0F4C3A),
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          key: const Key('login-submit-btn'),
          onPressed: _busy ? null : () => _loginWithPassword(),
          style: FilledButton.styleFrom(
            padding: const EdgeInsets.symmetric(vertical: 14),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            backgroundColor: const Color(0xFF0F4C3A),
          ),
          icon: _busy
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                )
              : const Icon(Icons.login_rounded, size: 20),
          label: Text(
            _busy ? 'Đang xác thực thông tin…' : 'Đăng nhập vào ca',
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
          ),
        ),
        const SizedBox(height: 12),

        // Lối vào Reviewer Sandbox 3 phút (Dành cho nhà tuyển dụng & đánh giá portfolio)
        OutlinedButton.icon(
          key: const Key('login-reviewer-sandbox-btn'),
          onPressed: _busy
              ? null
              : () async {
                  setState(() => _busy = true);
                  try {
                    await auth.enterReviewerSandbox();
                  } finally {
                    if (mounted) setState(() => _busy = false);
                  }
                },
          icon: const Icon(Icons.science_outlined, color: Color(0xFFD97706)),
          label: const Text(
            'Trải Nghiệm Reviewer Sandbox (3 Phút — Dữ Liệu Mẫu)',
            style: TextStyle(fontWeight: FontWeight.w700, color: Color(0xFFB45309)),
          ),
          style: OutlinedButton.styleFrom(
            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
            side: const BorderSide(color: Color(0xFFF59E0B), width: 1.5),
            backgroundColor: const Color(0xFFFFFBEB),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
        ),
        const SizedBox(height: 16),

        // Quick shift accounts — hiển thị ở debug HOẶC web demo để đánh giá nhanh.
        if (kIsWeb || kDebugMode || auth.apiBaseUrl.isEmpty)
          Row(
            children: [
              Expanded(
                  child: Divider(
                      color: theme.colorScheme.outlineVariant
                          .withValues(alpha: 0.6))),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 10),
                child: Text(
                  'TÀI KHOẢN CA TRỰC (DEMO)',
                  style: theme.textTheme.labelSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.8,
                    fontSize: 10,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
              Expanded(
                  child: Divider(
                      color: theme.colorScheme.outlineVariant
                          .withValues(alpha: 0.6))),
            ],
          ),
        if (kIsWeb || kDebugMode || auth.apiBaseUrl.isEmpty) const SizedBox(height: 10),
        if (kIsWeb || kDebugMode || auth.apiBaseUrl.isEmpty)
          Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: [
              _buildShiftChip(
                key: const Key('login-shift-morning-chip'),
                icon: Icons.wb_sunny_outlined,
                label: 'Ca Sáng (07:30 - 15:00)',
                color: const Color(0xFF059669),
                onTap: () => _loginWithPassword('staff_morning', 'DemoPass123!'),
              ),
              _buildShiftChip(
                key: const Key('login-shift-afternoon-chip'),
                icon: Icons.nights_stay_outlined,
                label: 'Ca Chiều (15:00 - 23:00)',
                color: const Color(0xFFD97706),
                onTap: () =>
                    _loginWithPassword('staff_afternoon', 'DemoPass123!'),
              ),
              _buildShiftChip(
                key: const Key('login-shift-split-chip'),
                icon: Icons.access_time_outlined,
                label: 'Ca Lỡ (07:30 - 18:00)',
                color: const Color(0xFF0284C7),
                onTap: () => _loginWithPassword('staff_split', 'DemoPass123!'),
              ),
              _buildShiftChip(
                key: const Key('login-shift-manager-chip'),
                icon: Icons.admin_panel_settings_outlined,
                label: 'Chủ Quán / Quản Lý',
                color: const Color(0xFF7C3AED),
                onTap: () => _loginWithPassword('manager_demo', 'DemoPass123!'),
              ),
            ],
          ),
        if (kDebugMode || auth.apiBaseUrl.isEmpty) const SizedBox(height: 16),

        Row(
          children: [
            Expanded(child: Divider(color: theme.colorScheme.outlineVariant)),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text(
                'HOẶC TIẾP TỤC VỚI',
                style: theme.textTheme.labelSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.8,
                  fontSize: 10,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
            Expanded(child: Divider(color: theme.colorScheme.outlineVariant)),
          ],
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          key: const Key('login-google-btn'),
          onPressed: _busy ? null : _loginWithGoogle,
          style: OutlinedButton.styleFrom(
            padding: const EdgeInsets.symmetric(vertical: 12),
            backgroundColor: isDark ? const Color(0xFF1E293B) : Colors.white,
            foregroundColor: isDark ? Colors.white : const Color(0xFF1F2937),
            side: BorderSide(
              color: isDark ? const Color(0xFF334155) : const Color(0xFFDADCE0),
              width: 1,
            ),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            elevation: isDark ? 0 : 0.5,
          ),
          icon: const GoogleLogo(size: 20),
          label: const Text(
            'Đăng nhập bằng Google',
            style: TextStyle(
              fontWeight: FontWeight.w600,
              fontSize: 14,
              letterSpacing: 0.2,
            ),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          auth.isGoogleSignInConfigured
              ? 'Tài khoản Google nhân viên sẽ được tự động phân quyền theo ca trực.'
              : 'Hỗ trợ đăng nhập Single Sign-On (SSO) tài khoản Google của nhân viên.',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.8),
            fontSize: 11,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 12),
        Wrap(
          alignment: WrapAlignment.center,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(
              'Chưa có tài khoản?',
              style: TextStyle(
                color: theme.colorScheme.onSurfaceVariant,
                fontSize: 13,
              ),
            ),
            const SizedBox(width: 4),
            TextButton(
              key: const Key('login-register-btn'),
              onPressed: _busy ? null : _openRegister,
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: const Text(
                'Đăng ký ngay',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 13,
                  color: Color(0xFF0F4C3A),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Center(
          child: TextButton.icon(
            key: const Key('login-accept-invite-btn'),
            onPressed: _busy
                ? null
                : () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => const AcceptInviteScreen(),
                      ),
                    );
                  },
            icon: const Icon(Icons.mark_email_read_outlined, size: 16),
            label: const Text(
              'Nhận được thư mời? Kích hoạt tài khoản tại đây',
              style: TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
                color: Color(0xFF0284C7),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildShiftChip({
    required Key key,
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onTap,
  }) {
    return InkWell(
      key: key,
      onTap: _busy ? null : onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w600,
                color: color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
