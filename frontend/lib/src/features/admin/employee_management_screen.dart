import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/app_shell.dart';
import '../../core/util/error_text.dart';
import '../../core/util/role_visibility.dart';
import '../../core/widgets/app_toast.dart';
import '../../core/widgets/state_views.dart';
import '../../core/widgets/user_avatar.dart';
import '../../data/models/dtos.dart';

/// Màn hình Quản trị Nhân viên & Cấp phát IAM (Phase 1).
/// Chỉ người dùng có capability `iam:admin` hoặc role `admin` mới được truy cập.
class EmployeeManagementScreen extends StatefulWidget {
  const EmployeeManagementScreen({super.key});

  @override
  State<EmployeeManagementScreen> createState() =>
      _EmployeeManagementScreenState();
}

class _EmployeeManagementScreenState extends State<EmployeeManagementScreen> {
  bool _loading = true;
  String? _errorMessage;
  List<EmployeeUserDto> _employees = [];
  List<BranchDto> _branches = [];
  List<RoleDto> _roles = [];

  // Bộ lọc
  final TextEditingController _searchCtrl = TextEditingController();
  String? _selectedBranchId;
  String? _selectedRole;
  String? _selectedStatus;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _loadData();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadData() async {
    final repo = RepositoryScope.maybeOf(context);
    if (repo == null) return;

    setState(() {
      _loading = true;
      _errorMessage = null;
    });

    try {
      final branchesFuture = repo.getBranches();
      final rolesFuture = repo.getRoles();
      final employeesFuture = repo.getEmployees(
        search:
            _searchCtrl.text.trim().isEmpty ? null : _searchCtrl.text.trim(),
        branchId: _selectedBranchId,
        role: _selectedRole,
        status: _selectedStatus,
      );

      final results = await Future.wait([
        branchesFuture,
        rolesFuture,
        employeesFuture,
      ]);

      if (mounted) {
        setState(() {
          _branches = results[0] as List<BranchDto>;
          _roles = results[1] as List<RoleDto>;
          _employees = results[2] as List<EmployeeUserDto>;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString();
          _loading = false;
        });
      }
    }
  }

  void _copyToClipboard(String label, String text) {
    Clipboard.setData(ClipboardData(text: text));
    AppToast.success(context, 'Đã sao chép $label vào bộ nhớ tạm');
  }

  // --- Actions ---

  Future<void> _openCreateEmployeeDialog() async {
    final repo = RepositoryScope.maybeOf(context);
    if (repo == null) return;

    final usernameCtrl = TextEditingController();
    final displayNameCtrl = TextEditingController();
    final emailCtrl = TextEditingController();
    final phoneCtrl = TextEditingController();
    String? branchId = _branches.isNotEmpty ? _branches.first.id : null;
    final selectedRoles = <String>{'staff'};
    String onboardingMethod = 'temporary_password';

    final confirmed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.person_add_alt_1_rounded, color: Color(0xFF2563EB)),
              SizedBox(width: 8),
              Text('Tạo tài khoản nhân viên mới'),
            ],
          ),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Thông tin cơ bản',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    key: const Key('admin-create-username-input'),
                    controller: usernameCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Tên đăng nhập (Username) *',
                      hintText: 'VD: nguyen.van.a',
                      prefixIcon: Icon(Icons.account_circle_outlined),
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    key: const Key('admin-create-display-name-input'),
                    controller: displayNameCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Họ và tên hiển thị *',
                      hintText: 'VD: Nguyễn Văn A',
                      prefixIcon: Icon(Icons.badge_outlined),
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          key: const Key('admin-create-email-input'),
                          controller: emailCtrl,
                          decoration: const InputDecoration(
                            labelText: 'Email công vụ',
                            hintText: 'a.nguyen@khotrasua.local',
                            prefixIcon: Icon(Icons.email_outlined),
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: TextField(
                          key: const Key('admin-create-phone-input'),
                          controller: phoneCtrl,
                          decoration: const InputDecoration(
                            labelText: 'Số điện thoại',
                            hintText: '0901234567',
                            prefixIcon: Icon(Icons.phone_outlined),
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'Cửa hàng & vai trò nhân viên',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                  ),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    key: const Key('admin-create-branch-dropdown'),
                    isExpanded: true,
                    initialValue: branchId,
                    decoration: const InputDecoration(
                      labelText: 'Cửa hàng làm việc',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.account_balance_outlined),
                    ),
                    items: _branches
                        .map((b) => DropdownMenuItem(
                              value: b.id,
                              child: Text('${b.code} - ${b.name}',
                                  overflow: TextOverflow.ellipsis),
                            ))
                        .toList(),
                    onChanged: (v) => setDialogState(() => branchId = v),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 4,
                    children: _roles.map((r) {
                      final isSelected = selectedRoles.contains(r.code);
                      return FilterChip(
                        label: Text(r.name),
                        selected: isSelected,
                        onSelected: (selected) {
                          setDialogState(() {
                            if (selected) {
                              selectedRoles.add(r.code);
                            } else {
                              if (selectedRoles.length > 1) {
                                selectedRoles.remove(r.code);
                              }
                            }
                          });
                        },
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'Phương thức bàn giao tài khoản (Onboarding)',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                  ),
                  const SizedBox(height: 8),
                  RadioGroup<String>(
                    groupValue: onboardingMethod,
                    onChanged: (v) =>
                        setDialogState(() => onboardingMethod = v!),
                    child: const Column(
                      children: [
                        RadioListTile<String>(
                          title: Text('Mật khẩu tạm thời một lần'),
                          subtitle: Text(
                            'Hệ thống sinh mật khẩu ngẫu nhiên an toàn. Bắt buộc đổi ở lần đăng nhập đầu tiên.',
                          ),
                          value: 'temporary_password',
                        ),
                        RadioListTile<String>(
                          title: Text('Gửi email mời kích hoạt'),
                          subtitle: Text(
                            'Sinh mã mời kích hoạt có hạn 7 ngày. Nhân viên tự thiết lập mật khẩu.',
                          ),
                          value: 'invite_email',
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Hủy'),
            ),
            FilledButton.icon(
              key: const Key('admin-create-employee-confirm-btn'),
              icon: const Icon(Icons.check),
              label: const Text('Tạo nhân viên'),
              onPressed: () {
                if (usernameCtrl.text.trim().isEmpty ||
                    displayNameCtrl.text.trim().isEmpty) {
                  AppToast.error(ctx, 'Vui lòng điền đủ Username và Họ tên');
                  return;
                }
                if (onboardingMethod == 'invite_email') {
                  final email = emailCtrl.text.trim();
                  if (email.isEmpty ||
                      !email.contains('@') ||
                      !email.contains('.')) {
                    AppToast.error(ctx,
                        'Phương thức mời yêu cầu email thật hợp lệ (vd: nhanvien@congty.com)');
                    return;
                  }
                }
                Navigator.pop(ctx, true);
              },
            ),
          ],
        ),
      ),
    );

    if (confirmed == true && mounted) {
      try {
        final result = await repo.createEmployee(
          username: usernameCtrl.text.trim(),
          displayName: displayNameCtrl.text.trim(),
          email: emailCtrl.text.trim().isEmpty ? null : emailCtrl.text.trim(),
          phoneNumber:
              phoneCtrl.text.trim().isEmpty ? null : phoneCtrl.text.trim(),
          branchId: branchId,
          roles: selectedRoles.toList(),
          onboardingMethod: onboardingMethod,
        );

        if (!mounted) return;

        // Hiển thị kết quả onboarding cho admin bàn giao
        if (onboardingMethod == 'temporary_password') {
          await showDialog(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Row(
                children: [
                  Icon(Icons.key_rounded, color: Color(0xFF059669)),
                  SizedBox(width: 8),
                  Text('Tạo nhân viên thành công'),
                ],
              ),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Đã khởi tạo tài khoản "${result.username}" (${result.displayName}).',
                  ),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF1F5F9),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: const Color(0xFFCBD5E1)),
                    ),
                    child: const Row(
                      children: [
                        Icon(Icons.info_outline, color: Color(0xFF2563EB)),
                        SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'Tài khoản đã sẵn sàng với mật khẩu tạm một lần. Nhân viên bắt buộc phải đổi mật khẩu khi đăng nhập lần đầu.',
                            style: TextStyle(fontSize: 13),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              actions: [
                FilledButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text('Hoàn tất'),
                ),
              ],
            ),
          );
        } else {
          final emailSent = result.lastInviteEmailSent ?? false;
          final inviteLink = result.lastInviteLink ??
              (result.lastInviteToken != null
                  ? '/accept-invite?token=${result.lastInviteToken}'
                  : null);

          await showDialog(
            context: context,
            builder: (ctx) => AlertDialog(
              title: Row(
                children: [
                  Icon(
                    emailSent
                        ? Icons.mark_email_read_rounded
                        : Icons.mail_outline_rounded,
                    color: emailSent
                        ? const Color(0xFF059669)
                        : const Color(0xFFD97706),
                  ),
                  const SizedBox(width: 8),
                  Text(emailSent
                      ? 'Đã gửi thư mời kích hoạt'
                      : 'Đã tạo lời mời kích hoạt'),
                ],
              ),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Đã khởi tạo tài khoản "${result.username}" (${result.displayName}).',
                  ),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: emailSent
                          ? const Color(0xFFF0FDF4)
                          : const Color(0xFFFFFBEB),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: emailSent
                            ? const Color(0xFFBBF7D0)
                            : const Color(0xFFFDE68A),
                      ),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          emailSent
                              ? Icons.check_circle_outline
                              : Icons.info_outline,
                          color: emailSent
                              ? const Color(0xFF16A34A)
                              : const Color(0xFFD97706),
                          size: 20,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            emailSent
                                ? 'Thư mời kích hoạt tài khoản đã được gửi trực tiếp tới email "${result.email}". Vui lòng nhắc nhân sự kiểm tra hộp thư đến (hoặc hòm thư Spam/Quảng cáo).'
                                : 'Hệ thống chưa gửi được email trực tiếp tới "${result.email}" (${result.lastEmailDeliveryMessage ?? "SMTP chưa bật"}). Bạn có thể sao chép liên kết kích hoạt dưới đây để gửi cho nhân sự.',
                            style: TextStyle(
                              fontSize: 13,
                              color: emailSent
                                  ? const Color(0xFF166534)
                                  : const Color(0xFF92400E),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (inviteLink != null) ...[
                    const SizedBox(height: 12),
                    const Text(
                      'Liên kết kích hoạt (Hiệu lực 7 ngày):',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF475569),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF1F5F9),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFFCBD5E1)),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: SelectableText(
                              inviteLink,
                              style: const TextStyle(
                                fontFamily: 'monospace',
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          IconButton(
                            key: const Key('admin-copy-invite-link-btn'),
                            icon: const Icon(Icons.copy_rounded,
                                color: Color(0xFF2563EB), size: 18),
                            tooltip: 'Sao chép liên kết',
                            onPressed: () => _copyToClipboard(
                                'liên kết kích hoạt', inviteLink),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
              actions: [
                FilledButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text('Hoàn tất'),
                ),
              ],
            ),
          );
        }

        _loadData();
      } catch (e) {
        if (mounted) {
          AppToast.error(context, 'Lỗi tạo nhân viên: ${friendlyError(e)}');
        }
      }
    }
  }

  Future<void> _toggleLockUser(
      EmployeeUserDto user, AppUser? currentUser) async {
    final repo = RepositoryScope.maybeOf(context);
    if (repo == null) return;

    if (currentUser != null &&
        (currentUser.id == user.id || currentUser.username == user.username)) {
      AppToast.error(context,
          'Chính sách an toàn: Bạn không thể tự khóa tài khoản của chính mình!');
      return;
    }

    final willLock = user.isActive;
    final reasonCtrl = TextEditingController();

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Row(
          children: [
            Icon(
              willLock ? Icons.lock_outline : Icons.lock_open_outlined,
              color:
                  willLock ? const Color(0xFFDC2626) : const Color(0xFF059669),
            ),
            const SizedBox(width: 8),
            Text(willLock ? 'Khóa tài khoản nhân viên' : 'Mở khóa tài khoản'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              willLock
                  ? 'Bạn có chắc chắn muốn KHÓA tài khoản "${user.displayName}" (@${user.username})? Toàn bộ phiên làm việc của nhân viên này sẽ bị thu hồi ngay lập tức.'
                  : 'Mở khóa và cho phép nhân viên "${user.displayName}" (@${user.username}) tiếp tục làm việc?',
            ),
            const SizedBox(height: 16),
            TextField(
              controller: reasonCtrl,
              decoration: const InputDecoration(
                labelText: 'Lý do thay đổi trạng thái *',
                hintText: 'VD: Thay đổi vị trí công tác / Kiểm tra tuân thủ',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor:
                  willLock ? const Color(0xFFDC2626) : const Color(0xFF059669),
            ),
            onPressed: () {
              if (reasonCtrl.text.trim().isEmpty) {
                AppToast.error(ctx, 'Vui lòng nhập lý do thay đổi');
                return;
              }
              Navigator.pop(ctx, true);
            },
            child: Text(willLock ? 'Khóa tài khoản' : 'Mở khóa'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      try {
        await repo.updateEmployeeStatus(
          user.id,
          willLock ? 'locked' : 'active',
          reason: reasonCtrl.text.trim(),
        );
        if (mounted) {
          AppToast.success(
            context,
            willLock ? 'Đã khóa tài khoản thành công' : 'Đã mở khóa tài khoản',
          );
          _loadData();
        }
      } catch (e) {
        if (mounted) {
          AppToast.error(
              context, 'Lỗi cập nhật trạng thái: ${friendlyError(e)}');
        }
      }
    }
  }

  Future<void> _openRolesAndScopesDialog(
      EmployeeUserDto user, AppUser? currentUser) async {
    final repo = RepositoryScope.maybeOf(context);
    if (repo == null) return;

    final selectedRoles = user.roles.toSet();
    String? selectedBranchId = user.branchId;
    final isSelf = currentUser != null && currentUser.id == user.id;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: Row(
            children: [
              const Icon(Icons.shield_outlined, color: Color(0xFF2563EB)),
              const SizedBox(width: 8),
              Text('Phân vai trò & Phạm vi: ${user.username}'),
            ],
          ),
          content: SizedBox(
            width: 480,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Chi nhánh quản lý',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                  ),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    isExpanded: true,
                    initialValue: selectedBranchId,
                    decoration:
                        const InputDecoration(border: OutlineInputBorder()),
                    items: [
                      const DropdownMenuItem(
                          value: null,
                          child: Text('Không chỉ định / Toàn hệ thống',
                              overflow: TextOverflow.ellipsis)),
                      ..._branches.map((b) => DropdownMenuItem(
                            value: b.id,
                            child: Text('${b.code} - ${b.name}',
                                overflow: TextOverflow.ellipsis),
                          )),
                    ],
                    onChanged: isSelf
                        ? null
                        : (v) => setDialogState(() => selectedBranchId = v),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'Vai trò hệ thống',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                  ),
                  const SizedBox(height: 8),
                  ..._roles.map((r) {
                    final isChecked = selectedRoles.contains(r.code);
                    return CheckboxListTile(
                      title: Text(r.name),
                      subtitle: Text(r.description ?? r.code,
                          style: const TextStyle(fontSize: 12)),
                      value: isChecked,
                      onChanged: (val) {
                        setDialogState(() {
                          if (val == true) {
                            selectedRoles.add(r.code);
                          } else {
                            if (selectedRoles.length > 1) {
                              selectedRoles.remove(r.code);
                            }
                          }
                        });
                      },
                    );
                  }),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Hủy'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Lưu phân quyền'),
            ),
          ],
        ),
      ),
    );

    if (confirmed == true && mounted) {
      try {
        await repo.updateEmployeeRoles(user.id, selectedRoles.toList());
        // A self role update revokes the current token immediately. Never send
        // a second request with that token or report a partial success as an error.
        if (!isSelf &&
            selectedBranchId != null &&
            selectedBranchId != user.branchId) {
          await repo.updateEmployeeScopes(user.id, [
            {
              'branch_id': selectedBranchId,
              'capability': 'inventory:view',
            }
          ]);
        }
        if (mounted) {
          if (isSelf) {
            AppToast.success(
                context, 'Đã cập nhật quyền. Vui lòng đăng nhập lại.');
            await SessionScope.maybeOf(context)?.onSignOut?.call();
          } else {
            AppToast.success(
                context, 'Đã cập nhật vai trò cho ${user.username}');
            _loadData();
          }
        }
      } catch (e) {
        if (mounted) {
          AppToast.error(context, 'Lỗi cập nhật: ${friendlyError(e)}');
        }
      }
    }
  }

  Future<void> _revokeSessions(EmployeeUserDto user) async {
    final repo = RepositoryScope.maybeOf(context);
    if (repo == null) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.power_settings_new_rounded, color: Color(0xFFF59E0B)),
            SizedBox(width: 8),
            Text('Thu hồi toàn bộ phiên đăng nhập'),
          ],
        ),
        content: Text(
          'Hành động này sẽ tăng auth_version và vô hiệu hóa ngay lập tức toàn bộ access token hiện có của nhân viên "${user.displayName}" (@${user.username}). Nhân viên sẽ phải đăng nhập lại.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Thu hồi phiên'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      try {
        await repo.revokeEmployeeSessions(user.id);
        if (mounted) {
          AppToast.success(context,
              'Đã thu hồi toàn bộ phiên đăng nhập của @${user.username}');
          _loadData();
        }
      } catch (e) {
        if (mounted) {
          AppToast.error(context, 'Lỗi thu hồi phiên: ${friendlyError(e)}');
        }
      }
    }
  }

  Future<void> _resetPassword(EmployeeUserDto user) async {
    final repo = RepositoryScope.maybeOf(context);
    if (repo == null) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.lock_reset_rounded, color: Color(0xFF2563EB)),
            SizedBox(width: 8),
            Text('Cấp lại mật khẩu tạm thời'),
          ],
        ),
        content: Text(
          'Hệ thống sẽ sinh mật khẩu ngẫu nhiên mới cho nhân viên "${user.displayName}". Toàn bộ phiên làm việc cũ sẽ bị hủy bỏ, và nhân viên bắt buộc đổi mật khẩu khi đăng nhập.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Cấp mật khẩu tạm'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      try {
        final newTempPassword = await repo.resetEmployeePassword(user.id);
        if (!mounted) return;

        await showDialog(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Row(
              children: [
                Icon(Icons.vpn_key_rounded, color: Color(0xFF059669)),
                SizedBox(width: 8),
                Text('Mật khẩu tạm thời mới'),
              ],
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Mật khẩu tạm thời cho tài khoản @${user.username}:'),
                const SizedBox(height: 12),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF1F5F9),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: const Color(0xFFCBD5E1)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      SelectableText(
                        newTempPassword,
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF0F172A),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.copy_rounded,
                            color: Color(0xFF2563EB)),
                        tooltip: 'Sao chép mật khẩu',
                        onPressed: () =>
                            _copyToClipboard('mật khẩu tạm', newTempPassword),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Lưu ý: Mật khẩu này chỉ hiển thị duy nhất một lần. Hãy bàn giao an toàn cho nhân viên.',
                  style: TextStyle(fontSize: 12, color: Color(0xFF64748B)),
                ),
              ],
            ),
            actions: [
              FilledButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('Đã bàn giao'),
              ),
            ],
          ),
        );
        _loadData();
      } catch (e) {
        if (mounted) {
          AppToast.error(context, 'Lỗi cấp lại mật khẩu: ${friendlyError(e)}');
        }
      }
    }
  }

  Future<void> _reinvite(EmployeeUserDto user) async {
    final repo = RepositoryScope.maybeOf(context);
    if (repo == null) return;

    try {
      final token = await repo.reinviteEmployee(user.id);
      if (!mounted) return;

      await showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.mark_email_read_rounded, color: Color(0xFF059669)),
              SizedBox(width: 8),
              Text('Gửi lại thư mời kích hoạt'),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                  'Mã kích hoạt mời mới cho @${user.username} (có hiệu lực 7 ngày):'),
              const SizedBox(height: 12),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFFCBD5E1)),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: SelectableText(
                        token,
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.copy_rounded,
                          color: Color(0xFF2563EB)),
                      tooltip: 'Sao chép mã',
                      onPressed: () => _copyToClipboard('mã kích hoạt', token),
                    ),
                  ],
                ),
              ),
            ],
          ),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Đóng'),
            ),
          ],
        ),
      );
      _loadData();
    } catch (e) {
      if (mounted) {
        AppToast.error(context, 'Lỗi gửi lại thư mời: ${friendlyError(e)}');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.maybeOf(context);
    final currentUser = session?.user;

    // Kiểm tra quyền
    if (!RoleVisibility.canManageEmployees(currentUser)) {
      return Center(
        child: Container(
          padding: const EdgeInsets.all(32),
          constraints: const BoxConstraints(maxWidth: 480),
          child: const Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.gpp_bad_outlined, size: 64, color: Color(0xFFF59E0B)),
              SizedBox(height: 16),
              Text(
                'Từ chối quyền truy cập',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              SizedBox(height: 8),
              Text(
                'Tài khoản của bạn không có capability iam:admin hoặc quyền Quản trị viên để quản lý danh sách nhân sự.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Color(0xFF64748B)),
              ),
            ],
          ),
        ),
      );
    }

    final totalCount = _employees.length;
    final activeCount = _employees.where((e) => e.isActive).length;
    final lockedCount = _employees.where((e) => e.isLocked).length;
    final pendingInviteCount =
        _employees.where((e) => e.hasPendingInvite).length;

    final width = MediaQuery.sizeOf(context).width;
    final isCompact = width < 750;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _loadData,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            // Header
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
                child: isCompact
                    ? Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Quản trị Nhân viên & Cấp phát IAM',
                            style: Theme.of(context)
                                .textTheme
                                .headlineSmall
                                ?.copyWith(
                                  fontWeight: FontWeight.w900,
                                  letterSpacing: -0.5,
                                ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Quản lý tài khoản nhân viên, cửa hàng, vai trò và phiên làm việc.',
                            style: TextStyle(
                              fontSize: 13,
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurfaceVariant,
                            ),
                          ),
                          const SizedBox(height: 12),
                          FilledButton.icon(
                            key: const Key('admin-create-employee-btn'),
                            icon: const Icon(Icons.person_add_alt_1_rounded),
                            label: const Text('Thêm nhân viên mới'),
                            onPressed: _openCreateEmployeeDialog,
                          ),
                        ],
                      )
                    : Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Quản trị Nhân viên & Cấp phát IAM',
                                  style: Theme.of(context)
                                      .textTheme
                                      .headlineSmall
                                      ?.copyWith(
                                        fontWeight: FontWeight.w900,
                                        letterSpacing: -0.5,
                                      ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Quản lý tài khoản nhân viên, cửa hàng, vai trò và phiên làm việc.',
                                  style: TextStyle(
                                    fontSize: 13,
                                    color: Theme.of(context)
                                        .colorScheme
                                        .onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 16),
                          FilledButton.icon(
                            key: const Key('admin-create-employee-btn'),
                            icon: const Icon(Icons.person_add_alt_1_rounded),
                            label: const Text('Thêm nhân viên mới'),
                            onPressed: _openCreateEmployeeDialog,
                          ),
                        ],
                      ),
              ),
            ),

            // Stats Banner
            SliverToBoxAdapter(
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                child: isCompact
                    ? Column(
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: _buildStatCard(
                                  'Tổng nhân sự',
                                  '$totalCount',
                                  Icons.people_outline,
                                  const Color(0xFF2563EB),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: _buildStatCard(
                                  'Đang hoạt động',
                                  '$activeCount',
                                  Icons.check_circle_outline,
                                  const Color(0xFF059669),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 10),
                          Row(
                            children: [
                              Expanded(
                                child: _buildStatCard(
                                  'Đã khóa',
                                  '$lockedCount',
                                  Icons.lock_outline,
                                  const Color(0xFFDC2626),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: _buildStatCard(
                                  'Chờ kích hoạt',
                                  '$pendingInviteCount',
                                  Icons.mail_outline,
                                  const Color(0xFFD97706),
                                ),
                              ),
                            ],
                          ),
                        ],
                      )
                    : Row(
                        children: [
                          Expanded(
                            child: _buildStatCard(
                              'Tổng nhân sự',
                              '$totalCount',
                              Icons.people_outline,
                              const Color(0xFF2563EB),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: _buildStatCard(
                              'Đang hoạt động',
                              '$activeCount',
                              Icons.check_circle_outline,
                              const Color(0xFF059669),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: _buildStatCard(
                              'Đã khóa',
                              '$lockedCount',
                              Icons.lock_outline,
                              const Color(0xFFDC2626),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: _buildStatCard(
                              'Chờ kích hoạt',
                              '$pendingInviteCount',
                              Icons.mail_outline,
                              const Color(0xFFD97706),
                            ),
                          ),
                        ],
                      ),
              ),
            ),

            // Filters Bar
            SliverToBoxAdapter(
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                child: isCompact
                    ? Column(
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: TextField(
                                  key: const Key('admin-employee-search-input'),
                                  controller: _searchCtrl,
                                  decoration: InputDecoration(
                                    hintText:
                                        'Tìm theo tên, username, email...',
                                    prefixIcon:
                                        const Icon(Icons.search, size: 20),
                                    border: const OutlineInputBorder(),
                                    contentPadding: const EdgeInsets.symmetric(
                                        horizontal: 12, vertical: 10),
                                    suffixIcon: _searchCtrl.text.isNotEmpty
                                        ? IconButton(
                                            icon: const Icon(Icons.clear,
                                                size: 18),
                                            onPressed: () {
                                              _searchCtrl.clear();
                                              _loadData();
                                            },
                                          )
                                        : null,
                                  ),
                                  onSubmitted: (_) => _loadData(),
                                ),
                              ),
                              const SizedBox(width: 8),
                              IconButton.filledTonal(
                                icon: const Icon(Icons.refresh_rounded),
                                tooltip: 'Tải lại danh sách',
                                onPressed: _loadData,
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Row(
                            children: [
                              Expanded(
                                child: DropdownButtonFormField<String?>(
                                  isExpanded: true,
                                  initialValue: _selectedBranchId,
                                  decoration: const InputDecoration(
                                    labelText: 'Chi nhánh',
                                    border: OutlineInputBorder(),
                                    contentPadding: EdgeInsets.symmetric(
                                        horizontal: 10, vertical: 8),
                                  ),
                                  items: [
                                    const DropdownMenuItem(
                                        value: null,
                                        child: Text('Tất cả chi nhánh',
                                            overflow: TextOverflow.ellipsis)),
                                    ..._branches.map((b) => DropdownMenuItem(
                                        value: b.id,
                                        child: Text(b.name,
                                            overflow: TextOverflow.ellipsis))),
                                  ],
                                  onChanged: (v) {
                                    setState(() => _selectedBranchId = v);
                                    _loadData();
                                  },
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: DropdownButtonFormField<String?>(
                                  isExpanded: true,
                                  initialValue: _selectedRole,
                                  decoration: const InputDecoration(
                                    labelText: 'Vai trò',
                                    border: OutlineInputBorder(),
                                    contentPadding: EdgeInsets.symmetric(
                                        horizontal: 10, vertical: 8),
                                  ),
                                  items: [
                                    const DropdownMenuItem(
                                        value: null,
                                        child: Text('Tất cả vai trò',
                                            overflow: TextOverflow.ellipsis)),
                                    ..._roles.map((r) => DropdownMenuItem(
                                        value: r.code,
                                        child: Text(r.name,
                                            overflow: TextOverflow.ellipsis))),
                                  ],
                                  onChanged: (v) {
                                    setState(() => _selectedRole = v);
                                    _loadData();
                                  },
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          DropdownButtonFormField<String?>(
                            isExpanded: true,
                            initialValue: _selectedStatus,
                            decoration: const InputDecoration(
                              labelText: 'Trạng thái tài khoản',
                              border: OutlineInputBorder(),
                              contentPadding: EdgeInsets.symmetric(
                                  horizontal: 10, vertical: 8),
                            ),
                            items: const [
                              DropdownMenuItem(
                                  value: null,
                                  child: Text('Tất cả trạng thái',
                                      overflow: TextOverflow.ellipsis)),
                              DropdownMenuItem(
                                  value: 'active',
                                  child: Text('Hoạt động',
                                      overflow: TextOverflow.ellipsis)),
                              DropdownMenuItem(
                                  value: 'locked',
                                  child: Text('Đã khóa',
                                      overflow: TextOverflow.ellipsis)),
                            ],
                            onChanged: (v) {
                              setState(() => _selectedStatus = v);
                              _loadData();
                            },
                          ),
                        ],
                      )
                    : Row(
                        children: [
                          Expanded(
                            flex: 2,
                            child: TextField(
                              key: const Key('admin-employee-search-input'),
                              controller: _searchCtrl,
                              decoration: InputDecoration(
                                hintText: 'Tìm theo tên, username, email...',
                                prefixIcon: const Icon(Icons.search, size: 20),
                                border: const OutlineInputBorder(),
                                contentPadding: const EdgeInsets.symmetric(
                                    horizontal: 12, vertical: 10),
                                suffixIcon: _searchCtrl.text.isNotEmpty
                                    ? IconButton(
                                        icon: const Icon(Icons.clear, size: 18),
                                        onPressed: () {
                                          _searchCtrl.clear();
                                          _loadData();
                                        },
                                      )
                                    : null,
                              ),
                              onSubmitted: (_) => _loadData(),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: DropdownButtonFormField<String?>(
                              isExpanded: true,
                              initialValue: _selectedBranchId,
                              decoration: const InputDecoration(
                                labelText: 'Chi nhánh',
                                border: OutlineInputBorder(),
                                contentPadding: EdgeInsets.symmetric(
                                    horizontal: 12, vertical: 10),
                              ),
                              items: [
                                const DropdownMenuItem(
                                    value: null,
                                    child: Text('Tất cả chi nhánh',
                                        overflow: TextOverflow.ellipsis)),
                                ..._branches.map((b) => DropdownMenuItem(
                                    value: b.id,
                                    child: Text(b.name,
                                        overflow: TextOverflow.ellipsis))),
                              ],
                              onChanged: (v) {
                                setState(() => _selectedBranchId = v);
                                _loadData();
                              },
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: DropdownButtonFormField<String?>(
                              isExpanded: true,
                              initialValue: _selectedRole,
                              decoration: const InputDecoration(
                                labelText: 'Vai trò',
                                border: OutlineInputBorder(),
                                contentPadding: EdgeInsets.symmetric(
                                    horizontal: 12, vertical: 10),
                              ),
                              items: [
                                const DropdownMenuItem(
                                    value: null,
                                    child: Text('Tất cả vai trò',
                                        overflow: TextOverflow.ellipsis)),
                                ..._roles.map((r) => DropdownMenuItem(
                                    value: r.code,
                                    child: Text(r.name,
                                        overflow: TextOverflow.ellipsis))),
                              ],
                              onChanged: (v) {
                                setState(() => _selectedRole = v);
                                _loadData();
                              },
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: DropdownButtonFormField<String?>(
                              isExpanded: true,
                              initialValue: _selectedStatus,
                              decoration: const InputDecoration(
                                labelText: 'Trạng thái',
                                border: OutlineInputBorder(),
                                contentPadding: EdgeInsets.symmetric(
                                    horizontal: 12, vertical: 10),
                              ),
                              items: const [
                                DropdownMenuItem(
                                    value: null,
                                    child: Text('Tất cả trạng thái',
                                        overflow: TextOverflow.ellipsis)),
                                DropdownMenuItem(
                                    value: 'active',
                                    child: Text('Hoạt động',
                                        overflow: TextOverflow.ellipsis)),
                                DropdownMenuItem(
                                    value: 'locked',
                                    child: Text('Đã khóa',
                                        overflow: TextOverflow.ellipsis)),
                              ],
                              onChanged: (v) {
                                setState(() => _selectedStatus = v);
                                _loadData();
                              },
                            ),
                          ),
                          const SizedBox(width: 12),
                          IconButton(
                            icon: const Icon(Icons.refresh_rounded),
                            tooltip: 'Tải lại danh sách',
                            onPressed: _loadData,
                          ),
                        ],
                      ),
              ),
            ),

            const SliverToBoxAdapter(child: Divider(height: 1)),

            // Body: Loading / Error / Empty / List
            if (_loading)
              const SliverFillRemaining(
                hasScrollBody: false,
                child: Center(child: LoadingView()),
              )
            else if (_errorMessage != null)
              SliverFillRemaining(
                hasScrollBody: false,
                child: Center(
                  child: ErrorView(message: _errorMessage!, onRetry: _loadData),
                ),
              )
            else if (_employees.isEmpty)
              SliverFillRemaining(
                hasScrollBody: false,
                child: Center(
                  child: EmptyView(
                    title: 'Không tìm thấy nhân viên nào',
                    subtitle:
                        'Thử thay đổi bộ lọc tìm kiếm hoặc thêm nhân viên mới.',
                    icon: Icons.person_search_outlined,
                    action: OutlinedButton.icon(
                      icon: const Icon(Icons.person_add),
                      label: const Text('Thêm nhân viên ngay'),
                      onPressed: _openCreateEmployeeDialog,
                    ),
                  ),
                ),
              )
            else
              SliverPadding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                sliver: SliverList.separated(
                  itemCount: _employees.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                  itemBuilder: (context, index) {
                    final user = _employees[index];
                    final isCurrent = currentUser != null &&
                        (currentUser.id == user.id ||
                            currentUser.username == user.username);

                    return _buildEmployeeCard(
                      user,
                      currentUser,
                      isCurrent,
                      isCompact,
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmployeeCard(
    EmployeeUserDto user,
    AppUser? currentUser,
    bool isCurrent,
    bool isCompact,
  ) {
    if (isCompact) {
      return Card(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
          side: BorderSide(
            color: user.isLocked
                ? const Color(0xFFFCA5A5)
                : const Color(0xFFE2E8F0),
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  UserAvatar(name: user.displayName, size: 40),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Row(
                      children: [
                        Flexible(
                          child: Text(
                            user.displayName,
                            style: const TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 15,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (isCurrent) ...[
                          const SizedBox(width: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: const Color(0xFFEFF6FF),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: const Text(
                              'Bạn',
                              style: TextStyle(
                                fontSize: 11,
                                color: Color(0xFF2563EB),
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 6),
                  _buildStatusBadge(user),
                  const SizedBox(width: 4),
                  _buildPopupMenu(user, currentUser, isCurrent),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                '@${user.username} · ${user.email ?? "Chưa có email"} · ${user.phoneNumber ?? "Chưa có SĐT"}',
                style: const TextStyle(
                  fontSize: 12,
                  color: Color(0xFF64748B),
                ),
              ),
              if (user.mustChangePassword) ...[
                const SizedBox(height: 4),
                const Text(
                  '⚠️ Bắt buộc đổi mật khẩu ở lần đăng nhập tới',
                  style: TextStyle(
                    fontSize: 11,
                    color: Color(0xFFD97706),
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
              const SizedBox(height: 8),
              const Divider(height: 1),
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(
                    Icons.account_balance_outlined,
                    size: 14,
                    color: Color(0xFF64748B),
                  ),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      user.branchName ?? 'Toàn hệ thống',
                      style: const TextStyle(
                        fontSize: 12.5,
                        fontWeight: FontWeight.w600,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
              if (user.roles.isNotEmpty) ...[
                const SizedBox(height: 6),
                Wrap(
                  spacing: 4,
                  runSpacing: 4,
                  children: user.roles.map((r) => _buildRoleChip(r)).toList(),
                ),
              ],
            ],
          ),
        ),
      );
    }

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(
          color:
              user.isLocked ? const Color(0xFFFCA5A5) : const Color(0xFFE2E8F0),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            UserAvatar(
              name: user.displayName,
              size: 44,
            ),
            const SizedBox(width: 14),
            Expanded(
              flex: 3,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          user.displayName,
                          style: const TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: 15,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (isCurrent) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFEFF6FF),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            'Bạn',
                            style: TextStyle(
                              fontSize: 11,
                              color: Color(0xFF2563EB),
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '@${user.username} · ${user.email ?? 'Chưa có email'} · ${user.phoneNumber ?? 'Chưa có SĐT'}',
                    style: const TextStyle(
                      fontSize: 12,
                      color: Color(0xFF64748B),
                    ),
                  ),
                  if (user.mustChangePassword) ...[
                    const SizedBox(height: 2),
                    const Text(
                      '⚠️ Bắt buộc đổi mật khẩu ở lần đăng nhập tới',
                      style: TextStyle(
                        fontSize: 11,
                        color: Color(0xFFD97706),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              flex: 2,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(
                        Icons.account_balance_outlined,
                        size: 14,
                        color: Color(0xFF64748B),
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          user.branchName ?? 'Toàn hệ thống',
                          style: const TextStyle(
                            fontSize: 12.5,
                            fontWeight: FontWeight.w600,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 4,
                    runSpacing: 4,
                    children: user.roles.map((r) => _buildRoleChip(r)).toList(),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            _buildStatusBadge(user),
            const SizedBox(width: 8),
            _buildPopupMenu(user, currentUser, isCurrent),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusBadge(EmployeeUserDto user) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: user.isLocked
            ? const Color(0xFFFEF2F2)
            : user.hasPendingInvite
                ? const Color(0xFFFFFBEB)
                : const Color(0xFFF0FDF4),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: user.isLocked
              ? const Color(0xFFEF4444)
              : user.hasPendingInvite
                  ? const Color(0xFFF59E0B)
                  : const Color(0xFF22C55E),
        ),
      ),
      child: Text(
        user.isLocked
            ? 'ĐÃ KHÓA'
            : user.hasPendingInvite
                ? 'CHỜ MỜI'
                : 'HOẠT ĐỘNG',
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.bold,
          color: user.isLocked
              ? const Color(0xFFDC2626)
              : user.hasPendingInvite
                  ? const Color(0xFFD97706)
                  : const Color(0xFF15803D),
        ),
      ),
    );
  }

  Widget _buildPopupMenu(
    EmployeeUserDto user,
    AppUser? currentUser,
    bool isCurrent,
  ) {
    return PopupMenuButton<String>(
      tooltip: 'Tác vụ nhân viên',
      icon: const Icon(Icons.more_vert_rounded),
      onSelected: (action) {
        switch (action) {
          case 'toggle_lock':
            _toggleLockUser(user, currentUser);
            break;
          case 'roles_scopes':
            _openRolesAndScopesDialog(user, currentUser);
            break;
          case 'reset_password':
            _resetPassword(user);
            break;
          case 'reinvite':
            _reinvite(user);
            break;
          case 'revoke_sessions':
            _revokeSessions(user);
            break;
        }
      },
      itemBuilder: (ctx) => [
        const PopupMenuItem(
          value: 'roles_scopes',
          child: Row(
            children: [
              Icon(Icons.shield_outlined, size: 18),
              SizedBox(width: 8),
              Expanded(
                  child: Text('Phân vai trò & Chi nhánh',
                      overflow: TextOverflow.ellipsis)),
            ],
          ),
        ),
        const PopupMenuItem(
          value: 'reset_password',
          child: Row(
            children: [
              Icon(Icons.lock_reset, size: 18),
              SizedBox(width: 8),
              Expanded(
                  child: Text('Cấp lại mật khẩu tạm',
                      overflow: TextOverflow.ellipsis)),
            ],
          ),
        ),
        if (user.hasPendingInvite)
          const PopupMenuItem(
            value: 'reinvite',
            child: Row(
              children: [
                Icon(Icons.mark_email_read_outlined, size: 18),
                SizedBox(width: 8),
                Expanded(
                    child: Text('Gửi lại thư mời',
                        overflow: TextOverflow.ellipsis)),
              ],
            ),
          ),
        const PopupMenuItem(
          value: 'revoke_sessions',
          child: Row(
            children: [
              Icon(Icons.power_settings_new, size: 18),
              SizedBox(width: 8),
              Expanded(
                  child: Text('Thu hồi phiên làm việc',
                      overflow: TextOverflow.ellipsis)),
            ],
          ),
        ),
        const PopupMenuDivider(),
        PopupMenuItem(
          value: 'toggle_lock',
          enabled: !isCurrent,
          child: Row(
            children: [
              Icon(
                user.isLocked ? Icons.lock_open : Icons.lock,
                size: 18,
                color: isCurrent
                    ? Colors.grey
                    : user.isLocked
                        ? const Color(0xFF059669)
                        : const Color(0xFFDC2626),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  user.isLocked ? 'Mở khóa tài khoản' : 'Khóa tài khoản',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: isCurrent
                        ? Colors.grey
                        : user.isLocked
                            ? const Color(0xFF059669)
                            : const Color(0xFFDC2626),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildStatCard(
      String title, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 24, color: color),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(fontSize: 11, color: Color(0xFF64748B)),
              ),
              Text(
                value,
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRoleChip(String role) {
    final lower = role.toLowerCase();
    Color bg = const Color(0xFFF1F5F9);
    Color fg = const Color(0xFF475569);

    if (lower.contains('admin')) {
      bg = const Color(0xFFFEF2F2);
      fg = const Color(0xFFDC2626);
    } else if (lower.contains('manager') ||
        lower.contains('approver') ||
        lower.contains('checker')) {
      bg = const Color(0xFFFAF5FF);
      fg = const Color(0xFF7C3AED);
    } else if (lower.contains('staff') || lower.contains('maker')) {
      bg = const Color(0xFFEFF6FF);
      fg = const Color(0xFF2563EB);
    } else if (lower.contains('auditor')) {
      bg = const Color(0xFFECFDF5);
      fg = const Color(0xFF059669);
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(5),
      ),
      child: Text(
        RoleVisibility.roleLabel(role).toUpperCase(),
        style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: fg),
      ),
    );
  }
}
