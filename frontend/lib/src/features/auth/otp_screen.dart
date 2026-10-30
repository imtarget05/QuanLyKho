import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

/// Màn hình nhập mã OTP 6 số kiểu ngân hàng: êm ái, rõ ràng, dễ dùng.
class OTPVerificationScreen extends StatefulWidget {
  final String username;
  final String purpose;
  final String email;
  final int resendCooldownSeconds;

  const OTPVerificationScreen({
    super.key,
    required this.username,
    this.purpose = 'password_reset',
    required this.email,
    this.resendCooldownSeconds = 60,
  });

  @override
  State<OTPVerificationScreen> createState() => _OTPVerificationScreenState();
}

class _OTPVerificationScreenState extends State<OTPVerificationScreen>
    with TickerProviderStateMixin {
  final List<TextEditingController> _controllers =
      List.generate(6, (_) => TextEditingController());
  final List<FocusNode> _focusNodes = List.generate(6, (_) => FocusNode());
  late final AnimationController _shakeController;
  late final Animation<double> _shakeAnimation;

  bool _isVerifying = false;
  int _resendSecondsLeft = 0;
  String? _error;
  String? _successMessage;
  Timer? _countdownTimer;

  String get otpCode => _controllers.map((c) => c.text).join();

  @override
  void initState() {
    super.initState();
    _shakeController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _shakeAnimation = Tween<double>(begin: 0, end: 10).animate(
      CurvedAnimation(parent: _shakeController, curve: Curves.elasticIn),
    );
    _startCountdown();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _focusNodes[0].requestFocus();
    });
  }

  void _startCountdown() {
    setState(() => _resendSecondsLeft = widget.resendCooldownSeconds);
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      setState(() {
        _resendSecondsLeft--;
        if (_resendSecondsLeft <= 0) timer.cancel();
      });
    });
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    _shakeController.dispose();
    for (final c in _controllers) { c.dispose(); }
    for (final f in _focusNodes) { f.dispose(); }
    super.dispose();
  }

  void _shake() {
    _shakeController.forward().then((_) => _shakeController.reverse());
  }

  Future<void> _verifyOTP() async {
    if (otpCode.length != 6) {
      setState(() => _error = 'Vui lòng nhập đầy đủ 6 chữ số.');
      _shake();
      return;
    }

    setState(() {
      _isVerifying = true;
      _error = null;
      _successMessage = null;
    });

    try {
      final response = await http.post(
        Uri.parse('http://localhost:8000/api/v1/auth/otp/verify'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'username': widget.username,
          'code': otpCode,
          'purpose': widget.purpose,
        }),
      ).timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        setState(() {
          _successMessage = 'Xác thực thành công.';
          _isVerifying = false;
        });
        await Future.delayed(const Duration(seconds: 1));
        if (mounted) Navigator.pop(context, true);
      } else {
        final errorData = jsonDecode(response.body);
        setState(() {
          _error = errorData['detail'] ?? 'Mã OTP không chính xác.';
          _isVerifying = false;
        });
        _shake();
        _clearAll();
      }
    } catch (e) {
      setState(() {
        _error = 'Không thể kết nối máy chủ. Vui lòng thử lại.';
        _isVerifying = false;
      });
      _shake();
    }
  }

  void _clearAll() {
    for (final c in _controllers) { c.clear(); }
    if (mounted) _focusNodes[0].requestFocus();
  }

  Future<void> _resendOTP() async {
    if (_resendSecondsLeft > 0) return;

    setState(() {
      _isVerifying = true;
      _error = null;
      _successMessage = null;
    });

    try {
      final response = await http.post(
        Uri.parse('http://localhost:8000/api/v1/auth/otp/send'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'username': widget.username,
          'purpose': widget.purpose,
          'channel': 'email',
        }),
      ).timeout(const Duration(seconds: 15));

      if (response.statusCode == 200 || response.statusCode == 201) {
        _startCountdown();
        setState(() {
          _successMessage = 'Đã gửi mã OTP mới về email ${widget.email}.';
          _isVerifying = false;
          _clearAll();
        });
      } else {
        final errorData = jsonDecode(response.body);
        setState(() {
          _error = errorData['detail'] ?? 'Gửi lại OTP thất bại.';
          _isVerifying = false;
        });
        _shake();
      }
    } catch (e) {
      setState(() {
        _error = 'Không thể gửi lại OTP. Vui lòng thử lại sau.';
        _isVerifying = false;
      });
    }
  }

  Widget _otpBox(int index) {
    return SizedBox(
      width: 56,
      height: 64,
      child: TextField(
        controller: _controllers[index],
        focusNode: _focusNodes[index],
        keyboardType: TextInputType.number,
        maxLength: 1,
        textAlign: TextAlign.center,
        style: const TextStyle(
          fontSize: 28,
          fontWeight: FontWeight.w800,
          letterSpacing: 2,
          color: Color(0xFF111827),
        ),
        decoration: InputDecoration(
          counterText: '',
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: BorderSide(
              color: _controllers[index].text.isNotEmpty
                  ? const Color(0xFF059669)
                  : const Color(0xFFD1D5DB),
              width: 2,
            ),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: Color(0xFF2563EB), width: 2),
          ),
          filled: true,
          fillColor: const Color(0xFFF9FAFB),
          contentPadding: EdgeInsets.zero,
        ),
        onChanged: (value) {
          setState(() => _error = null);
          if (value.isNotEmpty && index < 5) {
            _focusNodes[index + 1].requestFocus();
          } else if (value.isEmpty && index > 0) {
            _focusNodes[index - 1].requestFocus();
          }
        },
        onSubmitted: (_) => _verifyOTP(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final canResend = _resendSecondsLeft <= 0;

    return Scaffold(
      backgroundColor: const Color(0xFFFAFBFC),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, color: Color(0xFF111827)),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          'Xác thực OTP',
          style: TextStyle(
            color: Color(0xFF111827),
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              const SizedBox(height: 16),
              Container(
                width: 72,
                height: 72,
                decoration: BoxDecoration(
                  color: const Color(0xFFEFF6FF),
                  borderRadius: BorderRadius.circular(24),
                ),
                child: const Icon(
                  Icons.lock_outline,
                  size: 36,
                  color: Color(0xFF2563EB),
                ),
              ),
              const SizedBox(height: 32),
              const Text(
                'Mã xác thực',
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF111827),
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'Mã xác thực đã được gửi đến ${widget.email}. Vui lòng nhập mã 6 chữ số.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 15,
                  color: Colors.grey[600],
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 36),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(6, (index) {
                  return AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    margin: const EdgeInsets.symmetric(horizontal: 6),
                    transform: Matrix4.translationValues(
                      _shakeAnimation.value * (index.isEven ? 1 : -1),
                      0,
                      0,
                    ),
                    child: _otpBox(index),
                  );
                }),
              ),
              const SizedBox(height: 32),
              if (_error != null)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.red[50],
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.red[200]!),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline, color: Colors.red, size: 20),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          _error!,
                          style: const TextStyle(color: Colors.red, fontSize: 14),
                        ),
                      ),
                    ],
                  ),
                )
              else if (_successMessage != null)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.green[50],
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.green[200]!),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.check_circle, color: Colors.green, size: 20),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          _successMessage!,
                          style: const TextStyle(color: Colors.green, fontSize: 14),
                        ),
                      ),
                    ],
                  ),
                ),
              const Spacer(),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton(
                  onPressed: _isVerifying ? null : _verifyOTP,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF2563EB),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                    elevation: 0,
                  ),
                  child: _isVerifying
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor: AlwaysStoppedAnimation(Colors.white),
                          ),
                        )
                      : const Text(
                          'Xác thực',
                          style: TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                ),
              ),
              const SizedBox(height: 20),
              TextButton(
                onPressed: _isVerifying || !canResend ? null : _resendOTP,
                style: TextButton.styleFrom(
                  foregroundColor: canResend
                      ? const Color(0xFF2563EB)
                      : Colors.grey[500],
                ),
                child: canResend
                    ? const Text(
                        'Gửi lại mã OTP',
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      )
                    : Text(
                        'Gửi lại sau ${_resendSecondsLeft}s',
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
              ),
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}
