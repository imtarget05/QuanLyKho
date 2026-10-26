import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:flutter_localizations/flutter_localizations.dart';

import 'src/app/app_shell.dart';
import 'src/core/theme/app_theme.dart';
import 'src/app/theme_mode_controller.dart';
import 'src/features/auth/accept_invite_screen.dart';
import 'src/features/auth/auth_service.dart';
import 'src/features/auth/login_screen.dart';
import 'src/features/landing/landing_screen.dart';

import 'src/core/i18n/app_i18n.dart';
import 'src/core/i18n/locale_controller.dart';
import 'src/core/theme/app_ui_settings_controller.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.dark,
    statusBarBrightness: Brightness.light,
    systemNavigationBarColor: Colors.transparent,
    systemNavigationBarDividerColor: Colors.transparent,
    systemNavigationBarIconBrightness: Brightness.dark,
    systemNavigationBarContrastEnforced: false,
    systemStatusBarContrastEnforced: false,
  ));
  final uiSettings = AppUiSettingsController();
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => AuthService()..tryAutoLogin(),
        ),
        ChangeNotifierProvider(
          create: (_) => LocaleController(),
        ),
        ChangeNotifierProvider<AppUiSettingsController>.value(
          value: uiSettings,
        ),
        ChangeNotifierProvider<ThemeModeController>.value(
          value: uiSettings,
        ),
      ],
      child: const TeaInventoryApp(),
    ),
  );
}

/// Cầu nối session: đọc AuthService, expose user cho AppShell qua SessionScope.
class SessionBridge extends StatelessWidget {
  const SessionBridge({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthService>(
      builder: (context, auth, _) => SessionScope(
        user: auth.user,
        onSignOut: auth.signOut,
        child: child,
      ),
    );
  }
}

/// Chưa đăng nhập -> LoginScreen hoặc AcceptInviteScreen nếu truy cập từ link mời;
/// đã có token hợp lệ -> AppShell.
class _AuthGate extends StatefulWidget {
  const _AuthGate();

  @override
  State<_AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<_AuthGate> {
  bool _showAcceptInvite = false;
  String? _inviteToken;
  bool _showLogin = false;

  @override
  void initState() {
    super.initState();
    _checkUrlForInviteToken();
  }

  void _checkUrlForInviteToken() {
    try {
      final base = Uri.base;
      String? token;
      if (base.queryParameters.containsKey('token')) {
        token = base.queryParameters['token']?.trim();
      }
      if ((token == null || token.isEmpty) &&
          base.hasFragment &&
          base.fragment.isNotEmpty) {
        final frag = base.fragment.startsWith('/')
            ? base.fragment
            : '/${base.fragment}';
        final fragUri = Uri.tryParse(frag);
        if (fragUri != null && fragUri.queryParameters.containsKey('token')) {
          token = fragUri.queryParameters['token']?.trim();
        }
      }
      final isAcceptInvitePath = base.path.contains('accept-invite') ||
          (base.hasFragment && base.fragment.contains('accept-invite'));

      if ((token != null && token.isNotEmpty) || isAcceptInvitePath) {
        _showAcceptInvite = true;
        _inviteToken = (token != null && token.isNotEmpty) ? token : null;
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();
    if (auth.isLoading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (auth.user == null) {
      if (_showAcceptInvite) {
        return AcceptInviteScreen(
          initialToken: _inviteToken,
          onBackToLogin: () => setState(() => _showAcceptInvite = false),
          onSuccess: () => setState(() => _showAcceptInvite = false),
        );
      }
      if (_showLogin) {
        return const LoginScreen();
      }
      return LandingScreen(onEnter: () => setState(() => _showLogin = true));
    }
    return const AppShell();
  }
}

class TeaInventoryApp extends StatelessWidget {
  const TeaInventoryApp({super.key});

  @override
  Widget build(BuildContext context) {
    final uiSettings = context.watch<AppUiSettingsController>();
    final locale = context.watch<LocaleController>().locale;
    final i18n = AppI18n(locale);

    return MaterialApp(
      title: i18n.tr('app_title'),
      debugShowCheckedModeBanner: false,
      locale: locale,
      supportedLocales: const [
        Locale('vi'),
        Locale('en'),
      ],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      theme: AppTheme.light(
        preset: uiSettings.colorPreset,
        density: uiSettings.density,
      ),
      darkTheme: AppTheme.dark(
        preset: uiSettings.colorPreset,
        density: uiSettings.density,
      ),
      themeMode: uiSettings.mode,
      home: const SessionBridge(child: _AuthGate()),
    );
  }
}
