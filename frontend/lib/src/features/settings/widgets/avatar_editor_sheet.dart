import 'dart:convert';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../app/app_shell.dart';
import '../../../core/widgets/app_toast.dart';
import '../../../core/widgets/user_avatar.dart';
import '../../../data/models/dtos.dart';
import '../../../data/repositories/bankops_repository.dart';
import '../../../data/repositories/http_bankops_repository.dart';
import '../../auth/auth_service.dart';

/// Bộ avatar nhận diện chuyên nghiệp chuẩn quầy giao dịch và quản lý kho.
const List<({String label, String url})> kPresetAvatars = [
  (
    label: 'Giao dịch viên 1',
    url:
        'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=256&q=80',
  ),
  (
    label: 'Giao dịch viên 2',
    url:
        'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=256&q=80',
  ),
  (
    label: 'Quản lý cửa hàng',
    url:
        'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=256&q=80',
  ),
  (
    label: 'Trưởng ca pha chế',
    url:
        'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=256&q=80',
  ),
  (
    label: 'Kiểm soát viên',
    url:
        'https://images.unsplash.com/photo-1580489944761-15a19d654956?auto=format&fit=crop&w=256&q=80',
  ),
  (
    label: 'Quản trị hệ thống',
    url:
        'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=256&q=80',
  ),
];

/// Bảng điều khiển cập nhật và quản lý ảnh đại diện người dùng.
class AvatarEditorSheet extends StatefulWidget {
  const AvatarEditorSheet({super.key, this.currentUser});

  final AppUser? currentUser;

  static Future<bool?> show(BuildContext context, {AppUser? user}) {
    return showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => AvatarEditorSheet(currentUser: user),
    );
  }

  @override
  State<AvatarEditorSheet> createState() => _AvatarEditorSheetState();
}

class _AvatarEditorSheetState extends State<AvatarEditorSheet> {
  late String? _currentAvatarUrl;
  late final TextEditingController _urlCtrl;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _currentAvatarUrl = widget.currentUser?.avatarUrl;
    _urlCtrl = TextEditingController(
      text: (_currentAvatarUrl?.startsWith('http') ?? false)
          ? _currentAvatarUrl
          : '',
    );
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickFromDevice() async {
    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.image,
        withData: true,
      );

      if (result == null || result.files.isEmpty) {
        setState(() => _busy = false);
        return;
      }

      final file = result.files.single;
      final bytes = file.bytes;
      if (bytes == null || bytes.isEmpty) {
        throw Exception('Không thể đọc dữ liệu ảnh đã chọn.');
      }

      if (bytes.length > 2 * 1024 * 1024) {
        throw Exception(
            'Ảnh vượt quá dung lượng tối đa 2MB. Vui lòng chọn ảnh nhỏ hơn.');
      }

      final ext = file.extension?.toLowerCase() ?? 'png';
      final mime = (ext == 'jpg' || ext == 'jpeg')
          ? 'image/jpeg'
          : (ext == 'webp')
              ? 'image/webp'
              : 'image/png';

      final base64String = base64Encode(bytes);
      final dataUrl = 'data:$mime;base64,$base64String';

      setState(() {
        _currentAvatarUrl = dataUrl;
        _urlCtrl.text = '';
      });

      await _applyAndSave(dataUrl, 'Đã tải ảnh lên từ điện thoại thành công!');
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString().replaceAll('Exception: ', '');
          _busy = false;
        });
      }
    }
  }

  Future<void> _setDefaultFromEmail() async {
    final email = widget.currentUser?.effectiveEmail;
    if (email == null || email.trim().isEmpty || !email.contains('@')) {
      setState(() => _error = 'Tài khoản chưa có email hợp lệ.');
      return;
    }

    final gravatar = UserAvatar.gravatarUrl(email);
    setState(() {
      _currentAvatarUrl = gravatar;
      _urlCtrl.text = gravatar;
    });

    await _applyAndSave(
        gravatar, 'Đã đồng bộ ảnh đại diện mặc định theo email!');
  }

  Future<void> _selectPreset(String url) async {
    setState(() {
      _currentAvatarUrl = url;
      _urlCtrl.text = url;
    });

    await _applyAndSave(url, 'Đã chọn ảnh đại diện nhận diện quầy!');
  }

  Future<void> _clearAvatar() async {
    setState(() {
      _currentAvatarUrl = '';
      _urlCtrl.text = '';
    });

    await _applyAndSave(
        '', 'Đã xóa ảnh đại diện, chuyển về chữ cái viết tắt!');
  }

  Future<void> _applyUrl() async {
    final url = _urlCtrl.text.trim();
    if (url.isEmpty) {
      await _clearAvatar();
      return;
    }
    if (!url.startsWith('http://') &&
        !url.startsWith('https://') &&
        !url.startsWith('data:image')) {
      setState(() => _error = 'Đường dẫn ảnh phải bắt đầu bằng http:// hoặc https://');
      return;
    }

    setState(() => _currentAvatarUrl = url);
    await _applyAndSave(url, 'Cập nhật liên kết ảnh đại diện thành công!');
  }

  Future<void> _applyAndSave(String? newUrl, String successMessage) async {
    setState(() {
      _busy = true;
      _error = null;
    });

    final auth = Provider.of<AuthService?>(context, listen: false);
    BankOpsRepository? repo;
    try {
      repo = RepositoryScope.of(context);
    } catch (_) {}

    final u = widget.currentUser;
    final name = (u?.displayName.isNotEmpty == true) ? u!.displayName : 'Người dùng';

    try {
      final finalUrl = (newUrl != null && newUrl.trim().isNotEmpty) ? newUrl.trim() : null;

      if (auth != null) {
        final ok = await auth.updateProfile(
          displayName: name,
          email: u?.email,
          phoneNumber: u?.phoneNumber,
          branch: u?.branch,
          avatarUrl: finalUrl,
        );
        if (!ok && auth.lastError != null) {
          throw Exception(auth.lastError);
        }
      }

      if (repo != null && repo is! HttpBankOpsRepository) {
        try {
          await repo.updateProfile(
            displayName: name,
            email: u?.email,
            phoneNumber: u?.phoneNumber,
            branch: u?.branch,
            avatarUrl: finalUrl,
          );
        } catch (_) {}
      }

      if (!mounted) return;
      AppToast.success(context, successMessage);
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString().replaceAll('Exception: ', '');
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final user = widget.currentUser;

    return DraggableScrollableSheet(
      initialChildSize: 0.75,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      expand: false,
      builder: (ctx, scrollController) {
        return SingleChildScrollView(
          controller: scrollController,
          padding: EdgeInsets.fromLTRB(
            20,
            8,
            20,
            MediaQuery.of(context).viewInsets.bottom + 24,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(Icons.account_circle_outlined,
                      color: theme.colorScheme.primary),
                ),
                title: const Text(
                  'Ảnh đại diện cá nhân',
                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 17),
                ),
                subtitle: const Text(
                  'Chọn từ máy, đồng bộ Email hoặc chọn mẫu có sẵn',
                  style: TextStyle(fontSize: 12),
                ),
                trailing: IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.of(context).pop(false),
                ),
              ),
              const Divider(height: 16),
              if (_error != null)
                Container(
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: Colors.red.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.red.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline,
                          size: 16, color: Colors.red),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _error!,
                          style: const TextStyle(
                              color: Colors.red,
                              fontSize: 12,
                              fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ),
                ),
              Center(
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    UserAvatar(
                      name: (user?.displayName.isNotEmpty == true)
                          ? user!.displayName
                          : 'Người dùng',
                      email: user?.email,
                      avatarUrl: _currentAvatarUrl,
                      size: 88,
                    ),
                    if (_busy)
                      Container(
                        width: 88,
                        height: 88,
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.45),
                          shape: BoxShape.circle,
                        ),
                        child: const Center(
                          child: CircularProgressIndicator(
                            strokeWidth: 3,
                            color: Colors.white,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      key: const Key('avatar-pick-device-btn'),
                      icon: const Icon(Icons.photo_library_rounded, size: 18),
                      label: const Text('Tải ảnh từ máy'),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                      ),
                      onPressed: _busy ? null : _pickFromDevice,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: OutlinedButton.icon(
                      key: const Key('avatar-sync-email-btn'),
                      icon: const Icon(Icons.mark_email_read_rounded, size: 18),
                      label: const Text('Lấy theo Email'),
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                      ),
                      onPressed: _busy ? null : _setDefaultFromEmail,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              const Text(
                'Hoặc chọn ảnh nhận diện quầy vận hành:',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
              ),
              const SizedBox(height: 10),
              SizedBox(
                height: 72,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: kPresetAvatars.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 12),
                  itemBuilder: (ctx, idx) {
                    final preset = kPresetAvatars[idx];
                    final isSelected = _currentAvatarUrl == preset.url;
                    return GestureDetector(
                      onTap: _busy ? null : () => _selectPreset(preset.url),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: isSelected
                                    ? theme.colorScheme.primary
                                    : Colors.transparent,
                                width: 2.5,
                              ),
                            ),
                            child: UserAvatar(
                              avatarUrl: preset.url,
                              size: 44,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            preset.label,
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: isSelected
                                  ? FontWeight.w700
                                  : FontWeight.w500,
                              color: isSelected
                                  ? theme.colorScheme.primary
                                  : theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'Nhập liên kết ảnh trực tiếp (URL):',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
              ),
              const SizedBox(height: 6),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      key: const Key('avatar-url-input'),
                      controller: _urlCtrl,
                      decoration: InputDecoration(
                        hintText: 'https://...',
                        prefixIcon: const Icon(Icons.link_rounded, size: 20),
                        isDense: true,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton.tonal(
                    key: const Key('avatar-url-apply-btn'),
                    onPressed: _busy ? null : _applyUrl,
                    child: const Text('Áp dụng'),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              if (_currentAvatarUrl != null && _currentAvatarUrl!.isNotEmpty)
                Center(
                  child: TextButton.icon(
                    key: const Key('avatar-clear-btn'),
                    icon: const Icon(Icons.delete_outline,
                        color: Colors.red, size: 16),
                    label: const Text(
                      'Xóa ảnh đại diện (sử dụng chữ cái viết tắt)',
                      style: TextStyle(color: Colors.red, fontSize: 12),
                    ),
                    onPressed: _busy ? null : _clearAvatar,
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}
