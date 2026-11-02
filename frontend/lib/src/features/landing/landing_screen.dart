import 'package:flutter/material.dart';

import '../../core/theme/app_tokens.dart';

class LandingScreen extends StatelessWidget {
  const LandingScreen({super.key, required this.onEnter, this.onDemo});

  final VoidCallback onEnter;

  /// When provided, tapping "Trải nghiệm demo" fires this callback instead
  /// of [onEnter]. Falls back to [onEnter] when null (backward-compatible).
  final VoidCallback? onDemo;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final isWide = width >= Breakpoints.wide;
    final isCompact = width < Breakpoints.medium;

    return Scaffold(
      backgroundColor: const Color(0xFFF8F9FA),
      body: SingleChildScrollView(
        child: Column(
          children: [
            _HeroSection(
                isWide: isWide,
                isCompact: isCompact,
                onEnter: onEnter,
                onDemo: onDemo),
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
    this.onDemo,
  });

  final bool isWide;
  final bool isCompact;
  final VoidCallback onEnter;
  final VoidCallback? onDemo;

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
          colors: [Color(0xFF1E1736), Color(0xFF2E2055), Color(0xFF4A3282)],
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
                          horizontal: 14, vertical: 6),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                            color: Colors.white.withValues(alpha: 0.2)),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.auto_graph_rounded,
                              color: Color(0xFFDDD6FE), size: 14),
                          SizedBox(width: 6),
                          Flexible(
                            child: Text(
                              'Optimate x NexUp • ERP Quản trị Doanh nghiệp',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: Color(0xFFEDE9FE),
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                letterSpacing: -.2,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      'Quản lý Bán hàng, Xuất nhập Tồn kho\n& Công nợ tự động',
                      textAlign: isWide ? TextAlign.left : TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 34,
                        fontWeight: FontWeight.w800,
                        height: 1.2,
                        letterSpacing: -.6,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      'Tự tính doanh thu, giá vốn, lợi nhuận từng đơn. In hóa đơn A4 đính kèm mã VietQR, lập phiếu mua hàng, kiểm kê đối chiếu tồn thực tế và tự động quản lý công nợ quá hạn.',
                      textAlign: isWide ? TextAlign.left : TextAlign.center,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.88),
                        fontSize: 15,
                        height: 1.55,
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
                            foregroundColor: const Color(0xFF4A3282),
                            padding: const EdgeInsets.symmetric(
                                horizontal: 24, vertical: 14),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10)),
                          ),
                          icon: const Icon(Icons.login_rounded, size: 18),
                          label: const Text(
                            'Đăng nhập',
                            style: TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 14),
                          ),
                        ),
                        OutlinedButton.icon(
                          key: const Key('landing-demo-btn'),
                          onPressed: onDemo ?? onEnter,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.white,
                            side: BorderSide(
                                color: Colors.white.withValues(alpha: 0.6)),
                            padding: const EdgeInsets.symmetric(
                                horizontal: 22, vertical: 14),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10)),
                          ),
                          icon: const Icon(Icons.play_circle_outline_rounded,
                              size: 18),
                          label: const Text(
                            'Trải nghiệm demo',
                            style: TextStyle(
                                fontWeight: FontWeight.w600, fontSize: 14),
                          ),
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
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withValues(alpha: 0.16)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 10,
                height: 10,
                decoration: const BoxDecoration(
                    color: Color(0xFFEF4444), shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
              Container(
                width: 10,
                height: 10,
                decoration: const BoxDecoration(
                    color: Color(0xFFF59E0B), shape: BoxShape.circle),
              ),
              const SizedBox(width: 6),
              Container(
                width: 10,
                height: 10,
                decoration: const BoxDecoration(
                    color: Color(0xFF10B981), shape: BoxShape.circle),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Text('ERP Dashboard',
                    style: TextStyle(
                        color: Colors.white70,
                        fontSize: 10,
                        fontWeight: FontWeight.w600)),
              ),
            ],
          ),
          const SizedBox(height: 18),
          _metricPill('Doanh thu thuần', '160.796.872 đ',
              const Color(0xFF10B981), Icons.trending_up_rounded),
          const SizedBox(height: 10),
          _metricPill('Lợi nhuận gộp', '63.067.520 đ',
              const Color(0xFF8B5CF6), Icons.account_balance_wallet_rounded),
          const SizedBox(height: 10),
          _metricPill('Giá trị tồn kho', '252.002.000 đ',
              const Color(0xFF3B82F6), Icons.inventory_2_rounded),
          const SizedBox(height: 10),
          _metricPill('Công nợ phải thu', '152.092.072 đ',
              const Color(0xFFF59E0B), Icons.call_received_rounded),
        ],
      ),
    );
  }

  Widget _metricPill(String title, String val, Color c, IconData icon) =>
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: c.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(icon, color: c, size: 16),
            ),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 11,
                        fontWeight: FontWeight.w500)),
                Text(val,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.w700)),
              ],
            ),
          ],
        ),
      );
}

class _FeaturesSection extends StatelessWidget {
  const _FeaturesSection({required this.isWide, required this.isCompact});

  final bool isWide;
  final bool isCompact;

  static const _features = <_Feature>[
    _Feature(
        Icons.dashboard_rounded,
        'Tổng quan vận hành',
        '8 thẻ KPI tài chính, doanh thu, lợi nhuận, biểu đồ xu hướng và cơ cấu giá trị tồn kho theo thời gian thực.'),
    _Feature(
        Icons.shopping_cart_rounded,
        'Quản lý Bán hàng & Báo giá',
        'Lập đơn bán, tạo báo giá, 1-click chuyển đổi thành đơn hàng và in hóa đơn A4 đính kèm mã QR VietQR thanh toán.'),
    _Feature(
        Icons.local_shipping_rounded,
        'Quản lý Mua hàng & NCC',
        'Theo dõi nhà cung cấp, lập phiếu mua hàng, tự tính VAT, chiết khấu, chi phí vận chuyển và in phiếu A4 có chữ ký 4 bên.'),
    _Feature(
        Icons.inventory_2_rounded,
        'Quản lý Kho & Danh mục',
        'Phân nhóm hàng hóa, theo dõi tồn hiện tại, định mức tồn tối thiểu, giá trị tồn và badge cảnh báo Hết hàng / Vượt tồn.'),
    _Feature(
        Icons.fact_check_rounded,
        'Kiểm kê kho tự động',
        'Lập phiếu kiểm kê, đối chiếu số liệu hệ thống vs thực tế, tự tính chênh lệch tăng/giảm và tự động bù trừ tồn kho.'),
    _Feature(
        Icons.account_balance_wallet_rounded,
        'Công nợ Phải thu & Phải trả',
        'Theo dõi chi tiết công nợ khách hàng và nhà cung cấp, tự động so khớp ngày đến hạn để đánh dấu nợ quá hạn.'),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
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
                'Năng lực cốt lõi hệ thống ERP',
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                  letterSpacing: -.5,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Tự động hóa toàn diện quy trình mua bán hàng, quản lý kho và dòng tiền công nợ.',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 32),
              LayoutBuilder(
                builder: (context, constraints) {
                  final cardWidth = isWide
                      ? (constraints.maxWidth - 32) / 3
                      : (isCompact
                          ? constraints.maxWidth
                          : (constraints.maxWidth - 16) / 2);
                  return Wrap(
                    spacing: 16,
                    runSpacing: 16,
                    children: _features
                        .map((f) => SizedBox(
                              width: cardWidth,
                              child: _FeatureCard(feature: f),
                            ))
                        .toList(),
                  );
                },
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
              color: const Color(0xFF6B4BC3).withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(AppRadius.md),
            ),
            child: Icon(feature.icon, color: const Color(0xFF6B4BC3), size: 22),
          ),
          const SizedBox(height: 14),
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
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 36),
      color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
      child: Center(
        child: Column(
          children: [
            Text(
              'Sẵn sàng nâng tầm quản trị doanh nghiệp?',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(
              key: const Key('landing-footer-enter-btn'),
              onPressed: onEnter,
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF6B4BC3),
                foregroundColor: Colors.white,
                padding:
                    const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8)),
              ),
              child: const Text('Vào ứng dụng',
                  style: TextStyle(fontWeight: FontWeight.w700)),
            ),
          ],
        ),
      ),
    );
  }
}

