import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:qr_flutter/qr_flutter.dart';

import '../../app/app_shell.dart';
import '../../app/theme_mode_controller.dart';
import '../../core/i18n/locale_controller.dart';
import '../../core/theme/app_ui_settings_controller.dart';
import '../../core/theme/app_tokens.dart';
import '../../core/util/web_helpers.dart';
import '../../core/widgets/app_toast.dart';
import '../../core/widgets/section_header.dart';
import '../../core/util/role_visibility.dart';
import '../../core/widgets/store_logo.dart';
import '../../core/widgets/user_avatar.dart';
import '../admin/employee_management_screen.dart';
import '../auth/auth_service.dart';
import '../cash/cash_screen.dart';
import 'widgets/change_password_dialog.dart';
import 'widgets/edit_profile_dialog.dart';
import 'widgets/avatar_editor_sheet.dart';

/// Màn Cài đặt: chọn giao diện, hồ sơ cá nhân, bảo mật tài khoản & kiểm soát viên,
/// kiểm tra kết nối API hệ thống và đăng xuất.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  Future<void> _showResetStoreDataDialog(BuildContext context) async {
    bool keepCatalog = true;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlgState) {
          return AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: const Row(
              children: [
                Icon(Icons.cleaning_services_rounded, color: Colors.red),
                SizedBox(width: 8),
                Text('Khởi tạo lại hệ thống'),
              ],
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Thao tác này sẽ xóa sạch toàn bộ các phiếu yêu cầu, đối soát kiểm kê, giao dịch tiền mặt và dải serial thử nghiệm.',
                  style: TextStyle(fontSize: 13),
                ),
                const SizedBox(height: 12),
                RadioListTile<bool>(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Giữ danh mục mẫu quán thật (19 mặt hàng F&B)',
                      style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                  subtitle: const Text('Bao gồm giá vốn, giá bán, tồn kho tối thiểu chuẩn',
                      style: TextStyle(fontSize: 12)),
                  value: true,
                  // ignore: deprecated_member_use
                  groupValue: keepCatalog,
                  // ignore: deprecated_member_use
                  onChanged: (val) => setDlgState(() => keepCatalog = val ?? true),
                ),
                RadioListTile<bool>(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Xóa sạch hoàn toàn (Cửa hàng trắng)',
                      style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                  subtitle: const Text('Không có mặt hàng nào để bắt đầu nhập từ đầu',
                      style: TextStyle(fontSize: 12)),
                  value: false,
                  // ignore: deprecated_member_use
                  groupValue: keepCatalog,
                  // ignore: deprecated_member_use
                  onChanged: (val) => setDlgState(() => keepCatalog = val ?? false),
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(false),
                child: const Text('Hủy'),
              ),
              FilledButton.icon(
                key: const Key('btn-confirm-reset-store-data'),
                style: FilledButton.styleFrom(backgroundColor: Colors.red),
                icon: const Icon(Icons.delete_forever, size: 16),
                label: const Text('Xác nhận làm sạch'),
                onPressed: () => Navigator.of(ctx).pop(true),
              ),
            ],
          );
        },
      ),
    );

    if (confirmed == true && context.mounted) {
      try {
        final repo = RepositoryScope.of(context);
        await repo.resetStoreData(keepCatalog: keepCatalog);
        if (context.mounted) {
          AppToast.success(
            context,
            'Đã làm sạch và khởi tạo lại dữ liệu cửa hàng thành công!',
          );
        }
      } catch (e) {
        if (context.mounted) {
          AppToast.error(context, 'Lỗi: $e');
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final sc = Theme.of(context);
    final auth = context.watch<AuthService>();
    final themeController = context.watch<ThemeModeController?>();
    final uiSettings = context.watch<AppUiSettingsController?>();
    final localeController = context.watch<LocaleController?>();
    final isDark = sc.brightness == Brightness.dark;
    final user = auth.user;
    final currentMode =
        uiSettings?.mode ?? themeController?.mode ?? ThemeMode.system;
    final activePreset = uiSettings?.colorPreset ?? AppColorPreset.matcha;
    final activeDensity = uiSettings?.density ?? AppDensity.comfortable;
    final isVi = localeController?.isVietnamese ?? true;

    final isMobile = MediaQuery.sizeOf(context).width < 600;
    final pagePadding = isMobile
        ? const EdgeInsets.symmetric(horizontal: 14, vertical: 12)
        : const EdgeInsets.all(AppSpacing.lg);
    final cardPadding = isMobile
        ? const EdgeInsets.all(12)
        : const EdgeInsets.all(AppSpacing.lg);
    final sectionGap = SizedBox(height: isMobile ? 12 : AppSpacing.lg);
    final titleGap = SizedBox(height: isMobile ? 8 : AppSpacing.md);

    return Scaffold(
      appBar: AppBar(
        title: Text(isVi ? 'Cài đặt' : 'Settings'),
        centerTitle: true,
      ),
      body: SingleChildScrollView(
        padding: pagePadding,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Section Ngôn ngữ
            SectionHeader(
              title: isVi ? 'Ngôn ngữ hiển thị' : 'Display Language',
              showCount: false,
            ),
            titleGap,
            Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: BorderSide(
                  color: isDark
                      ? const Color(0xFF334155)
                      : const Color(0xFFE2E8F0),
                ),
              ),
              child: Padding(
                padding: cardPadding,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color:
                                sc.colorScheme.primary.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Icon(Icons.translate_rounded,
                              color: sc.colorScheme.primary, size: 20),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                isVi
                                    ? 'Tùy chọn ngôn ngữ ứng dụng'
                                    : 'Application Language',
                                style: sc.textTheme.titleSmall
                                    ?.copyWith(fontWeight: FontWeight.w700),
                              ),
                              Text(
                                isVi
                                    ? 'Hệ thống tự động áp dụng và lưu cấu hình'
                                    : 'Changes apply instantly and are saved',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: isDark
                                      ? const Color(0xFF94A3B8)
                                      : const Color(0xFF64748B),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.md),
                    SegmentedButton<String>(
                      segments: const [
                        ButtonSegment<String>(
                          value: 'vi',
                          icon: Text('🇻🇳', style: TextStyle(fontSize: 16)),
                          label: Text('Tiếng Việt (Mặc định)'),
                        ),
                        ButtonSegment<String>(
                          value: 'en',
                          icon: Text('🇬🇧', style: TextStyle(fontSize: 16)),
                          label: Text('English (Global)'),
                        ),
                      ],
                      selected: {isVi ? 'vi' : 'en'},
                      onSelectionChanged: (selected) {
                        localeController?.setLocale(Locale(selected.first));
                      },
                    ),
                  ],
                ),
              ),
            ),
            sectionGap,

            // Section Giao diện
            SectionHeader(
              title: isVi ? 'Giao diện' : 'Appearance',
              showCount: false,
            ),
            titleGap,
            Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: BorderSide(
                  color: isDark
                      ? const Color(0xFF334155)
                      : const Color(0xFFE2E8F0),
                ),
              ),
              child: Padding(
                padding: cardPadding,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // 1. Chế độ hiển thị
                    Text(
                      isVi
                          ? 'Chế độ hiển thị (Sáng / Tối)'
                          : 'Display Theme Mode',
                      style: sc.textTheme.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    SegmentedButton<ThemeMode>(
                      segments: [
                        ButtonSegment(
                          value: ThemeMode.system,
                          icon: const Icon(Icons.settings_suggest_outlined, size: 18),
                          label: Text(isVi ? 'Hệ thống' : 'System'),
                        ),
                        ButtonSegment(
                          value: ThemeMode.light,
                          icon: const Icon(Icons.light_mode_outlined, size: 18),
                          label: Text(isVi ? 'Sáng' : 'Light'),
                        ),
                        ButtonSegment(
                          value: ThemeMode.dark,
                          icon: const Icon(Icons.dark_mode_outlined, size: 18),
                          label: Text(isVi ? 'Tối' : 'Dark'),
                        ),
                      ],
                      selected: {currentMode},
                      onSelectionChanged: (modes) {
                        if (uiSettings != null) {
                          uiSettings.setMode(modes.first);
                        } else {
                          themeController?.setMode(modes.first);
                        }
                      },
                    ),

                    const SizedBox(height: AppSpacing.md),
                    const Divider(height: 1),
                    const SizedBox(height: AppSpacing.md),

                    // 2. Màu sắc thương hiệu
                    Row(
                      children: [
                        Icon(Icons.palette_outlined,
                            color: sc.colorScheme.primary, size: 20),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            isVi
                                ? 'Bảng màu thương hiệu (Brand Themes)'
                                : 'Brand Color Themes',
                            style: sc.textTheme.titleSmall
                                ?.copyWith(fontWeight: FontWeight.w700),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      isVi
                          ? 'Tùy chỉnh sắc thái màu sắc đại diện cho thương hiệu của bạn'
                          : 'Choose the visual personality for your business',
                      style: TextStyle(
                        fontSize: 12,
                        color: isDark
                            ? const Color(0xFF94A3B8)
                            : const Color(0xFF64748B),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: [
                        _ColorPresetCard(
                          preset: AppColorPreset.matcha,
                          name: isVi ? '🍵 Xanh Matcha' : '🍵 Fresh Matcha',
                          primaryColor: const Color(0xFF059669),
                          secondaryColor: const Color(0xFF10B981),
                          isSelected: activePreset == AppColorPreset.matcha,
                          onTap: () =>
                              uiSettings?.setColorPreset(AppColorPreset.matcha),
                        ),
                        _ColorPresetCard(
                          preset: AppColorPreset.milktea,
                          name: isVi
                              ? '🧋 Trà Sữa Cổ Điển'
                              : '🧋 Classic Milk Tea',
                          primaryColor: const Color(0xFF8D5B4C),
                          secondaryColor: const Color(0xFFD97706),
                          isSelected: activePreset == AppColorPreset.milktea,
                          onTap: () => uiSettings
                              ?.setColorPreset(AppColorPreset.milktea),
                        ),
                        _ColorPresetCard(
                          preset: AppColorPreset.oolong,
                          name: isVi
                              ? '🫐 Ô Long Thượng Hạng'
                              : '🫐 Royal Oolong',
                          primaryColor: const Color(0xFF1E293B),
                          secondaryColor: const Color(0xFF0284C7),
                          isSelected: activePreset == AppColorPreset.oolong,
                          onTap: () =>
                              uiSettings?.setColorPreset(AppColorPreset.oolong),
                        ),
                        _ColorPresetCard(
                          preset: AppColorPreset.berry,
                          name: isVi ? '🌸 Dâu & Trà Hoa' : '🌸 Sakura Berry',
                          primaryColor: const Color(0xFFBE185D),
                          secondaryColor: const Color(0xFFE11D48),
                          isSelected: activePreset == AppColorPreset.berry,
                          onTap: () =>
                              uiSettings?.setColorPreset(AppColorPreset.berry),
                        ),
                      ],
                    ),

                    const SizedBox(height: AppSpacing.lg),
                    const Divider(height: 1),
                    const SizedBox(height: AppSpacing.lg),

                    // 3. Mật độ hiển thị
                    Row(
                      children: [
                        Icon(Icons.view_compact_outlined,
                            color: sc.colorScheme.primary, size: 20),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            isVi ? 'Mật độ hiển thị giao diện' : 'Layout Density',
                            style: sc.textTheme.titleSmall
                                ?.copyWith(fontWeight: FontWeight.w700),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    LayoutBuilder(
                      builder: (context, constraints) {
                        final isCompactView = constraints.maxWidth < 420;
                        return SegmentedButton<AppDensity>(
                          segments: [
                            ButtonSegment<AppDensity>(
                              value: AppDensity.comfortable,
                              icon: const Icon(Icons.touch_app_outlined, size: 18),
                              label: Text(
                                isVi
                                    ? (isCompactView ? 'Tiêu chuẩn' : 'Tiêu chuẩn (POS/Cảm ứng)')
                                    : (isCompactView ? 'Comfortable' : 'Comfortable (Touch POS)'),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            ButtonSegment<AppDensity>(
                              value: AppDensity.compact,
                              icon:
                                  const Icon(Icons.density_small_rounded, size: 18),
                              label: Text(
                                isVi
                                    ? (isCompactView ? 'Gọn gàng' : 'Gọn gàng (Kiểm kho/Audit)')
                                    : (isCompactView ? 'Compact' : 'Compact (Audit/Tables)'),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                          selected: {activeDensity},
                          onSelectionChanged: (densities) {
                            uiSettings?.setDensity(densities.first);
                          },
                        );
                      },
                    ),

                    const SizedBox(height: AppSpacing.lg),
                    const Divider(height: 1),
                    const SizedBox(height: AppSpacing.sm),

                    // 4. Bật/tắt thanh Live Ticker
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        isVi
                            ? 'Thanh cảnh báo kho & ca trực (Live Ticker)'
                            : 'Live Inventory & Shift Alert Bar',
                        style: sc.textTheme.titleSmall
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      subtitle: Text(
                        isVi
                            ? 'Ghim thanh cảnh báo nhanh trạng thái ca trực, tồn kho định mức và hạn sử dụng FEFO ở đầu trang'
                            : 'Pins real-time alert ticker for shift status, minimum safety stock and FEFO expiry at the top of the app',
                        style: TextStyle(
                          fontSize: 12,
                          color: isDark
                              ? const Color(0xFF94A3B8)
                              : const Color(0xFF64748B),
                        ),
                      ),
                      value: uiSettings?.showLiveTicker ?? true,
                      activeThumbColor: sc.colorScheme.primary,
                      onChanged: (val) => uiSettings?.setShowLiveTicker(val),
                    ),
                  ],
                ),
              ),
            ),
            sectionGap,
            SectionHeader(
              title: isVi ? 'Hồ Sơ Của Tôi' : 'My Profile',
              showCount: false,
            ),
            titleGap,
            Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: BorderSide(
                  color: isDark
                      ? const Color(0xFF334155)
                      : const Color(0xFFE2E8F0),
                ),
              ),
              child: Padding(
                padding: cardPadding,
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final isMobileCard = constraints.maxWidth < 560;
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            UserAvatar(
                              name: user?.displayName ?? 'Khách',
                              email: user?.effectiveEmail,
                              avatarUrl: user?.avatarUrl,
                              size: isMobileCard ? 54 : 64,
                              showEditBadge: true,
                              onTap: () async {
                                final updated = await AvatarEditorSheet.show(
                                  context,
                                  user: user,
                                );
                                if (updated == true && context.mounted) {
                                  setState(() {});
                                }
                              },
                            ),
                            const SizedBox(width: 14),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(
                                    user?.displayName ?? 'Khách vãng lai',
                                    style: const TextStyle(
                                      fontSize: 17,
                                      fontWeight: FontWeight.w800,
                                      letterSpacing: -0.2,
                                    ),
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  const SizedBox(height: 3),
                                  Text(
                                    '@${user?.username ?? 'guest'} · Mã NV: ${user?.effectiveEmployeeCode ?? 'NV-082'}',
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w500,
                                      color: isDark
                                          ? const Color(0xFF94A3B8)
                                          : const Color(0xFF64748B),
                                    ),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(width: 8),
                            if (!isMobileCard)
                              OutlinedButton.icon(
                                key: const Key('settings-edit-profile-btn'),
                                icon: const Icon(Icons.edit_outlined, size: 16),
                                label: Text(isVi ? 'Chỉnh sửa hồ sơ' : 'Edit Profile'),
                                style: OutlinedButton.styleFrom(
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 14,
                                    vertical: 10,
                                  ),
                                ),
                                onPressed: () async {
                                  final updated = await EditProfileDialog.show(
                                    context,
                                    user: user,
                                  );
                                  if (updated == true && context.mounted) {
                                    AppToast.success(
                                      context,
                                      isVi
                                          ? 'Cập nhật hồ sơ cá nhân thành công!'
                                          : 'Profile updated successfully!',
                                    );
                                    setState(() {});
                                  }
                                },
                              )
                            else
                              IconButton.filledTonal(
                                key: const Key('settings-edit-profile-btn'),
                                icon: const Icon(Icons.edit_outlined, size: 18),
                                tooltip: isVi ? 'Chỉnh sửa hồ sơ' : 'Edit Profile',
                                onPressed: () async {
                                  final updated = await EditProfileDialog.show(
                                    context,
                                    user: user,
                                  );
                                  if (updated == true && context.mounted) {
                                    AppToast.success(
                                      context,
                                      isVi
                                          ? 'Cập nhật hồ sơ cá nhân thành công!'
                                          : 'Profile updated successfully!',
                                    );
                                    setState(() {});
                                  }
                                },
                              ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 6,
                          runSpacing: 6,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            for (final role in _uniqueDisplayRoles(
                                user?.roles ?? ['staff']))
                              _RoleBadge(role: role),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: const Color(0xFF10B981)
                                    .withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(
                                  color: const Color(0xFF10B981)
                                      .withValues(alpha: 0.3),
                                ),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(Icons.check_circle_rounded,
                                      size: 12, color: Color(0xFF059669)),
                                  const SizedBox(width: 4),
                                  Text(
                                    isVi ? 'Hoạt động' : 'Active',
                                    style: const TextStyle(
                                      fontSize: 11,
                                      fontWeight: FontWeight.w700,
                                      color: Color(0xFF059669),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        if (isMobileCard) ...[
                          const SizedBox(height: 12),
                          Row(
                            children: [
                              Expanded(
                                child: OutlinedButton.icon(
                                  key: const Key(
                                      'settings-edit-profile-mobile-btn'),
                                  icon: const Icon(Icons.edit_outlined,
                                      size: 16),
                                  label: Text(isVi ? 'Chỉnh sửa hồ sơ cá nhân' : 'Edit Profile'),
                                  style: OutlinedButton.styleFrom(
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    padding: const EdgeInsets.symmetric(
                                        vertical: 8),
                                  ),
                                  onPressed: () async {
                                    final updated =
                                        await EditProfileDialog.show(
                                      context,
                                      user: user,
                                    );
                                    if (updated == true && context.mounted) {
                                      AppToast.success(
                                        context,
                                        isVi
                                            ? 'Cập nhật hồ sơ cá nhân thành công!'
                                            : 'Profile updated successfully!',
                                      );
                                      setState(() {});
                                    }
                                  },
                                ),
                              ),
                              const SizedBox(width: 8),
                              OutlinedButton.icon(
                                key: const Key('settings-change-avatar-btn'),
                                icon: const Icon(Icons.camera_alt_outlined,
                                    size: 16),
                                label: Text(isVi ? 'Đổi avatar' : 'Change Avatar'),
                                style: OutlinedButton.styleFrom(
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 10, vertical: 8),
                                ),
                                onPressed: () async {
                                  final updated =
                                      await AvatarEditorSheet.show(
                                    context,
                                    user: user,
                                  );
                                  if (updated == true && context.mounted) {
                                    setState(() {});
                                  }
                                },
                              ),
                            ],
                          ),
                        ],
                        const SizedBox(height: 16),
                        const Divider(height: 1),
                        const SizedBox(height: 16),
                        Wrap(
                          spacing: 24,
                          runSpacing: 16,
                          children: [
                            _ProfileInfoItem(
                              icon: Icons.email_outlined,
                              label: 'Email liên hệ',
                              value: user?.effectiveEmail ??
                                  'demo@khotrasua.local',
                            ),
                            _ProfileInfoItem(
                              icon: Icons.phone_outlined,
                              label: 'Số điện thoại',
                              value: user?.effectivePhone ?? '0901 234 567',
                            ),
                            _ProfileInfoItem(
                              icon: Icons.storefront_outlined,
                              label: 'Cơ sở làm việc',
                              value: user?.effectiveBranch ??
                                  'Cửa hàng Trà Sữa Quận 1',
                            ),
                            const _ProfileInfoItem(
                              icon: Icons.shield_outlined,
                              label: 'Tiêu chuẩn bảo mật',
                              value: 'ISO 27001 · Dual Control Active',
                            ),
                          ],
                        ),
                      ],
                    );
                  },
                ),
              ),
            ),
            sectionGap,
            SectionHeader(
              title: isVi ? 'Tài khoản & Bảo mật' : 'Account & Security',
              showCount: false,
            ),
            titleGap,
            Card(
              child: ListTile(
                key: const Key('settings-change-password-tile'),
                leading: const Icon(Icons.lock_outline),
                title: Text(isVi ? 'Đổi mật khẩu đăng nhập' : 'Change Password'),
                subtitle: Text(isVi
                    ? 'Cập nhật mật khẩu tài khoản hiện tại'
                    : 'Update your account login password'),
                trailing: const Icon(Icons.chevron_right, size: 20),
                onTap: () async {
                  final updated = await ChangePasswordDialog.show(context);
                  if (updated == true && context.mounted) {
                    AppToast.success(context, isVi ? 'Đổi mật khẩu thành công!' : 'Password changed successfully!');
                  }
                },
              ),
            ),
            sectionGap,
            if (RoleVisibility.canManageEmployees(user) ||
                RoleVisibility.isAdmin(RoleVisibility.rolesOf(user))) ...[
              SectionHeader(
                title: isVi ? 'IAM & Quản trị Hệ thống' : 'IAM & System Administration',
                showCount: false,
              ),
              titleGap,
              Card(
                child: Column(
                  children: [
                    if (RoleVisibility.canManageEmployees(user))
                      ListTile(
                        key: const Key('settings-goto-employees-tile'),
                        leading: const Icon(Icons.manage_accounts_outlined,
                            color: Color(0xFF2563EB)),
                        title: Text(isVi ? 'Quản trị Nhân viên & Cấp phát IAM' : 'Staff & IAM Management'),
                        subtitle: Text(isVi
                            ? 'Tạo nhân viên, cấp mật khẩu tạm/thư mời, phân quyền và khóa tài khoản'
                            : 'Create staff, issue credentials/invites, assign roles & lock accounts'),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () {
                          Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => RepositoryScope(
                                repository: RepositoryScope.of(context),
                                child: const EmployeeManagementScreen(),
                              ),
                            ),
                          );
                        },
                      ),
                    if (RoleVisibility.isAdmin(RoleVisibility.rolesOf(user))) ...[
                      const Divider(height: 1),
                      ListTile(
                        key: const Key('btn-manage-cashboxes'),
                        leading: const Icon(Icons.savings_outlined,
                            color: Color(0xFF059669)),
                        title: Text(isVi ? 'Két tiền mặt & Quầy thu ngân' : 'Cash Safe & Counters'),
                        subtitle: Text(isVi
                            ? 'Tùy chỉnh két tiền quầy, số dư đầu ca và két sắt dự phòng'
                            : 'Customize counter cashboxes, opening balances & reserve safe'),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () {
                          Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => Scaffold(
                                appBar: AppBar(
                                  title: Text(isVi ? 'Quản Lý Két Tiền Mặt' : 'Cash Box Management'),
                                ),
                                body: RepositoryScope(
                                  repository: RepositoryScope.of(context),
                                  child: const CashScreen(),
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                      const Divider(height: 1),
                      ListTile(
                        key: const Key('btn-reset-store-data'),
                        leading: const Icon(Icons.cleaning_services_outlined,
                            color: Colors.red),
                        title: const Text(
                            'Khởi tạo lại hệ thống / Xóa sạch dữ liệu (Reset Data)'),
                        subtitle: const Text(
                            'Xóa dữ liệu cũ, làm sạch phiếu giao dịch và đưa về danh mục chuẩn quán thật'),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () => _showResetStoreDataDialog(context),
                      ),
                    ],
                  ],
                ),
              ),
              sectionGap,
            ],
            SectionHeader(
              title: isVi ? 'Ứng dụng' : 'Application',
              showCount: false,
            ),
            titleGap,
            const _AppDownloadCard(),
            sectionGap,
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: const StoreLogo(size: 28),
                    title: Text(
                      isVi ? 'Quản lý kho' : 'QuanLyKho Inventory',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    subtitle: Text(
                      isVi
                          ? 'Hệ thống quản lý bán hàng và kho hàng'
                          : 'Retail and warehouse management system',
                    ),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: const Icon(Icons.exit_to_app),
                    title: Text(isVi ? 'Đăng xuất' : 'Sign Out'),
                    onTap: () async {
                      await context.read<AuthService>().signOut();
                      if (context.mounted) {
                        Navigator.of(context)
                            .popUntil((route) => route.isFirst);
                      }
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 80),
          ],
        ),
      ),
    );
  }

  static List<String> _uniqueDisplayRoles(List<String> roles) {
    final result = <String>[];
    final seen = <String>{};
    for (final r in roles) {
      final label = _RoleBadge.roleLabel(r);
      if (seen.add(label)) {
        result.add(r);
      }
    }
    return result;
  }
}

class _RoleBadge extends StatelessWidget {
  const _RoleBadge({required this.role});

  final String role;

  static String roleLabel(String role) => switch (role.toUpperCase()) {
        'MAKER' => 'NHÂN VIÊN LẬP PHIẾU',
        'STAFF' => 'NHÂN VIÊN CỬA HÀNG',
        'CHECKER' || 'APPROVER' => 'NGƯỜI PHÊ DUYỆT / QUẢN LÝ',
        'AUDITOR' => 'KIỂM TOÁN VIÊN',
        'ADMIN' || 'MANAGER' => 'QUẢN TRỊ VIÊN / QUẢN LÝ',
        'INVENTORY_CUSTODIAN' => 'THỦ KHO NGUYÊN LIỆU',
        'CASH_SIMULATED_CUSTODIAN' => 'THỦ QUỸ CỬA HÀNG',
        _ => role.toUpperCase(),
      };

  @override
  Widget build(BuildContext context) {
    final lower = role.toLowerCase();
    final isChecker = lower.contains('checker') || lower.contains('approver');
    final isAuditor = lower.contains('auditor') || lower.contains('audit');
    final isMaker = lower.contains('maker') || lower.contains('staff');

    final color = isChecker
        ? const Color(0xFF7C3AED)
        : isAuditor
            ? const Color(0xFF059669)
            : isMaker
                ? const Color(0xFF2563EB)
                : const Color(0xFF475569);

    final label = roleLabel(role);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }
}

class _ProfileInfoItem extends StatelessWidget {
  const _ProfileInfoItem({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return SizedBox(
      width: 260,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(7),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF1E293B) : const Color(0xFFF1F5F9),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(icon, size: 16, color: const Color(0xFF0284C7)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 11.5,
                    color: isDark
                        ? const Color(0xFF94A3B8)
                        : const Color(0xFF64748B),
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  value,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ColorPresetCard extends StatelessWidget {
  const _ColorPresetCard({
    required this.preset,
    required this.name,
    required this.primaryColor,
    required this.secondaryColor,
    required this.isSelected,
    required this.onTap,
  });

  final AppColorPreset preset;
  final String name;
  final Color primaryColor;
  final Color secondaryColor;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected
              ? primaryColor.withValues(alpha: isDark ? 0.25 : 0.12)
              : (isDark ? const Color(0xFF1E293B) : Colors.white),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected
                ? primaryColor
                : (isDark ? const Color(0xFF334155) : const Color(0xFFCBD5E1)),
            width: isSelected ? 2 : 1,
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: primaryColor.withValues(alpha: 0.25),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  )
                ]
              : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 18,
              height: 18,
              decoration: BoxDecoration(
                gradient:
                    LinearGradient(colors: [primaryColor, secondaryColor]),
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 1.5),
              ),
            ),
            const SizedBox(width: 8),
            Flexible(
              child: Text(
                name,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                  color: isSelected
                      ? (isDark ? Colors.white : primaryColor)
                      : (isDark
                          ? const Color(0xFFE2E8F0)
                          : const Color(0xFF334155)),
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (isSelected) ...[
              const SizedBox(width: 6),
              Icon(Icons.check_circle_rounded, size: 16, color: primaryColor),
            ],
          ],
        ),
      ),
    );
  }
}

class _AppDownloadCard extends StatelessWidget {
  const _AppDownloadCard();

  static const String appUrl =
      'https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev';

  bool get _isIosDevice =>
      defaultTargetPlatform == TargetPlatform.iOS || isIosWeb();

  void _handleInstall(BuildContext context) {
    if (_isIosDevice) {
      AppToast.info(context,
          'Chạm biểu tượng Chia sẻ (⎋) dưới thanh Safari, chọn "Thêm vào MH chính"');
      return;
    }
    if (isPwaInstallSupported()) {
      promptPwaInstall();
    } else {
      AppToast.info(context,
          'Chạm menu 3 chấm (⋮) trình duyệt, chọn "Cài đặt ứng dụng"');
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final isMobile = MediaQuery.sizeOf(context).width < 600;

    final qrBlock = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFFE2E8F0), width: 1.2),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.04),
                blurRadius: 8,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          child: QrImageView(
            data: appUrl,
            version: QrVersions.auto,
            size: 110,
            backgroundColor: Colors.white,
            eyeStyle: const QrEyeStyle(
              eyeShape: QrEyeShape.square,
              color: Color(0xFF1E293B),
            ),
            dataModuleStyle: const QrDataModuleStyle(
              dataModuleShape: QrDataModuleShape.square,
              color: Color(0xFF1E293B),
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'Quét mã trên điện thoại',
          style: TextStyle(
            fontSize: 11.5,
            fontWeight: FontWeight.w600,
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );

    final actionBlock = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            const StoreLogo(size: 36),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Cài đặt ứng dụng',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.2,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Tự động đồng bộ phiên bản mới • Hoạt động ngoại tuyến',
                    style: TextStyle(
                      fontSize: 12,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          height: 42,
          child: ElevatedButton.icon(
            key: const Key('btn-install-pwa'),
            onPressed: () => _handleInstall(context),
            icon: Icon(
              _isIosDevice ? Icons.apple : Icons.download_rounded,
              size: 18,
            ),
            label: Text(
              _isIosDevice
                  ? 'Thêm vào màn hình chính (iPhone)'
                  : 'Cài đặt ứng dụng ngay',
              style: const TextStyle(
                fontWeight: FontWeight.w700,
                fontSize: 13.5,
              ),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF0284C7),
              foregroundColor: Colors.white,
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          ),
        ),
      ],
    );

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(
          color: isDark ? const Color(0xFF334155) : const Color(0xFFE2E8F0),
        ),
      ),
      child: Padding(
        padding: isMobile
            ? const EdgeInsets.all(12)
            : const EdgeInsets.all(AppSpacing.md),
        child: isMobile
            ? Column(
                children: [
                  actionBlock,
                  const SizedBox(height: 12),
                  const Divider(height: 1),
                  const SizedBox(height: 10),
                  qrBlock,
                ],
              )
            : Row(
                children: [
                  qrBlock,
                  const SizedBox(width: 18),
                  Expanded(child: actionBlock),
                ],
              ),
      ),
    );
  }
}

