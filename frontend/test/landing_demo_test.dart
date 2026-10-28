// Demo entry starts an in-memory sandbox without authenticating.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:kho_tra_sua/src/features/auth/auth_service.dart';
import 'package:kho_tra_sua/src/features/auth/login_screen.dart';
import 'package:kho_tra_sua/src/features/landing/landing_screen.dart';
import 'package:provider/provider.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';

/// Gate giả lập `_AuthGate` trong main.dart: LandingScreen -> LoginScreen
/// (thường hoặc phiên demo điền sẵn). Không gọi tryAutoLogin, không network.
class _AuthGateStub extends StatefulWidget {
  const _AuthGateStub();

  @override
  State<_AuthGateStub> createState() => _AuthGateStubState();
}

class _AuthGateStubState extends State<_AuthGateStub> {
  bool _showLogin = false;
  bool _showDemo = false;

  @override
  Widget build(BuildContext context) {
    if (_showDemo) {
      return AppShell(
          repository: FakeBankOpsRepository(latency: Duration.zero));
    }
    if (!_showLogin) {
      return LandingScreen(
        onEnter: () => setState(() => _showLogin = true),
        onDemo: () => setState(() => _showDemo = true),
      );
    }
    return const LoginScreen();
  }
}

AuthService _stubbedAuth() {
  // Mọi HTTP request đều bị chặn: test không bao giờ đụng localhost:8000.
  return AuthService(
    baseUrl: 'https://api.example.test',
    httpClient: MockClient(
      (_) async => throw http.ClientException('network disabled in tests'),
    ),
    googleIdTokenProvider: () async => null,
  );
}

Future<void> _pumpGate(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1440, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  await tester.pumpWidget(
    ChangeNotifierProvider<AuthService>.value(
      value: _stubbedAuth(),
      child: const MaterialApp(home: _AuthGateStub()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'CTA demo opens offline sandbox without login',
    (tester) async {
      await _pumpGate(tester);

      // Landing hiển thị đúng các CTA.
      expect(find.byKey(const Key('landing-enter-btn')), findsOneWidget);
      expect(find.byKey(const Key('landing-demo-btn')), findsOneWidget);
      expect(find.byKey(const Key('landing-footer-enter-btn')), findsOneWidget);

      await tester.tap(find.byKey(const Key('landing-demo-btn')));
      await tester.pumpAndSettle();

      // The app opens directly with the sample repository.
      expect(find.byKey(const Key('app-sidebar')), findsOneWidget);
      expect(find.byType(AppShell), findsOneWidget);
      expect(find.byType(LandingScreen), findsNothing);
      expect(find.byKey(const Key('app-demo-banner')), findsOneWidget);
      expect(find.textContaining('Dữ liệu demo'), findsOneWidget);

      // No authenticated identity or HTTP request is created.
      final auth =
          tester.element(find.byType(AppShell)).readProvider<AuthService>();
      expect(auth.user, isNull);
    },
  );

  testWidgets(
    'CTA Dang nhap (landing-enter-btn) van mo LoginScreen THUONG (khong prefill, khong banner)',
    (tester) async {
      await _pumpGate(tester);

      await tester.tap(find.byKey(const Key('landing-enter-btn')));
      await tester.pumpAndSettle();

      expect(find.byType(LoginScreen), findsOneWidget);
      final userField = tester.widget<TextField>(
        find.byKey(const Key('login-username-field')),
      );
      final passField = tester.widget<TextField>(
        find.byKey(const Key('login-password-field')),
      );
      expect(userField.controller?.text, isEmpty);
      expect(passField.controller?.text, isEmpty);
      expect(find.byKey(const Key('login-demo-banner')), findsNothing);
    },
  );

  testWidgets(
    'Footer Vao ung dung (landing-footer-enter-btn) van di thang LoginScreen thuong',
    (tester) async {
      await _pumpGate(tester);

      await tester
          .ensureVisible(find.byKey(const Key('landing-footer-enter-btn')));
      await tester.tap(find.byKey(const Key('landing-footer-enter-btn')));
      await tester.pumpAndSettle();

      expect(find.byType(LoginScreen), findsOneWidget);
      expect(find.byKey(const Key('login-demo-banner')), findsNothing);
      final userField = tester.widget<TextField>(
        find.byKey(const Key('login-username-field')),
      );
      expect(userField.controller?.text, isEmpty);
    },
  );

  testWidgets(
    'LandingScreen without onDemo falls back to onEnter',
    (tester) async {
      final auth = _stubbedAuth();
      var enterCount = 0;
      await tester.pumpWidget(
        ChangeNotifierProvider<AuthService>.value(
          value: auth,
          child: MaterialApp(
            home: LandingScreen(onEnter: () => enterCount++),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('landing-demo-btn')));
      await tester.pump();

      expect(enterCount, 1);
      expect(find.byType(LoginScreen), findsNothing);
      expect(auth.user, isNull);
    },
  );
}

extension _ReadProvider on BuildContext {
  T readProvider<T>() => Provider.of<T>(this, listen: false);
}
