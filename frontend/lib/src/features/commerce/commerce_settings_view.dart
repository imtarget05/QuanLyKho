import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/theme_mode_controller.dart';
import '../../core/i18n/locale_controller.dart';
import '../../core/theme/app_ui_settings_controller.dart';
import '../admin/employee_management_screen.dart';
import '../settings/widgets/change_password_dialog.dart';
import '../settings/widgets/edit_profile_dialog.dart';
import 'commerce_memory_store.dart';

/// Giao diện Cài đặt (Settings) tích hợp đầy đủ tính năng cấu hình từ version cũ:
/// - Hồ sơ & Tài khoản (Đổi mật khẩu, cập nhật profile)
/// - Giao diện & Hệ thống (Dark/Light mode, Color preset, Mật độ hiển thị)
/// - Ngôn ngữ hiển thị (Tiếng Việt / English)
/// - Quản lý nhân viên & Phân quyền (RBAC)
/// - Cấu hình máy in & Mẫu hóa đơn (K80 / K57 / A4)
/// - Quản trị dữ liệu & Khởi tạo lại (Reset demo data)
class CommerceSettingsView extends StatefulWidget {
  const CommerceSettingsView({
    super.key,
    required this.store,
    required this.userName,
    this.onSignOut,
    this.canManageUsers = true,
    this.canResetDemoData = false,
  });

  final CommerceMemoryStore store;
  final String userName;
  final Future<void> Function()? onSignOut;
  final bool canManageUsers;
  final bool canResetDemoData;

  @override
  State<CommerceSettingsView> createState() => _CommerceSettingsViewState();
}

class _CommerceSettingsViewState extends State<CommerceSettingsView> {
  static const _slate900 = Color(0xFF0F172A);
  static const _slate500 = Color(0xFF64748B);
  static const _border = Color(0xFFE2E8F0);
  static const _primary = Color(0xFF6366F1);

  String _paperSize = 'K80 (80mm - Tiêu chuẩn)';
  bool _autoPrint = true;

  Future<void> _handleResetData() async {
    if (!widget.canResetDemoData) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.cleaning_services_rounded, color: Color(0xFFDC2626)),
            SizedBox(width: 8),
            Text('Khởi tạo lại dữ liệu demo',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
          ],
        ),
        content: const Text(
          'Thao tác này sẽ làm mới toàn bộ danh mục sản phẩm, đơn hàng và công nợ về trạng thái mẫu ban đầu.\n\nBạn có chắc chắn muốn tiếp tục?',
          style: TextStyle(fontSize: 13, height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFFDC2626)),
            child: const Text('Khởi tạo lại'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      widget.store.resetToDefaultSample();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Đã khôi phục lại dữ liệu mẫu thành công!'),
          backgroundColor: Color(0xFF16A34A),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final compact = width < 760;

    return SingleChildScrollView(
      padding:
          EdgeInsets.fromLTRB(compact ? 16 : 32, 22, compact ? 16 : 32, 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Cài đặt hệ thống',
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.w800,
              color: _slate900,
              letterSpacing: -.5,
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'Tùy chỉnh tài khoản, giao diện hiển thị, cấu hình máy in và quản lý phân quyền.',
            style: TextStyle(fontSize: 13, color: _slate500),
          ),
          const SizedBox(height: 22),

          // 1. Hồ sơ & Bảo mật tài khoản
          _buildAccountCard(context),
          const SizedBox(height: 18),

          // 2. Giao diện & Ngôn ngữ
          _buildAppearanceAndLocaleCard(context),
          const SizedBox(height: 18),

          // 3. Quản lý Nhân sự & Phân quyền (RBAC)
          if (widget.canManageUsers) ...[
            _buildEmployeeManagementCard(context),
            const SizedBox(height: 18),
          ],

          // 4. Cấu hình Máy in & Mẫu hóa đơn
          _buildPrinterConfigCard(context),
          const SizedBox(height: 18),

          // 5. Quản trị Dữ liệu & Đăng xuất
          _buildMaintenanceCard(context),
        ],
      ),
    );
  }

  Widget _buildAccountCard(BuildContext context) {
    return _sectionCard(
      title: 'Tài khoản & Bảo mật',
      subtitle: 'Thông tin tài khoản đăng nhập hiện tại',
      child: Column(
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 26,
                backgroundColor: const Color(0xFFEEF2FF),
                child: Text(
                  widget.userName.isNotEmpty
                      ? widget.userName[0].toUpperCase()
                      : 'U',
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                    color: _primary,
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.userName,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: _slate900,
                      ),
                    ),
                    const SizedBox(height: 3),
                    const Text(
                      'Vai trò và quyền truy cập theo tài khoản',
                      style: TextStyle(fontSize: 12, color: _slate500),
                    ),
                  ],
                ),
              ),
              OutlinedButton.icon(
                onPressed: () => showDialog(
                  context: context,
                  builder: (ctx) => const EditProfileDialog(),
                ),
                icon: const Icon(Icons.edit_outlined, size: 16),
                label: const Text('Chỉnh sửa'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: _slate900,
                  side: const BorderSide(color: _border),
                  textStyle: const TextStyle(
                      fontSize: 12, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          const Divider(height: 24, color: _border),
          Row(
            children: [
              const Icon(Icons.lock_reset_rounded, size: 20, color: _slate500),
              const SizedBox(width: 10),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Đổi mật khẩu',
                      style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: _slate900),
                    ),
                    Text(
                      'Định kỳ thay đổi mật khẩu để bảo mật tài khoản',
                      style: TextStyle(fontSize: 11, color: _slate500),
                    ),
                  ],
                ),
              ),
              TextButton(
                onPressed: () => showDialog(
                  context: context,
                  builder: (ctx) => const ChangePasswordDialog(),
                ),
                child: const Text('Thay đổi'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAppearanceAndLocaleCard(BuildContext context) {
    ThemeModeController? themeCtrl;
    LocaleController? localeCtrl;
    AppUiSettingsController? uiCtrl;
    try {
      themeCtrl = Provider.of<ThemeModeController>(context, listen: false);
    } catch (_) {}
    try {
      localeCtrl = Provider.of<LocaleController>(context, listen: false);
    } catch (_) {}
    try {
      uiCtrl = Provider.of<AppUiSettingsController>(context, listen: false);
    } catch (_) {}

    return _sectionCard(
      title: 'Giao diện & Ngôn ngữ',
      subtitle: 'Tùy chỉnh chế độ hiển thị, màu chủ đạo và ngôn ngữ',
      child: Column(
        children: [
          // Theme Mode Switcher
          Row(
            children: [
              const Icon(Icons.dark_mode_outlined, size: 20, color: _slate500),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'Chế độ giao diện',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: _slate900),
                ),
              ),
              SegmentedButton<ThemeMode>(
                segments: const [
                  ButtonSegment(
                      value: ThemeMode.light,
                      label: Text('Sáng'),
                      icon: Icon(Icons.light_mode_outlined, size: 16)),
                  ButtonSegment(
                      value: ThemeMode.dark,
                      label: Text('Tối'),
                      icon: Icon(Icons.dark_mode_outlined, size: 16)),
                  ButtonSegment(
                      value: ThemeMode.system, label: Text('Tự động')),
                ],
                selected: {themeCtrl?.mode ?? ThemeMode.system},
                onSelectionChanged: (selected) {
                  if (themeCtrl != null && selected.isNotEmpty) {
                    themeCtrl.setMode(selected.first);
                    setState(() {});
                  }
                },
                style: const ButtonStyle(
                  visualDensity: VisualDensity.compact,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ],
          ),
          const Divider(height: 22, color: _border),

          // Language Switcher
          Row(
            children: [
              const Icon(Icons.language_rounded, size: 20, color: _slate500),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'Ngôn ngữ ứng dụng',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: _slate900),
                ),
              ),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'vi', label: Text('🇻🇳 Tiếng Việt')),
                  ButtonSegment(value: 'en', label: Text('🇬🇧 English')),
                ],
                selected: {(localeCtrl?.locale.languageCode ?? 'vi')},
                onSelectionChanged: (selected) {
                  if (localeCtrl != null && selected.isNotEmpty) {
                    localeCtrl.setLocale(Locale(selected.first));
                    setState(() {});
                  }
                },
                style: const ButtonStyle(
                  visualDensity: VisualDensity.compact,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ],
          ),
          if (uiCtrl != null) ...[
            const Divider(height: 22, color: _border),
            Row(
              children: [
                const Icon(Icons.view_compact_outlined,
                    size: 20, color: _slate500),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'Mật độ hiển thị',
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: _slate900),
                  ),
                ),
                SegmentedButton<AppDensity>(
                  segments: const [
                    ButtonSegment(
                        value: AppDensity.comfortable, label: Text('Rộng rãi')),
                    ButtonSegment(
                        value: AppDensity.compact, label: Text('Thu gọn')),
                  ],
                  selected: {uiCtrl.density},
                  onSelectionChanged: (selected) {
                    if (uiCtrl != null && selected.isNotEmpty) {
                      uiCtrl.setDensity(selected.first);
                      setState(() {});
                    }
                  },
                  style: const ButtonStyle(
                    visualDensity: VisualDensity.compact,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildEmployeeManagementCard(BuildContext context) {
    return _sectionCard(
      title: 'Nhân sự & Phân quyền',
      subtitle: 'Quản lý danh sách nhân viên, tài khoản thu ngân và thủ kho',
      child: Row(
        children: [
          const Icon(Icons.badge_outlined, size: 20, color: _slate500),
          const SizedBox(width: 10),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Danh sách nhân viên & vai trò (RBAC)',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: _slate900),
                ),
                Text(
                  'Cấp quyền, tạo mã nhân viên và kích hoạt / vô hiệu hóa tài khoản',
                  style: TextStyle(fontSize: 11, color: _slate500),
                ),
              ],
            ),
          ),
          FilledButton.icon(
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (ctx) => const EmployeeManagementScreen(),
                ),
              );
            },
            icon: const Icon(Icons.manage_accounts_outlined, size: 16),
            label: const Text('Quản lý nhân viên'),
            style: FilledButton.styleFrom(
              backgroundColor: _primary,
              textStyle:
                  const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPrinterConfigCard(BuildContext context) {
    return _sectionCard(
      title: 'Máy in & Hóa đơn',
      subtitle: 'Cấu hình thông số in phiếu bán hàng và nhập hàng',
      child: Column(
        children: [
          Row(
            children: [
              const Icon(Icons.print_outlined, size: 20, color: _slate500),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'Khổ giấy in nhiệt',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: _slate900),
                ),
              ),
              DropdownButton<String>(
                value: _paperSize,
                underline: const SizedBox.shrink(),
                style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: _slate900),
                items: const [
                  DropdownMenuItem(
                      value: 'K80 (80mm - Tiêu chuẩn)',
                      child: Text('K80 (80mm - Tiêu chuẩn)')),
                  DropdownMenuItem(
                      value: 'K57 (57mm - Mini)',
                      child: Text('K57 (57mm - Mini)')),
                  DropdownMenuItem(
                      value: 'A4 / A5 (Văn phòng)',
                      child: Text('A4 / A5 (Văn phòng)')),
                ],
                onChanged: (val) {
                  if (val != null) setState(() => _paperSize = val);
                },
              ),
            ],
          ),
          const Divider(height: 22, color: _border),
          Row(
            children: [
              const Icon(Icons.receipt_long_outlined,
                  size: 20, color: _slate500),
              const SizedBox(width: 10),
              const Expanded(
                child: Text(
                  'Tự động bật cửa sổ in sau khi tạo phiếu',
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: _slate900),
                ),
              ),
              Switch(
                value: _autoPrint,
                activeThumbColor: _primary,
                onChanged: (val) => setState(() => _autoPrint = val),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMaintenanceCard(BuildContext context) {
    return _sectionCard(
      title: 'Quản trị hệ thống & Dữ liệu',
      subtitle: widget.canResetDemoData
          ? 'Khởi tạo lại dữ liệu demo hoặc đăng xuất khỏi phiên làm việc'
          : 'Cấu hình hệ thống và đăng xuất khỏi phiên làm việc',
      child: Column(
        children: [
          if (widget.canResetDemoData) ...[
            Row(
              children: [
                const Icon(Icons.restart_alt_rounded,
                    size: 20, color: Color(0xFFDC2626)),
                const SizedBox(width: 10),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Khôi phục dữ liệu mẫu ban đầu',
                        style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFFDC2626)),
                      ),
                      Text(
                        'Làm mới kho hàng, phiếu mua bán và công nợ về trạng thái mẫu',
                        style: TextStyle(fontSize: 11, color: _slate500),
                      ),
                    ],
                  ),
                ),
                OutlinedButton.icon(
                  onPressed: _handleResetData,
                  icon: const Icon(Icons.refresh_rounded, size: 16),
                  label: const Text('Khởi tạo lại'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: const Color(0xFFDC2626),
                    side: const BorderSide(color: Color(0xFFFCA5A5)),
                    textStyle: const TextStyle(
                        fontSize: 12, fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
            const Divider(height: 22, color: _border),
          ],
          Row(
            children: [
              const Icon(Icons.logout_rounded, size: 20, color: _slate500),
              const SizedBox(width: 10),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Đăng xuất khỏi hệ thống',
                      style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: _slate900),
                    ),
                    Text(
                      'Kết thúc phiên làm việc và trở lại màn hình đăng nhập',
                      style: TextStyle(fontSize: 11, color: _slate500),
                    ),
                  ],
                ),
              ),
              FilledButton.icon(
                onPressed: widget.onSignOut,
                icon: const Icon(Icons.logout_rounded, size: 16),
                label: const Text('Đăng xuất'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFDC2626),
                  textStyle: const TextStyle(
                      fontSize: 12, fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _sectionCard(
      {required String title,
      required String subtitle,
      required Widget child}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: _border),
        boxShadow: const [
          BoxShadow(
              color: Color(0x04000000), blurRadius: 4, offset: Offset(0, 2))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: const TextStyle(
                  fontSize: 15, fontWeight: FontWeight.w800, color: _slate900)),
          const SizedBox(height: 3),
          Text(subtitle,
              style: const TextStyle(fontSize: 11.5, color: _slate500)),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }
}
