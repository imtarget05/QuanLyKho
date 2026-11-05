import 'package:flutter/material.dart';

import '../../core/theme/app_tokens.dart';
import '../../core/widgets/animated_count_up.dart';

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
              onDemo: onDemo,
            ),
            _TrustMetricsStrip(isCompact: isCompact),
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
        vertical: isCompact ? 40 : 64,
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
          constraints: const BoxConstraints(maxWidth: 1150),
          child: isWide
              ? Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Expanded(
                      flex: 6,
                      child: _HeroCopy(
                        isWide: true,
                        onEnter: onEnter,
                        onDemo: onDemo,
                      ),
                    ),
                    const SizedBox(width: 44),
                    const Expanded(
                      flex: 5,
                      child: _HeroIllustration(),
                    ),
                  ],
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    _HeroCopy(
                      isWide: false,
                      onEnter: onEnter,
                      onDemo: onDemo,
                    ),
                    const SizedBox(height: 32),
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 520),
                      child: const _HeroIllustration(),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}

class _HeroCopy extends StatelessWidget {
  const _HeroCopy({
    required this.isWide,
    required this.onEnter,
    this.onDemo,
  });

  final bool isWide;
  final VoidCallback onEnter;
  final VoidCallback? onDemo;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment:
          isWide ? CrossAxisAlignment.start : CrossAxisAlignment.center,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: Colors.white.withValues(alpha: 0.2)),
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
          alignment: isWide ? WrapAlignment.start : WrapAlignment.center,
          spacing: 12,
          runSpacing: 12,
          children: [
            FilledButton.icon(
              key: const Key('landing-enter-btn'),
              onPressed: onEnter,
              style: FilledButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: const Color(0xFF4A3282),
                padding:
                    const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
              ),
              icon: const Icon(Icons.login_rounded, size: 18),
              label: const Text(
                'Đăng nhập',
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
              ),
            ),
            OutlinedButton.icon(
              key: const Key('landing-demo-btn'),
              onPressed: onDemo ?? onEnter,
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.white,
                side: BorderSide(color: Colors.white.withValues(alpha: 0.6)),
                padding:
                    const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
              ),
              icon: const Icon(Icons.play_circle_outline_rounded, size: 18),
              label: const Text(
                'Trải nghiệm demo',
                style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _HeroIllustration extends StatefulWidget {
  const _HeroIllustration();

  @override
  State<_HeroIllustration> createState() => _HeroIllustrationState();
}

class _HeroIllustrationState extends State<_HeroIllustration> {
  int _selectedTab = 0;

  static const _tabs = ['Tổng quan', 'Bán hàng', 'Mua hàng', 'Công nợ'];

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white.withValues(alpha: 0.18)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.25),
            blurRadius: 28,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Top window bar with status
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
                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF10B981).withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                      color: const Color(0xFF10B981).withValues(alpha: 0.4)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.circle, color: Color(0xFF34D399), size: 7),
                    SizedBox(width: 5),
                    Text(
                      'Số liệu minh họa',
                      style: TextStyle(
                        color: Color(0xFF86EFAC),
                        fontSize: 10.5,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // Interactive preview tabs
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: List.generate(_tabs.length, (i) {
                final isSelected = _selectedTab == i;
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: InkWell(
                    onTap: () => setState(() => _selectedTab = i),
                    borderRadius: BorderRadius.circular(14),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? const Color(0xFF6B4BC3)
                            : Colors.white.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                          color: isSelected
                              ? const Color(0xFFA78BFA)
                              : Colors.white.withValues(alpha: 0.12),
                        ),
                      ),
                      child: Text(
                        _tabs[i],
                        style: TextStyle(
                          color: isSelected
                              ? Colors.white
                              : Colors.white.withValues(alpha: 0.75),
                          fontSize: 11.5,
                          fontWeight:
                              isSelected ? FontWeight.w700 : FontWeight.w500,
                        ),
                      ),
                    ),
                  ),
                );
              }),
            ),
          ),
          const SizedBox(height: 16),

          // Metric cards based on selected tab
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            child: Column(
              key: ValueKey<int>(_selectedTab),
              children: _buildMetricsForTab(_selectedTab),
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _buildMetricsForTab(int tabIndex) {
    switch (tabIndex) {
      case 1: // Bán hàng
        return [
          _metricPill(
            title: 'Doanh số bán hàng',
            value: 160796872,
            isCurrency: true,
            color: const Color(0xFF10B981),
            icon: Icons.trending_up_rounded,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Đơn hàng hoàn tất',
            value: 42,
            suffix: 'đơn',
            color: const Color(0xFF8B5CF6),
            icon: Icons.receipt_long_rounded,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Tỷ lệ thanh toán QR',
            value: 88.5,
            suffix: '%',
            decimalDigits: 1,
            color: const Color(0xFF38BDF8),
            icon: Icons.qr_code_2_rounded,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Giá trị TB / đơn',
            value: 3828500,
            isCurrency: true,
            color: const Color(0xFFF59E0B),
            icon: Icons.analytics_outlined,
          ),
        ];
      case 2: // Mua hàng
        return [
          _metricPill(
            title: 'Tổng tiền mua hàng',
            value: 305125480,
            isCurrency: true,
            color: const Color(0xFF38BDF8),
            icon: Icons.local_shipping_outlined,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Phiếu nhập kho',
            value: 19,
            suffix: 'phiếu',
            color: const Color(0xFF10B981),
            icon: Icons.assignment_outlined,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Công nợ phải trả NCC',
            value: 208388460,
            isCurrency: true,
            color: const Color(0xFFF87171),
            icon: Icons.call_made_rounded,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Nhà cung cấp đối tác',
            value: 8,
            suffix: 'NCC',
            color: const Color(0xFFA78BFA),
            icon: Icons.storefront_outlined,
          ),
        ];
      case 3: // Công nợ
        return [
          _metricPill(
            title: 'Công nợ phải thu KH',
            value: 152092072,
            isCurrency: true,
            color: const Color(0xFFF59E0B),
            icon: Icons.call_received_rounded,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Công nợ phải trả NCC',
            value: 208388460,
            isCurrency: true,
            color: const Color(0xFFF87171),
            icon: Icons.call_made_rounded,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Nợ trong hạn an toàn',
            value: 94.2,
            suffix: '%',
            decimalDigits: 1,
            color: const Color(0xFF10B981),
            icon: Icons.verified_user_outlined,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Số đối tác đang nợ',
            value: 12,
            suffix: 'đối tác',
            color: const Color(0xFF38BDF8),
            icon: Icons.groups_rounded,
          ),
        ];
      default: // 0: Tổng quan
        return [
          _metricPill(
            title: 'Doanh thu thuần',
            value: 160796872,
            isCurrency: true,
            color: const Color(0xFF10B981),
            icon: Icons.trending_up_rounded,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Lợi nhuận gộp',
            value: 63067520,
            isCurrency: true,
            color: const Color(0xFF8B5CF6),
            icon: Icons.account_balance_wallet_rounded,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Giá trị tồn kho',
            value: 252002000,
            isCurrency: true,
            color: const Color(0xFF38BDF8),
            icon: Icons.inventory_2_rounded,
          ),
          const SizedBox(height: 10),
          _metricPill(
            title: 'Công nợ phải thu',
            value: 152092072,
            isCurrency: true,
            color: const Color(0xFFF59E0B),
            icon: Icons.call_received_rounded,
          ),
        ];
    }
  }

  Widget _metricPill({
    required String title,
    required num value,
    required Color color,
    required IconData icon,
    bool isCurrency = false,
    String suffix = '',
    int decimalDigits = 0,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(7),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.22),
              borderRadius: BorderRadius.circular(9),
            ),
            child: Icon(icon, color: color, size: 16),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                AnimatedCountUp(
                  value: value,
                  isCurrency: isCurrency,
                  suffix: suffix,
                  decimalDigits: decimalDigits,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TrustMetricsStrip extends StatelessWidget {
  const _TrustMetricsStrip({required this.isCompact});
  final bool isCompact;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(
        color: Color(0xFF130E24),
        border: Border(
          top: BorderSide(color: Color(0x33A78BFA)),
          bottom: BorderSide(color: Color(0x22A78BFA)),
        ),
      ),
      padding: EdgeInsets.symmetric(
        horizontal: isCompact ? 16 : 48,
        vertical: isCompact ? 22 : 28,
      ),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1150),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Các chỉ số sau là ví dụ mô phỏng, chưa phải kết quả vận hành được đo.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Color(0xFFDDD6FE), fontSize: 12),
              ),
              const SizedBox(height: 16),
              LayoutBuilder(
                builder: (context, constraints) {
                  final isSmall = constraints.maxWidth < 620;
                  return Wrap(
                    alignment: WrapAlignment.spaceAround,
                    runAlignment: WrapAlignment.center,
                    spacing: 20,
                    runSpacing: 18,
                    children: [
                      _metricTile(
                        value: 99.8,
                        suffix: '%',
                        decimalDigits: 1,
                        title: 'Khớp kiểm kê kho',
                        desc: 'Đối soát số liệu thực tế',
                        color: const Color(0xFF34D399),
                        isSmall: isSmall,
                      ),
                      _metricTile(
                        value: 3,
                        prefix: '< ',
                        suffix: 'giây',
                        title: 'Tốc độ xuất phiếu',
                        desc: 'Hóa đơn A4 & mã VietQR',
                        color: const Color(0xFF60A5FA),
                        isSmall: isSmall,
                      ),
                      _metricTile(
                        value: 100,
                        suffix: '%',
                        title: 'Bù trừ tự động',
                        desc: 'Dòng tiền & công nợ',
                        color: const Color(0xFFA78BFA),
                        isSmall: isSmall,
                      ),
                      _metricTile(
                        value: 0,
                        suffix: 'đ',
                        title: 'Chi phí phát sinh',
                        desc: 'Sở hữu dữ liệu trọn đời',
                        color: const Color(0xFFFBBF24),
                        isSmall: isSmall,
                      ),
                    ],
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _metricTile({
    required num value,
    required String title,
    required String desc,
    required Color color,
    required bool isSmall,
    String prefix = '',
    String suffix = '',
    int decimalDigits = 0,
  }) {
    return SizedBox(
      width: isSmall ? 140 : 210,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          AnimatedCountUp(
            value: value,
            prefix: prefix,
            suffix: suffix,
            decimalDigits: decimalDigits,
            style: TextStyle(
              color: color,
              fontSize: isSmall ? 22 : 28,
              fontWeight: FontWeight.w900,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            title,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 13,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            desc,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.65),
              fontSize: 11,
              fontWeight: FontWeight.w400,
            ),
          ),
        ],
      ),
    );
  }
}

class _FeaturesSection extends StatelessWidget {
  const _FeaturesSection({required this.isWide, required this.isCompact});

  final bool isWide;
  final bool isCompact;

  static const _features = <_Feature>[
    _Feature(Icons.dashboard_rounded, 'Tổng quan vận hành',
        '8 thẻ KPI tài chính, doanh thu, lợi nhuận, biểu đồ xu hướng và cơ cấu giá trị tồn kho theo thời gian thực.'),
    _Feature(Icons.shopping_cart_rounded, 'Quản lý Bán hàng & Báo giá',
        'Lập đơn bán, tạo báo giá, 1-click chuyển đổi thành đơn hàng và in hóa đơn A4 đính kèm mã QR VietQR thanh toán.'),
    _Feature(Icons.local_shipping_rounded, 'Quản lý Mua hàng & NCC',
        'Theo dõi nhà cung cấp, lập phiếu mua hàng, tự tính VAT, chiết khấu, chi phí vận chuyển và in phiếu A4 có chữ ký 4 bên.'),
    _Feature(Icons.inventory_2_rounded, 'Quản lý Kho & Danh mục',
        'Phân nhóm hàng hóa, theo dõi tồn hiện tại, định mức tồn tối thiểu, giá trị tồn và badge cảnh báo Hết hàng / Vượt tồn.'),
    _Feature(Icons.fact_check_rounded, 'Kiểm kê kho tự động',
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
