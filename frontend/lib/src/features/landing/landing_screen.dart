import 'package:flutter/material.dart';

import '../../core/theme/app_tokens.dart';

class LandingScreen extends StatelessWidget {
  const LandingScreen({super.key, required this.onEnter});

  final VoidCallback onEnter;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final isWide = width >= Breakpoints.wide;
    final isCompact = width < Breakpoints.medium;

    return Scaffold(
      body: SingleChildScrollView(
        child: Column(
          children: [
            _HeroSection(isWide: isWide, isCompact: isCompact, onEnter: onEnter),
            _FeaturesSection(isWide: isWide, isCompact: isCompact),
            _FooterSection(onEnter: onEnter),
          ],
        ),
      ),
    );
  }
}

class _HeroSection extends StatelessWidget {
  const _HeroSection({
    required this.isWide,
    required this.isCompact,
    required this.onEnter,
  });

  final bool isWide;
  final bool isCompact;
  final VoidCallback onEnter;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(
        horizontal: isCompact ? 20 : 48,
        vertical: isCompact ? 48 : 72,
      ),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0F4C3A), Color(0xFF064E3B)],
        ),
      ),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1100),
          child: Flex(
            direction: isWide ? Axis.horizontal : Axis.vertical,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                flex: isWide ? 6 : 0,
                child: Column(
                  crossAxisAlignment: isWide
                      ? CrossAxisAlignment.start
                      : CrossAxisAlignment.center,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: const Text(
                        'QuanLyKho • Kho trà sữa',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      'Quản lý kho & ca làm việc\\ncho quán trà sữa',
                      textAlign: isWide ? TextAlign.left : TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 36,
                        fontWeight: FontWeight.w800,
                        height: 1.15,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Theo dõi tồn kho theo lô, ca làm việc, yêu cầu nhập/xuất, '
                      'duyệt phiếu và báo cáo — trên một giao diện nhất quán, '
                      'phù hợp desktop, tablet và điện thoại.',
                      textAlign: isWide ? TextAlign.left : TextAlign.center,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.85),
                        fontSize: 16,
                        height: 1.5,
                      ),
                    ),
                    const SizedBox(height: 28),
                    Wrap(
                      alignment: isWide
                          ? WrapAlignment.start
                          : WrapAlignment.center,
                      spacing: 12,
                      runSpacing: 12,
                      children: [
                        FilledButton.icon(
                          key: const Key('landing-enter-btn'),
                          onPressed: onEnter,
                          style: FilledButton.styleFrom(
                            backgroundColor: Colors.white,
                            foregroundColor: const Color(0xFF0F4C3A),
                            padding: const EdgeInsets.symmetric(
                                horizontal: 24, vertical: 14),
                          ),
                          icon: const Icon(Icons.login_rounded),
                          label: const Text(
                            'Đăng nhập',
                            style: TextStyle(fontWeight: FontWeight.w700),
                          ),
                        ),
                        OutlinedButton.icon(
                          onPressed: onEnter,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.white,
                            side: const BorderSide(color: Colors.white70),
                            padding: const EdgeInsets.symmetric(
                                horizontal: 24, vertical: 14),
                          ),
                          icon: const Icon(Icons.play_circle_outline_rounded),
                          label: const Text('Trải nghiệm demo'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              if (isWide) const SizedBox(width: 48),
              if (isWide) Expanded(flex: 4, child: _HeroIllustration()),
            ],
          ),
        ),
      ),
    );
  }
}


class _HeroIllustration extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      height: 320,
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.15)),
      ),
      child: const Center(
        child: Icon(
          Icons.inventory_2_rounded,
          size: 120,
          color: Colors.white54,
        ),
      ),
    );
  }
}

class _FeaturesSection extends StatelessWidget {
  const _FeaturesSection({required this.isWide, required this.isCompact});

  final bool isWide;
  final bool isCompact;

  static const _features = <_Feature>[
    _Feature(Icons.dashboard_rounded, 'Tổng quan',
        'KPI tồn kho, cảnh báo và hoạt động gần đây.'),
    _Feature(Icons.warehouse_rounded, 'Kho & danh mục',
        'Sản phẩm, đơn vị tính, kho/địa điểm, mức tồn min/max.'),
    _Feature(Icons.swap_horiz_rounded, 'Nhập / xuất',
        'Phiếu nhập, xuất, điều chỉnh có kiểm soát.'),
    _Feature(Icons.fact_check_rounded, 'Kiểm kê & duyệt',
        'Phiên kiểm kê, chênh lệch, maker ≠ checker.'),
    _Feature(Icons.receipt_long_rounded, 'Sổ biến động',
        'Tra cứu movement theo mặt hàng, kho, chứng từ.'),
    _Feature(Icons.bar_chart_rounded, 'Báo cáo & đối soát',
        'Nhập-xuất-tồn, giá vốn bình quân gia quyền.'),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cols = isWide ? 3 : (isCompact ? 1 : 2);
    return Container(
      width: double.infinity,
      color: theme.colorScheme.surface,
      padding: EdgeInsets.symmetric(
        horizontal: isCompact ? 20 : 48,
        vertical: isCompact ? 40 : 64,
      ),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1100),
          child: Column(
            children: [
              Text(
                'Năng lực cốt lõi',
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Tập trung vận hành kho trà sữa và ca làm việc — không tuyên bố '
                'module chưa được hỗ trợ.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 32),
              Wrap(
                spacing: 16,
                runSpacing: 16,
                children: _features
                    .map((f) => SizedBox(
                          width: (1100 - 16 * (cols - 1)) / cols,
                          child: _FeatureCard(feature: f),
                        ))
                    .toList(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Feature {
  const _Feature(this.icon, this.title, this.body);
  final IconData icon;
  final String title;
  final String body;
}

class _FeatureCard extends StatelessWidget {
  const _FeatureCard({required this.feature});
  final _Feature feature;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLowest,
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFF0F4C3A).withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(AppRadius.md),
            ),
            child: Icon(feature.icon, color: const Color(0xFF0F4C3A)),
          ),
          const SizedBox(height: 12),
          Text(
            feature.title,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            feature.body,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }
}

class _FooterSection extends StatelessWidget {
  const _FooterSection({required this.onEnter});
  final VoidCallback onEnter;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
      color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
      child: Center(
        child: Column(
          children: [
            Text(
              'Sẵn sàng bắt đầu?',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(
              key: const Key('landing-footer-enter-btn'),
              onPressed: onEnter,
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF0F4C3A),
                foregroundColor: Colors.white,
              ),
              child: const Text('Vào ứng dụng'),
            ),
          ],
        ),
      ),
    );
  }
}

