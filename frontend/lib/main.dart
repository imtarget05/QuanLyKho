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
import 'src/features/commerce/commerce_memory_store.dart';
import 'src/features/commerce/commerce_workspace.dart';
import 'src/features/commerce/commerce_api.dart';

import 'src/core/i18n/app_i18n.dart';
import 'src/core/i18n/locale_controller.dart';
import 'src/core/theme/app_ui_settings_controller.dart';
import 'src/data/repositories/bankops_repository.dart';
import 'src/data/repositories/fake_repository.dart';
import 'src/data/repositories/http_bankops_repository.dart';

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

/// Cầu nối session: đọc AuthService, expose user & repository cho toàn bộ ứng dụng qua SessionScope và RepositoryScope.
class SessionBridge extends StatelessWidget {
  const SessionBridge({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthService>(
      builder: (context, auth, _) {
        final BankOpsRepository repo = auth.isOfflineSession
            ? FakeBankOpsRepository()
            : HttpBankOpsRepository(
                baseUrl: auth.apiBaseUrl,
                tokenProvider: auth.getAccessToken,
              );
        return SessionScope(
          user: auth.user,
          onSignOut: auth.signOut,
          child: RepositoryScope(
            repository: repo,
            child: child,
          ),
        );
      },
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
  late final CommerceMemoryStore _demoStore = CommerceMemoryStore.demo();
  bool _showAcceptInvite = false;
  String? _inviteToken;
  bool _showLogin = false;
  bool _showDemo = false;

  @override
  void initState() {
    super.initState();
    _showDemo = false;
    _checkUrlForInviteToken();
  }

  @override
  void dispose() {
    _demoStore.dispose();
    super.dispose();
  }

  Future<void> _handleSignOut(AuthService auth) async {
    await auth.signOut();
    if (mounted) {
      setState(() {
        _showDemo = false;
        _showAcceptInvite = false;
        _showLogin = true;
      });
    }
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
        final frag =
            base.fragment.startsWith('/') ? base.fragment : '/${base.fragment}';
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
    if (_showDemo) {
      return CommerceWorkspace(
        store: _demoStore,
        userName: auth.user?.displayName ?? 'An Nguyễn',
        capabilities: _showDemo && auth.user == null
            ? null
            : auth.user?.capabilities.toSet(),
        roles: _showDemo && auth.user == null ? null : auth.user?.roles.toSet(),
        onSignOut: () => _handleSignOut(auth),
      );
    }
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
        return LoginScreen(
          onBackToLanding: () => setState(() => _showLogin = false),
        );
      }
      return LandingScreen(
        onEnter: () => setState(() => _showLogin = true),
        onDemo: () => setState(() => _showLogin = true),
      );
    }
    return _LiveCommerceGate(
      auth: auth,
      onSignOut: () => _handleSignOut(auth),
    );
  }
}

class _LiveCommerceGate extends StatefulWidget {
  const _LiveCommerceGate({required this.auth, required this.onSignOut});
  final AuthService auth;
  final Future<void> Function() onSignOut;

  @override
  State<_LiveCommerceGate> createState() => _LiveCommerceGateState();
}

class _LiveCommerceGateState extends State<_LiveCommerceGate> {
  late final CommerceMemoryStore _store = CommerceMemoryStore.empty();
  late final CommerceApi _api = CommerceApi(
    baseUrl: widget.auth.apiBaseUrl,
    tokenProvider: widget.auth.getAccessToken,
    userId: widget.auth.user?.id ?? '',
  );
  Object? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await _api.reload(_store);
    } catch (error) {
      _error = error;
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  void dispose() {
    _api.dispose();
    _store.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading && _store.products.isEmpty) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    if (_error != null && _store.products.isEmpty) {
      return Scaffold(
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.cloud_off_outlined, size: 40),
                  const SizedBox(height: 12),
                  const Text('Không tải được dữ liệu cửa hàng',
                      style: TextStyle(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 8),
                  Text('$_error', textAlign: TextAlign.center),
                  const SizedBox(height: 14),
                  FilledButton(
                      onPressed: _reload, child: const Text('Thử lại')),
                ],
              ),
            ),
          ),
        ),
      );
    }
    return CommerceWorkspace(
      store: _store,
      api: _api,
      onRefresh: _reload,
      userName: widget.auth.user?.displayName ?? 'Tài khoản',
      onSignOut: widget.onSignOut,
      capabilities: widget.auth.user?.capabilities.toSet(),
      roles: widget.auth.user?.roles.toSet(),
    );
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
      builder: (context, child) => SessionBridge(child: child ?? const SizedBox.shrink()),
      home: const _AuthGate(),
    );
  }
}
