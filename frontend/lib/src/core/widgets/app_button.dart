import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../theme/app_tokens.dart';

/// Enum kiểu nút bấm theo Apple HIG.
enum AppButtonKind {
  filled,    // Màu sól, hành động chính
  outlined,  // Viền, hành động phụ
  ghost,     // Không viền, hành động tối thiểu
  danger,    // Màu đỏ, hành động destructive
}

/// Nút bấm thống nhất kiểu Apple.
/// - Kích thước tối thiểu 44x44 (tiêu chuẩn chạm).
/// - Bo góc lớn (AppRadius.md), Übergang màu mượt.
/// - Không hardcode màu — lấy từ Theme / AppleColors.
class AppButton extends StatelessWidget {
  const AppButton({
    super.key,
    required this.child,
    this.onPressed,
    this.kind = AppButtonKind.filled,
    this.icon,
    this.fullWidth = false,
    this.enabled = true,
  });

  final Widget child;
  final VoidCallback? onPressed;
  final AppButtonKind kind;
  final IconData? icon;
  final bool fullWidth;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final sc = Theme.of(context).extension<AppStatusColors>()!;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final onTap = enabled ? onPressed : null;

    Widget content = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 18, color: _iconColor(context)),
          const SizedBox(width: AppSpacing.xs),
        ],
        child,
      ],
    );

    if (fullWidth) {
      content = SizedBox(
        width: double.infinity,
        child: Center(child: content),
      );
    }

    switch (kind) {
      case AppButtonKind.filled:
        return _FilledButton(
          onPressed: onTap,
          child: content,
          backgroundColor: _primaryColor(context),
          foregroundColor: Colors.white,
        );
      case AppButtonKind.outlined:
        return _OutlinedButton(
          onPressed: onTap,
          child: content,
          borderColor: _borderColor(context),
          textColor: _primaryColor(context),
        );
      case AppButtonKind.ghost:
        return _GhostButton(
          onPressed: onTap,
          child: content,
          textColor: _primaryColor(context),
          bgColor: isDark ? const Color(0xFF2C2C2E) : const Color(0xFFF2F2F7),
        );
      case AppButtonKind.danger:
        return _FilledButton(
          onPressed: onTap,
          child: content,
          backgroundColor: sc.danger,
          foregroundColor: Colors.white,
        );
    }
  }

  Color _primaryColor(BuildContext context) =>
      Theme.of(context).colorScheme.primary;

  Color _borderColor(BuildContext context) =>
      Theme.of(context).colorScheme.outlineVariant;

  Color _iconColor(BuildContext context) {
    switch (kind) {
      case AppButtonKind.filled:
      case AppButtonKind.danger:
        return Colors.white;
      case AppButtonKind.outlined:
      case AppButtonKind.ghost:
        return _primaryColor(context);
    }
  }
}

class _FilledButton extends StatelessWidget {
  const _FilledButton({
    required this.onPressed,
    required this.child,
    required this.backgroundColor,
    required this.foregroundColor,
  });
  final VoidCallback? onPressed;
  final Widget child;
  final Color backgroundColor;
  final Color foregroundColor;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 44,
      child: ElevatedButton(
        onPressed: onPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: backgroundColor,
          foregroundColor: foregroundColor,
          elevation: 0,
          shadowColor: Colors.transparent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.2,
          ),
        ),
        child: child,
      ),
    );
  }
}

class _OutlinedButton extends StatelessWidget {
  const _OutlinedButton({
    required this.onPressed,
    required this.child,
    required this.borderColor,
    required this.textColor,
  });
  final VoidCallback? onPressed;
  final Widget child;
  final Color borderColor;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 44,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          foregroundColor: textColor,
          side: BorderSide(color: borderColor, width: 1),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.2,
          ),
        ),
        child: child,
      ),
    );
  }
}

class _GhostButton extends StatelessWidget {
  const _GhostButton({
    required this.onPressed,
    required this.child,
    required this.textColor,
    required this.bgColor,
  });
  final VoidCallback? onPressed;
  final Widget child;
  final Color textColor;
  final Color bgColor;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 44,
      child: TextButton(
        onPressed: onPressed,
        style: TextButton.styleFrom(
          foregroundColor: textColor,
          backgroundColor: bgColor,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          textStyle: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.2,
          ),
        ),
        child: child,
      ),
    );
  }
}
