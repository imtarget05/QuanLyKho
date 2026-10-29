import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../theme/app_tokens.dart';

/// Nhãn trạng thái kiểu Apple (badge): padding nhỏ, bo tròn, màu hệ thống nhạt.
class AppBadge extends StatelessWidget {
  const AppBadge({
    super.key,
    required this.label,
    this.tone = BadgeTone.neutral,
    this.icon,
    this.fontSize = 11,
  });

  final String label;
  final BadgeTone tone;
  final IconData? icon;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final sc = Theme.of(context).extension<AppStatusColors>()!;
    final toneColor = switch (tone) {
      BadgeTone.success => sc.success,
      BadgeTone.warning => sc.warning,
      BadgeTone.danger => sc.danger,
      BadgeTone.info => sc.info,
      BadgeTone.neutral => sc.info,
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: toneColor.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 12, color: toneColor),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            style: TextStyle(
              color: toneColor,
              fontSize: fontSize,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.1,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

enum BadgeTone { success, warning, danger, info, neutral }

extension BadgeToneRequest on BadgeTone {}
