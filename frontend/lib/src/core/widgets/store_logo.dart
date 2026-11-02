import 'package:flutter/material.dart';

/// Logo thương hiệu "Quản Lý Bán Hàng & Kho" chuẩn vector sắc nét trên mọi thiết bị.
class StoreLogo extends StatelessWidget {
  const StoreLogo({super.key, this.size = 36, this.rounded = true});

  final double size;
  final bool rounded;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF6B4BC3), Color(0xFF0284C7)],
        ),
        borderRadius: BorderRadius.circular(rounded ? size * 0.24 : 0),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF6B4BC3).withValues(alpha: 0.3),
            blurRadius: size * 0.2,
            offset: Offset(0, size * 0.08),
          ),
        ],
      ),
      child: Center(
        child: SizedBox(
          width: size * 0.68,
          height: size * 0.68,
          child: const CustomPaint(painter: _StoreLogoPainter()),
        ),
      ),
    );
  }
}

class _StoreLogoPainter extends CustomPainter {
  const _StoreLogoPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final cx = w / 2;
    final cy = h / 2;

    // Top diamond (white roof/lid)
    final topPath = Path()
      ..moveTo(cx, cy - h * 0.42)
      ..lineTo(cx + w * 0.46, cy - h * 0.18)
      ..lineTo(cx, cy + h * 0.06)
      ..lineTo(cx - w * 0.46, cy - h * 0.18)
      ..close();
    canvas.drawPath(topPath, Paint()..color = Colors.white);

    // Left face
    final leftPath = Path()
      ..moveTo(cx - w * 0.46, cy - h * 0.18)
      ..lineTo(cx, cy + h * 0.06)
      ..lineTo(cx, cy + h * 0.48)
      ..lineTo(cx - w * 0.46, cy + h * 0.24)
      ..close();
    canvas.drawPath(
        leftPath, Paint()..color = const Color(0xFFE2E8F0));

    // Right face
    final rightPath = Path()
      ..moveTo(cx, cy + h * 0.06)
      ..lineTo(cx + w * 0.46, cy - h * 0.18)
      ..lineTo(cx + w * 0.46, cy + h * 0.24)
      ..lineTo(cx, cy + h * 0.48)
      ..close();
    canvas.drawPath(
        rightPath, Paint()..color = const Color(0xFFCBD5E1));

    // Accent stripe (purple-indigo highlight)
    final stripeTop = Path()
      ..moveTo(cx - w * 0.1, cy - h * 0.24)
      ..lineTo(cx, cy - h * 0.18)
      ..lineTo(cx + w * 0.1, cy - h * 0.24)
      ..lineTo(cx, cy - h * 0.3)
      ..close();
    canvas.drawPath(stripeTop, Paint()..color = const Color(0xFF8B5CF6));

    final stripeFront = Path()
      ..moveTo(cx - w * 0.09, cy + h * 0.01)
      ..lineTo(cx, cy + h * 0.06)
      ..lineTo(cx, cy + h * 0.48)
      ..lineTo(cx - w * 0.09, cy + h * 0.43)
      ..close();
    canvas.drawPath(stripeFront, Paint()..color = const Color(0xFF8B5CF6));

    final stripeRight = Path()
      ..moveTo(cx, cy + h * 0.06)
      ..lineTo(cx + w * 0.09, cy + h * 0.01)
      ..lineTo(cx + w * 0.09, cy + h * 0.43)
      ..lineTo(cx, cy + h * 0.48)
      ..close();
    canvas.drawPath(stripeRight, Paint()..color = const Color(0xFF6B4BC3));

    // Crisp checkmark in center top
    final checkPaint = Paint()
      ..color = const Color(0xFF4C1D95)
      ..strokeWidth = w * 0.09
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    final checkPath = Path()
      ..moveTo(cx - w * 0.12, cy - h * 0.06)
      ..lineTo(cx - w * 0.02, cy + h * 0.02)
      ..lineTo(cx + w * 0.15, cy - h * 0.12);
    canvas.drawPath(checkPath, checkPaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
