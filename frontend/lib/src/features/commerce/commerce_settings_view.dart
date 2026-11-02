import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app/app_shell.dart';
import '../../app/theme_mode_controller.dart';
import '../../core/i18n/app_i18n.dart';
import '../../core/i18n/locale_controller.dart';
import '../../core/theme/app_ui_settings_controller.dart';
import '../../core/util/role_visibility.dart';
import '../../data/models/dtos.dart';
import '../admin/employee_management_screen.dart';
import '../settings/widgets/change_password_dialog.dart';
import '../settings/widgets/edit_profile_dialog.dart';
import 'commerce_memory_store.dart';

/// Giao diện Cài đặt (Settings) tích hợp đầy đủ tính năng:
/// - Hồ sơ & Tài khoản (Google avatar, email, đổi mật khẩu, cập nhật profile)
/// - Giao diện & Hệ thống (Dark/Light mode, Color preset, Mật độ hiển thị)
/// - Ngôn ngữ hiển thị (Tiếng Việt / English chuẩn thuật ngữ ngân hàng & kho)
/// - Quản lý nhân viên & Phân quyền (RBAC)
/// - Cấu hình máy in & Mẫu hóa đơn (K80 / K57 / A4)
/// - Quản trị dữ liệu & Khởi tạo lại (Reset demo data)
class CommerceSettingsView extends StatefulWidget {
  const CommerceSettingsView({
    super.key,
    required this.store,
    required this.userName,
    this.user,
    this.onSignOut,
    this.canManageUsers = true,
    this.canResetDemoData = false,
  });

  final CommerceMemoryStore store;
  final String userName;
  final AppUser? user;
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
        title: Row(
          children: [
            const Icon(Icons.cleaning_services_rounded, color: Color(0xFFDC2626)),
            const SizedBox(width: 8),
            Text(
              context.tr('settings_reset_data'),
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
            ),
          ],
        ),
        content: Text(
          context.tr('settings_reset_desc'),
          style: const TextStyle(fontSize: 13, height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(context.tr('btn_cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFFDC2626),
            ),
            child: Text(context.tr('settings_reset_btn')),
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
    final compact = width < 650;

    return SingleChildScrollView(
      padding:
          EdgeInsets.fromLTRB(compact ? 16 : 32, 22, compact ? 16 : 32, 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.tr('settings_system_title'),
            style: const TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.w800,
              color: _slate900,
              letterSpacing: -.5,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            context.tr('settings_system_subtitle'),
            style: const TextStyle(fontSize: 13, color: _slate500),
          ),
          const SizedBox(height: 22),

          // 1. Hồ sơ & Bảo mật tài khoản
          _buildAccountCard(context, compact),
          const SizedBox(height: 18),

          // 2. Giao diện & Ngôn ngữ
          _buildAppearanceAndLocaleCard(context, compact),
          const SizedBox(height: 18),

          // 3. Quản lý Nhân sự & Phân quyền (RBAC)
          if (widget.canManageUsers) ...[
            _buildEmployeeManagementCard(context, compact),
            const SizedBox(height: 18),
          ],

          // 4. Cấu hình Máy in & Mẫu hóa đơn
          _buildPrinterConfigCard(context, compact),
          const SizedBox(height: 18),

          // 5. Quản trị Dữ liệu & Đăng xuất
          _buildMaintenanceCard(context, compact),
        ],
      ),
    );
  }

  Widget _buildAccountCard(BuildContext context, bool compact) {
    final session = SessionScope.maybeOf(context);
    final user = widget.user ?? session?.user;
    final displayName = user?.displayName.isNotEmpty == true
        ? user!.displayName
        : (widget.userName.isNotEmpty ? widget.userName : 'Người dùng');
    final email = user?.email ?? '';
    final avatarUrl = user?.avatarUrl;
    final roles = RoleVisibility.rolesOf(user);
    final roleLabel = roles.isNotEmpty
        ? RoleVisibility.roleLabel(roles.first)
        : (RoleVisibility.canManageEmployees(user)
            ? 'Chủ Quán (Admin)'
            : 'Nhân viên');

    return _sectionCard(
      title: context.tr('settings_account_security'),
      subtitle: context.tr('settings_account_subtitle'),
      child: Column(
        children: [
          compact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        CircleAvatar(
                          radius: 26,
                          backgroundColor: const Color(0xFFEEF2FF),
                          backgroundImage:
                              (avatarUrl != null && avatarUrl.isNotEmpty)
                                  ? NetworkImage(avatarUrl)
                                  : null,
                          child: (avatarUrl == null || avatarUrl.isEmpty)
                              ? Text(
                                  displayName.isNotEmpty
                                      ? displayName[0].toUpperCase()
                                      : 'U',
                                  style: const TextStyle(
                                    fontSize: 20,
                                    fontWeight: FontWeight.w800,
                                    color: _primary,
                                  ),
                                )
                              : null,
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                displayName,
                                style: const TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w700,
                                  color: _slate900,
                                ),
                              ),
                              if (email.isNotEmpty) ...[
                                const SizedBox(height: 2),
                                Text(
                                  email,
                                  style: const TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                    color: _primary,
                                  ),
                                ),
                              ],
                              const SizedBox(height: 3),
                              Text(
                                roleLabel,
                                style: const TextStyle(
                                    fontSize: 11, color: _slate500),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: () => showDialog(
                          context: context,
                          builder: (ctx) => const EditProfileDialog(),
                        ),
                        icon: const Icon(Icons.edit_outlined, size: 16),
                        label: Text(context.tr('settings_edit_btn')),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: _slate900,
                          side: const BorderSide(color: _border),
                          textStyle: const TextStyle(
                              fontSize: 12, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ),
                  ],
                )
              : Row(
                  children: [
                    CircleAvatar(
                      radius: 26,
                      backgroundColor: const Color(0xFFEEF2FF),
                      backgroundImage:
                          (avatarUrl != null && avatarUrl.isNotEmpty)
                              ? NetworkImage(avatarUrl)
                              : null,
                      child: (avatarUrl == null || avatarUrl.isEmpty)
                          ? Text(
                              displayName.isNotEmpty
                                  ? displayName[0].toUpperCase()
                                  : 'U',
                              style: const TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.w800,
                                color: _primary,
                              ),
                            )
                          : null,
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            displayName,
                            style: const TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: _slate900,
                            ),
                          ),
                          if (email.isNotEmpty) ...[
                            const SizedBox(height: 2),
                            Text(
                              email,
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: _primary,
                              ),
                            ),
                          ],
                          const SizedBox(height: 3),
                          Text(
                            roleLabel,
                            style: const TextStyle(
                                fontSize: 12, color: _slate500),
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
                      label: Text(context.tr('settings_edit_btn')),
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
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      context.tr('btn_change_password'),
                      style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: _slate900),
                    ),
                    Text(
                      context.tr('settings_change_pwd_desc'),
                      style: const TextStyle(fontSize: 11, color: _slate500),
                    ),
                  ],
                ),
              ),
              TextButton(
                onPressed: () => showDialog(
                  context: context,
                  builder: (ctx) => const ChangePasswordDialog(),
                ),
                child: Text(context.tr('settings_change_btn')),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAppearanceAndLocaleCard(BuildContext context, bool compact) {
    ThemeModeController? themeCtrl;
    LocaleController? localeCtrl;
    AppUiSettingsController? uiCtrl;
    try {
      themeCtrl = Provider.of<ThemeModeController>(context);
    } catch (_) {
      try {
        themeCtrl = Provider.of<ThemeModeController>(context, listen: false);
      } catch (_) {}
    }
    try {
      localeCtrl = Provider.of<LocaleController>(context);
    } catch (_) {
      try {
        localeCtrl = Provider.of<LocaleController>(context, listen: false);
      } catch (_) {}
    }
    try {
      uiCtrl = Provider.of<AppUiSettingsController>(context);
    } catch (_) {
      try {
        uiCtrl = Provider.of<AppUiSettingsController>(context, listen: false);
      } catch (_) {}
    }

    return _sectionCard(
      title: context.tr('settings_appearance_locale'),
      subtitle: context.tr('settings_appearance_subtitle'),
      child: Column(
        children: [
          // 1. Theme Mode Switcher
          _responsiveSettingRow(
            compact: compact,
            icon: Icons.dark_mode_outlined,
            title: context.tr('settings_theme_mode_label'),
            control: SegmentedButton<ThemeMode>(
              segments: [
                ButtonSegment(
                  value: ThemeMode.light,
                  label: Text(context.tr('settings_theme_light')),
                  icon: const Icon(Icons.light_mode_outlined, size: 16),
                ),
                ButtonSegment(
                  value: ThemeMode.dark,
                  label: Text(context.tr('settings_theme_dark')),
                  icon: const Icon(Icons.dark_mode_outlined, size: 16),
                ),
                ButtonSegment(
                  value: ThemeMode.system,
                  label: Text(context.tr('settings_theme_system')),
                ),
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
          ),
          const Divider(height: 22, color: _border),

          // 2. Language Switcher
          _responsiveSettingRow(
            compact: compact,
            icon: Icons.language_rounded,
            title: context.tr('settings_app_language_label'),
            control: SegmentedButton<String>(
              segments: [
                ButtonSegment(
                  value: 'vi',
                  label: Text(context.tr('settings_lang_vi')),
                ),
                ButtonSegment(
                  value: 'en',
                  label: Text(context.tr('settings_lang_en')),
                ),
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
          ),

          // 3. Density Switcher
          if (uiCtrl != null) ...[
            const Divider(height: 22, color: _border),
            _responsiveSettingRow(
              compact: compact,
              icon: Icons.view_compact_outlined,
              title: context.tr('settings_density'),
              control: SegmentedButton<AppDensity>(
                segments: [
                  ButtonSegment(
                    value: AppDensity.comfortable,
                    label: Text(context.tr('settings_density_comfortable')),
                  ),
                  ButtonSegment(
                    value: AppDensity.compact,
                    label: Text(context.tr('settings_density_compact')),
                  ),
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
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildEmployeeManagementCard(BuildContext context, bool compact) {
    return _sectionCard(
      title: context.tr('settings_hr_rbac'),
      subtitle: context.tr('settings_hr_subtitle'),
      child: compact
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.badge_outlined, size: 20, color: _slate500),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            context.tr('settings_rbac_list'),
                            style: const TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: _slate900,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            context.tr('settings_rbac_desc'),
                            style:
                                const TextStyle(fontSize: 11, color: _slate500),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (ctx) => const EmployeeManagementScreen(),
                        ),
                      );
                    },
                    icon: const Icon(Icons.manage_accounts_outlined, size: 16),
                    label: Text(context.tr('settings_manage_employees')),
                    style: FilledButton.styleFrom(
                      backgroundColor: _primary,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      textStyle: const TextStyle(
                          fontSize: 12, fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
              ],
            )
          : Row(
              children: [
                const Icon(Icons.badge_outlined, size: 20, color: _slate500),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        context.tr('settings_rbac_list'),
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: _slate900,
                        ),
                      ),
                      Text(
                        context.tr('settings_rbac_desc'),
                        style:
                            const TextStyle(fontSize: 11, color: _slate500),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                FilledButton.icon(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (ctx) => const EmployeeManagementScreen(),
                      ),
                    );
                  },
                  icon: const Icon(Icons.manage_accounts_outlined, size: 16),
                  label: Text(context.tr('settings_manage_employees')),
                  style: FilledButton.styleFrom(
                    backgroundColor: _primary,
                    textStyle: const TextStyle(
                        fontSize: 12, fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
    );
  }

  Widget _buildPrinterConfigCard(BuildContext context, bool compact) {
    return _sectionCard(
      title: context.tr('settings_printer_invoice'),
      subtitle: context.tr('settings_printer_subtitle'),
      child: Column(
        children: [
          Row(
            children: [
              const Icon(Icons.print_outlined, size: 20, color: _slate500),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  context.tr('settings_paper_size'),
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: _slate900,
                  ),
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
              Expanded(
                child: Text(
                  context.tr('settings_auto_print'),
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: _slate900,
                  ),
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

  Widget _buildMaintenanceCard(BuildContext context, bool compact) {
    return _sectionCard(
      title: context.tr('settings_system_data'),
      subtitle: widget.canResetDemoData
          ? context.tr('settings_system_data_subtitle')
          : context.tr('settings_signout_desc'),
      child: Column(
        children: [
          if (widget.canResetDemoData) ...[
            compact
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(Icons.restart_alt_rounded,
                              size: 20, color: Color(0xFFDC2626)),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  context.tr('settings_reset_data'),
                                  style: const TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w700,
                                    color: Color(0xFFDC2626),
                                  ),
                                ),
                                Text(
                                  context.tr('settings_reset_desc'),
                                  style: const TextStyle(
                                      fontSize: 11, color: _slate500),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      SizedBox(
                        width: double.infinity,
                        child: OutlinedButton.icon(
                          onPressed: _handleResetData,
                          icon: const Icon(Icons.refresh_rounded, size: 16),
                          label: Text(context.tr('settings_reset_btn')),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: const Color(0xFFDC2626),
                            side: const BorderSide(color: Color(0xFFFCA5A5)),
                            textStyle: const TextStyle(
                                fontSize: 12, fontWeight: FontWeight.w700),
                          ),
                        ),
                      ),
                    ],
                  )
                : Row(
                    children: [
                      const Icon(Icons.restart_alt_rounded,
                          size: 20, color: Color(0xFFDC2626)),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              context.tr('settings_reset_data'),
                              style: const TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w700,
                                  color: Color(0xFFDC2626)),
                            ),
                            Text(
                              context.tr('settings_reset_desc'),
                              style: const TextStyle(
                                  fontSize: 11, color: _slate500),
                            ),
                          ],
                        ),
                      ),
                      OutlinedButton.icon(
                        onPressed: _handleResetData,
                        icon: const Icon(Icons.refresh_rounded, size: 16),
                        label: Text(context.tr('settings_reset_btn')),
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
          compact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.logout_rounded,
                            size: 20, color: _slate500),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                context.tr('settings_signout_title'),
                                style: const TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    color: _slate900),
                              ),
                              Text(
                                context.tr('settings_signout_desc'),
                                style: const TextStyle(
                                    fontSize: 11, color: _slate500),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: widget.onSignOut,
                        icon: const Icon(Icons.logout_rounded, size: 16),
                        label: Text(context.tr('settings_signout_btn')),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFFDC2626),
                          textStyle: const TextStyle(
                              fontSize: 12, fontWeight: FontWeight.w700),
                        ),
                      ),
                    ),
                  ],
                )
              : Row(
                  children: [
                    const Icon(Icons.logout_rounded, size: 20, color: _slate500),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            context.tr('settings_signout_title'),
                            style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: _slate900),
                          ),
                          Text(
                            context.tr('settings_signout_desc'),
                            style: const TextStyle(
                                fontSize: 11, color: _slate500),
                          ),
                        ],
                      ),
                    ),
                    FilledButton.icon(
                      onPressed: widget.onSignOut,
                      icon: const Icon(Icons.logout_rounded, size: 16),
                      label: Text(context.tr('settings_signout_btn')),
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

  /// Responsive row helper:
  /// Trên màn hình nhỏ (`compact == true`): Tiêu đề ở hàng trên, control ở hàng dưới full-width.
  /// Trên màn hình rộng: Tiêu đề bên trái, control bên phải.
  Widget _responsiveSettingRow({
    required bool compact,
    required IconData icon,
    required String title,
    required Widget control,
  }) {
    if (compact) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 20, color: _slate500),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: _slate900,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: control,
          ),
        ],
      );
    }
    return Row(
      children: [
        Icon(icon, size: 20, color: _slate500),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: _slate900,
            ),
          ),
        ),
        const SizedBox(width: 12),
        control,
      ],
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
