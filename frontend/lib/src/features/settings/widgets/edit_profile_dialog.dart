import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../app/app_shell.dart';
import '../../../core/widgets/user_avatar.dart';
import '../../../data/models/dtos.dart';
import '../../../data/repositories/bankops_repository.dart';
import '../../../data/repositories/http_bankops_repository.dart';
import '../../auth/auth_service.dart';
import 'avatar_editor_sheet.dart';

/// Hộp thoại Chỉnh sửa hồ sơ cá nhân (Họ tên, Email, Số điện thoại, Chi nhánh).
class EditProfileDialog extends StatefulWidget {
  const EditProfileDialog({super.key, this.currentUser});

  final AppUser? currentUser;

  static Future<bool?> show(BuildContext context, {AppUser? user}) {
    return showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => EditProfileDialog(currentUser: user),
    );
  }

  @override
  State<EditProfileDialog> createState() => _EditProfileDialogState();
}

class _EditProfileDialogState extends State<EditProfileDialog> {
  late final TextEditingController _nameCtrl;
  late final TextEditingController _emailCtrl;
  late final TextEditingController _phoneCtrl;
  late final TextEditingController _branchCtrl;

  bool _busy = false;
  bool _initialized = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _nameCtrl = TextEditingController();
    _emailCtrl = TextEditingController();
    _phoneCtrl = TextEditingController();
    _branchCtrl = TextEditingController();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_initialized) {
      _initialized = true;
      final u = _resolveUser();
      _nameCtrl.text = u?.displayName.trim() ?? '';
      final realEmail = u?.email?.trim();
      if (realEmail != null && realEmail.isNotEmpty) {
        _emailCtrl.text = realEmail;
      } else {
        final effEmail = u?.effectiveEmail.trim() ?? '';
        _emailCtrl.text = effEmail.endsWith('@khotrasua.local') ? '' : effEmail;
      }
      final realPhone = u?.phoneNumber?.trim();
      _phoneCtrl.text =
          (realPhone != null && realPhone != '0901 234 567') ? realPhone : '';
      final realBranch = u?.branch?.trim();
      _branchCtrl.text =
          (realBranch != null && !realBranch.contains('Hội sở')) ? realBranch : '';
    }
  }

  AppUser? _resolveUser() {
    if (widget.currentUser != null) return widget.currentUser;
    try {
      final auth = Provider.of<AuthService?>(context, listen: false);
      if (auth?.user != null) return auth!.user;
    } catch (_) {}
    try {
      final session = SessionScope.maybeOf(context);
      if (session?.user != null) return session!.user;
    } catch (_) {}
    return null;
  }

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _phoneCtrl.dispose();
    _branchCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final name = _nameCtrl.text.trim();
    final email = _emailCtrl.text.trim();
    final phone = _phoneCtrl.text.trim();
    final branch = _branchCtrl.text.trim();

    if (name.isEmpty) {
      setState(() => _errorMessage = 'Vui lòng nhập họ và tên.');
      return;
    }

    if (email.isNotEmpty &&
        !RegExp(r'^[\w\.\-]+@[\w\.\-]+\.\w+$').hasMatch(email)) {
      setState(() => _errorMessage = 'Địa chỉ email không đúng định dạng.');
      return;
    }

    final cleanPhone = phone.replaceAll(RegExp(r'[\s\-\.]'), '');
    if (cleanPhone.isNotEmpty &&
        (!RegExp(r'^\+?\d{9,12}$').hasMatch(cleanPhone))) {
      setState(
          () => _errorMessage = 'Số điện thoại không hợp lệ (9–11 chữ số).');
      return;
    }

    setState(() {
      _busy = true;
      _errorMessage = null;
    });

    final auth = Provider.of<AuthService?>(context, listen: false);
    BankOpsRepository? repo;
    try {
      repo = RepositoryScope.of(context);
    } catch (_) {}

    try {
      if (auth != null) {
        final ok = await auth.updateProfile(
          displayName: name,
          email: email.isEmpty ? null : email,
          phoneNumber: phone.isEmpty ? null : phone,
          branch: branch.isEmpty ? null : branch,
        );
        if (!ok && auth.lastError != null) {
          throw Exception(auth.lastError);
        }
      }

      if (repo != null && repo is! HttpBankOpsRepository) {
        try {
          await repo.updateProfile(
            displayName: name,
            email: email.isEmpty ? null : email,
            phoneNumber: phone.isEmpty ? null : phone,
            branch: branch.isEmpty ? null : branch,
          );
        } catch (_) {}
      }

      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        if (e is ApiException) {
          _errorMessage = e.message;
        } else {
          _errorMessage = e.toString().replaceAll('Exception: ', '');
        }
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final width = MediaQuery.sizeOf(context).width;
    final isCompact = width < 600;

    return AlertDialog(
      insetPadding: EdgeInsets.symmetric(
        horizontal: isCompact ? 12 : 40,
        vertical: 24,
      ),
      titlePadding: EdgeInsets.fromLTRB(isCompact ? 16 : 24, 20, isCompact ? 16 : 24, 8),
      contentPadding: EdgeInsets.symmetric(horizontal: isCompact ? 16 : 24, vertical: 12),
      actionsPadding: EdgeInsets.fromLTRB(isCompact ? 16 : 24, 12, isCompact ? 16 : 24, 20),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: const Color(0xFF0284C7).withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(
              Icons.manage_accounts_outlined,
              color: Color(0xFF0284C7),
              size: 24,
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Chỉnh sửa hồ sơ cá nhân',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                SizedBox(height: 2),
                Text(
                  'Cập nhật họ tên hiển thị và thông tin liên hệ công vụ',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w400,
                    color: Color(0xFF64748B),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: SizedBox(
          width: isCompact ? double.maxFinite : 480,
          child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_errorMessage != null) ...[
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFEF2F2),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: const Color(0xFFFCA5A5)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline,
                          color: Color(0xFFDC2626), size: 20),
                      const SizedBox(width: 8),
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
              Center(
                child: Wrap(
                  spacing: 14,
                  runSpacing: 10,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  alignment: WrapAlignment.center,
                  children: [
                    UserAvatar(
                      name: (_resolveUser()?.displayName.isNotEmpty == true)
                          ? _resolveUser()!.displayName
                          : (widget.currentUser?.displayName.isNotEmpty == true
                              ? widget.currentUser!.displayName
                              : 'Người dùng'),
                      email: _resolveUser()?.email ?? widget.currentUser?.email,
                      avatarUrl: _resolveUser()?.avatarUrl ??
                          widget.currentUser?.avatarUrl,
                      size: 56,
                      showEditBadge: true,
                      onTap: () async {
                        final updated = await AvatarEditorSheet.show(
                          context,
                          user: _resolveUser(),
                        );
                        if (updated == true && context.mounted) {
                          setState(() {});
                        }
                      },
                    ),
                    OutlinedButton.icon(
                      icon: const Icon(Icons.camera_alt_outlined, size: 16),
                      label: const Text('Đổi ảnh đại diện',
                          style: TextStyle(fontSize: 12)),
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 8),
                      ),
                      onPressed: () async {
                        final updated = await AvatarEditorSheet.show(
                          context,
                          user: _resolveUser(),
                        );
                        if (updated == true && context.mounted) {
                          setState(() {});
                        }
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Họ và tên hiển thị *',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color:
                      isDark ? Colors.grey.shade300 : const Color(0xFF334155),
                ),
              ),
              const SizedBox(height: 6),
              TextField(
                key: const Key('edit-profile-name-field'),
                controller: _nameCtrl,
                textCapitalization: TextCapitalization.words,
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.person_outline, size: 20),
                  hintText: 'Nhập họ và tên đầy đủ',
                  filled: true,
                  fillColor: isDark
                      ? const Color(0xFF1E293B)
                      : const Color(0xFFF8FAFC),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: BorderSide(
                      color: isDark
                          ? const Color(0xFF334155)
                          : const Color(0xFFCBD5E1),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Email liên hệ công vụ',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color:
                      isDark ? Colors.grey.shade300 : const Color(0xFF334155),
                ),
              ),
              const SizedBox(height: 6),
              TextField(
                key: const Key('edit-profile-email-field'),
                controller: _emailCtrl,
                keyboardType: TextInputType.emailAddress,
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.email_outlined, size: 20),
                  hintText: 'email@domain.com',
                  filled: true,
                  fillColor: isDark
                      ? const Color(0xFF1E293B)
                      : const Color(0xFFF8FAFC),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: BorderSide(
                      color: isDark
                          ? const Color(0xFF334155)
                          : const Color(0xFFCBD5E1),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Số điện thoại liên hệ',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color:
                      isDark ? Colors.grey.shade300 : const Color(0xFF334155),
                ),
              ),
              const SizedBox(height: 6),
              TextField(
                key: const Key('edit-profile-phone-field'),
                controller: _phoneCtrl,
                keyboardType: TextInputType.phone,
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.phone_outlined, size: 20),
                  hintText: 'Nhập số điện thoại liên hệ',
                  filled: true,
                  fillColor: isDark
                      ? const Color(0xFF1E293B)
                      : const Color(0xFFF8FAFC),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: BorderSide(
                      color: isDark
                          ? const Color(0xFF334155)
                          : const Color(0xFFCBD5E1),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Đơn vị / Chi nhánh công tác',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color:
                      isDark ? Colors.grey.shade300 : const Color(0xFF334155),
                ),
              ),
              const SizedBox(height: 6),
              TextField(
                key: const Key('edit-profile-branch-field'),
                controller: _branchCtrl,
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.business_outlined, size: 20),
                  hintText: 'Nhập chi nhánh hoặc bộ phận công tác',
                  filled: true,
                  fillColor: isDark
                      ? const Color(0xFF1E293B)
                      : const Color(0xFFF8FAFC),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: BorderSide(
                      color: isDark
                          ? const Color(0xFF334155)
                          : const Color(0xFFCBD5E1),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
    actions: [
        OutlinedButton(
          key: const Key('edit-profile-cancel-btn'),
          onPressed: _busy ? null : () => Navigator.of(context).pop(false),
          style: OutlinedButton.styleFrom(
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
          child: const Text('Hủy bỏ'),
        ),
        FilledButton.icon(
          key: const Key('edit-profile-save-btn'),
          onPressed: _busy ? null : _submit,
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF0284C7),
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
          icon: _busy
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                )
              : const Icon(Icons.check, size: 18),
          label: const Text('Lưu thay đổi'),
        ),
      ],
    );
  }
}
