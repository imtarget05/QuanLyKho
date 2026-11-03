import 'dart:async';
import 'package:flutter/material.dart';

/// Banner thông báo nổi bật khi tài khoản người dùng được nâng quyền lên Quản Trị Viên (Admin).
///
/// Hỗ trợ đếm ngược tự động 5 giây để làm mới phiên làm việc hoặc bấm [Làm mới ngay]
/// để kích hoạt ngay lập tức. Layout tự động co giãn thích ứng với màn hình mobile (<500px).
class AdminPromotionBanner extends StatefulWidget {
  const AdminPromotionBanner({
    super.key = const Key('admin-promotion-banner'),
    required this.onRefresh,
    this.onDismiss,
    this.pauseCountdown = false,
    this.initialSeconds = 5,
    this.headline,
  });

  /// Hàm gọi lại khi bấm "Làm mới ngay" hoặc khi đồng hồ đếm ngược về 0.
  final VoidCallback onRefresh;

  /// Hàm gọi lại khi bấm "Để sau" để đóng banner tạm thời.
  final VoidCallback? onDismiss;

  /// Tạm dừng bộ đếm ngược (khi đang mở modal/form nhập liệu dở dang).
  final bool pauseCountdown;

  /// Số giây đếm ngược ban đầu (mặc định 5s).
  final int initialSeconds;

  /// Tiêu đề banner (mặc định "Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)").
  final String? headline;

  @override
  State<AdminPromotionBanner> createState() => _AdminPromotionBannerState();
}

class _AdminPromotionBannerState extends State<AdminPromotionBanner> {
  late int _remainingSeconds;
  Timer? _countdownTimer;
  bool _hasTriggered = false;

  @override
  void initState() {
    super.initState();
    _remainingSeconds = widget.initialSeconds;
    if (!widget.pauseCountdown) {
      _startTimer();
    }
  }

  void _startTimer() {
    _countdownTimer?.cancel();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      if (widget.pauseCountdown) {
        return;
      }
      if (_remainingSeconds <= 1) {
        if (_hasTriggered) return;
        _hasTriggered = true;
        timer.cancel();
        _countdownTimer = null;
        setState(() {
          _remainingSeconds = 0;
        });
        widget.onRefresh();
      } else {
        setState(() {
          _remainingSeconds--;
        });
      }
    });
  }

  @override
  void didUpdateWidget(covariant AdminPromotionBanner oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.pauseCountdown != widget.pauseCountdown) {
      if (widget.pauseCountdown) {
        _countdownTimer?.cancel();
        _countdownTimer = null;
      } else if (_remainingSeconds > 0 && _countdownTimer == null) {
        _startTimer();
      }
    }
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    _countdownTimer = null;
    super.dispose();
  }

  void _handleRefresh() {
    if (_hasTriggered) return;
    _hasTriggered = true;
    _countdownTimer?.cancel();
    _countdownTimer = null;
    widget.onRefresh();
  }

  void _handleDismiss() {
    if (_hasTriggered) return;
    _hasTriggered = true;
    _countdownTimer?.cancel();
    _countdownTimer = null;
    if (widget.onDismiss != null) {
      widget.onDismiss!();
    }
  }

  @override
  Widget build(BuildContext context) {
    final headlineText = widget.headline ??
        'Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)';
    final subtitleText =
        'Tài khoản vừa được cấp quyền Quản Trị Viên. Tự động làm mới trong $_remainingSeconds giây...';

    final dismissButton = TextButton(
      key: const ValueKey('btn-admin-promoted-dismiss'),
      onPressed: _handleDismiss,
      style: TextButton.styleFrom(
        foregroundColor: const Color(0xFFE0E7FF),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
      ),
      child: const Text('Để sau'),
    );

    final refreshButton = FilledButton.icon(
      key: const ValueKey('btn-admin-promoted-refresh'),
      onPressed: _handleRefresh,
      icon: const Icon(Icons.refresh_rounded, size: 16),
      label: const Text('Làm mới ngay'),
      style: FilledButton.styleFrom(
        backgroundColor: const Color(0xFFFBBF24),
        foregroundColor: const Color(0xFF1E1B4B),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        textStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
      ),
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        final screenWidth = MediaQuery.sizeOf(context).width;
        final isCompact = constraints.maxWidth < 500 || screenWidth < 500;

        return Container(
          margin: EdgeInsets.symmetric(
            horizontal: isCompact ? 12 : 16,
            vertical: 8,
          ),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF312E81), Color(0xFF4338CA)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: const Color(0xFF6366F1), width: 1),
            boxShadow: const [
              BoxShadow(
                color: Color(0x331E1B4B),
                blurRadius: 8,
                offset: Offset(0, 2),
              ),
            ],
          ),
          child: isCompact
              ? Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Padding(
                          padding: EdgeInsets.only(top: 2),
                          child: Icon(
                            Icons.shield_rounded,
                            color: Color(0xFFFBBF24),
                            size: 24,
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                headlineText,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 13,
                                  fontWeight: FontWeight.w700,
                                  height: 1.3,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                subtitleText,
                                style: const TextStyle(
                                  color: Color(0xFFE0E7FF),
                                  fontSize: 12,
                                  height: 1.3,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Align(
                      alignment: Alignment.centerRight,
                      child: Wrap(
                        alignment: WrapAlignment.end,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          if (widget.onDismiss != null) dismissButton,
                          refreshButton,
                        ],
                      ),
                    ),
                  ],
                )
              : Row(
                  children: [
                    const Icon(
                      Icons.shield_rounded,
                      color: Color(0xFFFBBF24),
                      size: 28,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            headlineText,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            subtitleText,
                            style: const TextStyle(
                              color: Color(0xFFE0E7FF),
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    if (widget.onDismiss != null) ...[
                      dismissButton,
                      const SizedBox(width: 8),
                    ],
                    refreshButton,
                  ],
                ),
        );
      },
    );
  }
}
