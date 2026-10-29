import 'package:flutter/material.dart';

/// Màu hệ thống kiểu Apple (SF Symbols / Human Interface Guidelines).
/// Dùng làm hệ màu mặc định khi chưa chọn preset thương hiệu.
abstract class AppleColors {
  static const Color primary = Color(0xFF0A7BFF);      // System Blue
  static const Color primaryContainer = Color(0xFFE3F2FF);
  static const Color primaryOnContainer = Color(0xFF0057B8);

  static const Color success = Color(0xFF34C759);      // System Green
  static const Color successContainer = Color(0xFFE6F7EC);
  static const Color successOnContainer = Color(0xFF1D8B3A);

  static const Color danger = Color(0xFFFF3B30);       // System Red
  static const Color dangerContainer = Color(0xFFFCEDED);
  static const Color dangerOnContainer = Color(0xFFD70015);

  static const Color warning = Color(0xFFFF9500);      // System Orange
  static const Color warningContainer = Color(0xFFFFF3E0);
  static const Color warningOnContainer = Color(0xFFD67C00);

  static const Color info = Color(0xFF5AC8FA);         // System Light Blue
  static const Color infoContainer = Color(0xFFE6F7FF);
  static const Color infoOnContainer = Color(0xFF007AFF);

  /// Màu nền nhóm (system grouped background) — Apple dùng nền xám nhạt
  /// thay vì trắng tuyệt đối trên các vùng chính.
  static const Color systemGroupedBackground = Color(0xFFF2F2F7);
  static const Color systemGroupedBackgroundDark = Color(0xFF000000);

  static const Color secondaryLabel = Color(0xFF8E8E93); // System Gray 3
  static const Color tertiaryLabel = Color(0xFFC7C7CC);  // System Gray 4
  static const Color separator = Color(0xFFE5E5EA);      // System Gray 5 separator
  static const Color separatorDark = Color(0xFF1C1C1E);

  static const Color cardBackground = Color(0xFFFFFFFF);
  static const Color cardBackgroundDark = Color(0xFF1C1C1E);
}

extension AppleColorsX on BuildContext {
  Color get applePrimary => AppleColors.primary;
  Color get appleSuccess => AppleColors.success;
  Color get appleDanger => AppleColors.danger;
  Color get appleWarning => AppleColors.warning;
  Color get appleInfo => AppleColors.info;
}
