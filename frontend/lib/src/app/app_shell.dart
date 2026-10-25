import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';

import '../data/models/dtos.dart';
import '../data/repositories/bankops_repository.dart';
import '../core/sync/data_sync_controller.dart';
import '../core/theme/app_tokens.dart';
import '../core/theme/app_ui_settings_controller.dart';
import '../core/i18n/app_i18n.dart';
import '../core/i18n/locale_controller.dart';
import '../core/util/role_visibility.dart';
import '../core/widgets/app_screen.dart';
import '../core/offline/offline_ui.dart';
import '../core/offline/stocktake_outbox.dart';
import '../core/util/web_helpers.dart';
import '../core/widgets/app_toast.dart';
import '../core/widgets/global_search.dart';
import '../core/widgets/store_logo.dart';
import '../core/widgets/user_avatar.dart';
import 'theme_mode_controller.dart';
import '../data/repositories/http_bankops_repository.dart';
import '../data/repositories/fake_repository.dart';
import '../features/activity/activity_screen.dart';
import '../features/approvals/approvals_screen.dart';
import '../features/auth/auth_service.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/inventory/inventory_screen.dart';
import '../features/reports/reports_screen.dart';
import '../features/requests/requests_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/ai/ai_assistant_dialog.dart';
import '../features/admin/employee_management_screen.dart';

class SessionScope extends InheritedWidget {
  const SessionScope(
      {super.key, required super.child, this.user, this.onSignOut});
  final AppUser? user;
  final Future<void> Function()? onSignOut;

  static SessionScope? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<SessionScope>();

  @override
  bool updateShouldNotify(SessionScope old) =>
      old.user != user || old.onSignOut != onSignOut;
}

class RepositoryScope extends InheritedWidget {
  const RepositoryScope(
      {super.key, required this.repository, required super.child});

  final BankOpsRepository repository;

  static BankOpsRepository? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<RepositoryScope>()?.repository;

  static BankOpsRepository of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<RepositoryScope>()!.repository;

  @override
  bool updateShouldNotify(RepositoryScope old) => repository != old.repository;
}

/// Shell 3-tier theo docs/07-flutter.md:
/// <600 bottom nav 4 mục + More | 600–1199 rail | >=1200 sidebar + topbar.
class AppShell extends StatefulWidget {
  const AppShell({super.key, this.repository});

  final BankOpsRepository? repository;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  BankOpsRepository? _repository;
  String? _repositoryUserId;
  String? _repositoryBranch;
  int _index = 0;
  int _refreshTick = 0;
  late final DataSyncController _syncController = DataSyncController();
  final GlobalKey _bodySubtreeKey = GlobalKey();
  int _pendingApprovalCount = 0;
  int _requestsNavId = 0;
  bool _autoOpenStockRequest = false;
  bool _autoOpenCashRequest = false;
  String? _inventoryInitialCategory;
  String? _inventoryInitialStockFilter;
  String? _inventoryInitialViewMode;
  String? _inventoryInitialLocationId;
  String? _inventoryInitialSearchQuery;
  String? _inventoryInitialItemId;
  String? _pendingStockLocationId;
  String? _pendingStockItemId;
  double? _pendingStockQuantity;
  int _inventoryNavKey = 0;
  /// Tạm thời ẩn chat bot trợ lý theo yêu cầu người dùng
  static const bool _enableAiAssistant = false;
  bool _aiUnavailable = false;
  bool _isUpdateAvailable = false;
  Timer? _offlinePingTimer;

  @override
  void initState() {
    super.initState();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    _syncController.addListener(_onSyncSignal);
    OfflineHub.instance.listen(_onOfflineHubChanged);
    onAppUpdateAvailable(() {
      if (mounted) {
        setState(() => _isUpdateAvailable = true);
      }
    });
  }

  void _onSyncSignal() {
    if (!mounted) return;
    final repo = _repository;
    if (repo != null) {
      _fetchPendingCount(repo);
    }
    final event = _syncController.lastEvent;
    if (event != null &&
        (event.action == 'submitted' || event.action == 'create') &&
        _canAccessApprovals(SessionScope.maybeOf(context))) {
      AppToast.info(
        context,
        event.message ??
            '🔔 Yêu cầu mới chờ phê duyệt kiểm soát kép (Dual Control)!',
      );
    }
  }

  void _onOfflineHubChanged() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (widget.repository != null) {
      _repository = widget.repository;
      _startOfflinePing();
    } else {
      final auth = Provider.of<AuthService?>(context);
      final wantsOfflineDemo = auth?.isOfflineSession ?? false;
      final usingOfflineDemo = _repository is FakeBankOpsRepository;
      final userId = auth?.user?.id;
      final branch = auth?.user?.branch;
      if (_repository == null || usingOfflineDemo != wantsOfflineDemo ||
          _repositoryUserId != userId || _repositoryBranch != branch) {
        _repository?.dispose();
        _repositoryUserId = userId;
        _repositoryBranch = branch;
        _repository = wantsOfflineDemo
            ? FakeBankOpsRepository()
            : HttpBankOpsRepository(
                baseUrl: auth?.apiBaseUrl,
                tokenProvider: () async {
                  if (auth?.user?.id != userId || auth?.user?.branch != branch) {
                    return null;
                  }
                  final token = await auth?.getAccessToken();
                  if (auth?.user?.id != userId || auth?.user?.branch != branch) {
                    return null;
                  }
                  return token;
                },
              );
      }
      _startOfflinePing();
    }
    _syncController.bindRepository(_repository);
    OfflineHub.instance.repository = _repository;
    final sessionUser = SessionScope.maybeOf(context)?.user ??
        Provider.of<AuthService?>(context, listen: false)?.user;
    OfflineHub.instance.currentUserId = sessionUser?.id;
    OfflineHub.instance.currentBranch = sessionUser?.branch;
    OfflineHub.instance.onSynced = () {
      if (mounted) setState(() => _refreshTick++);
    };
    StocktakeOutbox.shared.bindIdentity(sessionUser?.id, sessionUser?.branch).then((_) async {
      if (mounted && OfflineHub.instance.currentUserId == sessionUser?.id &&
          OfflineHub.instance.currentBranch == sessionUser?.branch) {
        await OfflineHub.instance.refreshLegacy();
        if (mounted && OfflineHub.instance.currentUserId == sessionUser?.id &&
            OfflineHub.instance.currentBranch == sessionUser?.branch) {
          OfflineHub.instance.addQueued();
          OfflineHub.instance.flushNow();
        }
      }
    });
    if (_repository != null) {
      _fetchPendingCount(_repository!);
    }

    final repo = _repository;
    if (repo != null && repo is HttpBankOpsRepository) {
      final base = repo.baseUrl.replaceFirst(RegExp(r'/+$'), '');
      OfflineHub.instance.pingUrl = '$base/health/live';
    } else {
      final auth = Provider.of<AuthService?>(context, listen: false);
      if (auth != null && auth.apiBaseUrl.isNotEmpty) {
        final base = auth.apiBaseUrl.replaceFirst(RegExp(r'/+$'), '');
        OfflineHub.instance.pingUrl = '$base/health/live';
      }
    }
  }

  /// Thu thập lại trạng thái mạng mỗi 30s (ping health của backend), cập nhật
  /// [OfflineHub] để hiển thị banner "Ngoại tuyến - sẽ đồng bộ".
  Future<void> _pingHealth() async {
    try {
      final res = await http
          .get(Uri.parse(OfflineHub.instance.pingUrl))
          .timeout(const Duration(seconds: 8));
      if (res.statusCode >= 200 && res.statusCode < 300) {
        OfflineHub.instance.markOnline();
        OfflineHub.instance.flushNow();
        _aiUnavailable = false;
      } else if (res.statusCode == 503) {
        // Gateway trả 503 khi upstream chưa được cấu hình (ví dụ Render DB
        // chưa sẵn sàng), hoặc backend đã tắt AI. Lúc này AI không thể dùng
        // được từ mọi màn hình, nên ẩn FAB thay vì hiển thị 'Offline'.
        try {
          final decoded = json.decode(utf8.decode(res.bodyBytes));
          final code = (decoded as Map)['error']['code'] as String?;
          if (code == 'UPSTREAM_NOT_CONFIGURED' || code == 'AI_UNAVAILABLE') {
            _aiUnavailable = true;
          }
        } catch (_) {
          // Không thể đọc body 503 -> giữ Idle.
        }
        OfflineHub.instance.markOffline();
      } else {
        OfflineHub.instance.markOffline();
      }
    } catch (_) {
      OfflineHub.instance.markOffline();
    }
  }

  void _startOfflinePing() {
    if (_offlinePingTimer?.isActive ?? false) return;
    _offlinePingTimer = Timer.periodic(const Duration(seconds: 30), (timer) {
      _pingHealth();
    });
  }

  @override
  void dispose() {
    _offlinePingTimer?.cancel();
    OfflineHub.instance.onSynced = null;
    OfflineHub.instance.repository = null;
    OfflineHub.instance.currentUserId = null;
    OfflineHub.instance.currentBranch = null;
    OfflineHub.instance.cancelRetry();
    StocktakeOutbox.shared.bindIdentity(null, null);
    OfflineHub.instance.unlisten(_onOfflineHubChanged);
    _syncController.removeListener(_onSyncSignal);
    _syncController.dispose();
    _repository?.dispose();
    super.dispose();
  }


  Future<void> _fetchPendingCount(BankOpsRepository repo) async {
    try {
      final items = await repo.getApprovalInbox();
      if (mounted) {
        setState(() {
          _pendingApprovalCount = items.length;
        });
      }
    } catch (_) {}
  }

  static const _items = <_Item>[
    _Item(0, 'Tổng quan', Icons.dashboard_outlined, Icons.dashboard),
    _Item(1, 'Kho', Icons.inventory_2_outlined, Icons.inventory_2),
    _Item(2, 'Ca làm việc', Icons.schedule_outlined, Icons.schedule),
    _Item(3, 'Yêu cầu', Icons.receipt_long_outlined, Icons.receipt_long),
    _Item(4, 'Duyệt', Icons.fact_check_outlined, Icons.fact_check),
    _Item(6, 'Hoạt động', Icons.timeline_outlined, Icons.timeline),
    _Item(7, 'Báo cáo', Icons.insert_chart_outlined, Icons.insert_chart),
    _Item(8, 'Cài đặt', Icons.settings_outlined, Icons.settings),
    _Item(
        9, 'Nhân viên', Icons.manage_accounts_outlined, Icons.manage_accounts),
  ];

  String _labelFor(BuildContext context, int index) {
    const keys = <String>[
      'nav_dashboard',
      'nav_inventory',
      'nav_shift_work',
      'nav_requests',
      'nav_approvals',
      'nav_integrations',
      'nav_activity',
      'nav_reports',
      'nav_settings',
      'nav_employees',
    ];
    if (index >= 0 && index < keys.length) {
      return context.tr(keys[index]);
    }
    return '';
  }

  String _titleFor(BuildContext context, int index) =>
      _labelFor(context, index);

  static const _slugs = <String>[
    'dashboard',
    'inventory',
    'cash',
    'requests',
    'approvals',
    'integrations',
    'activity',
    'reports',
    'settings',
    'employees',
  ];

  static const _icons = <IconData>[
    Icons.dashboard_outlined,
    Icons.inventory_2_outlined,
    Icons.schedule_outlined,
    Icons.receipt_long_outlined,
    Icons.fact_check_outlined,
    Icons.timeline_outlined,
    Icons.timeline_outlined,
    Icons.insert_chart_outlined,
    Icons.settings_outlined,
    Icons.manage_accounts_outlined,
  ];

  static const _filled = <IconData>[
    Icons.dashboard,
    Icons.inventory_2,
    Icons.schedule,
    Icons.receipt_long,
    Icons.fact_check,
    Icons.timeline,
    Icons.timeline,
    Icons.insert_chart,
    Icons.settings,
    Icons.manage_accounts,
  ];

  bool _canAccessApprovals(SessionScope? session) {
    final user = session?.user;
    if (user == null) {
      return true; // Giữ nguyên cho unauthenticated & widget tests
    }
    final roles = RoleVisibility.rolesOf(user);
    return !RoleVisibility.isAuditorOnly(roles);
  }

  Widget _screenFor(int i, SessionScope? session) {
    if (i == 4 && !_canAccessApprovals(session)) {
      return Center(
        child: Container(
          padding: const EdgeInsets.all(32),
          constraints: const BoxConstraints(maxWidth: 480),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.gpp_bad_outlined,
                  size: 64, color: Color(0xFFF59E0B)),
              const SizedBox(height: 16),
              Text(
                context.tr('nav_access_denied_title'),
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                context.tr('nav_auditor_denied'),
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xFF64748B)),
              ),
              const SizedBox(height: 20),
              FilledButton.icon(
                icon: const Icon(Icons.arrow_back),
                label: Text(context.tr('nav_access_denied_back')),
                onPressed: () => setState(() => _index = 0),
              ),
            ],
          ),
        ),
      );
    }
    switch (i) {
      case 0:
        return DashboardScreen(onNavigate: _go);
      case 1:
        return InventoryScreen(
          key: ValueKey('inventory-$_inventoryNavKey'),
          mode: InventoryTabMode.stock,
          onNavigate: _go,
          onCreateStockRequest: ({locationId, itemId, suggestedQty}) => _go(
            3,
            autoOpenStock: true,
            initialStockLocationId: locationId,
            initialStockItemId: itemId,
            initialStockQuantity: suggestedQty,
          ),
          initialCategory: _inventoryInitialCategory,
          initialStockFilter: _inventoryInitialStockFilter,
          initialViewMode: _inventoryInitialViewMode,
          initialLocationId: _inventoryInitialLocationId,
          initialSearchQuery: _inventoryInitialSearchQuery,
          initialItemId: _inventoryInitialItemId,
        );
      case 2:
        return InventoryScreen(
          mode: InventoryTabMode.shiftWork,
          onNavigate: _go,
          onCreateStockRequest: ({locationId, itemId, suggestedQty}) => _go(
            3,
            autoOpenStock: true,
            initialStockLocationId: locationId,
            initialStockItemId: itemId,
            initialStockQuantity: suggestedQty,
          ),
        );
      case 3:
        return RequestsScreen(
          key: ValueKey('requests-$_requestsNavId'),
          initialOpenCreateStock: _autoOpenStockRequest,
          initialOpenCreateCash: _autoOpenCashRequest,
          initialLocationId: _pendingStockLocationId,
          initialItemId: _pendingStockItemId,
          initialQuantity: _pendingStockQuantity,
          onInitialOpenHandled: () {
            if (mounted) {
              setState(() {
                _autoOpenStockRequest = false;
                _autoOpenCashRequest = false;
                _pendingStockLocationId = null;
                _pendingStockItemId = null;
                _pendingStockQuantity = null;
              });
            }
          },
        );
      case 4:
        return const ApprovalsScreen();
      case 5:
        // Pilot trà sữa: ẩn Tích hợp/ETL khỏi UI chính.
        return const ActivityScreen();
      case 6:
        return const ActivityScreen();
      case 7:
        return const ReportsScreen();
      case 8:
        return const SettingsScreen();
      case 9:
        if (!RoleVisibility.canManageEmployees(session?.user)) {
          return Center(
            child: Container(
              padding: const EdgeInsets.all(32),
              constraints: const BoxConstraints(maxWidth: 480),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.gpp_bad_outlined,
                      size: 64, color: Color(0xFFEF4444)),
                  const SizedBox(height: 16),
                  Text(
                    context.tr('nav_access_denied_title'),
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    context.tr('nav_admin_denied'),
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Color(0xFF64748B)),
                  ),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    icon: const Icon(Icons.arrow_back),
                    label: Text(context.tr('nav_access_denied_back')),
                    onPressed: () => setState(() => _index = 0),
                  ),
                ],
              ),
            ),
          );
        }
        return const EmployeeManagementScreen();
      default:
        return const SizedBox.shrink();
    }
  }

  Future<void> _reload() async {
    setState(() => _refreshTick++);
  }

  void _openSettings() {
    _go(8);
  }

  Future<void> _openSearch() async {
    final repo = _repository;
    if (repo == null) return;
    final res = await showGlobalSearch(context, repo);
    if (res != null && mounted) {
      _go(
        res.tabIndex,
        searchQuery: res.query,
        initialStockItemId: res.itemId,
        locationId: res.locationId,
      );
    }
  }

  /// Điều hướng có kiểm tra quyền hiển thị theo vai trò (RoleVisibility).
  /// Tab bị ẩn với role hiện tại -> toast + ở yên, không chuyển.
  void _go(
    int i, {
    bool autoOpenStock = false,
    bool autoOpenCash = false,
    String? category,
    String? stockFilter,
    String? viewMode,
    String? locationId,
    String? initialStockItemId,
    String? initialStockLocationId,
    double? initialStockQuantity,
    String? searchQuery,
  }) {
    final session = SessionScope.maybeOf(context);
    final roles = RoleVisibility.rolesOf(session?.user);
    if (!RoleVisibility.visibleTabs(roles, session?.user).contains(i)) {
      AppToast.info(context, 'Vai trò của bạn không có quyền vào phân hệ này');
      return;
    }
    setState(() {
      _index = i;
      if (i == 1) {
        _inventoryNavKey++;
        _inventoryInitialCategory = category;
        _inventoryInitialStockFilter = stockFilter;
        _inventoryInitialViewMode = viewMode;
        _inventoryInitialLocationId = locationId;
        _inventoryInitialSearchQuery = searchQuery;
        _inventoryInitialItemId = initialStockItemId;
      }
      if (autoOpenStock || autoOpenCash) {
        _requestsNavId++;
        _autoOpenStockRequest = autoOpenStock;
        _autoOpenCashRequest = autoOpenCash;
        _pendingStockLocationId = initialStockLocationId;
        _pendingStockItemId = initialStockItemId;
        _pendingStockQuantity = initialStockQuantity;
      }
    });
  }

  Future<void> _signOut() async {
    await SessionScope.maybeOf(context)?.onSignOut?.call();
    if (mounted) setState(() => _index = 0);
  }

  /// Slot 3 của bottom-bar compact: Duyệt (có quyền duyệt) -> Yêu cầu
  /// (có quyền tạo) -> Hoạt động (auditor thuần, chỉ xem).
  int _compactSlot3(SessionScope? session) {
    if (_canAccessApprovals(session)) return 4;
    final roles = RoleVisibility.rolesOf(session?.user);
    if (RoleVisibility.canCreate(roles)) return 3;
    return 6;
  }

  /// Bar chỉ có 5 slot: 0-2 map thẳng _index, slot 3 = tab _compactSlot3,
  /// slot 4 = Thêm (mở sheet).
  int _bottomSelected(SessionScope? session) {
    if (_index >= 0 && _index <= 2) return _index;
    if (_index == _compactSlot3(session)) return 3;
    return 4;
  }

  Widget _destination(String label, int index,
      {IconData? icon, IconData? selectedIcon, Key? key}) {
    return NavigationDestination(
      key: key,
      icon: Icon(icon ?? _icons[index], size: 22),
      selectedIcon: Icon(selectedIcon ?? _filled[index], size: 22),
      label: label,
    );
  }

  Widget _bottomBar({SessionScope? session}) {
    final slot3 = _compactSlot3(session);
    return NavigationBar(
      selectedIndex: _bottomSelected(session),
      onDestinationSelected: (i) {
        if (i == 4) {
          _openMoreSheet(session: session);
          return;
        }
        setState(() => _index = i == 3 ? slot3 : i);
      },
      height: 64,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      destinations: [
        _destination(_labelFor(context, 0), 0,
            key: const Key('nav-bottom-dashboard')),
        _destination(_labelFor(context, 1), 1,
            key: const Key('nav-bottom-inventory')),
        _destination(_labelFor(context, 2), 2,
            key: const Key('nav-bottom-shifts')),
        _slot3Destination(slot3),
        _destination(_tr(context, 'nav_more'), 4,
            icon: Icons.more_horiz_outlined,
            selectedIcon: Icons.expand_more,
            key: const Key('nav-bottom-more')),
      ],
    );
  }

  String _tr(BuildContext context, String key) {
    final locale =
        Provider.of<LocaleController?>(context)?.locale ?? const Locale('vi');
    return AppI18n(locale).tr(key);
  }

  /// Slot 3 hiển thị đúng nhãn/icon/key theo tab + badge số chờ duyệt.
  Widget _slot3Destination(int slot3) {
    if (slot3 == 4) {
      final badgeCount = _pendingApprovalCount;
      Widget badge(IconData icon) {
        final ic = Icon(icon, size: 22);
        if (badgeCount <= 0) return ic;
        return Badge(
          label: Text('$badgeCount'),
          child: ic,
        );
      }

      return NavigationDestination(
        key: const Key('nav-bottom-approvals'),
        icon: badge(_icons[4]),
        selectedIcon: badge(_filled[4]),
        label: _labelFor(context, 4),
      );
    }
    if (slot3 == 3) {
      return _destination(_labelFor(context, 3), 3,
          key: const Key('nav-bottom-requests'));
    }
    return _destination(_labelFor(context, 6), 6,
        key: const Key('nav-bottom-activity'));
  }

  void _openMoreSheet({SessionScope? session}) {
    final canApprove = _canAccessApprovals(session);
    final roles = RoleVisibility.rolesOf(session?.user);
    final visibleItems = _items
        .where((it) =>
            (it.index != 4 || canApprove) &&
            RoleVisibility.visibleTabs(roles, session?.user).contains(it.index))
        .toList();
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (sheetContext) => DraggableScrollableSheet(
        initialChildSize: 0.65,
        minChildSize: 0.4,
        maxChildSize: 0.9,
        expand: false,
        builder: (scrollContext, scrollController) => Column(
          children: [
            ListTile(
              leading: const Icon(Icons.apps_rounded),
              title: Text(
                context.tr('nav_select_workspace'),
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
              ),
              trailing: IconButton(
                icon: const Icon(Icons.close),
                tooltip: context.tr('btn_close'),
                onPressed: () => Navigator.of(sheetContext).pop(),
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: ListView.separated(
                controller: scrollController,
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.symmetric(vertical: 8),
                itemCount: visibleItems.length,
                separatorBuilder: (_, __) =>
                    const Divider(height: 1, indent: 56),
                itemBuilder: (ctx, idx) {
                  final it = visibleItems[idx];
                  final isCurrent = _index == it.index;
                  return ListTile(
                    leading: Icon(
                      _icons[it.index],
                      color: isCurrent
                          ? const Color(0xFF2563EB)
                          : Theme.of(sheetContext)
                              .colorScheme
                              .onSurfaceVariant,
                    ),
                    title: Text(
                      _titleFor(context, it.index),
                      style: TextStyle(
                        fontWeight:
                            isCurrent ? FontWeight.w700 : FontWeight.w500,
                        color: isCurrent ? const Color(0xFF2563EB) : null,
                      ),
                    ),
                    trailing: isCurrent
                        ? const Icon(Icons.check_circle_rounded,
                            color: Color(0xFF2563EB), size: 18)
                        : const Icon(Icons.arrow_forward_ios,
                            size: 14, color: Colors.grey),
                    dense: true,
                    onTap: () {
                      Navigator.of(sheetContext).pop();
                      setState(() => _index = it.index);
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _navRail({required double width, SessionScope? session}) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final isWide = width >= 200;
    final canApprove = _canAccessApprovals(session);
    final roles = RoleVisibility.rolesOf(session?.user);
    final visibleItems = _items
        .where((it) =>
            (it.index != 4 || canApprove) &&
            RoleVisibility.visibleTabs(roles, session?.user).contains(it.index))
        .toList();

    return Container(
      width: width,
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF0F172A) : Colors.white,
        border: Border(
          right: BorderSide(
            color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
          ),
        ),
      ),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
            child: Row(
              children: [
                const StoreLogo(size: 32),
                if (isWide) ...[
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.tr('nav_brand_title'),
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w900,
                            letterSpacing: -0.3,
                          ),
                        ),
                        Text(
                          context.tr('nav_brand_sub'),
                          style: const TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: Color(0xFF64748B),
                            letterSpacing: 0.5,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: const Color(0xFF10B981).withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        CircleAvatar(
                            radius: 3, backgroundColor: Color(0xFF10B981)),
                        SizedBox(width: 4),
                        Text(
                          'LIVE',
                          style: TextStyle(
                            color: Color(0xFF059669),
                            fontSize: 9,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              itemCount: visibleItems.length,
              itemBuilder: (context, i) {
                final item = visibleItems[i];
                final selected = _index == item.index;

                // Category header on wide layout
                Widget? sectionHeader;
                if (isWide) {
                  if (item.index == 0) {
                    sectionHeader =
                        _buildNavSectionHeader(context.tr('nav_section_ops'));
                  } else if (item.index == 3) {
                    sectionHeader =
                        _buildNavSectionHeader(context.tr('nav_section_control'));
                  } else if (item.index == 5 || item.index == 6) {
                    sectionHeader =
                        _buildNavSectionHeader(context.tr('nav_section_system'));
                  }
                }

                final navBtn = Container(
                  height: 44,
                  margin: const EdgeInsets.symmetric(vertical: 2),
                  decoration: BoxDecoration(
                    color: selected
                        ? (isDark
                            ? const Color(0xFF1E293B)
                            : const Color(0xFFEFF6FF))
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(10),
                    border: selected
                        ? Border.all(
                            color: isDark
                                ? const Color(0xFF334155)
                                : const Color(0xFFBFDBFE),
                            width: 1,
                          )
                        : null,
                  ),
                  child: InkWell(
                    key: Key('nav-${_slugs[item.index]}'),
                    onTap: () => setState(() => _index = item.index),
                    borderRadius: BorderRadius.circular(10),
                    child: Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: isWide ? 12 : 8,
                        vertical: 6,
                      ),
                      child: Row(
                        mainAxisAlignment: isWide
                            ? MainAxisAlignment.start
                            : MainAxisAlignment.center,
                        children: [
                          Icon(
                            selected ? item.filled : item.icon,
                            size: 20,
                            color: selected
                                ? const Color(0xFF2563EB)
                                : theme.colorScheme.onSurfaceVariant,
                          ),
                          if (isWide) ...[
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                _labelFor(context, item.index),
                                style: TextStyle(
                                  color: selected
                                      ? (isDark
                                          ? Colors.white
                                          : const Color(0xFF1E3A8A))
                                      : theme.colorScheme.onSurface,
                                  fontWeight: selected
                                      ? FontWeight.w700
                                      : FontWeight.w500,
                                  fontSize: 13.5,
                                ),
                              ),
                            ),
                            if (item.index == 4) // Approvals tab badge
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: (_pendingApprovalCount > 0
                                          ? const Color(0xFFDC2626)
                                          : const Color(0xFFF59E0B))
                                      .withValues(alpha: 0.2),
                                  borderRadius: BorderRadius.circular(10),
                                ),
                                child: Text(
                                  _pendingApprovalCount > 0
                                      ? context.tr('nav_badge_pending', {
                                          'count': '$_pendingApprovalCount'
                                        })
                                      : context.tr('nav_badge_approvals'),
                                  style: TextStyle(
                                    color: _pendingApprovalCount > 0
                                        ? const Color(0xFFDC2626)
                                        : const Color(0xFFD97706),
                                    fontSize: 9,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                              ),
                          ],
                        ],
                      ),
                    ),
                  ),
                );

                if (sectionHeader != null) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      sectionHeader,
                      navBtn,
                    ],
                  );
                }
                return navBtn;
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNavSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 14, 8, 4),
      child: Text(
        title,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w800,
          color: Theme.of(context)
              .colorScheme
              .onSurfaceVariant
              .withValues(alpha: 0.7),
          letterSpacing: 0.8,
        ),
      ),
    );
  }

  PreferredSizeWidget _topBar({SessionScope? session}) {
    final theme = Theme.of(context);
    final user = session?.user;
    final role = user?.roles.isNotEmpty == true
        ? user!.roles.first.toUpperCase()
        : 'STAFF';

    Color roleColor;
    if (role.contains('MAKER')) {
      roleColor = const Color(0xFF2563EB);
    } else if (role.contains('CHECKER')) {
      roleColor = const Color(0xFF7C3AED);
    } else if (role.contains('ADMIN')) {
      roleColor = const Color(0xFF059669);
    } else {
      roleColor = const Color(0xFF475467);
    }

    // Màn hẹp (<600): chỉ giữ search + chuông + avatar để AppBar không tràn.
    // Refresh dùng kéo-thả, theme/cài đặt vào qua More sheet và menu avatar.
    final compact = MediaQuery.sizeOf(context).width < 600;

    return AppBar(
      title: Row(
        children: [
          Icon(
            _icons[_index],
            size: 20,
            color: const Color(0xFF2563EB),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              _titleFor(context, _index),
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 18),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
      centerTitle: false,
      backgroundColor: theme.colorScheme.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 1,
      actions: [
        IconButton(
          key: const Key('topbar-search-btn'),
          icon: const Icon(Icons.search_rounded, size: 20),
          onPressed: _openSearch,
          tooltip: context.tr('topbar_search_tooltip'),
        ),
        IconButton(
          key: const Key('topbar-refresh-btn'),
          icon: const Icon(Icons.refresh_rounded, size: 20),
          onPressed: _reload,
          tooltip: context.tr('topbar_refresh_tooltip'),
        ),
        if (_canAccessApprovals(session))
          Stack(
            alignment: Alignment.center,
            children: [
              IconButton(
                key: const Key('topbar-approvals-notif-btn'),
                icon: const Icon(Icons.notifications_outlined, size: 20),
                tooltip: context.tr('topbar_approvals_tooltip',
                    {'count': '$_pendingApprovalCount'}),
                onPressed: () => setState(() => _index = 4),
              ),
              if (_pendingApprovalCount > 0)
                Positioned(
                  top: 8,
                  right: 8,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: const BoxDecoration(
                      color: Color(0xFFDC2626),
                      shape: BoxShape.circle,
                    ),
                    constraints:
                        const BoxConstraints(minWidth: 16, minHeight: 16),
                    child: Text(
                      '$_pendingApprovalCount',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 9,
                        fontWeight: FontWeight.w900,
                        height: 1.0,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        IconButton(
          key: const Key('topbar-language-btn'),
          icon: Text(
            context.isVietnamese ? '🇻🇳 VI' : '🇬🇧 EN',
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
          ),
          tooltip: context.tr('topbar_lang_tooltip'),
          onPressed: () {
            context.read<LocaleController?>()?.toggleLanguage();
          },
        ),
        if (!compact)
          IconButton(
            icon: Icon(
              theme.brightness == Brightness.dark
                  ? Icons.light_mode_outlined
                  : Icons.dark_mode_outlined,
              size: 20,
            ),
            tooltip: context.tr('topbar_theme_tooltip'),
            onPressed: () {
              // ignore: use_build_context_synchronously
              final ctrl =
                  Provider.of<ThemeModeController?>(context, listen: false);
              if (ctrl != null) {
                ctrl.setMode(
                  theme.brightness == Brightness.dark
                      ? ThemeMode.light
                      : ThemeMode.dark,
                );
              }
            },
          ),
        if (!compact)
          IconButton(
            icon: const Icon(Icons.settings_outlined, size: 20),
            onPressed: _openSettings,
            tooltip: context.tr('topbar_settings_tooltip'),
          ),
        const SizedBox(width: 8),
        Container(
          height: 36,
          padding: const EdgeInsets.only(left: 8, right: 4),
          decoration: BoxDecoration(
            border: Border.all(
              color: theme.colorScheme.outlineVariant.withValues(alpha: 0.6),
            ),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (!compact) ...[
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: roleColor.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    role,
                    style: TextStyle(
                      color: roleColor,
                      fontSize: 10,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  user?.displayName ?? context.tr('topbar_guest'),
                  style: const TextStyle(
                      fontWeight: FontWeight.w600, fontSize: 13),
                ),
              ],
              PopupMenuButton<String>(
                key: const Key('topbar-user-menu'),
                icon: user != null
                    ? UserAvatar(
                        name: user.displayName,
                        email: user.effectiveEmail,
                        avatarUrl: user.avatarUrl,
                        size: 26,
                      )
                    : const UserAvatar(size: 26),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12)),
                tooltip: user?.displayName ?? context.tr('topbar_account'),
                itemBuilder: (context) => [
                  if (user != null) ...[
                    PopupMenuItem(
                      enabled: false,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            user.displayName,
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                          Text(
                            user.username,
                            style: TextStyle(
                                fontSize: 12,
                                color: theme.colorScheme.onSurfaceVariant),
                          ),
                        ],
                      ),
                    ),
                    const PopupMenuDivider(),
                    PopupMenuItem(
                      value: 'settings',
                      child: ListTile(
                        leading: const Icon(Icons.settings, size: 18),
                        title: Text(context.tr('nav_settings')),
                        contentPadding: EdgeInsets.zero,
                      ),
                    ),
                    const PopupMenuDivider(),
                  ],
                  PopupMenuItem(
                    key: const Key('menu-signout'),
                    value: 'signout',
                    child: ListTile(
                      leading: const Icon(Icons.logout_rounded,
                          size: 18, color: Colors.red),
                      title: Text(context.tr('btn_logout'),
                          style: const TextStyle(color: Colors.red)),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                ],
                onSelected: (v) {
                  if (v == 'settings') _openSettings();
                  if (v == 'signout') _signOut();
                },
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    try {
      context.watch<LocaleController>();
    } catch (_) {
      try {
        context.watch<LocaleController?>();
      } catch (_) {}
    }
    final session = SessionScope.maybeOf(context);
    final layout = Breakpoints.fromWidth(MediaQuery.sizeOf(context).width);

    final body = AppScreen(
      body: KeyedSubtree(
        key: _bodySubtreeKey,
        child: KeyedSubtree(
          key: ValueKey(
              'screen-$_index-$_refreshTick-${session?.user?.id ?? ''}-${context.currentLocale.languageCode}'),
          child: _screenFor(_index, session),
        ),
      ),
      header: _index == 0 ? const _DashboardHeader() : null,
    );

    final bodyWithTicker = _withLiveTicker(body);
    final auth = Provider.of<AuthService?>(context);
    final isSandbox = auth?.isOfflineSession ?? false;
    final sandboxBanner = isSandbox
        ? Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            color: const Color(0xFFFEF3C7),
            child: const Row(
              children: [
                Icon(Icons.info_outline, size: 18, color: Color(0xFFB45309)),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Chế độ Reviewer Sandbox (Mô Phỏng 3 Phút) — Dữ liệu mẫu in-memory, không ghi cơ sở dữ liệu thật.',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF92400E),
                    ),
                  ),
                ),
              ],
            ),
          )
        : null;

    Widget mainBody;
    if (layout.isWide) {
      mainBody = Row(
        children: [
          _navRail(width: 256, session: session),
          const VerticalDivider(width: 8, thickness: 1),
          Expanded(
            child: Column(
              children: [
                if (sandboxBanner != null) sandboxBanner,
                OfflineBanner(pending: OfflineHub.instance.pending),
                _topBar(session: session),
                Expanded(child: bodyWithTicker),
              ],
            ),
          ),
        ],
      );
    } else if (layout.isMedium) {
      mainBody = Stack(
        children: [
          Row(
            children: [
              _navRail(width: 88, session: session),
              const VerticalDivider(width: 8, thickness: 1),
              Expanded(
                child: Column(
                  children: [
                    if (sandboxBanner != null) sandboxBanner,
                    Expanded(child: bodyWithTicker),
                  ],
                ),
              ),
            ],
          ),
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: OfflineBanner(pending: OfflineHub.instance.pending),
          ),
        ],
      );
    } else {
      mainBody = Stack(
        children: [
          Column(
            children: [
              if (sandboxBanner != null) sandboxBanner,
              Expanded(child: bodyWithTicker),
            ],
          ),
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: OfflineBanner(pending: OfflineHub.instance.pending),
          ),
        ],
      );
    }

    final scaffold = Scaffold(
      floatingActionButton: (!_enableAiAssistant || _aiUnavailable)
          ? null
          : (layout.isWide
              ? FloatingActionButton.extended(
                  key: const Key('btn-ai-assistant'),
                  onPressed: () => AiAssistantDialog.show(context),
                  icon: const Icon(Icons.psychology_outlined),
                  label: const Text('Trợ lý AI'),
                  backgroundColor: const Color(0xFF2563EB),
                  foregroundColor: Colors.white,
                )
              : FloatingActionButton(
                  key: const Key('btn-ai-assistant'),
                  onPressed: () => AiAssistantDialog.show(context),
                  backgroundColor: const Color(0xFF2563EB),
                  foregroundColor: Colors.white,
                  tooltip: 'Trợ lý AI',
                  child: const Icon(Icons.psychology_outlined),
                )),
      appBar: layout.isWide ? null : _topBar(session: session),
      body: mainBody,
      bottomNavigationBar:
          layout.isCompact ? _bottomBar(session: session) : null,
    );

    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final overlayStyle = SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: isDark ? Brightness.light : Brightness.dark,
      statusBarBrightness: isDark ? Brightness.dark : Brightness.light,
      systemNavigationBarColor: Colors.transparent,
      systemNavigationBarDividerColor: Colors.transparent,
      systemNavigationBarIconBrightness:
          isDark ? Brightness.light : Brightness.dark,
      systemNavigationBarContrastEnforced: false,
      systemStatusBarContrastEnforced: false,
    );

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: overlayStyle,
      child: RepositoryScope(
        repository: _repository!,
        child: SyncScope(
          controller: _syncController,
          child: _shortcutWrapper(scaffold),
        ),
      ),
    );
  }

  Widget _withLiveTicker(Widget body) {
    final isOfflineDemo =
        context.watch<AuthService?>()?.isOfflineSession ?? false;
    final showTicker =
        context.watch<AppUiSettingsController?>()?.showLiveTicker ?? true;
    if (!isOfflineDemo && !showTicker && !_isUpdateAvailable) return body;
    return Column(
      children: [
        if (_isUpdateAvailable)
          const _AppUpdateBanner(onUpdate: forceAppUpdate),
        if (isOfflineDemo)
          const _OfflineDemoBanner()
        else if (showTicker)
          const _TeaOpsTicker(),
        Expanded(child: body),
      ],
    );
  }

  /// Phím tắt toàn cục: `Ctrl+K` mở tìm kiếm từ mọi màn.
  Widget _shortcutWrapper(Widget page) {
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyK, control: true):
            _openSearch,
      },
      child: Focus(autofocus: true, child: page),
    );
  }
}

class _DashboardHeader extends StatelessWidget {
  const _DashboardHeader();

  @override
  Widget build(BuildContext context) {
    return const SizedBox.shrink();
  }
}

/// Thanh trạng thái thao tác nhanh tại quầy. Người dùng có thể tắt trong
/// Thanh trạng thái thao tác nhanh tại quầy, cập nhật ca trực động theo thời gian thực (Giờ:Phút).
class _TeaOpsTicker extends StatefulWidget {
  const _TeaOpsTicker();

  @override
  State<_TeaOpsTicker> createState() => _TeaOpsTickerState();
}

class _TeaOpsTickerState extends State<_TeaOpsTicker> {
  Timer? _timer;
  DateTime _now = DateTime.now();

  @override
  void initState() {
    super.initState();
    _now = DateTime.now();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted) setState(() => _now = DateTime.now());
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  String _getShiftAlertText(Locale locale) {
    final isVi = locale.languageCode == 'vi';
    final hour = _now.hour;
    final timeStr =
        '${_now.hour.toString().padLeft(2, '0')}:${_now.minute.toString().padLeft(2, '0')}';

    if (hour >= 6 && hour < 14) {
      return isVi
          ? '⚡ Ca Sáng ($timeStr) · Kiểm kê mở quầy & sẵn sàng pha chế · 3 nguyên liệu FEFO'
          : '⚡ Morning Shift ($timeStr) · Opening stocktake & preparation · 3 FEFO items';
    } else if (hour >= 14 && hour < 22) {
      return isVi
          ? '⚡ Ca Chiều/Tối ($timeStr) · Theo dõi tồn quầy cao điểm & xuất huỷ ca · Giám sát định mức'
          : '⚡ Afternoon/Evening Shift ($timeStr) · Peak inventory monitoring & shift disposal';
    } else {
      return isVi
          ? '🌙 Ca Đêm / Chốt Sổ ($timeStr) · Đối soát doanh thu & kiểm kê cuối ngày · Sẵn sàng ca sáng mai'
          : '🌙 Night / Closing Shift ($timeStr) · Daily reconciliation & closing stocktake';
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final locale =
        Provider.of<LocaleController?>(context)?.locale ?? const Locale('vi');
    final text = _getShiftAlertText(locale);
    return Semantics(
      liveRegion: true,
      label: text,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        color: theme.colorScheme.primaryContainer,
        child: Row(
          children: [
            Icon(Icons.notifications_active_outlined,
                size: 17, color: theme.colorScheme.onPrimaryContainer),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                text,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: theme.colorScheme.onPrimaryContainer,
                ),
              ),
            ),
            const SizedBox(width: 4),
            IconButton(
              key: const Key('btn-dismiss-live-ticker'),
              icon: Icon(Icons.close_rounded,
                  size: 17, color: theme.colorScheme.onPrimaryContainer),
              tooltip: context.tr('topbar_dismiss_ticker'),
              visualDensity: VisualDensity.compact,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
              onPressed: () {
                context
                    .read<AppUiSettingsController?>()
                    ?.setShowLiveTicker(false);
              },
            ),
          ],
        ),
      ),
    );
  }
}

/// Hiển thị rõ rằng phiên dự phòng không đọc/ghi dữ liệu cửa hàng thật.
class _OfflineDemoBanner extends StatelessWidget {
  const _OfflineDemoBanner();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isVi = context.isVietnamese;
    final text = isVi
        ? 'Chế độ ngoại tuyến · Dữ liệu lưu trữ cục bộ trên thiết bị'
        : 'Offline Mode · Data stored locally on device';
    return Semantics(
      liveRegion: true,
      label: '$text.',
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        color: scheme.tertiaryContainer,
        child: Row(
          children: [
            Icon(Icons.cloud_off_outlined,
                size: 17, color: scheme.onTertiaryContainer),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                text,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: scheme.onTertiaryContainer,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AppUpdateBanner extends StatelessWidget {
  const _AppUpdateBanner({required this.onUpdate});
  final VoidCallback onUpdate;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: const BoxDecoration(
        color: Color(0xFF0284C7),
      ),
      child: Row(
        children: [
          const Icon(Icons.system_update_rounded,
              size: 16, color: Colors.white),
          const SizedBox(width: 8),
          const Expanded(
            child: Text(
              'Đã có bản cập nhật mới trên máy chủ',
              style: TextStyle(
                color: Colors.white,
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          ElevatedButton(
            key: const Key('btn-banner-update-app'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white,
              foregroundColor: const Color(0xFF0284C7),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              elevation: 0,
            ),
            onPressed: onUpdate,
            child: const Text(
              'Cập nhật ngay',
              style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w800),
            ),
          ),
        ],
      ),
    );
  }
}

class _Item {
  const _Item(this.index, this.label, this.icon, this.filled);
  final int index;
  final String label;
  final IconData icon;
  final IconData filled;
}
