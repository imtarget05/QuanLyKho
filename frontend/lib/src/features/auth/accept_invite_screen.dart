import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/widgets/store_logo.dart';
import 'auth_service.dart';

/// Màn hình Kích hoạt tài khoản từ thư mời của Quản trị viên (Email Invite Onboarding).
/// Hỗ trợ cả Web (nhận token từ link URL) và Mobile (dán mã token).
class AcceptInviteScreen extends StatefulWidget {
  const AcceptInviteScreen({
    super.key,
    this.initialToken,
    this.onBackToLogin,
    this.onSuccess,
  });

  final String? initialToken;
  final VoidCallback? onBackToLogin;
  final VoidCallback? onSuccess;

  @override
  State<AcceptInviteScreen> createState() => _AcceptInviteScreenState();
}

class _AcceptInviteScreenState extends State<AcceptInviteScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _tokenCtrl;
  final _passwordCtrl = TextEditingController();
  final _confirmPasswordCtrl = TextEditingController();

  String _previousPassword = '';
  bool _obscurePassword = true;
  bool _obscureConfirm = true;
  bool _busy = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _tokenCtrl = TextEditingController(text: widget.initialToken ?? '');
    _passwordCtrl.addListener(_onPasswordChanged);
    _confirmPasswordCtrl.addListener(_onConfirmPasswordChanged);
  }

  void _onPasswordChanged() {
    final newPass = _passwordCtrl.text;
    if (newPass == _previousPassword) return;

    final isAutofillOrPaste = (newPass.length - _previousPassword.length) > 1;
    final confirmMatchesPrevious =
        _confirmPasswordCtrl.text == _previousPassword;

    // Tự động đồng bộ sang ô xác nhận khi:
    // 1. Trình duyệt / Password manager tự động điền mật khẩu mạnh (chunk length delta > 1)
    // 2. Hoặc ô xác nhận trước đó đang đồng bộ với mật khẩu cũ
    if (newPass.isNotEmpty &&
        (isAutofillOrPaste ||
            (confirmMatchesPrevious && _previousPassword.isNotEmpty))) {
      _confirmPasswordCtrl.text = newPass;
      _confirmPasswordCtrl.selection =
          TextSelection.collapsed(offset: newPass.length);
    }

    _previousPassword = newPass;
    if (mounted) setState(() {});
  }

  void _onConfirmPasswordChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _passwordCtrl.removeListener(_onPasswordChanged);
    _confirmPasswordCtrl.removeListener(_onConfirmPasswordChanged);
    _tokenCtrl.dispose();
    _passwordCtrl.dispose();
    _confirmPasswordCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy) return;
    setState(() => _errorMessage = null);

    if (!_formKey.currentState!.validate()) {
      return;
    }

    final token = _tokenCtrl.text.trim();
    final password = _passwordCtrl.text;
    final confirm = _confirmPasswordCtrl.text;

    if (password != confirm) {
      setState(() => _errorMessage = 'Xác nhận mật khẩu mới không khớp.');
      return;
    }

    setState(() => _busy = true);
    try {
      final auth = context.read<AuthService>();
      final ok = await auth.acceptInvite(
        inviteToken: token,
        newPassword: password,
      );

      if (!mounted) return;

      if (!ok) {
        setState(() {
          _errorMessage = auth.lastError ??
              'Kích hoạt tài khoản thất bại. Vui lòng kiểm tra mã mời.';
        });
      } else {
        TextInput.finishAutofillContext();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: const Color(0xFF059669),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
            content: const Row(
              children: [
                Icon(Icons.check_circle_outline, color: Colors.white, size: 20),
                SizedBox(width: 8),
                Expanded(
                  child: Text('Kích hoạt tài khoản thành công! Chào mừng bạn.'),
                ),
              ],
            ),
          ),
        );
        widget.onSuccess?.call();
        if (mounted && Navigator.of(context).canPop()) {
          Navigator.of(context).pop();
        }
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      backgroundColor:
          isDark ? const Color(0xFF0F172A) : const Color(0xFFF8FAFC),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Card(
                elevation: isDark ? 0 : 2,
                shadowColor: Colors.black.withValues(alpha: 0.08),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                  side: BorderSide(
                    color: isDark
                        ? const Color(0xFF334155)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
                color: isDark ? const Color(0xFF1E293B) : Colors.white,
                child: Padding(
                  padding: const EdgeInsets.all(32),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // Logo & Brand Header
                        Center(
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const StoreLogo(size: 40),
                              const SizedBox(width: 12),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    'NEXUP ONE',
                                    style: TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w800,
                                      letterSpacing: 0.8,
                                      color: isDark
                                          ? Colors.white
                                          : const Color(0xFF1E1736),
                                    ),
                                  ),
                                  Text(
                                    'ERP Quản Trị Doanh Nghiệp',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: isDark
                                          ? const Color(0xFF94A3B8)
                                          : const Color(0xFF64748B),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 24),

                        Text(
                          'Kích Hoạt Tài Khoản',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                            color: isDark
                                ? Colors.white
                                : const Color(0xFF0F172A),
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Nhận lời mời từ Quản trị viên. Thiết lập mật khẩu mới để bắt đầu làm việc.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 13,
                            color: isDark
                                ? const Color(0xFF94A3B8)
                                : const Color(0xFF64748B),
                            height: 1.4,
                          ),
                        ),
                        const SizedBox(height: 24),

                        // Error Banner
                        if (_errorMessage != null) ...[
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 14,
                              vertical: 10,
                            ),
                            decoration: BoxDecoration(
                              color: const Color(0xFFFEF2F2),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(
                                color: const Color(0xFFFCA5A5),
                              ),
                            ),
                            child: Row(
                              children: [
                                const Icon(
                                  Icons.error_outline_rounded,
                                  color: Color(0xFFDC2626),
                                  size: 20,
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    _errorMessage!,
                                    style: const TextStyle(
                                      color: Color(0xFFB91C1C),
                                      fontSize: 13,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 16),
                        ],

                        // Input Token
                        Text(
                          'Mã mời kích hoạt',
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: isDark
                                ? const Color(0xFFCBD5E1)
                                : const Color(0xFF334155),
                          ),
                        ),
                        const SizedBox(height: 6),
                        TextFormField(
                          controller: _tokenCtrl,
                          decoration: InputDecoration(
                            hintText: 'Dán mã mời kích hoạt...',
                            prefixIcon: const Icon(
                              Icons.vpn_key_rounded,
                              size: 20,
                              color: Color(0xFF0284C7),
                            ),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 14,
                              vertical: 12,
                            ),
                          ),
                          validator: (v) {
                            if (v == null || v.trim().isEmpty) {
                              return 'Vui lòng nhập hoặc dán mã mời kích hoạt';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 16),

                        // Khối mật khẩu được cô lập trong AutofillGroup riêng
                        // để trình duyệt / extension nhận diện đúng cặp trường new-password
                        AutofillGroup(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              // Input New Password
                              Text(
                                'Mật khẩu mới',
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: isDark
                                      ? const Color(0xFFCBD5E1)
                                      : const Color(0xFF334155),
                                ),
                              ),
                              const SizedBox(height: 6),
                              TextFormField(
                                controller: _passwordCtrl,
                                obscureText: _obscurePassword,
                                autofillHints: const [AutofillHints.newPassword],
                                decoration: InputDecoration(
                                  hintText: 'Tối thiểu 6 ký tự',
                                  prefixIcon: const Icon(Icons.lock_outline, size: 20),
                                  suffixIcon: IconButton(
                                    icon: Icon(
                                      _obscurePassword
                                          ? Icons.visibility_outlined
                                          : Icons.visibility_off_outlined,
                                      size: 20,
                                    ),
                                    onPressed: () => setState(
                                        () => _obscurePassword = !_obscurePassword),
                                  ),
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  contentPadding: const EdgeInsets.symmetric(
                                    horizontal: 14,
                                    vertical: 12,
                                  ),
                                ),
                                validator: (v) {
                                  if (v == null || v.length < 6) {
                                    return 'Mật khẩu phải có tối thiểu 6 ký tự';
                                  }
                                  return null;
                                },
                              ),
                              const SizedBox(height: 16),

                              // Input Confirm Password
                              Text(
                                'Xác nhận mật khẩu mới',
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: isDark
                                      ? const Color(0xFFCBD5E1)
                                      : const Color(0xFF334155),
                                ),
                              ),
                              const SizedBox(height: 6),
                              TextFormField(
                                controller: _confirmPasswordCtrl,
                                obscureText: _obscureConfirm,
                                autofillHints: const [AutofillHints.newPassword],
                                decoration: InputDecoration(
                                  hintText: 'Nhập lại mật khẩu mới',
                                  prefixIcon: const Icon(Icons.lock_outline, size: 20),
                                  suffixIcon: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      if (_passwordCtrl.text.isNotEmpty &&
                                          _confirmPasswordCtrl.text != _passwordCtrl.text)
                                        IconButton(
                                          tooltip: 'Sao chép từ mật khẩu trên',
                                          icon: const Icon(
                                            Icons.sync_rounded,
                                            size: 20,
                                            color: Color(0xFF0284C7),
                                          ),
                                          onPressed: () {
                                            _confirmPasswordCtrl.text = _passwordCtrl.text;
                                            _confirmPasswordCtrl.selection =
                                                TextSelection.collapsed(
                                              offset: _passwordCtrl.text.length,
                                            );
                                          },
                                        ),
                                      IconButton(
                                        icon: Icon(
                                          _obscureConfirm
                                              ? Icons.visibility_outlined
                                              : Icons.visibility_off_outlined,
                                          size: 20,
                                        ),
                                        onPressed: () => setState(
                                            () => _obscureConfirm = !_obscureConfirm),
                                      ),
                                    ],
                                  ),
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  contentPadding: const EdgeInsets.symmetric(
                                    horizontal: 14,
                                    vertical: 12,
                                  ),
                                ),
                                validator: (v) {
                                  if (v != _passwordCtrl.text) {
                                    return 'Mật khẩu xác nhận không trùng khớp';
                                  }
                                  return null;
                                },
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 24),

                        // Submit Button
                        FilledButton(
                          onPressed: _busy ? null : _submit,
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF6B4BC3),
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 14),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                          ),
                          child: _busy
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Colors.white,
                                  ),
                                )
                              : const Text(
                                  'Kích Hoạt & Đăng Nhập Ngay',
                                  style: TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                        ),
                        const SizedBox(height: 12),

                        // Back to login button
                        TextButton(
                          onPressed: _busy
                              ? null
                              : () {
                                  if (widget.onBackToLogin != null) {
                                    widget.onBackToLogin!();
                                  } else {
                                    Navigator.maybePop(context);
                                  }
                                },
                          child: Text(
                            '← Quay lại Đăng nhập',
                            style: TextStyle(
                              color: isDark
                                  ? const Color(0xFF94A3B8)
                                  : const Color(0xFF64748B),
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
