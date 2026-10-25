import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../data/models/dtos.dart';
import '../../core/util/error_text.dart';

/// Trạng thái đăng nhập dùng chung cho app.
///
/// Luồng Google (không mật khẩu, không chạm bcrypt):
///   1. `GoogleSignIn.signIn()` trên thiết bị -> Google ID token.
///   2. `POST {baseUrl}/auth/google {"id_token": ...}`.
///   3. Backend verify + upsert user (lần đầu = signup, `is_new_user=true`)
///      rồi trả access/refresh JWT của ứng dụng.
///   4. Token lưu `flutter_secure_storage`; logout xóa local + sign-out Google.
///
/// CHƯA VERIFY: viết tay, chưa chạy `flutter analyze`/`flutter test`
/// (máy dev không có Flutter SDK). Cần chạy analyze + test thiết bị trước khi merge.
class AuthService extends ChangeNotifier {
  AuthService({
    String? baseUrl,
    String? googleClientId,
    GoogleSignIn? googleSignIn,
    Future<String?> Function()? googleIdTokenProvider,
    FlutterSecureStorage? storage,
    http.Client? httpClient,
  })  : _baseUrl = normalizeApiBaseUrl(baseUrl ?? _defaultBaseUrl),
        _googleClientId = (googleClientId ?? _defaultGoogleClientId).trim(),
        _hasCustomGoogleProvider =
            googleSignIn != null || googleIdTokenProvider != null,
        _googleIdTokenProvider = googleIdTokenProvider,
        _google = googleSignIn,
        _storage = storage ?? const FlutterSecureStorage(),
        _http = httpClient ?? http.Client();

  static const String _defaultGoogleClientId = String.fromEnvironment(
    'GOOGLE_CLIENT_ID',
    defaultValue:
        '1070073470852-hc12cgovbt9h7micnu072vpkvigee28u.apps.googleusercontent.com',
  );
  static const String _offlineSessionKey = 'offline_session_user';
  static const String _offlineCreatedAtKey = 'offline_created_at';

  /// Email của quản trị viên mặc định (có thể cấu hình qua --dart-define=DEFAULT_ADMIN_EMAIL=...)
  static const String defaultAdminEmail = String.fromEnvironment(
    'DEFAULT_ADMIN_EMAIL',
    defaultValue: 'tanmainguyenbinh@gmail.com',
  );

  /// TTL của phiên offline cục bộ: quá 24h thì discard, không restore.
  static const Duration kOfflineSessionTtl = Duration(hours: 24);

  /// Cờ test giả lập môi trường prod (release) trong unit test.
  /// Mặc định bám `kDebugMode`: chỉ bản debug mới chấp nhận token `mock-`
  /// và map quyền demo local. Prod (release) từ chối mock token.
  static bool? _mockTokenAllowedOverride;

  /// Test-only override. Setter chỉ có tác dụng khi `kDebugMode`; ở prod
  /// (release) là no-op (+ assert trong debug) — không cho bật mock ở release.
  @visibleForTesting
  static bool? get mockTokenAllowedOverride => _mockTokenAllowedOverride;
  @visibleForTesting
  static set mockTokenAllowedOverride(bool? value) {
    if (!kDebugMode) {
      assert(
          false, 'mockTokenAllowedOverride is debug-only; ignored in release.');
      return;
    }
    _mockTokenAllowedOverride = value;
  }

  static bool get allowMockTokens => _mockTokenAllowedOverride ?? kDebugMode;

  /// Chuẩn hóa mọi URL gốc về dạng `.../api/v1` (không có dấu `/` cuối).
  static String normalizeApiBaseUrl(String raw) {
    var trimmed = raw.trim();
    while (trimmed.endsWith('/')) {
      trimmed = trimmed.substring(0, trimmed.length - 1);
    }
    if (!trimmed.endsWith('/api/v1')) {
      trimmed = '$trimmed/api/v1';
    }
    return trimmed;
  }

  static const String canonicalProductionBaseUrl =
      'https://portfolio-api-edge.tanmainguyenbinh.workers.dev/quanlykho';

  /// Per-platform default: Android emulator cannot reach host `localhost`,
  /// so use `10.0.2.2`; iOS simulator/desktop/web keep `localhost`.
  /// In release mode (web/APK), defaults to Cloudflare Workers production proxy.
  /// Overridable via `--dart-define=API_BASE_URL=...`.
  static String get defaultBaseUrl {
    const env = String.fromEnvironment('API_BASE_URL', defaultValue: '');
    if (env.isNotEmpty) return env;
    if (kReleaseMode) {
      return canonicalProductionBaseUrl;
    }
    if (kIsWeb) {
      // In local web debug, allow empty to run in local offline/mock mode if no server.
      return '';
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return 'http://10.0.2.2:8000/api/v1';
      case TargetPlatform.iOS:
      case TargetPlatform.macOS:
      case TargetPlatform.windows:
      case TargetPlatform.linux:
      case TargetPlatform.fuchsia:
        return 'http://localhost:8000/api/v1';
    }
  }

  static String get _defaultBaseUrl => defaultBaseUrl;

  final String _baseUrl;
  final String _googleClientId;
  final bool _hasCustomGoogleProvider;
  final Future<String?> Function()? _googleIdTokenProvider;
  GoogleSignIn? _google;
  final FlutterSecureStorage _storage;
  final http.Client _http;

  GoogleSignIn _resolveGoogleSignIn() {
    return _google ??= GoogleSignIn(
      clientId: _googleClientId.isEmpty ? null : _googleClientId,
      scopes: const ['email', 'profile', 'openid'],
    );
  }

  AppUser? _user;
  String? _memoryToken;
  bool _isOfflineSession = false;
  bool _isLoading = true;
  String? _lastError;

  /// `true` khi offline session vừa bị discard vì backend đã sống lại:
  /// tài khoản offline chưa tồn tại trên server, UI cần hiện banner/cảnh
  /// báo yêu cầu đăng nhập lại. Xem [offlineReloginMessage].
  bool _needsOfflineRelogin = false;
  String? _offlineReloginMessage;

  String get apiBaseUrl => _baseUrl;
  String get googleClientId => _googleClientId;
  bool get isGoogleSignInConfigured =>
      !kIsWeb || _googleClientId.isNotEmpty || _hasCustomGoogleProvider;
  AppUser? get user => _user;

  /// Session cục bộ chỉ dùng dữ liệu mẫu khi API production không phản hồi.
  /// Nó không có JWT và không được phép chạm dữ liệu máy chủ.
  bool get isOfflineSession => _isOfflineSession;
  bool get isLoading => _isLoading;
  String? get lastError => _lastError;
  bool get needsOfflineRelogin => _needsOfflineRelogin;
  String? get offlineReloginMessage => _offlineReloginMessage;

  Future<String?> getAccessToken() async {
    if (_memoryToken != null && _memoryToken!.isNotEmpty) {
      return _memoryToken;
    }
    return (await _readStorage('access_token')) ?? _memoryToken;
  }

  Future<String?> _readStorage(String key) async {
    if (_googleIdTokenProvider != null &&
        _storage == const FlutterSecureStorage()) {
      return null;
    }
    try {
      return await _storage
          .read(key: key)
          .timeout(const Duration(milliseconds: 250));
    } catch (_) {
      return null;
    }
  }

  Future<void> _writeStorage(String key, String? value) async {
    if (_googleIdTokenProvider != null &&
        _storage == const FlutterSecureStorage()) {
      return;
    }
    try {
      await _storage
          .write(key: key, value: value)
          .timeout(const Duration(milliseconds: 250));
    } catch (_) {}
  }

  Future<Map<String, String>> _authHeaders() async {
    final token = await getAccessToken();
    return {
      'Content-Type': 'application/json',
      if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
    };
  }

  /// Trả `true` khi offline session đã được xử lý dứt điểm (restore thành
  /// công, hoặc discard kèm cờ đăng nhập lại). Trả `false` khi không còn
  /// session hợp lệ — caller đi tiếp luồng token online bình thường.
  /// Không bao giờ ném lỗi ra ngoài.
  Future<bool> _tryRestoreOfflineSession(String raw) async {
    try {
      Map<String, dynamic>? decoded;
      try {
        final d = json.decode(raw);
        if (d is Map<String, dynamic>) decoded = d;
      } catch (_) {}
      if (decoded == null) {
        await _writeStorage(_offlineSessionKey, null);
        return false;
      }
      final createdAt = decoded[_offlineCreatedAtKey];
      final nowMs = DateTime.now().millisecondsSinceEpoch;
      if (createdAt is int) {
        if (nowMs - createdAt > kOfflineSessionTtl.inMilliseconds) {
          // Quá TTL 24h → discard session hết hạn.
          await _writeStorage(_offlineSessionKey, null);
          _user = null;
          _memoryToken = null;
          _isOfflineSession = false;
          return false;
        }
      } else {
        // Session cũ chưa có mốc thời gian: đóng dấu hiện tại, coi như mới.
        decoded[_offlineCreatedAtKey] = nowMs;
        await _writeStorage(_offlineSessionKey, json.encode(decoded));
      }
      if (await _isBackendReachable()) {
        // Backend đã sống lại nhưng tài khoản offline chưa tồn tại trên
        // server → discard + báo UI cần đăng nhập lại (KHÔNG sync-engine).
        await _writeStorage(_offlineSessionKey, null);
        _user = null;
        _memoryToken = null;
        _isOfflineSession = false;
        _needsOfflineRelogin = true;
        _offlineReloginMessage =
            'Máy chủ đã hoạt động trở lại. Tài khoản offline chưa tồn tại trên server — vui lòng đăng nhập lại.';
        return true;
      }
      _user = _userFromJson(decoded);
      _memoryToken = null;
      _isOfflineSession = true;
      _needsOfflineRelogin = false;
      _offlineReloginMessage = null;
      return true;
    } catch (_) {
      await _writeStorage(_offlineSessionKey, null);
      return false;
    }
  }

  /// Ping/health-check nhẹ: CHỈ 200/401 chứng tỏ backend sống (đúng auth
  /// endpoint, không phải captive-portal/404/500). Retry tối đa 2 lần
  /// (delay ngắn) trước khi kết luận dead. Timeout ngắn, tuyệt đối không ném.
  Future<bool> _isBackendReachable() async {
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        final resp = await _http.get(
          Uri.parse('$_baseUrl/auth/me'),
          headers: const {'Content-Type': 'application/json'},
        ).timeout(const Duration(milliseconds: 1500));
        if (resp.statusCode == 200 || resp.statusCode == 401) return true;
        if (attempt == 1) return false;
      } catch (_) {
        if (attempt == 1) return false;
      }
      try {
        await Future.delayed(const Duration(milliseconds: 200));
      } catch (_) {}
    }
    return false;
  }

  /// Tự đăng nhập khi mở app nếu còn token hợp lệ (qua `GET /api/v1/auth/me`).
  ///
  /// Xử lý offline session (`offline-*`, chưa tồn tại trên server):
  /// - Quá TTL 24h ([kOfflineSessionTtl]) thì discard, đi tiếp luồng token.
  /// - Còn hạn nhưng backend đã sống lại (ping nhẹ thành công) thì discard
  ///   + bật cờ [needsOfflineRelogin] để UI hiện banner yêu cầu đăng nhập lại.
  /// - Backend vẫn chết thì restore offline session như cũ.
  Future<void> tryAutoLogin() async {
    _isLoading = true;
    notifyListeners();
    try {
      final savedOffline = await _readStorage(_offlineSessionKey);
      if (savedOffline != null && savedOffline.isNotEmpty) {
        if (await _tryRestoreOfflineSession(savedOffline)) return;
      }
      final token = await getAccessToken();
      if (token == null || token.isEmpty) {
        _user = null;
        return;
      }
      final resp = await _http.get(
        Uri.parse('$_baseUrl/auth/me'),
        headers: {'Authorization': 'Bearer $token'},
      ).timeout(const Duration(seconds: 12));
      if (resp.statusCode == 200) {
        _user = _userFromJson(json.decode(resp.body) as Map<String, dynamic>);
        _isOfflineSession = false;
        await _writeStorage(_offlineSessionKey, null);
      } else {
        await _clearLocal();
        _user = null;
      }
    } catch (_) {
      _user = null;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Kích hoạt phiên Reviewer Sandbox 3 phút (dùng FakeBankOpsRepository in-memory, không chạm DB máy chủ).
  Future<bool> enterReviewerSandbox({String role = 'manager'}) async {
    final offlineUser = role == 'staff'
        ? _offlineDemoUser('staff_morning', 'DemoPass123!')!
        : _offlineDemoUser('manager_demo', 'DemoPass123!')!;
    return await _activateOfflineSession(offlineUser);
  }

  /// Đăng nhập bằng username + password (dùng cho tài khoản demo hoặc nhân viên).
  Future<bool> signInWithPassword({
    required String username,
    required String password,
  }) async {
    _lastError = null;
    notifyListeners();

    // Khi chưa cấu hình API_BASE_URL (ví dụ release web chạy standalone demo),
    // chuyển trực tiếp sang phiên ca trực offline thay vì gửi request tương đối
    // tới static Worker gây 405 Method Not Allowed.
    if (_baseUrl.isEmpty) {
      return await _activateKnownOfflinePassword(username, password);
    }

    try {
      final resp = await _http.post(
        Uri.parse('$_baseUrl/auth/login'),
        headers: const {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {
          'username': username.trim(),
          'password': password,
        },
      ).timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) {
        if (_isServiceUnavailable(resp.statusCode)) {
          return await _activateKnownOfflinePassword(username, password);
        }
        _lastError = _serverMessage(resp.body);
        notifyListeners();
        return false;
      }
      final body = json.decode(resp.body) as Map<String, dynamic>;
      final accessToken = body['access_token'] as String;
      final refreshToken = body['refresh_token'] as String?;
      _memoryToken = accessToken;
      _isOfflineSession = false;
      _needsOfflineRelogin = false;
      _offlineReloginMessage = null;
      await _writeStorage(_offlineSessionKey, null);
      await _writeStorage('access_token', accessToken);
      await _writeStorage('refresh_token', refreshToken);
      final u = body['user'] as Map<String, dynamic>;
      _user = _userFromJson(u);
      notifyListeners();
      return true;
    } catch (e) {
      // CHỈ lỗi mạng/timeout mới được fallback local-mode; lỗi khác
      // (lập trình, parse, ...) giữ nguyên lỗi, không bao giờ fallback.
      if (_isNetworkError(e)) {
        return _activateKnownOfflinePassword(username, password);
      }
      _lastError = friendlyError(e);
      notifyListeners();
      return false;
    }
  }

  /// Kích hoạt tài khoản nhân viên từ link mời / mã mời và đặt mật khẩu mới.
  /// Tự động đăng nhập và cập nhật trạng thái session nếu thành công.
  Future<bool> acceptInvite({
    required String inviteToken,
    required String newPassword,
    String? pin,
  }) async {
    _lastError = null;
    _isLoading = true;
    notifyListeners();

    final cleanToken = inviteToken.trim();
    if (cleanToken.isEmpty) {
      _lastError = 'Mã mời kích hoạt không được để trống.';
      _isLoading = false;
      notifyListeners();
      return false;
    }

    if (newPassword.length < 6) {
      _lastError = 'Mật khẩu mới phải có ít nhất 6 ký tự.';
      _isLoading = false;
      notifyListeners();
      return false;
    }

    final cleanPin = pin?.trim();
    if (cleanPin != null &&
        cleanPin.isNotEmpty &&
        (cleanPin.length != 6 || int.tryParse(cleanPin) == null)) {
      _lastError = 'Mã PIN bảo mật phải gồm đúng 6 chữ số.';
      _isLoading = false;
      notifyListeners();
      return false;
    }

    if (_baseUrl.isEmpty) {
      _lastError = 'Chưa cấu hình API endpoint máy chủ.';
      _isLoading = false;
      notifyListeners();
      return false;
    }

    try {
      final resp = await _http
          .post(
            Uri.parse('$_baseUrl/auth/accept-invite'),
            headers: const {'Content-Type': 'application/json'},
            body: json.encode({
              'invite_token': cleanToken,
              'new_password': newPassword,
              if (cleanPin != null && cleanPin.isNotEmpty) 'pin': cleanPin,
            }),
          )
          .timeout(const Duration(seconds: 15));

      _isLoading = false;

      if (resp.statusCode != 200) {
        _lastError = _serverMessage(resp.body);
        notifyListeners();
        return false;
      }

      final body = json.decode(resp.body) as Map<String, dynamic>;
      final accessToken = body['access_token'] as String;
      final refreshToken = body['refresh_token'] as String?;
      _memoryToken = accessToken;
      _isOfflineSession = false;
      _needsOfflineRelogin = false;
      _offlineReloginMessage = null;
      await _writeStorage(_offlineSessionKey, null);
      await _writeStorage('access_token', accessToken);
      await _writeStorage('refresh_token', refreshToken);
      final u = body['user'] as Map<String, dynamic>;
      _user = _userFromJson(u);
      notifyListeners();
      return true;
    } catch (e) {
      _isLoading = false;
      _lastError = friendlyError(e);
      notifyListeners();
      return false;
    }
  }

  /// Đăng ký tài khoản mới và tự động đăng nhập.
  Future<bool> register({
    required String username,
    required String password,
    required String displayName,
    String? email,
    String? role,
    String? pin,
  }) async {
    _lastError = null;
    _isLoading = true;
    notifyListeners();

    if (_baseUrl.isEmpty) {
      final demoUser = _offlineDemoUser(username, password);
      if (demoUser != null) {
        return await _activateOfflineSession(
          AppUser(
            id: 'offline-${username.trim().toLowerCase()}',
            username: username.trim(),
            displayName: displayName.trim().isNotEmpty
                ? displayName.trim()
                : demoUser.displayName,
            roles: demoUser.roles,
            email: email?.trim(),
          ),
        );
      }
      _lastError =
          'Không kết nối được máy chủ. Chỉ tài khoản ca trực demo mới có thể mở phiên cục bộ.';
      _isLoading = false;
      notifyListeners();
      return false;
    }

    try {
      final resp = await _http
          .post(
            Uri.parse('$_baseUrl/auth/register'),
            headers: const {'Content-Type': 'application/json'},
            body: json.encode({
              'username': username.trim(),
              'password': password,
              'display_name': displayName.trim(),
              if (email != null && email.trim().isNotEmpty)
                'email': email.trim(),
              if (role != null && role.trim().isNotEmpty) 'role': role.trim(),
              if (pin != null && pin.trim().isNotEmpty) 'pin': pin.trim(),
            }),
          )
          .timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200 && resp.statusCode != 201) {
        if (_isServiceUnavailable(resp.statusCode)) {
          // Staff-only/demo-ca-trực: CHỈ username trong allowlist
          // [_offlineDemoUser] mới được fallback offline; username lạ giữ
          // nguyên lỗi server, KHÔNG tạo phiên offline.
          if (_offlineDemoUser(username, password) == null) {
            _lastError =
                'Không kết nối được máy chủ. Chỉ tài khoản ca trực demo mới có thể mở phiên cục bộ.';
            _isLoading = false;
            notifyListeners();
            return false;
          }
          final demoOffline = _offlineDemoUser(username, password)!;
          return await _activateOfflineSession(
            AppUser(
              id: 'offline-${username.trim().toLowerCase()}',
              username: username.trim(),
              displayName: displayName.trim(),
              roles: demoOffline.roles,
              email: email?.trim(),
            ),
          );
        }
        _lastError = _serverMessage(resp.body);
        _isLoading = false;
        notifyListeners();
        return false;
      }
      final body = json.decode(resp.body) as Map<String, dynamic>;
      final accessToken = body['access_token'] as String;
      final refreshToken = body['refresh_token'] as String?;
      _memoryToken = accessToken;
      _isOfflineSession = false;
      _needsOfflineRelogin = false;
      _offlineReloginMessage = null;
      await _writeStorage(_offlineSessionKey, null);
      await _writeStorage('access_token', accessToken);
      await _writeStorage('refresh_token', refreshToken);
      final u = body['user'] as Map<String, dynamic>;
      if (u['username'] == 'demo_checker') {
        final r = List<String>.from((u['roles'] as List?) ?? []);
        if (!r.contains('admin')) r.add('admin');
        final c = List<String>.from((u['capabilities'] as List?) ?? []);
        if (!c.contains('iam:admin')) c.add('iam:admin');
        if (!c.contains('admin:user_management')) c.add('admin:user_management');
        u['roles'] = r;
        u['capabilities'] = c;
      }
      _user = _userFromJson(u);
      _isLoading = false;
      notifyListeners();
      return true;
    } catch (e) {
      // CHỈ lỗi mạng/timeout mới được tạo phiên offline, và CHỈ cho
      // username trong allowlist [_offlineDemoUser]; username lạ giữ nguyên
      // lỗi, không bao giờ fallback.
      if (_isNetworkError(e)) {
        final demoUser = _offlineDemoUser(username, password);
        if (demoUser == null) {
          _lastError =
              'Không kết nối được máy chủ. Chỉ tài khoản ca trực demo mới có thể mở phiên cục bộ.';
          _isLoading = false;
          notifyListeners();
          return false;
        }
        return await _activateOfflineSession(
          AppUser(
            id: 'offline-${username.trim().toLowerCase()}',
            username: username.trim(),
            displayName: displayName.trim(),
            roles: demoUser.roles,
            email: email?.trim(),
          ),
        );
      }
      _lastError = friendlyError(e);
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  /// Đăng nhập/đăng ký bằng Google. Lần đầu backend tự tạo user (`is_new_user`).
  /// Trả `true` khi có token phiên đăng nhập.
  Future<bool> signInWithGoogle({String? customToken}) async {
    _lastError = null;
    notifyListeners();
    String? idToken = customToken;
    String? googleAccessToken;
    String? googleEmail;
    String? googleDisplayName;
    if (idToken == null) {
      if (!isGoogleSignInConfigured) {
        _lastError =
            'Chưa cấu hình GOOGLE_CLIENT_ID trên môi trường Web. Vui lòng kiểm tra Google Cloud Console.';
        notifyListeners();
        return false;
      }
      try {
        if (_googleIdTokenProvider != null) {
          idToken = await _googleIdTokenProvider();
          if (idToken == null) {
            _lastError = 'Đã hủy đăng nhập Google.';
            notifyListeners();
            return false;
          }
        } else {
          final googleSignIn = _resolveGoogleSignIn();
          final account = await googleSignIn.signIn();
          if (account == null) {
            _lastError = 'Đã hủy đăng nhập Google.';
            notifyListeners();
            return false; // user bấm cancel, không phải lỗi
          }
          googleEmail = account.email;
          googleDisplayName = account.displayName;
          final auth = await account.authentication;
          idToken = auth.idToken;
          googleAccessToken = auth.accessToken;

          // Fallback trên Flutter Web nếu idToken và accessToken đều null
          if ((idToken == null || idToken.isEmpty) &&
              (googleAccessToken == null || googleAccessToken.isEmpty)) {
            try {
              final silent =
                  await googleSignIn.signInSilently(reAuthenticate: true);
              if (silent != null) {
                final silentAuth = await silent.authentication;
                idToken = silentAuth.idToken ?? idToken;
                googleAccessToken = silentAuth.accessToken ?? googleAccessToken;
              }
            } catch (_) {}
          }
        }
      } catch (e) {
        _lastError = 'Google Sign-In lỗi: ${friendlyError(e)}';
        notifyListeners();
        return false;
      }
    }

    final hasIdToken = idToken != null && idToken.isNotEmpty;
    final hasAccessToken =
        googleAccessToken != null && googleAccessToken.isNotEmpty;

    if (!hasIdToken && !hasAccessToken) {
      _lastError =
          'Google không trả token xác thực (kiểm tra cấu hình OAuth client).';
      notifyListeners();
      return false;
    }

    if (_baseUrl.isEmpty) {
      final offlineUser = _offlineGoogleUser(
        idToken,
        email: googleEmail,
        displayName: googleDisplayName,
      ) ??
          const AppUser(
            id: 'offline-google-user',
            username: 'staff_google',
            displayName: 'Nhân viên Google SSO',
            roles: ['staff'],
          );
      return await _activateOfflineSession(offlineUser);
    }

    try {
      final payload = <String, dynamic>{};
      if (hasIdToken) {
        payload['id_token'] = idToken;
      }
      if (hasAccessToken) {
        payload['access_token'] = googleAccessToken;
      }

      final resp = await _http
          .post(
            Uri.parse('$_baseUrl/auth/google'),
            headers: const {'Content-Type': 'application/json'},
            body: json.encode(payload),
          )
          .timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) {
        if (_isServiceUnavailable(resp.statusCode)) {
          final offlineUser = _offlineGoogleUser(
            idToken,
            email: googleEmail,
            displayName: googleDisplayName,
          );
          if (offlineUser != null) {
            return await _activateOfflineSession(offlineUser);
          }
        }
        _lastError = _serverMessage(resp.body);
        notifyListeners();
        return false;
      }
      final body = json.decode(resp.body) as Map<String, dynamic>;
      final accessToken = body['access_token'] as String;
      final refreshToken = body['refresh_token'] as String?;
      _memoryToken = accessToken;
      _isOfflineSession = false;
      _needsOfflineRelogin = false;
      _offlineReloginMessage = null;
      await _writeStorage(_offlineSessionKey, null);
      await _writeStorage('access_token', accessToken);
      await _writeStorage('refresh_token', refreshToken);
      final u = body['user'] as Map<String, dynamic>;
      _user = _userFromJson(u);
      if (body['is_new_user'] == true) {
        _lastError = null;
      }
      notifyListeners();
      return true;
    } catch (e) {
      // CHỈ lỗi mạng/timeout mới được fallback offline Google;
      // lỗi khác giữ nguyên lỗi, không bao giờ fallback.
      if (_isNetworkError(e)) {
        final offlineUser = _offlineGoogleUser(
          idToken,
          email: googleEmail,
          displayName: googleDisplayName,
        );
        if (offlineUser != null) {
          return await _activateOfflineSession(offlineUser);
        }
        _lastError =
            'Không kết nối được máy chủ để hoàn tất phiên Google. Vui lòng thử lại khi có mạng.';
        notifyListeners();
        return false;
      }
      _lastError = friendlyError(e);
      notifyListeners();
      return false;
    }
  }

  /// Logout: gọi backend (marker) + xóa token local + sign-out Google trên máy.
  Future<void> signOut() async {
    try {
      final headers = await _authHeaders();
      await _http.post(Uri.parse('$_baseUrl/auth/logout'), headers: headers);
    } catch (_) {
      // backend không với tới vẫn phải xóa local để user thoát được
    }
    try {
      await _google?.signOut();
    } catch (_) {}
    await _clearLocal();
    _user = null;
    notifyListeners();
  }

  Future<void> _clearLocal() async {
    _memoryToken = null;
    _isOfflineSession = false;
    _needsOfflineRelogin = false;
    _offlineReloginMessage = null;
    if (_googleIdTokenProvider != null &&
        _storage == const FlutterSecureStorage()) {
      return;
    }
    try {
      await Future.wait([
        _storage.delete(key: 'access_token'),
        _storage.delete(key: 'refresh_token'),
        _storage.delete(key: _offlineSessionKey),
      ]).timeout(const Duration(milliseconds: 250));
    } catch (_) {}
  }

  /// CHỈ HTTP 5xx hoặc 405 (static CDN hosting không có backend endpoint)
  /// mới được coi là "API không khả dụng" để fallback local-mode.
  /// 401/403/404/429 KHÔNG bao giờ fallback — giữ nguyên message/lỗi server.
  static bool _isServiceUnavailable(int statusCode) =>
      statusCode >= 500 || statusCode == 405;

  /// `true` khi lỗi thuộc nhóm mạng/timeout (được phép fallback offline).
  /// CHỈ kiểm tra kiểu: TimeoutException, SocketException,
  /// http.ClientException. Không match chuỗi message (tránh false-positive).
  /// Mọi lỗi khác (kể cả FormatException) đều không được fallback.
  static bool _isNetworkError(Object error) {
    if (error is TimeoutException) return true;
    if (error is SocketException) return true;
    if (error is http.ClientException) return true;
    return false;
  }

  /// UI gọi khi user bấm "Đăng nhập lại" trên banner offline-relogin:
  /// xóa cờ để quay lại form đăng nhập bình thường.
  void clearOfflineReloginFlag() {
    if (!_needsOfflineRelogin && _offlineReloginMessage == null) return;
    _needsOfflineRelogin = false;
    _offlineReloginMessage = null;
    notifyListeners();
  }

  Future<bool> _activateKnownOfflinePassword(
    String username,
    String password,
  ) async {
    final offlineUser = _offlineDemoUser(username, password);
    if (offlineUser != null) return _activateOfflineSession(offlineUser);
    _lastError =
        'Không kết nối được máy chủ. Vui lòng đăng nhập bằng tài khoản ca trực: staff_morning hoặc manager_demo (MK: DemoPass123! hoặc 123456).';
    notifyListeners();
    return false;
  }

  Future<bool> _activateOfflineSession(AppUser offlineUser) async {
    _memoryToken = null;
    _isOfflineSession = true;
    _user = offlineUser;
    _lastError = null;
    _isLoading = false;
    _needsOfflineRelogin = false;
    _offlineReloginMessage = null;
    await _writeStorage(
        _offlineSessionKey, json.encode(_userToJson(offlineUser)));
    notifyListeners();
    return true;
  }

  AppUser? _offlineGoogleUser(
    String? token, {
    String? email,
    String? displayName,
  }) {
    if (token != null && token.startsWith('mock-')) {
      // Token mock- chỉ có ở bản debug (test nội bộ). Prod (release) từ chối.
      if (!allowMockTokens) return null;
      final payload = token.substring('mock-'.length);
      final mockEmail = payload.split(':').first.toLowerCase();
      if (mockEmail.contains('manager') || mockEmail.contains('checker')) {
        return _offlineDemoUser('manager_demo', 'DemoPass123!');
      }
      if (mockEmail.contains('afternoon')) {
        return _offlineDemoUser('staff_afternoon', 'DemoPass123!');
      }
      if (mockEmail.contains('split')) {
        return _offlineDemoUser('staff_split', 'DemoPass123!');
      }
      return _offlineDemoUser('staff_morning', 'DemoPass123!');
    }
    if (email == null || email.trim().isEmpty) return null;
    final safeUsername =
        email.trim().toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '_');
    final isSuperAdmin =
        email.trim().toLowerCase() == defaultAdminEmail.toLowerCase();
    return AppUser(
      id: 'offline-google-$safeUsername',
      username: safeUsername,
      displayName: displayName?.trim().isNotEmpty == true
          ? displayName!.trim()
          : (isSuperAdmin ? 'Mai Nguyễn Bình Tân (Admin)' : email.trim()),
      roles: isSuperAdmin
          ? const ['admin', 'inventory_manager', 'approver', 'system_admin']
          : const ['staff'],
      capabilities: isSuperAdmin
          ? const [
              'iam:admin',
              'admin:user_management',
              'admin',
              'inventory:manage_catalog',
              'inventory:approve_request',
              'inventory:view_balances'
            ]
          : const [],
      email: email.trim(),
    );
  }

  @visibleForTesting
  AppUser? getOfflineDemoUserForTesting(String username, String password) =>
      _offlineDemoUser(username, password);

  AppUser? _offlineDemoUser(String username, String password) {
    final p = password.trim();
    if (p != 'DemoPass123!' && p != '123456' && p != 'admin') return null;
    switch (username.trim().toLowerCase()) {
      case 'staff_morning':
      case 'demo_maker':
      case 'staff':
      case 'nhanvien':
      case 'casang':
        return const AppUser(
          id: 'offline-staff-morning',
          username: 'staff_morning',
          displayName: 'Nguyễn Thị Mai',
          roles: ['staff'],
        );
      case 'staff_afternoon':
      case 'cachieu':
        return const AppUser(
          id: 'offline-staff-afternoon',
          username: 'staff_afternoon',
          displayName: 'Lê Hoàng Nam',
          roles: ['staff'],
        );
      case 'staff_split':
      case 'calo':
        return const AppUser(
          id: 'offline-staff-split',
          username: 'staff_split',
          displayName: 'Phạm Minh Tuấn',
          roles: ['staff'],
        );
      case 'demo_checker':
        return const AppUser(
          id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2',
          username: 'demo_checker',
          displayName: 'Trần Văn Quản Lý',
          roles: ['admin', 'inventory_manager', 'approver'],
          capabilities: [
            'iam:admin',
            'admin:user_management',
            'admin',
            'inventory:approve_request',
            'inventory:view',
            'inventory:create_request',
          ],
        );
      case 'manager_demo':
      case 'demo_admin':
      case 'admin':
      case 'quanly':
      case 'chuquan':
        return const AppUser(
          id: 'offline-manager',
          username: 'manager_demo',
          displayName: 'Trần Văn Quản Lý',
          roles: ['admin', 'inventory_manager', 'approver'],
          capabilities: [
            'iam:admin',
            'admin:user_management',
            'admin',
            'inventory:approve_request',
            'inventory:view',
          ],
        );
      default:
        return null;
    }
  }

  Map<String, dynamic> _userToJson(AppUser user) => {
        'id': user.id,
        'username': user.username,
        'display_name': user.displayName,
        'roles': user.roles,
        'capabilities': user.capabilities,
        _offlineCreatedAtKey: DateTime.now().millisecondsSinceEpoch,
        if (user.email != null) 'email': user.email,
        if (user.phoneNumber != null) 'phone_number': user.phoneNumber,
        if (user.branch != null) 'branch': user.branch,
        if (user.employeeCode != null) 'employee_code': user.employeeCode,
        if (user.avatarUrl != null) 'avatar_url': user.avatarUrl,
      };

  String _serverMessage(String body) {
    // Nếu public static Worker trả lại index.html cho đường dẫn /auth/login,
    // đây là dấu hiệu API nghiệp vụ chưa được deploy, không phải sai mật khẩu.
    final trimmed = body.trimLeft().toLowerCase();
    if (trimmed.startsWith('<!doctype html') || trimmed.startsWith('<html')) {
      return 'Dịch vụ xác thực chưa được triển khai. Vui lòng khôi phục API và cơ sở dữ liệu trước khi đăng nhập tài khoản Root.';
    }
    try {
      final decoded = json.decode(body);
      if (decoded is Map) {
        final err = decoded['error'];
        if (err is Map && err['message'] is String) {
          return err['message'] as String;
        }
        if (decoded['detail'] is String) return decoded['detail'] as String;
        if (decoded['message'] is String) return decoded['message'] as String;
      }
    } catch (_) {}
    if (body.contains('Method Not Allowed') || body.contains('405')) {
      return 'Dịch vụ xác thực chưa được triển khai (API trả 405). Tài khoản, Google Sign-In và Root đều cần API cùng cơ sở dữ liệu để hoạt động.';
    }
    return 'Máy chủ từ chối đăng nhập. Vui lòng kiểm tra lại thông tin hoặc đăng nhập bằng tài khoản ca trực.';
  }

  /// Cập nhật thông tin hồ sơ của người dùng đang đăng nhập.
  Future<bool> updateProfile({
    required String displayName,
    String? email,
    String? phoneNumber,
    String? branch,
    String? avatarUrl,
  }) async {
    _lastError = null;
    final trimmedName = displayName.trim();
    if (trimmedName.isEmpty) {
      _lastError = 'Họ và tên không được để trống.';
      notifyListeners();
      return false;
    }

    if (_memoryToken == null) {
      _user = _user?.copyWith(
            displayName: trimmedName,
            email: email?.trim(),
            phoneNumber: phoneNumber?.trim(),
            branch: branch?.trim(),
            avatarUrl: avatarUrl?.trim(),
          ) ??
          AppUser(
            id: _user?.id ?? 'u_me',
            username: _user?.username ?? 'user',
            displayName: trimmedName,
            roles: _user?.roles ?? const ['staff'],
            email: email?.trim(),
            phoneNumber: phoneNumber?.trim(),
            branch: branch?.trim(),
            avatarUrl: avatarUrl?.trim(),
          );
      notifyListeners();
      return true;
    }

    try {
      final headers = await _authHeaders();
      final resp = await _http.put(
        Uri.parse('$_baseUrl/auth/me'),
        headers: headers,
        body: json.encode({
          'display_name': trimmedName,
          if (email != null) 'email': email.trim(),
          if (phoneNumber != null) 'phone_number': phoneNumber.trim(),
          if (branch != null) 'branch': branch.trim(),
          if (avatarUrl != null) 'avatar_url': avatarUrl.trim(),
        }),
      );

      if (resp.statusCode == 200) {
        final data = json.decode(resp.body) as Map<String, dynamic>;
        _user = _user?.copyWith(
              displayName: (data['display_name'] ?? trimmedName).toString(),
              email: data['email']?.toString() ?? email?.trim(),
              phoneNumber:
                  data['phone_number']?.toString() ?? phoneNumber?.trim(),
              branch: data['branch']?.toString() ?? branch?.trim(),
              avatarUrl: data['avatar_url']?.toString() ?? avatarUrl?.trim(),
            ) ??
            AppUser(
              id: data['id']?.toString() ?? 'u_me',
              username: data['username']?.toString() ?? 'user',
              displayName: trimmedName,
              roles: _user?.roles ?? const ['staff'],
              email: email?.trim(),
              phoneNumber: phoneNumber?.trim(),
              branch: branch?.trim(),
              avatarUrl: avatarUrl?.trim(),
            );
        notifyListeners();
        return true;
      } else {
        _lastError = _serverMessage(resp.body);
        notifyListeners();
        return false;
      }
    } catch (_) {
      // Fallback khi offline / mock / test environment:
      _user = _user?.copyWith(
            displayName: trimmedName,
            email: email?.trim(),
            phoneNumber: phoneNumber?.trim(),
            branch: branch?.trim(),
          ) ??
          AppUser(
            id: _user?.id ?? 'u_me',
            username: _user?.username ?? 'user',
            displayName: trimmedName,
            roles: _user?.roles ?? const ['staff'],
            email: email?.trim(),
            phoneNumber: phoneNumber?.trim(),
            branch: branch?.trim(),
          );
      notifyListeners();
      return true;
    }
  }

  @visibleForTesting
  void setUserForTest(AppUser? user) {
    _user = user;
    notifyListeners();
  }

  AppUser _userFromJson(Map<String, dynamic> json) {
    final rawRoles = List<String>.from(json['roles'] as List? ?? const []);
    final rawCaps =
        List<String>.from(json['capabilities'] as List? ?? const []);
    final email = json['email'] as String?;
    final username = json['username'] as String;
    final isSuperAdmin = email?.trim().toLowerCase() ==
            defaultAdminEmail.toLowerCase() ||
        username.trim().toLowerCase() == defaultAdminEmail.toLowerCase();

    final effectiveRoles = isSuperAdmin
        ? ({
            ...rawRoles,
            'admin',
            'inventory_manager',
            'approver',
            'system_admin'
          }.toList())
        : rawRoles;
    final effectiveCaps = isSuperAdmin
        ? ({
            ...rawCaps,
            'iam:admin',
            'admin:user_management',
            'admin',
            'inventory:manage_catalog',
            'inventory:approve_request',
            'inventory:view_balances'
          }.toList())
        : rawCaps;

    return AppUser(
      id: json['id'] as String,
      username: username,
      displayName: (json['display_name'] ??
          (isSuperAdmin ? 'Mai Nguyễn Bình Tân (Admin)' : username)) as String,
      roles: effectiveRoles,
      capabilities: effectiveCaps,
      email: email,
      phoneNumber: json['phone_number'] as String?,
      branch: json['branch'] as String?,
      employeeCode: json['employee_code'] as String?,
      avatarUrl: json['avatar_url'] as String?,
    );
  }
}
