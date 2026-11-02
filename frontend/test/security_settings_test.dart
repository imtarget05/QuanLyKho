import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/app/theme_mode_controller.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/core/widgets/google_logo.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/auth/auth_service.dart';
import 'package:kho_tra_sua/src/features/auth/login_screen.dart';
import 'package:kho_tra_sua/src/features/auth/widgets/forgot_password_dialog.dart';
import 'package:kho_tra_sua/src/features/settings/settings_screen.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/features/settings/widgets/change_password_dialog.dart';
import 'package:kho_tra_sua/src/features/settings/widgets/change_pin_dialog.dart';
import 'package:kho_tra_sua/src/features/settings/widgets/edit_profile_dialog.dart';
import 'package:kho_tra_sua/src/features/approvals/approvals_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

void main() {
  group('LoginScreen Redesign Tests', () {
    testWidgets('LoginScreen inputs start empty and demo chips are removed',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1200, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final auth = AuthService(baseUrl: 'http://localhost:8000');

      await tester.pumpWidget(
        ChangeNotifierProvider<AuthService>.value(
          value: auth,
          child: MaterialApp(
            theme: AppTheme.light(),
            home: const LoginScreen(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Check username & password fields are empty
      final usernameField = tester
          .widget<TextField>(find.byKey(const Key('login-username-field')));
      final passwordField = tester
          .widget<TextField>(find.byKey(const Key('login-password-field')));

      expect(usernameField.controller?.text, isEmpty);
      expect(passwordField.controller?.text, isEmpty);

      // Verify quick demo chips and reviewer sandbox are removed
      expect(find.byKey(const Key('login-demo-maker-chip')), findsNothing);
      expect(find.byKey(const Key('login-demo-checker-chip')), findsNothing);
      expect(find.byKey(const Key('login-demo-auditor-chip')), findsNothing);
      expect(find.text('CHỌN NHANH VAI TRÒ DEMO'), findsNothing);
      expect(find.byKey(const Key('login-reviewer-sandbox-btn')), findsNothing);
      expect(find.byKey(const Key('login-shift-morning-chip')), findsNothing);
      expect(find.byKey(const Key('login-shift-afternoon-chip')), findsNothing);
      expect(find.byKey(const Key('login-shift-split-chip')), findsNothing);
      expect(find.byKey(const Key('login-shift-manager-chip')), findsNothing);
      expect(find.text('TÀI KHOẢN CA TRỰC (DEMO)'), findsNothing);

      // Verify submit button has updated title
      expect(
        find.descendant(
          of: find.byKey(const Key('login-submit-btn')),
          matching: find.text('Đăng nhập hệ thống'),
        ),
        findsOneWidget,
      );

      // Verify Google button exists with GoogleLogo and official text
      final googleBtn = find.byKey(const Key('login-google-btn'));
      expect(googleBtn, findsOneWidget);
      expect(find.descendant(of: googleBtn, matching: find.byType(GoogleLogo)),
          findsOneWidget);
      expect(find.text('Đăng nhập bằng Google'), findsOneWidget);

      // Verify Forgot Password button exists
      final forgotBtn = find.byKey(const Key('login-forgot-password-btn'));
      expect(forgotBtn, findsOneWidget);
      expect(find.text('Quên mật khẩu?'), findsOneWidget);
    });
  });

  group('ChangePasswordDialog Tests', () {
    testWidgets('Validates inputs and calls repository on valid submission',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1200, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (ctx) => ElevatedButton(
                onPressed: () => showDialog(
                  context: ctx,
                  builder: (_) => RepositoryScope(
                    repository: fakeRepo,
                    child: const ChangePasswordDialog(),
                  ),
                ),
                child: const Text('Open Dialog'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open Dialog'));
      await tester.pumpAndSettle();

      expect(find.byType(ChangePasswordDialog), findsOneWidget);

      // Test validation: submit with empty inputs
      await tester.tap(find.byKey(const Key('change-password-submit-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Vui lòng nhập mật khẩu hiện tại.'), findsOneWidget);

      // Enter old password, short new password (<6 chars)
      await tester.enterText(
          find.byKey(const Key('change-password-old-field')), 'oldpass123');
      await tester.enterText(
          find.byKey(const Key('change-password-new-field')), '12345');
      await tester.tap(find.byKey(const Key('change-password-submit-btn')));
      await tester.pumpAndSettle();
      expect(
          find.text('Mật khẩu mới phải có ít nhất 6 ký tự.'), findsOneWidget);

      // Enter same new password as old password
      await tester.enterText(
          find.byKey(const Key('change-password-new-field')), 'oldpass123');
      await tester.tap(find.byKey(const Key('change-password-submit-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Mật khẩu mới không được trùng với mật khẩu cũ.'),
          findsOneWidget);

      // Enter mismatched confirm password
      await tester.enterText(
          find.byKey(const Key('change-password-new-field')), 'newpass123');
      await tester.enterText(
          find.byKey(const Key('change-password-confirm-field')), 'wrongpass');
      await tester.tap(find.byKey(const Key('change-password-submit-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Mật khẩu xác nhận không trùng khớp.'), findsOneWidget);

      // Enter matching confirm password and submit successfully
      await tester.enterText(
          find.byKey(const Key('change-password-confirm-field')), 'newpass123');
      await tester.tap(find.byKey(const Key('change-password-submit-btn')));
      await tester.pumpAndSettle();

      // Dialog should close after success
      expect(find.byType(ChangePasswordDialog), findsNothing);
    });
  });

  group('ChangePinDialog Tests', () {
    testWidgets(
        'Validates 6-digit PIN and calls repository on valid submission',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1200, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (ctx) => ElevatedButton(
                onPressed: () => showDialog(
                  context: ctx,
                  builder: (_) => RepositoryScope(
                    repository: fakeRepo,
                    child: const ChangePinDialog(),
                  ),
                ),
                child: const Text('Open PIN Dialog'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open PIN Dialog'));
      await tester.pumpAndSettle();

      expect(find.byType(ChangePinDialog), findsOneWidget);

      // Test validation: submit empty
      await tester.tap(find.byKey(const Key('change-pin-submit-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Vui lòng nhập mật khẩu tài khoản để xác thực.'),
          findsOneWidget);

      // Enter password, invalid PIN (< 6 digits)
      await tester.enterText(
          find.byKey(const Key('change-pin-password-field')), 'MyPassword123');
      await tester.enterText(
          find.byKey(const Key('change-pin-new-field')), '1234');
      await tester.tap(find.byKey(const Key('change-pin-submit-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Mã PIN mới phải gồm đúng 6 chữ số (0-9).'),
          findsOneWidget);

      // Enter mismatched confirm PIN
      await tester.enterText(
          find.byKey(const Key('change-pin-new-field')), '654321');
      await tester.enterText(
          find.byKey(const Key('change-pin-confirm-field')), '111111');
      await tester.tap(find.byKey(const Key('change-pin-submit-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Mã PIN xác nhận không trùng khớp.'), findsOneWidget);

      // Enter valid 6 digits matching PIN
      await tester.enterText(
          find.byKey(const Key('change-pin-confirm-field')), '654321');
      await tester.tap(find.byKey(const Key('change-pin-submit-btn')));
      await tester.pumpAndSettle();

      // Dialog should close after success
      expect(find.byType(ChangePinDialog), findsNothing);
    });
  });

  group('SettingsScreen Security Options Tests', () {
    testWidgets(
        'SettingsScreen displays change password and removed change PIN action',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1200, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);
      final auth = AuthService(baseUrl: 'http://localhost:8000');
      final themeController = ThemeModeController();

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<AuthService>.value(value: auth),
            ChangeNotifierProvider<ThemeModeController>.value(
                value: themeController),
          ],
          child: MaterialApp(
            home: RepositoryScope(
              repository: fakeRepo,
              child: const SettingsScreen(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Tài khoản & Bảo mật'), findsOneWidget);
      expect(find.byKey(const Key('settings-change-password-tile')),
          findsOneWidget);
      expect(find.byKey(const Key('settings-change-pin-tile')), findsNothing);

      // Tap change password tile opens dialog
      await tester.ensureVisible(
          find.byKey(const Key('settings-change-password-tile')));
      await tester.tap(find.byKey(const Key('settings-change-password-tile')));
      await tester.pumpAndSettle();
      expect(find.byType(ChangePasswordDialog), findsOneWidget);

      // Close dialog
      await tester.tap(find.byKey(const Key('change-password-cancel-btn')));
      await tester.pumpAndSettle();
      expect(find.byType(ChangePasswordDialog), findsNothing);
    });

    testWidgets(
        'SettingsScreen does not display demo accounts, simulation disclaimers, or reset commands',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1200, 1600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);
      final auth = AuthService(baseUrl: 'http://localhost:8000');
      final themeController = ThemeModeController();

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<AuthService>.value(value: auth),
            ChangeNotifierProvider<ThemeModeController>.value(
                value: themeController),
          ],
          child: MaterialApp(
            home: RepositoryScope(
              repository: fakeRepo,
              child: const SettingsScreen(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify demo elements are removed
      expect(find.text('Dữ liệu demo'), findsNothing);
      expect(find.text('Môi trường giả lập'), findsNothing);
      expect(find.text('Tài khoản demo'), findsNothing);
      expect(find.text('Reset demo về dữ liệu gốc'), findsNothing);
      expect(
          find.byKey(const Key('settings-copy-reset-cmd-btn')), findsNothing);
      expect(find.textContaining('DemoPass123!'), findsNothing);
      expect(find.textContaining('Bản demo — mọi dữ liệu là giả lập.'),
          findsNothing);

      // Verify enterprise sections exist
      expect(find.text('Hồ Sơ Của Tôi'), findsOneWidget);
      expect(find.text('Tài khoản & Bảo mật'), findsOneWidget);
      expect(find.text('Hệ thống & Cổng kết nối API'), findsNothing);
      expect(find.text('Quản lý kho'), findsOneWidget);
      expect(find.text('Đăng xuất'), findsOneWidget);
    });
  });

  group('ForgotPasswordDialog Tests', () {
    testWidgets('Validates 2-step OTP flow and resets password',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1200, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (ctx) => ElevatedButton(
                onPressed: () => showDialog(
                  context: ctx,
                  builder: (_) => RepositoryScope(
                    repository: fakeRepo,
                    child: const ForgotPasswordDialog(),
                  ),
                ),
                child: const Text('Open Forgot Dialog'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open Forgot Dialog'));
      await tester.pumpAndSettle();

      expect(find.byType(ForgotPasswordDialog), findsOneWidget);
      expect(
          find.text('Bước 1/2: Xác thực tài khoản người dùng'), findsOneWidget);

      // Submit empty username -> error
      await tester.tap(find.byKey(const Key('forgot-password-send-otp-btn')));
      await tester.pumpAndSettle();
      expect(
          find.text('Vui lòng nhập tên đăng nhập hoặc email.'), findsOneWidget);

      // Submit invalid user -> error
      await tester.enterText(
          find.byKey(const Key('forgot-password-username-field')),
          'non_existent_user');
      await tester.tap(find.byKey(const Key('forgot-password-send-otp-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Không tìm thấy tài khoản với tên đăng nhập này.'),
          findsOneWidget);

      // Submit valid demo user -> advances to Step 2
      await tester.enterText(
          find.byKey(const Key('forgot-password-username-field')),
          'demo_maker');
      await tester.tap(find.byKey(const Key('forgot-password-send-otp-btn')));
      await tester.pumpAndSettle();

      expect(find.text('Bước 2/2: Nhập mã OTP & Đặt mật khẩu mới'),
          findsOneWidget);
      expect(find.textContaining('Mã OTP mô phỏng: '), findsOneWidget);

      // Clear OTP and submit -> error
      await tester.enterText(
          find.byKey(const Key('forgot-password-otp-field')), '12');
      await tester.tap(find.byKey(const Key('forgot-password-submit-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Mã OTP phải gồm đúng 6 chữ số.'), findsOneWidget);

      // Enter OTP 123456, short password -> error
      await tester.enterText(
          find.byKey(const Key('forgot-password-otp-field')), '123456');
      await tester.enterText(
          find.byKey(const Key('forgot-password-new-field')), '12345');
      await tester.tap(find.byKey(const Key('forgot-password-submit-btn')));
      await tester.pumpAndSettle();
      expect(
          find.text('Mật khẩu mới phải có tối thiểu 6 ký tự.'), findsOneWidget);

      // Mismatched confirm password -> error
      await tester.enterText(
          find.byKey(const Key('forgot-password-new-field')), 'Password123!');
      await tester.enterText(
          find.byKey(const Key('forgot-password-confirm-field')),
          'DifferentPassword!');
      await tester.tap(find.byKey(const Key('forgot-password-submit-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Mật khẩu xác nhận không trùng khớp.'), findsOneWidget);

      // Test Back button returns to Step 1
      await tester.tap(find.byKey(const Key('forgot-password-back-btn')));
      await tester.pumpAndSettle();
      expect(
          find.text('Bước 1/2: Xác thực tài khoản người dùng'), findsOneWidget);

      // Re-advance to Step 2
      await tester.tap(find.byKey(const Key('forgot-password-send-otp-btn')));
      await tester.pumpAndSettle();

      // Submit valid OTP and matching password
      await tester.enterText(
          find.byKey(const Key('forgot-password-otp-field')), '123456');
      await tester.enterText(
          find.byKey(const Key('forgot-password-new-field')), 'Password123!');
      await tester.enterText(
          find.byKey(const Key('forgot-password-confirm-field')),
          'Password123!');
      await tester.tap(find.byKey(const Key('forgot-password-submit-btn')));
      await tester.pumpAndSettle();

      // Dialog should close after success
      expect(find.byType(ForgotPasswordDialog), findsNothing);
    });

    testWidgets(
        'LoginScreen Quên mật khẩu button opens dialog and sets username',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1200, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);
      final auth = AuthService(baseUrl: 'http://localhost:8000');

      await tester.pumpWidget(
        ChangeNotifierProvider<AuthService>.value(
          value: auth,
          child: MaterialApp(
            home: RepositoryScope(
              repository: fakeRepo,
              child: const LoginScreen(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tap Quên mật khẩu button
      await tester.tap(find.byKey(const Key('login-forgot-password-btn')));
      await tester.pumpAndSettle();

      expect(find.byType(ForgotPasswordDialog), findsOneWidget);

      // Enter demo_checker in dialog
      await tester.enterText(
          find.byKey(const Key('forgot-password-username-field')),
          'demo_checker');
      await tester.tap(find.byKey(const Key('forgot-password-send-otp-btn')));
      await tester.pumpAndSettle();

      // Set new password
      await tester.enterText(
          find.byKey(const Key('forgot-password-otp-field')), '123456');
      await tester.enterText(
          find.byKey(const Key('forgot-password-new-field')), 'ResetPass2026!');
      await tester.enterText(
          find.byKey(const Key('forgot-password-confirm-field')),
          'ResetPass2026!');
      await tester.tap(find.byKey(const Key('forgot-password-submit-btn')));
      await tester.pumpAndSettle();

      // Dialog closed and login username field populated with demo_checker
      expect(find.byType(ForgotPasswordDialog), findsNothing);
      final usernameField = tester
          .widget<TextField>(find.byKey(const Key('login-username-field')));
      expect(usernameField.controller?.text, 'demo_checker');
      expect(find.text('Khôi phục mật khẩu thành công! Vui lòng đăng nhập.'),
          findsOneWidget);
    });
  });

  group('SettingsScreen My Profile Tests', () {
    testWidgets(
        'SettingsScreen displays My Profile card with full user information',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1200, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);
      final auth = AuthService(baseUrl: 'http://localhost:8000');
      const testUser = AppUser(
        id: 'u_test_maker',
        username: 'demo_maker',
        displayName: 'Nguyễn Văn Maker',
        roles: ['maker', 'staff'],
        email: 'maker@bankops.vn',
        phoneNumber: '0901 234 567',
        branch: 'Chi nhánh Bến Thành (Hội sở)',
        employeeCode: 'BO-8892',
      );
      auth.setUserForTest(testUser);
      final themeController = ThemeModeController();

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<AuthService>.value(value: auth),
            ChangeNotifierProvider<ThemeModeController>.value(
                value: themeController),
          ],
          child: MaterialApp(
            home: RepositoryScope(
              repository: fakeRepo,
              child: const SettingsScreen(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Check section header and profile details
      expect(find.text('Hồ Sơ Của Tôi'), findsOneWidget);
      expect(find.text('Nguyễn Văn Maker'), findsOneWidget);
      expect(find.text('@demo_maker · Mã NV: BO-8892'), findsOneWidget);
      expect(find.text('NHÂN VIÊN LẬP PHIẾU'), findsOneWidget);
      expect(find.text('Hoạt động'), findsOneWidget);
      expect(find.text('maker@bankops.vn'), findsOneWidget);
      expect(find.text('0901 234 567'), findsOneWidget);
      expect(find.text('Chi nhánh Bến Thành (Hội sở)'), findsOneWidget);
      expect(find.text('ISO 27001 · Dual Control Active'), findsOneWidget);
      expect(
          find.byKey(const Key('settings-edit-profile-btn')), findsOneWidget);
    });

    testWidgets(
        'EditProfileDialog validates inputs and updates user profile in settings',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1200, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);
      final auth = AuthService(baseUrl: 'http://localhost:8000');
      const testUser = AppUser(
        id: 'u_test_maker',
        username: 'demo_maker',
        displayName: 'Nguyễn Văn Maker',
        roles: ['maker', 'staff'],
        email: 'maker@bankops.vn',
        phoneNumber: '0901 234 567',
        branch: 'Chi nhánh Bến Thành (Hội sở)',
        employeeCode: 'BO-8892',
      );
      auth.setUserForTest(testUser);
      final themeController = ThemeModeController();

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<AuthService>.value(value: auth),
            ChangeNotifierProvider<ThemeModeController>.value(
                value: themeController),
          ],
          child: MaterialApp(
            home: RepositoryScope(
              repository: fakeRepo,
              child: const SettingsScreen(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tap Edit Profile button
      await tester
          .ensureVisible(find.byKey(const Key('settings-edit-profile-btn')));
      await tester.tap(find.byKey(const Key('settings-edit-profile-btn')));
      await tester.pumpAndSettle();

      expect(find.byType(EditProfileDialog), findsOneWidget);
      expect(find.text('Chỉnh sửa hồ sơ cá nhân'), findsOneWidget);

      // Verify fields are pre-filled
      final nameField = tester
          .widget<TextField>(find.byKey(const Key('edit-profile-name-field')));
      expect(nameField.controller?.text, 'Nguyễn Văn Maker');

      // Test validation: empty name
      await tester.enterText(
          find.byKey(const Key('edit-profile-name-field')), '');
      await tester.tap(find.byKey(const Key('edit-profile-save-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Vui lòng nhập họ và tên.'), findsOneWidget);

      // Test validation: invalid email
      await tester.enterText(
          find.byKey(const Key('edit-profile-name-field')), 'Nguyễn Hoàng An');
      await tester.enterText(
          find.byKey(const Key('edit-profile-email-field')), 'invalid-email');
      await tester.tap(find.byKey(const Key('edit-profile-save-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Địa chỉ email không đúng định dạng.'), findsOneWidget);

      // Fill valid information and submit
      await tester.enterText(find.byKey(const Key('edit-profile-name-field')),
          'Nguyễn Hoàng An (Trưởng GDV)');
      await tester.enterText(find.byKey(const Key('edit-profile-email-field')),
          'hoangan@bankops.vn');
      await tester.enterText(
          find.byKey(const Key('edit-profile-phone-field')), '0912 345 678');
      await tester.enterText(find.byKey(const Key('edit-profile-branch-field')),
          'Sở Giao Dịch TP.HCM');

      await tester.tap(find.byKey(const Key('edit-profile-save-btn')));
      await tester.pumpAndSettle();

      // Dialog closed
      expect(find.byType(EditProfileDialog), findsNothing);

      // Verify SettingsScreen updated reactively
      expect(find.text('Nguyễn Hoàng An (Trưởng GDV)'), findsOneWidget);
      expect(find.text('hoangan@bankops.vn'), findsOneWidget);
      expect(find.text('0912 345 678'), findsOneWidget);
      expect(find.text('Sở Giao Dịch TP.HCM'), findsOneWidget);
      expect(find.text('Cập nhật hồ sơ cá nhân thành công!'), findsOneWidget);
    });
  });

  group('Supervisor PIN Dual-Control Integration Tests', () {
    testWidgets(
        'Change PIN updates fake repo supervisorPin and ApprovalsScreen enforces new PIN',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);

      // Initially, supervisorPin is 123456
      expect(fakeRepo.supervisorPin, '123456');

      // Change PIN to 654321 via changePin
      await fakeRepo.changePin(
          currentPassword: 'DemoPass123!', newPin: '654321');
      expect(fakeRepo.supervisorPin, '654321');

      // Create high-risk cash request: 600,000,000 VND
      final created = await fakeRepo.createCashRequest(
        cashboxId: '11111111-1111-4111-8111-111111111111',
        kind: RequestKind.receipt,
        amount: '600000000.00',
        reason: 'Tiếp quỹ lớn',
      );
      await fakeRepo.submitCashRequest(created.id);

      await tester.pumpWidget(
        RepositoryScope(
          repository: fakeRepo,
          child: MaterialApp(
            theme: AppTheme.light(),
            home: const Scaffold(body: ApprovalsScreen()),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tap approve
      await tester.tap(find.byKey(Key('btn-approve-${created.id}')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(
          find.text('Xác Thực Quyền Kiểm Soát Kép (Supervisor Authorization)'),
          findsOneWidget);
      expect(
          find.text('Nhập PIN demo Kiểm soát viên (654321):'), findsOneWidget);

      // Enter old PIN 123456 -> rejected!
      await tester.enterText(
          find.byKey(const Key('supervisor-pin-input')), '123456');
      await tester.tap(find.byKey(const Key('confirm-supervisor-pin-btn')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.textContaining('Mã PIN không đúng (Demo: 654321)'),
          findsOneWidget);

      // Enter new PIN 654321 -> approved!
      await tester.enterText(
          find.byKey(const Key('supervisor-pin-input')), '654321');
      await tester.tap(find.byKey(const Key('confirm-supervisor-pin-btn')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byKey(Key('approval-card-${created.id}')), findsNothing);
    });
  });
}
