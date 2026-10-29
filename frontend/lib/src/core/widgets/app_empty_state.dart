import 'package:flutter/material.dart';

import 'app_button.dart';

/// Màn trạng thái trống kiểu Apple: icon lớn, tiêu đề rõ, mô tả ngắn, nút hành động tùy chọn.
class AppEmptyState extends StatelessWidget {
  const AppEmptyState({
    super.key,
    required this.title,
    this.subtitle,
    this.icon = Icons.inbox_outlined,
    this.iconColor,
    this.onPressed,
    this.actionLabel,
    this.maxWidth = 320.0,
  });

  final String title;
  final String? subtitle;
  final IconData icon;
  final Color? iconColor;
  final VoidCallback? onPressed;
  final String? actionLabel;
  final double maxWidth;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color = iconColor ?? scheme.onSurfaceVariant.withValues(alpha: 0.5);

    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, size: 48, color: color),
            ),
            const SizedBox(height: 20),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.3,
                color: Color(0xFF1C1C1E),
              ),
            ),
            if (subtitle != null && subtitle!.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                subtitle!,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 14,
                  color: scheme.onSurfaceVariant,
                  height: 1.5,
                ),
              ),
            ],
            if (onPressed != null || actionLabel != null) ...[
              const SizedBox(height: 24),
              AppButton(
                kind: AppButtonKind.outlined,
                onPressed: onPressed ?? () {},
                child: Text(actionLabel ?? 'See more'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
