import 'package:flutter/material.dart';

import '../theme/app_tokens.dart';

/// Thẻ kiểu Apple: nền trắng/xám, bo góc lớn, đổ bóng nhẹ, không viền mạnh.
class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.elevation = 1,
    this.borderColor,
    this.color,
    this.margin,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final int elevation;
  final Color? borderColor;
  final Color? color;
  final EdgeInsetsGeometry? margin;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardColor = color ?? (isDark ? const Color(0xFF1C1C1E) : Colors.white);
    final border = borderColor ??
        (isDark
            ? const Color(0xFF2C2C2E)
            : const Color(0xFFE5E5EA));

    return Container(
      margin: margin,
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(AppRadius.md + 2), // 14px, Apple-style
        border: Border.all(color: border),
        boxShadow: elevation > 0
            ? [
                BoxShadow(
                  color: Colors.black.withValues(alpha: isDark ? 0.25 : 0.06),
                  blurRadius: elevation.toDouble() * 8,
                  offset: const Offset(0, 2),
                ),
              ]
            : null,
      ),
      child: Padding(padding: padding, child: child),
    );
  }
}

/// Thẻ chứa danh sáchItem (ngang, có padding trái phải, dùng trong danh sách kho).
class AppListCard extends StatelessWidget {
  const AppListCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
    this.onTap,
    this.borderColor,
    this.color,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final Color? borderColor;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardColor = color ?? (isDark ? const Color(0xFF1C1C1E) : Colors.white);
    final border = borderColor ??
        (isDark
            ? const Color(0xFF2C2C2E)
            : const Color(0xFFE5E5EA));

    Widget content = Container(
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(AppRadius.md + 2),
        border: Border.all(color: border),
      ),
      child: Padding(padding: padding, child: child),
    );

    if (onTap != null) {
      content = Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppRadius.md + 2),
          child: content,
        ),
      );
    }

    return content;
  }
}
