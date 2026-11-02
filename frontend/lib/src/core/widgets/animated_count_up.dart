import 'package:flutter/material.dart';

/// Animated counter widget that smoothly interpolates numbers from 0 to target value.
/// Supports Vietnamese Dong format (160.796.872 đ), counts, percentages, and decimals.
class AnimatedCountUp extends StatelessWidget {
  const AnimatedCountUp({
    super.key,
    required this.value,
    this.prefix = '',
    this.suffix = '',
    this.isCurrency = false,
    this.decimalDigits = 0,
    this.duration = const Duration(milliseconds: 1100),
    this.curve = Curves.easeOutCubic,
    this.style,
  });

  final num value;
  final String prefix;
  final String suffix;
  final bool isCurrency;
  final int decimalDigits;
  final Duration duration;
  final Curve curve;
  final TextStyle? style;

  static String formatNumber(
    double val, {
    bool isCurrency = false,
    int decimalDigits = 0,
    String prefix = '',
    String suffix = '',
  }) {
    String formatted;
    if (decimalDigits > 0) {
      formatted = val.toStringAsFixed(decimalDigits);
      final parts = formatted.split('.');
      final intPart = _formatThousands(int.tryParse(parts[0]) ?? 0);
      formatted = '$intPart,${parts[1]}';
    } else {
      formatted = _formatThousands(val.round());
    }

    final buf = StringBuffer();
    if (prefix.isNotEmpty) buf.write(prefix);
    buf.write(formatted);
    if (isCurrency) {
      buf.write(' đ');
    }
    if (suffix.isNotEmpty) {
      if (!suffix.startsWith(' ') && !suffix.startsWith('%') && !isCurrency) {
        buf.write(' ');
      }
      buf.write(suffix);
    }
    return buf.toString();
  }

  static String _formatThousands(int n) {
    final s = n.abs().toString();
    final buf = StringBuffer();
    for (int i = 0; i < s.length; i++) {
      if (i > 0 && (s.length - i) % 3 == 0) buf.write('.');
      buf.write(s[i]);
    }
    return n < 0 ? '-${buf.toString()}' : buf.toString();
  }

  @override
  Widget build(BuildContext context) {
    final target = value.toDouble();
    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: 0, end: target),
      duration: duration,
      curve: curve,
      builder: (context, currentVal, child) {
        return Text(
          formatNumber(
            currentVal,
            isCurrency: isCurrency,
            decimalDigits: decimalDigits,
            prefix: prefix,
            suffix: suffix,
          ),
          style: style,
        );
      },
    );
  }
}
