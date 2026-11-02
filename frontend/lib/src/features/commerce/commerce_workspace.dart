import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:intl/intl.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import 'commerce_memory_store.dart';
import 'commerce_api.dart';
import 'commerce_reports_page.dart';

class CommerceWorkspace extends StatefulWidget {
  const CommerceWorkspace({
    super.key,
    required this.store,
    this.api,
    this.onRefresh,
    this.userName = 'Chủ cửa hàng',
    this.onSignOut,
    this.capabilities,
    this.roles,
  });

  final CommerceMemoryStore store;
  final CommerceApi? api;
  final Future<void> Function()? onRefresh;
  final String userName;
  final Future<void> Function()? onSignOut;
  final Set<String>? capabilities;
  final Set<String>? roles;

  @override
  State<CommerceWorkspace> createState() => _CommerceWorkspaceState();
}

class _CommerceWorkspaceState extends State<CommerceWorkspace> {
  int _index = 1;
  static const _navigationPages = [0, 1, 2, 3, 4, 5, 6];
  static const _mobilePages = [0, 1, 2, 3];
  static const _pageTitles = [
    'Tổng quan',
    'Bán hàng',
    'Mua hàng',
    'Kho hàng',
    'Công nợ',
    'Báo cáo',
    'Duyệt phiếu',
  ];
  static const _navigationNames = [
    'Tổng quan',
    'Bán hàng',
    'Mua hàng',
    'Kho hàng',
    'Công nợ',
    'Báo cáo',
    'Duyệt phiếu',
  ];
  static const _navigationIcons = [
    Icons.grid_view_rounded,
    Icons.point_of_sale_rounded,
    Icons.shopping_bag_outlined,
    Icons.inventory_2_outlined,
    Icons.account_balance_wallet_outlined,
    Icons.bar_chart_rounded,
    Icons.fact_check_outlined,
  ];

  bool _hasAnyCapability(List<String> values) {
    final capabilities = widget.capabilities;
    if (capabilities != null) {
      return values.any(capabilities.contains);
    }
    final roles = widget.roles;
    if (roles != null) {
      return roles.any((role) => const {
            'admin',
            'system_admin',
            'owner',
            'business_owner'
          }.contains(role.toLowerCase()));
    }
    return true;
  }

  bool get _canViewOwnerData {
    const privilegedRoles = {
      'admin',
      'system_admin',
      'root_admin',
      'owner',
      'business_owner',
      'store_owner',
      'chu_quan',
      'chuquan',
    };
    const privilegedCapabilities = {
      'admin',
      'admin:user_management',
      'iam:admin',
      'owner:financial_reports',
    };
    final roles = widget.roles;
    if (roles?.any((role) => privilegedRoles.contains(role.toLowerCase())) ==
        true) return true;
    final capabilities = widget.capabilities;
    if (capabilities != null) {
      return capabilities
          .any((capability) => privilegedCapabilities.contains(capability));
    }
    // A workspace with auth metadata is non-owner unless explicitly granted
    // a privileged role or capability. Unauthenticated local preview remains
    // the owner view.
    return roles == null;
  }

  void _create(String kind) => _showCreateOrder(context, widget.store, kind,
      api: widget.api,
      onRefresh: widget.onRefresh,
      canViewOwnerData: _canViewOwnerData);

  Future<void> _selectLocation(String? value) async {
    if (value == null || widget.api == null) return;
    widget.api!.locationId = value;
    await widget.onRefresh?.call();
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final wide = width >= 700;
    final store = widget.store;
    final canWrite = _hasAnyCapability(
        const ['inventory:create_request', 'admin:user_management']);
    final canManageCatalog = _hasAnyCapability(
        const ['inventory:manage_catalog', 'admin:user_management']);
    final canApprove = _hasAnyCapability(const ['inventory:approve_request']);
    final canViewOwnerData = _canViewOwnerData;
    final pageIndex =
        !canViewOwnerData && (_index == 4 || _index == 5) ? 0 : _index;
    final name = _pageTitles[pageIndex];
    final pages = [
      _OverviewPage(
          store: store,
          canWrite: canWrite,
          canApprove: canApprove,
          canViewOwnerData: canViewOwnerData,
          onNavigate: (i) => setState(() => _index = i)),
      _OrderListPage(
          store: store,
          kind: 'sale',
          onCreate: () => _create('sale'),
          canWrite: canWrite,
          canViewOwnerData: canViewOwnerData,
          api: widget.api,
          onRefresh: widget.onRefresh),
      _OrderListPage(
          store: store,
          kind: 'purchase',
          onCreate: () => _create('purchase'),
          canWrite: canWrite,
          canViewOwnerData: canViewOwnerData,
          api: widget.api,
          onRefresh: widget.onRefresh),
      _InventoryPage(
          store: store,
          canManageCatalog: canManageCatalog,
          canWrite: canWrite,
          canViewOwnerData: canViewOwnerData,
          onNavigate: (i) => setState(() => _index = i),
          api: widget.api,
          onRefresh: widget.onRefresh),
      _DebtPage(
          store: store,
          canWrite: canWrite,
          api: widget.api,
          onRefresh: widget.onRefresh),
      canViewOwnerData
          ? CommerceReportsPage(store: store)
          : const SizedBox.shrink(),
      _ApprovalPage(
          store: store,
          api: widget.api,
          onRefresh: widget.onRefresh,
          canViewOwnerData: canViewOwnerData),
    ];

    return Scaffold(
      backgroundColor: const Color(0xFFF6F7F5),
      body: SafeArea(
        child: Row(
          children: [
            if (wide)
              _WorkspaceSidebar(
                  index: pageIndex,
                  onSelect: (i) => setState(() => _index = i),
                  userName: widget.userName,
                  onSignOut: widget.onSignOut,
                  canApprove: canApprove,
                  canViewOwnerData: canViewOwnerData),
            Expanded(
              child: Column(
                children: [
                  _WorkspaceTopbar(
                    title: name,
                    isLive: widget.api != null,
                    locations: widget.api?.locations ?? const [],
                    locationId: widget.api?.locationId,
                    onLocationChanged: _selectLocation,
                    onCreate: canWrite && pageIndex == 1
                        ? () => _create('sale')
                        : canWrite && pageIndex == 2
                            ? () => _create('purchase')
                            : null,
                    createLabel:
                        pageIndex == 1 ? 'Tạo phiếu bán' : 'Tạo phiếu nhập',
                    userName: widget.userName,
                    onSignOut: widget.onSignOut,
                  ),
                  Expanded(
                    child: AnimatedBuilder(
                      animation: store,
                      builder: (context, _) =>
                          IndexedStack(index: pageIndex, children: pages),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: wide
          ? null
          : NavigationBar(
              selectedIndex: _mobilePages.contains(pageIndex)
                  ? _mobilePages.indexOf(pageIndex)
                  : 4,
              onDestinationSelected: (value) {
                if (value == 4) {
                  showModalBottomSheet<void>(
                      context: context,
                      builder: (sheetContext) => SafeArea(
                              child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                ListTile(
                                    leading: const Icon(
                                        Icons.account_balance_wallet_outlined),
                                    title: const Text('Công nợ'),
                                    onTap: () {
                                      Navigator.pop(sheetContext);
                                      setState(() => _index = 4);
                                    }),
                                if (canViewOwnerData)
                                  ListTile(
                                      leading:
                                          const Icon(Icons.bar_chart_rounded),
                                      title: const Text('Báo cáo'),
                                      onTap: () {
                                        Navigator.pop(sheetContext);
                                        setState(() => _index = 5);
                                      }),
                                if (canApprove)
                                  ListTile(
                                      leading:
                                          const Icon(Icons.fact_check_outlined),
                                      title: const Text('Duyệt phiếu'),
                                      onTap: () {
                                        Navigator.pop(sheetContext);
                                        setState(() => _index = 6);
                                      }),
                                const Divider(),
                                ListTile(
                                  leading:
                                      const Icon(Icons.person_outline_rounded),
                                  title: Text(widget.userName),
                                  subtitle: const Text('Optimate x NexUp ERP',
                                      style: TextStyle(fontSize: 11)),
                                ),
                                ListTile(
                                    leading: const Icon(Icons.logout_rounded,
                                        color: Color(0xFFDC2626)),
                                    title: const Text('Đăng xuất',
                                        style: TextStyle(
                                            color: Color(0xFFDC2626),
                                            fontWeight: FontWeight.w600)),
                                    onTap: () {
                                      Navigator.pop(sheetContext);
                                      widget.onSignOut?.call();
                                    }),
                              ])));
                } else {
                  setState(() => _index = _mobilePages[value]);
                }
              },
              height: 68,
              backgroundColor: Colors.white,
              indicatorColor: const Color(0xFFEDE8FC),
              destinations: [
                for (var i = 0; i < _mobilePages.length; i++)
                  NavigationDestination(
                      icon: Icon(_navigationIcons[i]),
                      label: _navigationNames[
                          _navigationPages.indexOf(_mobilePages[i])]),
                const NavigationDestination(
                    icon: Icon(Icons.more_horiz_rounded), label: 'Thêm'),
              ],
            ),
    );
  }
}

class _WorkspaceSidebar extends StatelessWidget {
  const _WorkspaceSidebar({
    required this.index,
    required this.onSelect,
    required this.userName,
    required this.onSignOut,
    required this.canApprove,
    required this.canViewOwnerData,
  });
  final int index;
  final ValueChanged<int> onSelect;
  final String userName;
  final Future<void> Function()? onSignOut;
  final bool canApprove;
  final bool canViewOwnerData;

  static const names = _CommerceWorkspaceState._navigationNames;
  static const icons = _CommerceWorkspaceState._navigationIcons;
  static const pages = _CommerceWorkspaceState._navigationPages;

  @override
  Widget build(BuildContext context) => Container(
        width: 232,
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(right: BorderSide(color: Color(0xFFE8EAE7))),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(22, 22, 16, 22),
              child: Row(
                children: [
                  Container(
                    width: 34,
                    height: 34,
                    decoration: BoxDecoration(
                        color: const Color(0xFF7555D1),
                        borderRadius: BorderRadius.circular(10)),
                    child: const Icon(Icons.auto_graph_rounded,
                        color: Colors.white, size: 20),
                  ),
                  const SizedBox(width: 11),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('NexUpOne',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 16,
                                letterSpacing: -.3)),
                        Text('QUẢN LÝ DOANH NGHIỆP',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                                fontSize: 9,
                                color: Color(0xFF888D87),
                                letterSpacing: .8,
                                fontWeight: FontWeight.w700)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const Padding(
              padding: EdgeInsets.fromLTRB(22, 2, 12, 9),
              child: Text('VẬN HÀNH',
                  style: TextStyle(
                      fontSize: 10,
                      color: Color(0xFF92978F),
                      letterSpacing: 1,
                      fontWeight: FontWeight.w800)),
            ),
            for (var i = 0; i < names.length; i++)
              if ((pages[i] != 6 || canApprove) &&
                  (canViewOwnerData || pages[i] != 5))
                _SideNavItem(
                    label: names[i],
                    icon: icons[i],
                    selected: index == pages[i],
                    onTap: () => onSelect(pages[i])),
            const Spacer(),
            const Divider(height: 1, color: Color(0xFFE8EAE7)),
            ListTile(
              onTap: onSignOut,
              leading: CircleAvatar(
                  radius: 17,
                  backgroundColor: const Color(0xFFE9E4F8),
                  child: Text(
                      userName.trim().isEmpty
                          ? 'A'
                          : userName.trim()[0].toUpperCase(),
                      style: const TextStyle(
                          color: Color(0xFF6244BA),
                          fontWeight: FontWeight.w800))),
              title: Text(userName.isEmpty ? 'An Nguyễn' : userName,
                  style: const TextStyle(
                      fontSize: 12, fontWeight: FontWeight.w700)),
              subtitle: const Text('Quản lý cửa hàng',
                  style: TextStyle(fontSize: 10)),
              trailing: PopupMenuButton<String>(
                icon: const Icon(Icons.more_horiz, size: 19),
                tooltip: 'Tài khoản & Đăng xuất',
                onSelected: (v) {
                  if (v == 'signout') onSignOut?.call();
                },
                itemBuilder: (context) => const [
                  PopupMenuItem(
                    value: 'profile',
                    child: ListTile(
                      leading: Icon(Icons.person_outline, size: 18),
                      title: Text('Hồ sơ tài khoản',
                          style: TextStyle(fontSize: 13)),
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                  PopupMenuItem(
                    value: 'signout',
                    child: ListTile(
                      leading: Icon(Icons.logout_rounded,
                          size: 18, color: Colors.red),
                      title: Text('Đăng xuất',
                          style: TextStyle(
                              fontSize: 13,
                              color: Colors.red,
                              fontWeight: FontWeight.w700)),
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                ],
              ),
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 18, vertical: 6),
            ),
          ],
        ),
      );
}

class _SideNavItem extends StatelessWidget {
  const _SideNavItem(
      {required this.label,
      required this.icon,
      required this.selected,
      required this.onTap});
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
        child: Material(
          color: selected ? const Color(0xFFF1EDFC) : Colors.transparent,
          borderRadius: BorderRadius.circular(10),
          child: InkWell(
            borderRadius: BorderRadius.circular(10),
            onTap: onTap,
            child: SizedBox(
              height: 42,
              child: Row(
                children: [
                  const SizedBox(width: 12),
                  Icon(icon,
                      size: 19,
                      color: selected
                          ? const Color(0xFF6746C3)
                          : const Color(0xFF727771)),
                  const SizedBox(width: 12),
                  Text(label,
                      style: TextStyle(
                          fontSize: 12.5,
                          fontWeight:
                              selected ? FontWeight.w700 : FontWeight.w500,
                          color: selected
                              ? const Color(0xFF5235A9)
                              : const Color(0xFF424740))),
                  const Spacer(),
                  if (selected)
                    Container(
                        width: 3,
                        height: 18,
                        decoration: BoxDecoration(
                            color: const Color(0xFF7555D1),
                            borderRadius: BorderRadius.circular(3))),
                  const SizedBox(width: 10),
                ],
              ),
            ),
          ),
        ),
      );
}

class _WorkspaceTopbar extends StatelessWidget {
  const _WorkspaceTopbar({
    required this.title,
    required this.onCreate,
    required this.createLabel,
    required this.isLive,
    required this.locations,
    required this.locationId,
    required this.onLocationChanged,
    required this.userName,
    required this.onSignOut,
  });
  final String title;
  final VoidCallback? onCreate;
  final String createLabel;
  final bool isLive;
  final List<Map<String, dynamic>> locations;
  final String? locationId;
  final ValueChanged<String?> onLocationChanged;
  final String userName;
  final Future<void> Function()? onSignOut;

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.sizeOf(context).width;
    final contentWidth = screenWidth - (screenWidth >= 700 ? 232 : 0);
    final compact = contentWidth < 600;
    return Container(
      height: 66,
      padding: EdgeInsets.symmetric(horizontal: compact ? 16 : 26),
      decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(bottom: BorderSide(color: Color(0xFFE8EAE7)))),
      child: Row(
        children: [
          if (compact)
            const Icon(Icons.auto_graph_rounded,
                color: Color(0xFF7555D1), size: 20),
          if (compact) const SizedBox(width: 9),
          if (compact)
            Expanded(
              child: Text(title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      fontSize: 17,
                      letterSpacing: -.4)),
            )
          else
            Text(title,
                style: const TextStyle(
                    fontWeight: FontWeight.w800,
                    fontSize: 17,
                    letterSpacing: -.4)),
          if (compact && !isLive) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
              decoration: BoxDecoration(
                color: const Color(0xFFF1EDFC),
                borderRadius: BorderRadius.circular(18),
              ),
              child: const Text('DEMO · RAM',
                  style: TextStyle(
                      fontSize: 8,
                      color: Color(0xFF6244BA),
                      fontWeight: FontWeight.w800)),
            ),
          ],
          if (!compact) ...[
            const SizedBox(width: 10),
            Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
                decoration: BoxDecoration(
                    color: isLive
                        ? const Color(0xFFE7F6EF)
                        : const Color(0xFFF1EDFC),
                    borderRadius: BorderRadius.circular(18)),
                child: Text(
                    isLive ? 'KẾT NỐI MÁY CHỦ' : 'DEMO · chỉ lưu trong phiên',
                    style: TextStyle(
                        fontSize: 9,
                        color: isLive
                            ? const Color(0xFF168256)
                            : const Color(0xFF6244BA),
                        fontWeight: FontWeight.w800))),
          ],
          const Spacer(),
          if (isLive && locations.length > 1)
            SizedBox(
              width: compact ? 120 : 190,
              child: DropdownButtonFormField<String>(
                value: locationId,
                isExpanded: true,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.store_outlined, size: 17),
                  isDense: true,
                  border: OutlineInputBorder(),
                  contentPadding:
                      EdgeInsets.symmetric(horizontal: 8, vertical: 7),
                ),
                items: locations
                    .map((location) => DropdownMenuItem(
                          value: location['id']?.toString(),
                          child: Text('${location['name'] ?? location['code']}',
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 11)),
                        ))
                    .toList(),
                onChanged: onLocationChanged,
              ),
            ),
          if (isLive && locations.length > 1) const SizedBox(width: 10),
          if (onCreate != null) ...[
            if (!compact) const SizedBox(width: 6),
            compact
                ? IconButton.filled(
                    onPressed: onCreate,
                    tooltip: createLabel,
                    icon: const Icon(Icons.add_rounded),
                    style: IconButton.styleFrom(
                        backgroundColor: const Color(0xFF6B4BC3),
                        foregroundColor: Colors.white,
                        visualDensity: VisualDensity.compact),
                  )
                : FilledButton.icon(
                    onPressed: onCreate,
                    icon: const Icon(Icons.add_rounded, size: 18),
                    label: Text(createLabel),
                    style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF6B4BC3),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 13, vertical: 11),
                        textStyle: const TextStyle(
                            fontSize: 11, fontWeight: FontWeight.w700),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(9))),
                  ),
          ],
          if (screenWidth < 700) ...[
            const SizedBox(width: 8),
            PopupMenuButton<String>(
              tooltip: 'Tài khoản',
              offset: const Offset(0, 42),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
              child: Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: const Color(0xFFECE8F9),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFF7555D1)),
                ),
                alignment: Alignment.center,
                child: Text(
                  userName.isNotEmpty ? userName[0].toUpperCase() : 'U',
                  style: const TextStyle(
                      color: Color(0xFF6746C3),
                      fontWeight: FontWeight.w800,
                      fontSize: 13),
                ),
              ),
              itemBuilder: (context) => [
                PopupMenuItem<String>(
                  enabled: false,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(userName,
                          style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF1E1736))),
                      const Text('Optimate x NexUp ERP',
                          style: TextStyle(
                              fontSize: 11, color: Color(0xFF888D87))),
                    ],
                  ),
                ),
                const PopupMenuDivider(),
                const PopupMenuItem<String>(
                  value: 'logout',
                  child: Row(
                    children: [
                      Icon(Icons.logout_rounded,
                          color: Color(0xFFDC2626), size: 18),
                      SizedBox(width: 8),
                      Text('Đăng xuất',
                          style: TextStyle(
                              color: Color(0xFFDC2626),
                              fontWeight: FontWeight.w600)),
                    ],
                  ),
                ),
              ],
              onSelected: (val) {
                if (val == 'logout') {
                  onSignOut?.call();
                }
              },
            ),
          ],
          const SizedBox(width: 5),
        ],
      ),
    );
  }
}

class _PageFrame extends StatelessWidget {
  const _PageFrame({required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          padding: EdgeInsets.fromLTRB(constraints.maxWidth < 600 ? 16 : 28, 24,
              constraints.maxWidth < 600 ? 16 : 28, 32),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1360),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: children),
            ),
          ),
        ),
      );
}

class _PageHeading extends StatelessWidget {
  const _PageHeading(this.title, this.subtitle);
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 20),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Text(title,
                      style: const TextStyle(
                          fontSize: 23,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -.7)),
                  const SizedBox(height: 4),
                  Text(subtitle,
                      style: const TextStyle(
                          fontSize: 12, color: Color(0xFF7F857D)))
                ])),
          ],
        ),
      );
}

class _OverviewPage extends StatelessWidget {
  const _OverviewPage({
    required this.store,
    required this.onNavigate,
    required this.canWrite,
    required this.canApprove,
    required this.canViewOwnerData,
  });
  final CommerceMemoryStore store;
  final ValueChanged<int> onNavigate;
  final bool canWrite;
  final bool canApprove;
  final bool canViewOwnerData;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final cols = width >= 1100
        ? 4
        : width >= 650
            ? 2
            : 1;
    final totalRevenue =
        store.confirmedSales.fold<int>(0, (s, o) => s + o.total);
    final totalGrossProfit = store.confirmedSales.fold<int>(
        0,
        (s, o) =>
            s +
            o.subtotal -
            o.discount -
            o.lines.fold(0, (c, l) => c + l.costAmount));
    final profitMargin = totalRevenue > 0
        ? (totalGrossProfit * 100 / totalRevenue).toStringAsFixed(1)
        : '0.0';
    final cards = [
      if (canViewOwnerData)
        _MetricCard(
            label: 'Doanh thu thuần',
            value: _money(totalRevenue),
            icon: Icons.payments_outlined,
            color: const Color(0xFF7555D1),
            foot: 'Tổng đơn hoàn tất'),
      if (canViewOwnerData)
        _MetricCard(
            label: 'Lợi nhuận gộp',
            value: _money(totalGrossProfit),
            icon: Icons.trending_up_rounded,
            color: const Color(0xFF15966A),
            foot: 'Tỷ suất: $profitMargin%'),
      _MetricCard(
          label: 'Số đơn hàng',
          value: '${store.confirmedSales.length} đơn',
          icon: Icons.receipt_long_outlined,
          color: const Color(0xFF2980B9),
          foot: 'Hoàn tất giao hàng'),
      if (canViewOwnerData)
        _MetricCard(
            label: 'Giá trị tồn kho',
            value: _money(store.inventoryValue.round()),
            icon: Icons.inventory_2_outlined,
            color: const Color(0xFF0284C7),
            foot: '${store.products.length} mặt hàng'),
      if (canViewOwnerData)
        _MetricCard(
            label: 'Tỷ suất lợi nhuận',
            value: '$profitMargin%',
            icon: Icons.percent_rounded,
            color: const Color(0xFFD97706),
            foot: 'Biên lợi nhuận gộp'),
      _MetricCard(
          label: 'Cảnh báo tồn kho',
          value: '${store.lowStockCount} mặt hàng',
          icon: Icons.warning_amber_rounded,
          color: const Color(0xFFE11D48),
          foot: 'Cần bổ sung kho ngay'),
      if (canViewOwnerData)
        _MetricCard(
            label: 'Công nợ phải thu KH',
            value: _money(store.receivableTotal),
            icon: Icons.call_received_rounded,
            color: const Color(0xFF8B5CF6),
            foot: '${store.receivables.length} hóa đơn chưa thu'),
      if (canViewOwnerData)
        _MetricCard(
            label: 'Công nợ phải trả NCC',
            value: _money(store.payableTotal),
            icon: Icons.call_made_rounded,
            color: const Color(0xFFDC2626),
            foot: '${store.payables.length} phiếu cần thanh toán'),
    ];
    return _PageFrame(children: [
      const _PageHeading('Tổng quan vận hành',
          'Theo dõi doanh thu, chi phí, mua bán và công nợ theo thời gian thực.'),
      GridView.count(
          crossAxisCount: cols,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisSpacing: 14,
          mainAxisSpacing: 10,
          childAspectRatio: width < 650 ? 2.2 : (width < 1100 ? 1.85 : 2.2),
          children: cards),
      const SizedBox(height: 22),
      Wrap(spacing: 12, runSpacing: 10, children: [
        if (canWrite)
          _QuickAction(
              label: 'Tạo đơn bán',
              icon: Icons.add_shopping_cart,
              onTap: () => onNavigate(1)),
        if (canWrite)
          _QuickAction(
              label: 'Tạo phiếu nhập',
              icon: Icons.add_box_outlined,
              onTap: () => onNavigate(2)),
        if (canWrite)
          _QuickAction(
              label: 'Kiểm kê kho',
              icon: Icons.fact_check_outlined,
              onTap: () => onNavigate(3)),
        if (canViewOwnerData)
          _QuickAction(
              label: 'Theo dõi công nợ',
              icon: Icons.account_balance_wallet_outlined,
              onTap: () => onNavigate(4)),
        if (canViewOwnerData)
          _QuickAction(
              label: 'Xem báo cáo',
              icon: Icons.bar_chart_rounded,
              onTap: () => onNavigate(5)),
        if (canApprove)
          _QuickAction(
              label: 'Phiếu chờ duyệt',
              icon: Icons.fact_check_outlined,
              onTap: () => onNavigate(6)),
      ]),
      if (canViewOwnerData) ...[
        const SizedBox(height: 22),
        _RevenueTrendCard(store: store),
      ],
      const SizedBox(height: 18),
      _OverviewInsights(store: store, canViewOwnerData: canViewOwnerData),
      const SizedBox(height: 18),
      LayoutBuilder(builder: (context, c) {
        final isWide = c.maxWidth >= 850;
        final lowStock =
            store.products.where((p) => p.stock <= p.minimum).toList();
        return isWide
            ? Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                    flex: 6,
                    child: _RecentOrdersCard(
                        orders: store.orders.take(5).toList(),
                        showFinancialDetails: canViewOwnerData)),
                const SizedBox(width: 16),
                Expanded(flex: 4, child: _LowStockCard(products: lowStock))
              ])
            : Column(children: [
                _RecentOrdersCard(
                    orders: store.orders.take(5).toList(),
                    showFinancialDetails: canViewOwnerData),
                const SizedBox(height: 16),
                _LowStockCard(products: lowStock)
              ]);
      }),
    ]);
  }
}

class _OverviewInsights extends StatelessWidget {
  const _OverviewInsights(
      {required this.store, required this.canViewOwnerData});
  final CommerceMemoryStore store;
  final bool canViewOwnerData;

  @override
  Widget build(BuildContext context) {
    final categoryValues = <String, double>{};
    final soldProducts = <String, double>{};
    final customerSales = <String, int>{};
    for (final product in store.products) {
      categoryValues[product.category] =
          (categoryValues[product.category] ?? 0) +
              product.stock * product.cost;
    }
    for (final order in store.confirmedSales) {
      customerSales[order.partyName] =
          (customerSales[order.partyName] ?? 0) + order.total;
      for (final line in order.lines) {
        soldProducts[line.name] =
            (soldProducts[line.name] ?? 0) + line.quantity;
      }
    }
    final categories = categoryValues.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final products = soldProducts.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final customers = customerSales.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return LayoutBuilder(builder: (context, constraints) {
      final columns = !canViewOwnerData
          ? 1
          : constraints.maxWidth >= 1050
              ? 3
              : constraints.maxWidth >= 620
                  ? 2
                  : 1;
      final spacing = 14.0;
      final width = (constraints.maxWidth - spacing * (columns - 1)) / columns;
      return Wrap(spacing: spacing, runSpacing: spacing, children: [
        if (canViewOwnerData)
          SizedBox(
              width: width,
              child: _OverviewInventoryMix(categories: categories)),
        SizedBox(
            width: width,
            child: _OverviewRanking(
                title: 'Top sản phẩm bán chạy',
                subtitle: 'Theo số lượng đã bán',
                rows: products
                    .take(5)
                    .map((entry) => (
                          entry.key,
                          '${entry.value.toStringAsFixed(0)} sp',
                          entry.value
                        ))
                    .toList(),
                color: const Color(0xFF7955C8))),
        if (canViewOwnerData)
          SizedBox(
              width: width,
              child: _OverviewRanking(
                  title: 'Top khách hàng',
                  subtitle: 'Theo doanh thu tích lũy',
                  rows: customers
                      .take(5)
                      .map((entry) => (
                            entry.key,
                            _money(entry.value),
                            entry.value.toDouble()
                          ))
                      .toList(),
                  color: const Color(0xFF287A59))),
      ]);
    });
  }
}

class _OverviewInventoryMix extends StatelessWidget {
  const _OverviewInventoryMix({required this.categories});
  final List<MapEntry<String, double>> categories;

  @override
  Widget build(BuildContext context) {
    const colors = [
      Color(0xFF7955C8),
      Color(0xFF287A59),
      Color(0xFFE1A34E),
      Color(0xFF4D91A7),
      Color(0xFFD87558),
    ];
    final total = categories.fold<double>(0, (sum, item) => sum + item.value);
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: _cardDecoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Cơ cấu giá trị tồn kho',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        Text('${categories.length} nhóm hàng',
            style: const TextStyle(fontSize: 11, color: Color(0xFF81877F))),
        const SizedBox(height: 16),
        if (total <= 0)
          const SizedBox(
              height: 150,
              child: Center(
                  child: Text('Chưa có dữ liệu tồn kho.',
                      style:
                          TextStyle(fontSize: 11, color: Color(0xFF81877F)))))
        else
          Row(children: [
            SizedBox(
                width: 112,
                height: 112,
                child: PieChart(PieChartData(
                    centerSpaceRadius: 31,
                    sectionsSpace: 3,
                    sections: [
                      for (var i = 0; i < categories.length; i++)
                        PieChartSectionData(
                            value: categories[i].value,
                            color: colors[i % colors.length],
                            radius: 20,
                            showTitle: false)
                    ]))),
            const SizedBox(width: 14),
            Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  for (var i = 0; i < math.min(5, categories.length); i++)
                    Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: Row(children: [
                          Container(
                              width: 8,
                              height: 8,
                              decoration: BoxDecoration(
                                  color: colors[i % colors.length],
                                  shape: BoxShape.circle)),
                          const SizedBox(width: 7),
                          Expanded(
                              child: Text(categories[i].key,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(fontSize: 10))),
                          Text(
                              '${(categories[i].value * 100 / total).round()}%',
                              style: const TextStyle(
                                  fontSize: 10, fontWeight: FontWeight.w700)),
                        ]))
                ]))
          ])
      ]),
    );
  }
}

class _OverviewRanking extends StatelessWidget {
  const _OverviewRanking({
    required this.title,
    required this.subtitle,
    required this.rows,
    required this.color,
  });
  final String title;
  final String subtitle;
  final List<(String, String, double)> rows;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final maximum = rows.isEmpty || rows.first.$3 <= 0 ? 1.0 : rows.first.$3;
    return Container(
        padding: const EdgeInsets.all(18),
        decoration: _cardDecoration(),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title,
              style:
                  const TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text(subtitle,
              style: const TextStyle(fontSize: 11, color: Color(0xFF81877F))),
          const SizedBox(height: 15),
          if (rows.isEmpty)
            const SizedBox(
                height: 110,
                child: Center(
                    child: Text('Chưa có dữ liệu.',
                        style:
                            TextStyle(fontSize: 11, color: Color(0xFF81877F)))))
          else
            for (var i = 0; i < rows.length; i++) ...[
              Row(children: [
                Container(
                    width: 21,
                    height: 21,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                        color: i == 0
                            ? color.withValues(alpha: .12)
                            : const Color(0xFFF3F4F2),
                        shape: BoxShape.circle),
                    child: Text('${i + 1}',
                        style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            color: i == 0 ? color : const Color(0xFF81877F)))),
                const SizedBox(width: 8),
                Expanded(
                    child: Text(rows[i].$1,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 11, fontWeight: FontWeight.w600))),
                Text(rows[i].$2,
                    style: const TextStyle(
                        fontSize: 10, fontWeight: FontWeight.w700)),
              ]),
              const SizedBox(height: 5),
              ClipRRect(
                  borderRadius: BorderRadius.circular(5),
                  child: LinearProgressIndicator(
                      value: rows[i].$3 / maximum,
                      minHeight: 4,
                      color: color,
                      backgroundColor: const Color(0xFFF0F1EF))),
              if (i != rows.length - 1) const SizedBox(height: 10),
            ]
        ]));
  }
}

class _RevenueTrendCard extends StatelessWidget {
  const _RevenueTrendCard({required this.store});
  final CommerceMemoryStore store;

  @override
  Widget build(BuildContext context) {
    final today = DateTime.now();
    final months =
        List.generate(12, (index) => DateTime(today.year, index + 1));
    final values = months
        .map((month) => store.confirmedSales
            .where((order) =>
                order.createdAt.year == month.year &&
                order.createdAt.month == month.month)
            .fold<int>(0, (sum, order) => sum + order.total))
        .toList(growable: false);
    final maxY =
        values.fold<int>(0, (value, item) => item > value ? item : value);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 8),
      decoration: _cardDecoration(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Doanh thu theo tháng',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
          const SizedBox(height: 16),
          SizedBox(
            height: 180,
            child: BarChart(
              BarChartData(
                maxY: maxY == 0 ? 1 : maxY * 1.18,
                minY: 0,
                gridData: const FlGridData(show: false),
                borderData: FlBorderData(show: false),
                barTouchData: BarTouchData(enabled: false),
                titlesData: FlTitlesData(
                  leftTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  topTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 26,
                      getTitlesWidget: (value, meta) {
                        final index = value.toInt();
                        if (index < 0 || index >= months.length) {
                          return const SizedBox.shrink();
                        }
                        return Padding(
                          padding: const EdgeInsets.only(top: 7),
                          child: Text('T${months[index].month}',
                              style: const TextStyle(
                                  fontSize: 9, color: Color(0xFF81877F))),
                        );
                      },
                    ),
                  ),
                ),
                barGroups: [
                  for (var index = 0; index < values.length; index++)
                    BarChartGroupData(x: index, barRods: [
                      BarChartRodData(
                        toY:
                            values[index] == 0 ? .02 : values[index].toDouble(),
                        width: 14,
                        color: const Color(0xFF7657CF),
                        borderRadius: BorderRadius.circular(5),
                        backDrawRodData: BackgroundBarChartRodData(
                          show: true,
                          toY: maxY == 0 ? 1 : maxY * 1.18,
                          color: const Color(0xFFF2F0F8),
                        ),
                      )
                    ])
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard(
      {required this.label,
      required this.value,
      required this.icon,
      required this.color,
      required this.foot});
  final String label;
  final String value;
  final IconData icon;
  final Color color;
  final String foot;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: _cardDecoration(),
        child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(children: [
                Expanded(
                    child: Text(label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 11,
                            color: Color(0xFF777D76),
                            fontWeight: FontWeight.w600))),
                Container(
                    width: 28,
                    height: 28,
                    decoration: BoxDecoration(
                        color: color.withValues(alpha: .1),
                        borderRadius: BorderRadius.circular(8)),
                    child: Icon(icon, color: color, size: 16))
              ]),
              FittedBox(
                  alignment: Alignment.centerLeft,
                  fit: BoxFit.scaleDown,
                  child: Text(value,
                      style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -.6))),
              Text(foot,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 10, color: Color(0xFF858B84))),
            ]),
      );
}

class _QuickAction extends StatelessWidget {
  const _QuickAction(
      {required this.label, required this.icon, required this.onTap});
  final String label;
  final IconData icon;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => OutlinedButton.icon(
      onPressed: onTap,
      icon: Icon(icon, size: 17),
      label: Text(label),
      style: OutlinedButton.styleFrom(
          foregroundColor: const Color(0xFF5F43B2),
          side: const BorderSide(color: Color(0xFFDCD5EF)),
          backgroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 12),
          textStyle: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(9))));
}

class _OrderListPage extends StatefulWidget {
  const _OrderListPage(
      {required this.store,
      required this.kind,
      required this.onCreate,
      required this.canWrite,
      required this.canViewOwnerData,
      this.api,
      this.onRefresh});
  final CommerceMemoryStore store;
  final String kind;
  final VoidCallback onCreate;
  final bool canWrite;
  final bool canViewOwnerData;
  final CommerceApi? api;
  final Future<void> Function()? onRefresh;
  @override
  State<_OrderListPage> createState() => _OrderListPageState();
}

class _OrderListPageState extends State<_OrderListPage> {
  String _query = '';
  String _section = '';
  String _statusFilter = 'Tất cả trạng thái';
  String _periodFilter = 'Mọi thời gian';
  String _sortFilter = 'Mới nhất trước';

  Future<void> _addParty(String kind) async {
    final requestKey = CommerceApi.newIdempotencyKey();
    final details = await _showPartyDialog(
        context, kind == 'customer' ? 'khách hàng' : 'nhà cung cấp');
    if (details == null || !mounted) return;
    try {
      if (widget.api case final api?) {
        await api.createParty(
            kind: kind,
            name: details.$1,
            phone: details.$2,
            idempotencyKey: requestKey);
        await widget.onRefresh?.call();
      } else {
        widget.store.addParty(kind: kind, name: details.$1, phone: details.$2);
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('$error')));
    }
  }

  Future<void> _convertQuote(CommerceOrder quote) async {
    try {
      if (widget.api case final api?) {
        await api.convertQuote(quote.id);
        await widget.onRefresh?.call();
      } else {
        widget.store.convertQuote(quote.id);
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Đã chuyển ${quote.code} thành đơn bán.')),
      );
    } catch (error) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$error'),
          backgroundColor: const Color(0xFFB34B43),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final screenWidth = MediaQuery.sizeOf(context).width;
    final pageWidth = screenWidth - (screenWidth >= 700 ? 232 : 0);
    final salesWorkspace = widget.kind == 'sale';
    final purchaseWorkspace = widget.kind == 'purchase';
    final isGroupedWorkspace = salesWorkspace || purchaseWorkspace;
    final sectionOptions = salesWorkspace
        ? [
            'Tổng quan bán hàng',
            'Báo giá',
            'Khách hàng',
            if (widget.canViewOwnerData) 'Công nợ khách hàng',
          ]
        : purchaseWorkspace
            ? [
                'Tổng quan mua hàng',
                'Nhà cung cấp',
                if (widget.canViewOwnerData) 'Công nợ NCC',
              ]
            : const <String>[];
    final defaultSection = salesWorkspace
        ? 'Tổng quan bán hàng'
        : purchaseWorkspace
            ? 'Tổng quan mua hàng'
            : 'Báo giá';
    final section =
        sectionOptions.contains(_section) ? _section : defaultSection;
    final customerDirectory = salesWorkspace && section == 'Khách hàng';
    final supplierDirectory = purchaseWorkspace && section == 'Nhà cung cấp';
    final partyDirectory = customerDirectory || supplierDirectory;
    final quote =
        widget.kind == 'quote' || (salesWorkspace && section == 'Báo giá');
    final sale = salesWorkspace && !quote && !customerDirectory;
    final sourceOrders = quote
        ? widget.store.quotes
        : sale
            ? widget.store.sales
            : widget.store.purchases;
    final summaryOrders = sourceOrders;
    final now = DateTime.now();
    final orders = sourceOrders
        .where((o) =>
            o.code.toLowerCase().contains(_query.toLowerCase()) ||
            o.partyName.toLowerCase().contains(_query.toLowerCase()))
        .where((order) {
      if (_statusFilter == 'Tất cả trạng thái') return true;
      if (_statusFilter == 'Chờ duyệt') {
        return order.state == CommerceOrderState.pending;
      }
      if (_statusFilter == 'Đã từ chối') {
        return order.state == CommerceOrderState.cancelled;
      }
      if (_statusFilter == 'Chờ phản hồi') {
        return order.state == CommerceOrderState.draft;
      }
      if (_statusFilter == 'Đã chuyển đơn') {
        return order.state == CommerceOrderState.converted;
      }
      if (_statusFilter == 'Chưa thanh toán') {
        return order.state == CommerceOrderState.completed && order.paid == 0;
      }
      if (_statusFilter == 'Thanh toán một phần') {
        return order.state == CommerceOrderState.completed &&
            order.paid > 0 &&
            order.outstanding > 0;
      }
      if (_statusFilter == 'Đã thanh toán') {
        return order.state == CommerceOrderState.completed &&
            order.outstanding == 0;
      }
      return true;
    }).where((order) {
      final age = now.difference(order.createdAt).inDays;
      return switch (_periodFilter) {
        'Hôm nay' => CommerceMemoryStore.sameDay(order.createdAt, now),
        '7 ngày qua' => age >= 0 && age < 7,
        '30 ngày qua' => age >= 0 && age < 30,
        _ => true,
      };
    }).toList()
      ..sort((a, b) => _sortFilter == 'Mới nhất trước'
          ? b.createdAt.compareTo(a.createdAt)
          : a.createdAt.compareTo(b.createdAt));
    final postedOrders = quote
        ? summaryOrders
        : summaryOrders
            .where((order) => order.state == CommerceOrderState.completed)
            .toList();
    final due = postedOrders.fold<int>(0, (sum, o) => sum + o.outstanding);
    final parties = (customerDirectory
            ? widget.store.customers
            : supplierDirectory
                ? widget.store.suppliers
                : const <CommerceParty>[])
        .where((party) =>
            party.name.toLowerCase().contains(_query.toLowerCase()) ||
            party.phone.toLowerCase().contains(_query.toLowerCase()))
        .toList(growable: false);
    final headingTitle = customerDirectory
        ? 'Khách hàng'
        : supplierDirectory
            ? 'Nhà cung cấp'
            : quote
                ? 'Quản lý báo giá'
                : sale
                    ? 'Quản lý bán hàng'
                    : 'Quản lý mua hàng';
    final headingSubtitle = customerDirectory
        ? 'Danh sách khách hàng và thông tin liên hệ.'
        : supplierDirectory
            ? 'Danh sách nhà cung cấp và thông tin liên hệ.'
            : quote
                ? 'Lập báo giá nhanh và chuyển thành đơn bán khi khách đồng ý.'
                : sale
                    ? 'Theo dõi đơn bán, thanh toán và doanh thu.'
                    : 'Theo dõi phiếu nhập, nhà cung cấp và thanh toán.';
    final summary = partyDirectory
        ? <(String, String, IconData)>[
            (
              customerDirectory ? 'Khách hàng' : 'Nhà cung cấp',
              '${parties.length}',
              Icons.people_outline_rounded
            ),
            (
              'Có số điện thoại',
              '${parties.where((party) => party.phone.isNotEmpty).length}',
              Icons.phone_outlined
            ),
          ]
        : sale
            ? <(String, String, IconData)>[
                (
                  'Doanh thu',
                  _money(postedOrders.fold<int>(0, (s, o) => s + o.total)),
                  Icons.payments_outlined
                ),
                (
                  'Lợi nhuận',
                  _money(postedOrders.fold<int>(
                      0,
                      (sum, order) =>
                          sum +
                          order.subtotal -
                          order.discount -
                          order.lines.fold<int>(
                              0, (cost, line) => cost + line.costAmount))),
                  Icons.trending_up_rounded
                ),
                (
                  'Số phiếu bán',
                  '${summaryOrders.length}',
                  Icons.receipt_long_outlined
                ),
                (
                  'Phải thu',
                  _money(due),
                  Icons.account_balance_wallet_outlined
                ),
              ]
            : quote
                ? <(String, String, IconData)>[
                    (
                      'Tổng báo giá',
                      '${summaryOrders.length}',
                      Icons.receipt_long_outlined
                    ),
                    (
                      'Tổng giá trị báo',
                      _money(summaryOrders.fold<int>(0, (s, o) => s + o.total)),
                      Icons.payments_outlined
                    ),
                    (
                      'Đang chờ khách',
                      '${summaryOrders.where((o) => o.state == CommerceOrderState.draft).length} phiếu',
                      Icons.hourglass_empty_rounded
                    ),
                    (
                      'Đã chuyển đơn',
                      '${summaryOrders.where((o) => o.state == CommerceOrderState.converted).length} phiếu',
                      Icons.check_circle_outline_rounded
                    ),
                  ]
                : <(String, String, IconData)>[
                    (
                      'Tổng mua hàng',
                      _money(postedOrders.fold<int>(0, (s, o) => s + o.total)),
                      Icons.shopping_bag_outlined
                    ),
                    (
                      'Số phiếu mua',
                      '${summaryOrders.length}',
                      Icons.receipt_long_outlined
                    ),
                    (
                      'Công nợ phải trả',
                      _money(due),
                      Icons.account_balance_wallet_outlined
                    ),
                    (
                      'NCC đang hợp tác',
                      '${widget.store.suppliers.length}',
                      Icons.people_outline_rounded
                    ),
                  ];
    final documentLabel = customerDirectory
        ? 'Danh sách khách hàng'
        : supplierDirectory
            ? 'Danh sách nhà cung cấp'
            : quote
                ? 'Danh sách báo giá'
                : sale
                    ? 'Danh sách đơn bán'
                    : 'Danh sách phiếu nhập';
    final createLabel = customerDirectory
        ? 'Thêm khách hàng'
        : supplierDirectory
            ? 'Thêm nhà cung cấp'
            : quote
                ? 'Tạo báo giá'
                : sale
                    ? 'Tạo đơn bán'
                    : 'Tạo phiếu nhập';
    final hasRows = partyDirectory ? parties.isNotEmpty : orders.isNotEmpty;
    final hasUnfilteredRows = partyDirectory
        ? (customerDirectory ? widget.store.customers : widget.store.suppliers)
            .isNotEmpty
        : summaryOrders.isNotEmpty;
    final emptyMessage = hasUnfilteredRows
        ? 'Không có dữ liệu khớp với bộ lọc.'
        : customerDirectory
            ? 'Chưa có khách hàng. Thêm khách hàng để lập đơn bán.'
            : supplierDirectory
                ? 'Chưa có nhà cung cấp. Thêm nhà cung cấp để lập phiếu nhập.'
                : quote
                    ? 'Chưa có báo giá. Tạo báo giá đầu tiên để gửi khách hàng.'
                    : sale
                        ? 'Chưa có đơn bán. Tạo đơn bán đầu tiên để bắt đầu.'
                        : 'Chưa có phiếu mua. Tạo phiếu mua đầu tiên để nhập hàng.';
    final searchField = (double? width) => SizedBox(
          width: width,
          height: 38,
          child: TextField(
              onChanged: (v) => setState(() => _query = v),
              decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.search, size: 17),
                  hintText: partyDirectory
                      ? 'Tìm tên, số điện thoại...'
                      : 'Tìm mã phiếu, khách hàng...',
                  isDense: true,
                  contentPadding: const EdgeInsets.symmetric(vertical: 8),
                  border: const OutlineInputBorder())),
        );
    final statusOptions = quote
        ? const [
            'Tất cả trạng thái',
            'Chờ phản hồi',
            'Đã chuyển đơn',
            'Đã từ chối',
          ]
        : widget.canViewOwnerData
            ? const [
                'Tất cả trạng thái',
                'Chờ duyệt',
                'Chưa thanh toán',
                'Thanh toán một phần',
                'Đã thanh toán',
                'Đã từ chối',
              ]
            : const ['Tất cả trạng thái', 'Chờ duyệt', 'Đã từ chối'];
    final filters = partyDirectory
        ? const SizedBox.shrink()
        : SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                _OrderFilterSelect(
                  value: statusOptions.contains(_statusFilter)
                      ? _statusFilter
                      : statusOptions.first,
                  items: statusOptions,
                  icon: Icons.tune_rounded,
                  onChanged: (value) => setState(() => _statusFilter = value),
                ),
                const SizedBox(width: 8),
                _OrderFilterSelect(
                  value: _periodFilter,
                  items: const [
                    'Mọi thời gian',
                    'Hôm nay',
                    '7 ngày qua',
                    '30 ngày qua',
                  ],
                  icon: Icons.calendar_today_outlined,
                  onChanged: (value) => setState(() => _periodFilter = value),
                ),
                const SizedBox(width: 8),
                _OrderFilterSelect(
                  value: _sortFilter,
                  items: const ['Mới nhất trước', 'Cũ nhất trước'],
                  icon: Icons.swap_vert_rounded,
                  onChanged: (value) => setState(() => _sortFilter = value),
                ),
              ],
            ),
          );
    final createButton = FilledButton.icon(
        onPressed: customerDirectory
            ? () => _addParty('customer')
            : supplierDirectory
                ? () => _addParty('supplier')
                : quote
                    ? () => _showCreateOrder(context, widget.store, 'quote',
                        api: widget.api,
                        onRefresh: widget.onRefresh,
                        canViewOwnerData: widget.canViewOwnerData)
                    : widget.onCreate,
        icon: const Icon(Icons.add, size: 17),
        label: Text(createLabel),
        style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF6B4BC3),
            textStyle:
                const TextStyle(fontSize: 11, fontWeight: FontWeight.w700)));
    return _PageFrame(children: [
      _PageHeading(headingTitle, headingSubtitle),
      if (isGroupedWorkspace)
        _WorkspaceSectionTabs(
          labels: sectionOptions,
          selected: section,
          onSelect: (value) => setState(() {
            _section = value;
            _query = '';
            _statusFilter = 'Tất cả trạng thái';
            _periodFilter = 'Mọi thời gian';
            _sortFilter = 'Mới nhất trước';
          }),
        ),
      _MiniSummaryRow(
          items: widget.canViewOwnerData
              ? summary
              : summary
                  .where((item) =>
                      item.$1.contains('Số phiếu') ||
                      item.$1.contains('Tổng báo giá') ||
                      item.$1 == 'Khách hàng' ||
                      item.$1 == 'Nhà cung cấp' ||
                      item.$1 == 'Có số điện thoại' ||
                      item.$1 == 'NCC đang hợp tác')
                  .toList()),
      const SizedBox(height: 20),
      Container(
          decoration: _cardDecoration(),
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (pageWidth < 700) ...[
              Text(documentLabel,
                  style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w800)),
              const SizedBox(height: 10),
              Row(children: [
                Expanded(child: searchField(null)),
                if (widget.canWrite) ...[
                  const SizedBox(width: 8),
                  createButton,
                ],
              ]),
            ] else
              Row(children: [
                Expanded(
                    child: Text(documentLabel,
                        style: const TextStyle(
                            fontSize: 15, fontWeight: FontWeight.w800))),
                searchField(250),
                if (widget.canWrite) ...[
                  const SizedBox(width: 10),
                  createButton,
                ],
              ]),
            const SizedBox(height: 12),
            filters,
            if (!partyDirectory) const SizedBox(height: 8),
            if (partyDirectory)
              _PartyTable(parties: parties)
            else if (pageWidth < 700)
              for (final order in orders)
                _OrderListTile(
                  order: order,
                  onConvert: widget.canWrite &&
                          quote &&
                          order.state == CommerceOrderState.draft
                      ? () => _convertQuote(order)
                      : null,
                  showFinancialDetails: widget.canViewOwnerData,
                )
            else
              _OrdersTable(
                orders: orders,
                onConvert: quote ? _convertQuote : null,
                showFinancialDetails: widget.canViewOwnerData,
              ),
            if (!hasRows)
              Padding(
                  padding: EdgeInsets.all(28),
                  child: Center(
                      child: Text(emptyMessage,
                          style: TextStyle(
                              color: Color(0xFF7F857D), fontSize: 12)))),
          ])),
    ]);
  }
}

class _WorkspaceSectionTabs extends StatelessWidget {
  const _WorkspaceSectionTabs({
    required this.labels,
    required this.selected,
    required this.onSelect,
  });
  final List<String> labels;
  final String selected;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final label in labels) ...[
                InkWell(
                  borderRadius: BorderRadius.circular(20),
                  onTap: () => onSelect(label),
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                    decoration: BoxDecoration(
                      color: selected == label
                          ? const Color(0xFFEDE8FC)
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: selected == label
                            ? const Color(0xFF7657CF)
                            : Colors.transparent,
                        width: 1.2,
                      ),
                    ),
                    child: Text(label,
                        style: TextStyle(
                            fontSize: 12,
                            fontWeight: selected == label
                                ? FontWeight.w700
                                : FontWeight.w500,
                            color: selected == label
                                ? const Color(0xFF6848BC)
                                : const Color(0xFF727771))),
                  ),
                ),
                const SizedBox(width: 6),
              ],
            ],
          ),
        ),
      );
}

class _OrderFilterSelect extends StatelessWidget {
  const _OrderFilterSelect({
    required this.value,
    required this.items,
    required this.icon,
    required this.onChanged,
  });

  final String value;
  final List<String> items;
  final IconData icon;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final width = icon == Icons.tune_rounded ? 205.0 : 150.0;
    return Container(
      width: width,
      height: 36,
      padding: const EdgeInsets.only(left: 8, right: 7),
      decoration: BoxDecoration(
        color: const Color(0xFFFAFBF9),
        border: Border.all(color: const Color(0xFFE5E8E3)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(icon, size: 15, color: const Color(0xFF777D76)),
          const SizedBox(width: 6),
          Expanded(
            child: DropdownButton<String>(
              value: value,
              isExpanded: true,
              isDense: true,
              iconSize: 16,
              underline: const SizedBox.shrink(),
              style: const TextStyle(
                  fontSize: 10.5,
                  color: Color(0xFF454A44),
                  fontWeight: FontWeight.w600),
              items: items
                  .map((item) => DropdownMenuItem(
                        value: item,
                        child: Text(item,
                            maxLines: 1, overflow: TextOverflow.ellipsis),
                      ))
                  .toList(growable: false),
              onChanged: (next) {
                if (next != null) onChanged(next);
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _PartyTable extends StatelessWidget {
  const _PartyTable({required this.parties});
  final List<CommerceParty> parties;

  @override
  Widget build(BuildContext context) {
    if (MediaQuery.sizeOf(context).width < 700) {
      return Column(
        children: [
          for (final party in parties)
            ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 4),
              leading: const CircleAvatar(
                  backgroundColor: Color(0xFFF1EDFC),
                  child: Icon(Icons.person_outline,
                      color: Color(0xFF6848BC), size: 18)),
              title: Text(party.name,
                  style: const TextStyle(
                      fontSize: 12, fontWeight: FontWeight.w700)),
              subtitle: Text(
                  party.phone.isEmpty ? 'Chưa có số điện thoại' : party.phone,
                  style: const TextStyle(fontSize: 10)),
            ),
        ],
      );
    }
    return SizedBox(
      width: double.infinity,
      child: DataTable(
        headingRowHeight: 38,
        dataRowMinHeight: 48,
        dataRowMaxHeight: 56,
        horizontalMargin: 8,
        columnSpacing: 32,
        headingTextStyle: const TextStyle(
            fontSize: 10,
            color: Color(0xFF737971),
            fontWeight: FontWeight.w700),
        columns: const [
          DataColumn(label: Text('TÊN ĐỐI TÁC')),
          DataColumn(label: Text('SỐ ĐIỆN THOẠI')),
          DataColumn(label: Text('PHÂN LOẠI')),
        ],
        rows: parties
            .map((party) => DataRow(cells: [
                  DataCell(Text(party.name,
                      style: const TextStyle(
                          fontSize: 11, fontWeight: FontWeight.w600))),
                  DataCell(Text(party.phone.isEmpty ? '—' : party.phone,
                      style: const TextStyle(fontSize: 11))),
                  DataCell(Text(
                      party.kind == 'customer' ? 'Khách hàng' : 'Nhà cung cấp',
                      style: const TextStyle(fontSize: 10))),
                ]))
            .toList(growable: false),
      ),
    );
  }
}

class _MiniSummaryRow extends StatelessWidget {
  const _MiniSummaryRow({required this.items});
  final List<(String, String, IconData)> items;
  @override
  Widget build(BuildContext context) {
    final count = MediaQuery.sizeOf(context).width >= 1000 ? 4 : 2;
    const colors = [
      (Color(0xFF7253C8), Color(0xFFEDE8FC)),
      (Color(0xFF0284C7), Color(0xFFE0F2FE)),
      (Color(0xFFD97706), Color(0xFFFEF3C7)),
      (Color(0xFFDC2626), Color(0xFFFEE2E2)),
    ];
    return GridView.count(
        crossAxisCount: count,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: MediaQuery.sizeOf(context).width < 600 ? 2.65 : 3.6,
        children: items.asMap().entries.map((entry) {
          final idx = entry.key % colors.length;
          final (fg, bg) = colors[idx];
          final e = entry.value;
          return Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: _cardDecoration(),
              child: Row(children: [
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: bg,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(e.$3, size: 19, color: fg),
                ),
                const SizedBox(width: 11),
                Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                      Text(e.$1,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 10,
                              color: Color(0xFF7F857D),
                              fontWeight: FontWeight.w600)),
                      const SizedBox(height: 3),
                      Text(e.$2,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w800,
                              letterSpacing: -.3))
                    ]))
              ]));
        }).toList());
  }
}

class _OrdersTable extends StatelessWidget {
  const _OrdersTable({
    required this.orders,
    required this.showFinancialDetails,
    this.onConvert,
  });
  final List<CommerceOrder> orders;
  final bool showFinancialDetails;
  final ValueChanged<CommerceOrder>? onConvert;
  @override
  Widget build(BuildContext context) => SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SizedBox(
          width: showFinancialDetails ? 1160 : 820,
          child: DataTable(
              headingRowHeight: 38,
              dataRowMinHeight: 46,
              dataRowMaxHeight: 54,
              horizontalMargin: 8,
              columnSpacing: 20,
              headingTextStyle: const TextStyle(
                  fontSize: 10,
                  color: Color(0xFF737971),
                  fontWeight: FontWeight.w700),
              columns: [
                const DataColumn(label: Text('MÃ PHIẾU')),
                const DataColumn(label: Text('NGÀY')),
                const DataColumn(label: Text('ĐỐI TÁC')),
                if (showFinancialDetails) ...[
                  const DataColumn(label: Text('TỔNG TIỀN'), numeric: true),
                  const DataColumn(label: Text('CÒN NỢ'), numeric: true),
                  const DataColumn(label: Text('THANH TOÁN')),
                ],
                const DataColumn(label: Text('GHI CHÚ')),
                const DataColumn(label: Text('TRẠNG THÁI')),
                if (showFinancialDetails)
                  const DataColumn(label: Text('IN PHIẾU')),
                if (onConvert != null)
                  const DataColumn(label: Text('THAO TÁC')),
              ],
              rows: orders
                  .map((o) => DataRow(cells: [
                        DataCell(Text(o.code,
                            style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF6546BA)))),
                        DataCell(Text(
                            DateFormat('dd/MM/yyyy').format(o.createdAt),
                            style: const TextStyle(fontSize: 10))),
                        DataCell(Text(o.partyName,
                            style: const TextStyle(
                                fontSize: 11, fontWeight: FontWeight.w600))),
                        if (showFinancialDetails)
                          DataCell(Text(_money(o.total),
                              style: const TextStyle(
                                  fontSize: 11, fontWeight: FontWeight.w700))),
                        if (showFinancialDetails)
                          DataCell(Text(
                            _money(o.outstanding),
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: o.outstanding > 0
                                  ? const Color(0xFFDC2626)
                                  : const Color(0xFF16A34A),
                            ),
                          )),
                        if (showFinancialDetails)
                          DataCell(_PaymentBadge(label: o.paymentStatus)),
                        DataCell(Text(
                          o.note.isEmpty ? '—' : o.note,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 10, color: Color(0xFF6B7280)),
                        )),
                        DataCell(_OrderStatusBadge(order: o)),
                        if (showFinancialDetails)
                          DataCell(_OrderPdfMenu(order: o)),
                        if (onConvert != null)
                          DataCell(TextButton(
                            onPressed: o.state == CommerceOrderState.draft
                                ? () => onConvert!(o)
                                : null,
                            child: const Text('Chuyển thành đơn'),
                          )),
                      ]))
                  .toList())));
}

class _OrderStatusBadge extends StatelessWidget {
  const _OrderStatusBadge({required this.order});
  final CommerceOrder order;

  @override
  Widget build(BuildContext context) {
    final (label, fg, bg) = switch (order.state) {
      CommerceOrderState.completed => (
          order.kind == 'purchase' ? 'Đã nhập kho' : 'Hoàn tất',
          const Color(0xFF16A34A),
          const Color(0xFFDCFCE7),
        ),
      CommerceOrderState.pending => (
          order.kind == 'purchase' ? 'Đang chờ hàng' : 'Đang xử lý',
          const Color(0xFFD97706),
          const Color(0xFFFEF3C7),
        ),
      CommerceOrderState.converted => (
          'Đã chuyển đơn',
          const Color(0xFF6B4BC3),
          const Color(0xFFEDE8FC),
        ),
      CommerceOrderState.draft => (
          'Chờ phản hồi',
          const Color(0xFF4B5563),
          const Color(0xFFF3F4F6),
        ),
      CommerceOrderState.cancelled => (
          'Đã huỷ',
          const Color(0xFFDC2626),
          const Color(0xFFFEE2E2),
        ),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(label,
          style:
              TextStyle(fontSize: 9, color: fg, fontWeight: FontWeight.w700)),
    );
  }
}

class _OrderListTile extends StatelessWidget {
  const _OrderListTile({
    required this.order,
    this.onConvert,
    this.showFinancialDetails = true,
  });
  final CommerceOrder order;
  final VoidCallback? onConvert;
  final bool showFinancialDetails;
  @override
  Widget build(BuildContext context) => Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
          color: const Color(0xFFFAFBF9),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: const Color(0xFFECEEEA))),
      child: Row(children: [
        Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(order.code,
              style: const TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 11,
                  color: Color(0xFF6546BA))),
          const SizedBox(height: 3),
          Text(order.partyName, style: const TextStyle(fontSize: 11)),
          const SizedBox(height: 6),
          if (showFinancialDetails) _PaymentBadge(label: order.paymentStatus)
        ])),
        Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          if (showFinancialDetails)
            Text(_money(order.total),
                style:
                    const TextStyle(fontWeight: FontWeight.w800, fontSize: 12)),
          const SizedBox(height: 5),
          Text(DateFormat('dd/MM').format(order.createdAt),
              style: const TextStyle(fontSize: 10, color: Color(0xFF81877F)))
        ]),
        if (!showFinancialDetails) _OrderStatusBadge(order: order),
        if (showFinancialDetails) _OrderPdfMenu(order: order),
        if (onConvert != null)
          IconButton(
            tooltip: 'Chuyển thành đơn bán',
            onPressed: onConvert,
            icon: const Icon(Icons.arrow_forward_rounded),
          ),
      ]));
}

class _PaymentBadge extends StatelessWidget {
  const _PaymentBadge({required this.label});
  final String label;
  @override
  Widget build(BuildContext context) {
    final paid = label == 'Đã thanh toán';
    final partial = label == 'Thanh toán một phần';
    final quote = label == 'Chờ phản hồi' || label == 'Đã chuyển đơn';
    final color = paid
        ? const Color(0xFF1D936A)
        : quote
            ? const Color(0xFF6750A4)
            : partial
                ? const Color(0xFFBD7B23)
                : const Color(0xFFBC4B4B);
    return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
            color: color.withValues(alpha: .09),
            borderRadius: BorderRadius.circular(20)),
        child: Text(label,
            style: TextStyle(
                fontSize: 9, color: color, fontWeight: FontWeight.w700)));
  }
}

class _OrderPdfMenu extends StatelessWidget {
  const _OrderPdfMenu({required this.order});
  final CommerceOrder order;

  @override
  Widget build(BuildContext context) => PopupMenuButton<String>(
        tooltip: 'In, tải hoặc chia sẻ phiếu',
        icon: const Icon(Icons.print_outlined, size: 19),
        onSelected: (action) => action == 'share'
            ? _shareOrder(context, order)
            : _printOrder(context, order),
        itemBuilder: (context) => const [
          PopupMenuItem(
            value: 'print',
            child: ListTile(
              leading: Icon(Icons.download_outlined),
              title: Text('In / tải PDF'),
              contentPadding: EdgeInsets.zero,
              dense: true,
            ),
          ),
          PopupMenuItem(
            value: 'share',
            child: ListTile(
              leading: Icon(Icons.share_outlined),
              title: Text('Chia sẻ qua email hoặc ứng dụng'),
              contentPadding: EdgeInsets.zero,
              dense: true,
            ),
          ),
        ],
      );
}

class _RecentOrdersCard extends StatelessWidget {
  const _RecentOrdersCard({
    required this.orders,
    this.showFinancialDetails = true,
  });
  final List<CommerceOrder> orders;
  final bool showFinancialDetails;
  @override
  Widget build(BuildContext context) => Container(
      decoration: _cardDecoration(),
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Chứng từ gần đây',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
        const SizedBox(height: 10),
        for (final order in orders)
          _OrderListTile(
              order: order, showFinancialDetails: showFinancialDetails)
      ]));
}

class _LowStockCard extends StatelessWidget {
  const _LowStockCard({required this.products});
  final List<CommerceProduct> products;
  @override
  Widget build(BuildContext context) => Container(
      decoration: _cardDecoration(),
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(
              child: Text('Cảnh báo tồn kho',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800))),
          Text('${products.length} mặt hàng',
              style: const TextStyle(
                  fontSize: 10,
                  color: Color(0xFFBD7B23),
                  fontWeight: FontWeight.w700))
        ]),
        const SizedBox(height: 10),
        if (products.isEmpty)
          const Text('Tồn kho đang trong định mức.',
              style: TextStyle(fontSize: 11, color: Color(0xFF7F857D))),
        for (final p in products)
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 7),
              child: Row(children: [
                const Icon(Icons.warning_amber_rounded,
                    color: Color(0xFFDB9142), size: 17),
                const SizedBox(width: 8),
                Expanded(
                    child: Text(p.name,
                        style: const TextStyle(
                            fontSize: 11, fontWeight: FontWeight.w600))),
                Text('${p.stock} / ${p.minimum} ${p.unit}',
                    style: const TextStyle(
                        fontSize: 10,
                        color: Color(0xFFB36B25),
                        fontWeight: FontWeight.w700))
              ]))
      ]));
}

class _InventoryPage extends StatefulWidget {
  const _InventoryPage({
    required this.store,
    required this.canManageCatalog,
    required this.canWrite,
    required this.canViewOwnerData,
    required this.onNavigate,
    this.api,
    this.onRefresh,
  });
  final CommerceMemoryStore store;
  final bool canManageCatalog;
  final bool canWrite;
  final bool canViewOwnerData;
  final ValueChanged<int> onNavigate;
  final CommerceApi? api;
  final Future<void> Function()? onRefresh;
  @override
  State<_InventoryPage> createState() => _InventoryPageState();
}

class _InventoryPageState extends State<_InventoryPage> {
  String _query = '';
  String _section = 'Tổng quan kho';
  String _categoryFilter = 'Tất cả nhóm';
  String _stockFilter = 'Tất cả tình trạng';
  String _sortFilter = 'Tên A–Z';

  void _selectSection(String value) {
    switch (value) {
      case 'Nhập kho':
        widget.onNavigate(2);
        return;
      case 'Xuất kho':
        widget.onNavigate(1);
        return;
      default:
        setState(() => _section = value);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_section == 'Lịch sử kho') {
      return _InventoryHistoryPage(
        api: widget.api,
        store: widget.store,
        onBack: () => setState(() => _section = 'Tổng quan kho'),
      );
    }
    if (_section == 'Kiểm kê') {
      return _StocktakeHistoryPage(
        store: widget.store,
        canWrite: widget.canWrite,
        canViewOwnerData: widget.canViewOwnerData,
        onBack: () => setState(() => _section = 'Tổng quan kho'),
        onSelectSection: _selectSection,
        api: widget.api,
        onRefresh: widget.onRefresh,
      );
    }
    final allProducts = widget.store.products;
    final categories =
        allProducts.map((product) => product.category).toSet().toList()..sort();
    final products = allProducts
        .where((p) =>
            p.name.toLowerCase().contains(_query.toLowerCase()) ||
            p.sku.toLowerCase().contains(_query.toLowerCase()))
        .where((product) =>
            _categoryFilter == 'Tất cả nhóm' ||
            product.category == _categoryFilter)
        .where((product) {
      if (_stockFilter == 'Hết hàng') return product.stock <= 0;
      if (_stockFilter == 'Sắp hết') {
        return product.stock > 0 && product.stock <= product.minimum;
      }
      if (_stockFilter == 'Còn hàng') return product.stock > product.minimum;
      return true;
    }).toList()
      ..sort((a, b) => switch (_sortFilter) {
            'Tồn nhiều nhất' => b.stock.compareTo(a.stock),
            'Tồn ít nhất' => a.stock.compareTo(b.stock),
            'Giá trị tồn cao nhất' =>
              (b.stock * b.cost).compareTo(a.stock * a.cost),
            _ => a.name.toLowerCase().compareTo(b.name.toLowerCase()),
          });
    final search = SizedBox(
      width: 250,
      height: 38,
      child: TextField(
        onChanged: (v) => setState(() => _query = v),
        decoration: const InputDecoration(
          prefixIcon: Icon(Icons.search, size: 17),
          hintText: 'Tìm sản phẩm, mã SP...',
          isDense: true,
          border: OutlineInputBorder(),
        ),
      ),
    );
    final actions = Wrap(spacing: 8, runSpacing: 8, children: [
      if (widget.canManageCatalog)
        FilledButton.icon(
          onPressed: () => _showCreateProduct(context, widget.store,
              api: widget.api,
              onRefresh: widget.onRefresh,
              canViewOwnerData: widget.canViewOwnerData),
          icon: const Icon(Icons.add, size: 16),
          label: const Text('Thêm sản phẩm'),
          style:
              FilledButton.styleFrom(backgroundColor: const Color(0xFF6B4BC3)),
        ),
      if (widget.api != null && widget.canManageCatalog)
        OutlinedButton.icon(
          onPressed: () =>
              _showCreateLocation(context, widget.api!, widget.onRefresh),
          icon: const Icon(Icons.add_business_outlined, size: 16),
          label: const Text('Thêm kho'),
        ),
      if (widget.canWrite)
        OutlinedButton.icon(
          onPressed: () => _showStocktake(context, widget.store,
              api: widget.api, onRefresh: widget.onRefresh),
          icon: const Icon(Icons.fact_check_outlined, size: 16),
          label: const Text('Kiểm kê'),
          style: OutlinedButton.styleFrom(
            foregroundColor: const Color(0xFF6848BC),
            textStyle:
                const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
          ),
        ),
    ]);
    const title = Text('Danh sách tồn kho',
        style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800));
    return _PageFrame(children: [
      const _PageHeading('Quản lý kho hàng',
          'Quản lý danh mục sản phẩm, tồn kho và lịch sử biến động.'),
      _WorkspaceSectionTabs(
        labels: [
          'Tổng quan kho',
          'Nhập kho',
          'Xuất kho',
          if (widget.canWrite) 'Kiểm kê',
          'Lịch sử kho',
        ],
        selected: _section,
        onSelect: _selectSection,
      ),
      const SizedBox(height: 16),
      _MiniSummaryRow(items: [
        if (widget.canViewOwnerData)
          (
            'Tổng giá trị tồn',
            _money(widget.store.inventoryValue.round()),
            Icons.inventory_2_outlined
          ),
        ('Số mặt hàng', '${allProducts.length}', Icons.category_outlined),
        (
          'Sắp hết hàng',
          '${widget.store.products.where((p) => p.stock > 0 && p.stock <= p.minimum).length}',
          Icons.warning_amber_outlined
        ),
        (
          'Hết hàng',
          '${widget.store.products.where((p) => p.stock <= 0).length}',
          Icons.remove_circle_outline_rounded
        )
      ]),
      const SizedBox(height: 20),
      Container(
          decoration: _cardDecoration(),
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (MediaQuery.sizeOf(context).width < 700) ...[
              title,
              const SizedBox(height: 10),
              SizedBox(width: double.infinity, child: search),
              const SizedBox(height: 10),
              actions,
            ] else
              Row(children: [
                const Expanded(child: title),
                search,
                const SizedBox(width: 10),
                actions,
              ]),
            const SizedBox(height: 10),
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _OrderFilterSelect(
                    value: _categoryFilter,
                    items: ['Tất cả nhóm', ...categories],
                    icon: Icons.category_outlined,
                    onChanged: (value) =>
                        setState(() => _categoryFilter = value),
                  ),
                  const SizedBox(width: 8),
                  _OrderFilterSelect(
                    value: _stockFilter,
                    items: const [
                      'Tất cả tình trạng',
                      'Còn hàng',
                      'Sắp hết',
                      'Hết hàng',
                    ],
                    icon: Icons.tune_rounded,
                    onChanged: (value) => setState(() => _stockFilter = value),
                  ),
                  const SizedBox(width: 8),
                  _OrderFilterSelect(
                    value: _sortFilter,
                    items: [
                      'Tên A–Z',
                      'Tồn nhiều nhất',
                      'Tồn ít nhất',
                      if (widget.canViewOwnerData) 'Giá trị tồn cao nhất',
                    ],
                    icon: Icons.swap_vert_rounded,
                    onChanged: (value) => setState(() => _sortFilter = value),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 10),
            if (products.isEmpty)
              const _EmptyCard(
                  'Chưa có sản phẩm. Thêm sản phẩm trước, sau đó tạo phiếu mua để nhập tồn kho.')
            else if (MediaQuery.sizeOf(context).width < 700)
              for (final p in products)
                _ProductTile(
                    product: p, showFinancialDetails: widget.canViewOwnerData)
            else
              _ProductTable(
                  products: products,
                  showFinancialDetails: widget.canViewOwnerData)
          ])),
    ]);
  }
}

class _StocktakeHistoryPage extends StatelessWidget {
  const _StocktakeHistoryPage({
    required this.store,
    required this.canWrite,
    required this.canViewOwnerData,
    required this.onBack,
    required this.onSelectSection,
    this.api,
    this.onRefresh,
  });

  final CommerceMemoryStore store;
  final bool canWrite;
  final bool canViewOwnerData;
  final VoidCallback onBack;
  final ValueChanged<String> onSelectSection;
  final CommerceApi? api;
  final Future<void> Function()? onRefresh;

  @override
  Widget build(BuildContext context) {
    final tickets = store.stocktakeHistory;
    return _PageFrame(children: [
      const _PageHeading('Quản lý kho hàng',
          'Quản lý danh mục sản phẩm, tồn kho và lịch sử biến động.'),
      _WorkspaceSectionTabs(
        labels: const [
          'Tổng quan kho',
          'Nhập kho',
          'Xuất kho',
          'Kiểm kê',
          'Lịch sử kho',
        ],
        selected: 'Kiểm kê',
        onSelect: onSelectSection,
      ),
      const SizedBox(height: 12),
      Container(
        decoration: _cardDecoration(),
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Kiểm kê kho',
                          style: TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w800)),
                      Text(
                          'Xem và theo dõi lịch sử kiểm kê kho hàng, theo dõi chênh lệch.',
                          style: TextStyle(
                              fontSize: 11, color: Color(0xFF7F857D))),
                    ],
                  ),
                ),
                if (canWrite)
                  FilledButton.icon(
                    onPressed: () => _showStocktake(context, store,
                        api: api, onRefresh: onRefresh),
                    icon: const Icon(Icons.add, size: 16),
                    label: const Text('Tạo phiếu kiểm kê'),
                    style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF6B4BC3)),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            if (tickets.isEmpty)
              const _EmptyCard('Chưa có lịch sử phiếu kiểm kê.')
            else
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: SizedBox(
                  width: 1040,
                  child: DataTable(
                    headingRowHeight: 38,
                    dataRowMinHeight: 46,
                    dataRowMaxHeight: 54,
                    horizontalMargin: 8,
                    columnSpacing: 22,
                    headingTextStyle: const TextStyle(
                        fontSize: 10,
                        color: Color(0xFF737971),
                        fontWeight: FontWeight.w700),
                    columns: [
                      DataColumn(label: Text('MÃ PHIẾU')),
                      DataColumn(label: Text('NGÀY KIỂM')),
                      DataColumn(label: Text('NGƯỜI KIỂM')),
                      DataColumn(label: Text('SỐ MẶT HÀNG'), numeric: true),
                      DataColumn(label: Text('TĂNG'), numeric: true),
                      DataColumn(label: Text('GIẢM'), numeric: true),
                      if (canViewOwnerData)
                        DataColumn(
                            label: Text('CHÊNH LỆCH (Đ)'), numeric: true),
                      DataColumn(label: Text('TRẠNG THÁI')),
                      DataColumn(label: Text('THAO TÁC')),
                    ],
                    rows: tickets.map((t) {
                      int diff = 0;
                      for (final e in t.counts.entries) {
                        final book = t.bookCounts[e.key] ?? 0;
                        final p = store.products
                            .where((item) => item.id == e.key)
                            .firstOrNull;
                        if (p != null) {
                          diff += ((e.value - book) * p.cost).round();
                        }
                      }
                      return DataRow(cells: [
                        DataCell(Text(t.id,
                            style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF6546BA)))),
                        DataCell(Text(
                            DateFormat('dd/MM/yyyy').format(t.createdAt),
                            style: const TextStyle(fontSize: 10))),
                        DataCell(Text(t.inspector,
                            style: const TextStyle(fontSize: 11))),
                        DataCell(Text('${t.itemsCount}',
                            style: const TextStyle(fontSize: 11))),
                        DataCell(Text('${t.increaseCount}',
                            style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF16A34A)))),
                        DataCell(Text('${t.decreaseCount}',
                            style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFFDC2626)))),
                        if (canViewOwnerData)
                          DataCell(Text(
                            diff == 0
                                ? '0 đ'
                                : diff > 0
                                    ? '+${_money(diff)}'
                                    : '-${_money(diff.abs())}',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              color: diff == 0
                                  ? const Color(0xFF6B7280)
                                  : diff > 0
                                      ? const Color(0xFF16A34A)
                                      : const Color(0xFFDC2626),
                            ),
                          )),
                        DataCell(Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: const Color(0xFFDCFCE7),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Text(t.status,
                              style: const TextStyle(
                                  fontSize: 9,
                                  color: Color(0xFF16A34A),
                                  fontWeight: FontWeight.w700)),
                        )),
                        DataCell(IconButton(
                          icon: const Icon(Icons.remove_red_eye_outlined,
                              size: 18),
                          tooltip: 'Xem chi tiết',
                          onPressed: () {
                            showDialog<void>(
                              context: context,
                              builder: (ctx) => AlertDialog(
                                title: Text('Chi tiết phiếu kiểm kê ${t.id}'),
                                content: SizedBox(
                                  width: 460,
                                  child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                          'Ngày kiểm: ${DateFormat('dd/MM/yyyy HH:mm').format(t.createdAt)}'),
                                      Text('Người kiểm: ${t.inspector}'),
                                      if (t.note.isNotEmpty)
                                        Text('Ghi chú: ${t.note}'),
                                      const Divider(),
                                      for (final e in t.counts.entries) ...[
                                        Builder(builder: (_) {
                                          final p = store.products
                                              .where((item) => item.id == e.key)
                                              .firstOrNull;
                                          final book = t.bookCounts[e.key] ?? 0;
                                          final variance = e.value - book;
                                          return Padding(
                                            padding: const EdgeInsets.symmetric(
                                                vertical: 4),
                                            child: Row(
                                              children: [
                                                Expanded(
                                                    child:
                                                        Text(p?.name ?? e.key)),
                                                Text(
                                                    'Sổ: $book   Thực tế: ${e.value}'),
                                                const SizedBox(width: 8),
                                                Text(
                                                  variance >= 0
                                                      ? '+$variance'
                                                      : '$variance',
                                                  style: TextStyle(
                                                    fontWeight: FontWeight.bold,
                                                    color: variance >= 0
                                                        ? Colors.green
                                                        : Colors.red,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          );
                                        }),
                                      ],
                                    ],
                                  ),
                                ),
                                actions: [
                                  TextButton(
                                      onPressed: () => Navigator.pop(ctx),
                                      child: const Text('Đóng'))
                                ],
                              ),
                            );
                          },
                        )),
                      ]);
                    }).toList(),
                  ),
                ),
              ),
          ],
        ),
      ),
    ]);
  }
}

class _InventoryHistoryPage extends StatefulWidget {
  const _InventoryHistoryPage({
    required this.api,
    required this.store,
    required this.onBack,
  });

  final CommerceApi? api;
  final CommerceMemoryStore store;
  final VoidCallback onBack;

  @override
  State<_InventoryHistoryPage> createState() => _InventoryHistoryPageState();
}

class _InventoryHistoryPageState extends State<_InventoryHistoryPage> {
  late final Future<List<Map<String, dynamic>>> _movements =
      widget.api?.inventoryMovements() ?? Future.value(const []);
  late final Future<List<Map<String, dynamic>>> _stocktakes =
      widget.api?.stocktakeHistory() ??
          Future.value([
            for (final stocktake in widget.store.stocktakeHistory)
              {
                'id': stocktake.id,
                'status': stocktake.status,
                'completed_at': stocktake.createdAt.toIso8601String(),
                'lines': [
                  for (final entry in stocktake.counts.entries)
                    {
                      'counted_qty': entry.value,
                      'book_qty': stocktake.bookCounts[entry.key] ?? 0,
                      'variance':
                          entry.value - (stocktake.bookCounts[entry.key] ?? 0),
                    }
                ],
              }
          ]);

  @override
  Widget build(BuildContext context) => _PageFrame(children: [
        _PageHeading('Lịch sử kho',
            'Theo dõi biến động tồn và kết quả kiểm kê đã chốt.'),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: widget.onBack,
            icon: const Icon(Icons.arrow_back_rounded, size: 17),
            label: const Text('Danh sách tồn kho'),
          ),
        ),
        const SizedBox(height: 8),
        _historySection(
          title: 'Biến động tồn kho',
          icon: Icons.swap_vert_rounded,
          future: _movements,
          emptyMessage: 'Chưa có biến động kho.',
          rowBuilder: (rows) => _MovementHistoryList(
            rows: rows,
            products: widget.store.products,
          ),
        ),
        const SizedBox(height: 16),
        _historySection(
          title: 'Lịch sử kiểm kê',
          icon: Icons.fact_check_outlined,
          future: _stocktakes,
          emptyMessage: 'Chưa có đợt kiểm kê đã hoàn tất.',
          rowBuilder: (rows) => Column(children: [
            for (final row in rows)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.fact_check_outlined,
                    color: Color(0xFF6848BC)),
                title: Text('${row['note'] ?? row['id'] ?? 'Kiểm kê'}',
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                subtitle: Text(
                    '${_historyDate(row['completed_at'] ?? row['created_at'])} · ${(row['lines'] as List? ?? const []).length} sản phẩm'),
                trailing: Text(_stocktakeStatus('${row['status']}')),
              ),
          ]),
        ),
      ]);

  Widget _historySection({
    required String title,
    required IconData icon,
    required Future<List<Map<String, dynamic>>> future,
    required String emptyMessage,
    required Widget Function(List<Map<String, dynamic>>) rowBuilder,
  }) =>
      Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: _cardDecoration(),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(icon, size: 19, color: const Color(0xFF6848BC)),
            const SizedBox(width: 9),
            Text(title,
                style:
                    const TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
          ]),
          const SizedBox(height: 8),
          FutureBuilder<List<Map<String, dynamic>>>(
            future: future,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const Padding(
                  padding: EdgeInsets.all(20),
                  child: Center(
                    child: SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  ),
                );
              }
              if (snapshot.hasError) {
                return _EmptyCard('Không tải được lịch sử: ${snapshot.error}');
              }
              final rows = snapshot.data ?? const [];
              return rows.isEmpty ? _EmptyCard(emptyMessage) : rowBuilder(rows);
            },
          ),
        ]),
      );
}

class _MovementHistoryList extends StatelessWidget {
  const _MovementHistoryList({required this.rows, required this.products});
  final List<Map<String, dynamic>> rows;
  final List<CommerceProduct> products;

  @override
  Widget build(BuildContext context) => Column(
        children: [
          for (final row in rows)
            Builder(builder: (context) {
              final product = products
                  .where((item) => item.id == '${row['item_id']}')
                  .firstOrNull;
              final quantity =
                  double.tryParse('${row['quantity_signed']}') ?? 0;
              final positive = quantity >= 0;
              return ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(
                  positive
                      ? Icons.south_west_rounded
                      : Icons.north_east_rounded,
                  color: positive
                      ? const Color(0xFF168256)
                      : const Color(0xFFB34B43),
                ),
                title: Text(product?.name ?? 'Sản phẩm đã ngừng hoạt động',
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                subtitle: Text(
                    '${product?.sku ?? row['item_id']} · ${_historyDate(row['posted_at'])}'),
                trailing: Text(
                  '${positive ? '+' : ''}${NumberFormat.decimalPattern('vi_VN').format(quantity)} ${product?.unit ?? ''}',
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    color: positive
                        ? const Color(0xFF168256)
                        : const Color(0xFFB34B43),
                  ),
                ),
              );
            }),
        ],
      );
}

String _historyDate(dynamic value) {
  final date = DateTime.tryParse('$value')?.toLocal();
  return date == null ? '—' : DateFormat('dd/MM/yyyy HH:mm').format(date);
}

String _stocktakeStatus(String status) => switch (status) {
      'closed' || 'posted' => 'Đã chốt',
      'rejected' => 'Từ chối',
      _ => status,
    };

class _ProductTable extends StatelessWidget {
  const _ProductTable({
    required this.products,
    required this.showFinancialDetails,
  });
  final List<CommerceProduct> products;
  final bool showFinancialDetails;

  IconData _categoryIcon(String category) => switch (category) {
        'Nguyên liệu' => Icons.coffee_rounded,
        'Thực phẩm' => Icons.cake_rounded,
        'Thiết bị' => Icons.precision_manufacturing_outlined,
        'Bao bì' => Icons.inventory_2_outlined,
        _ => Icons.category_outlined,
      };

  Color _categoryColor(String category) => switch (category) {
        'Nguyên liệu' => const Color(0xFF8B5CF6),
        'Thực phẩm' => const Color(0xFFEC4899),
        'Thiết bị' => const Color(0xFF3B82F6),
        'Bao bì' => const Color(0xFFF59E0B),
        _ => const Color(0xFF10B981),
      };

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
          headingRowHeight: 38,
          dataRowMinHeight: 52,
          dataRowMaxHeight: 60,
          horizontalMargin: 8,
          columnSpacing: 22,
          headingTextStyle: const TextStyle(
              fontSize: 10,
              color: Color(0xFF737971),
              fontWeight: FontWeight.w700),
          columns: [
            DataColumn(label: Text('ẢNH')),
            DataColumn(label: Text('MÃ SP')),
            DataColumn(label: Text('TÊN SẢN PHẨM')),
            DataColumn(label: Text('NHÓM')),
            DataColumn(label: Text('TỒN HIỆN TẠI')),
            DataColumn(label: Text('TỒN TỐI THIỂU')),
            if (showFinancialDetails) ...[
              DataColumn(label: Text('GIÁ TRỊ TỒN')),
              DataColumn(label: Text('GIÁ VỐN')),
            ],
            DataColumn(label: Text('TRẠNG THÁI')),
          ],
          rows: products
              .map((p) => DataRow(cells: [
                    DataCell(Container(
                      width: 34,
                      height: 34,
                      decoration: BoxDecoration(
                        color:
                            _categoryColor(p.category).withValues(alpha: .14),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(_categoryIcon(p.category),
                          size: 18, color: _categoryColor(p.category)),
                    )),
                    DataCell(Text(p.sku,
                        style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF6546BA)))),
                    DataCell(Text(p.name,
                        style: const TextStyle(
                            fontSize: 11, fontWeight: FontWeight.w600))),
                    DataCell(
                        Text(p.category, style: const TextStyle(fontSize: 10))),
                    DataCell(Text(
                        '${NumberFormat.decimalPattern('vi_VN').format(p.stock)} ${p.unit}',
                        style: const TextStyle(
                            fontSize: 11, fontWeight: FontWeight.w700))),
                    DataCell(Text(
                        '${NumberFormat.decimalPattern('vi_VN').format(p.minimum)} ${p.unit}',
                        style: const TextStyle(
                            fontSize: 10, color: Color(0xFF6B7280)))),
                    if (showFinancialDetails)
                      DataCell(Text(_money((p.stock * p.cost).round()),
                          style: const TextStyle(
                              fontSize: 11, fontWeight: FontWeight.w700))),
                    if (showFinancialDetails)
                      DataCell(Text(_money(p.cost),
                          style: const TextStyle(fontSize: 10))),
                    DataCell(_StockBadge(product: p)),
                  ]))
              .toList()));
}

class _ProductTile extends StatelessWidget {
  const _ProductTile({
    required this.product,
    required this.showFinancialDetails,
  });
  final CommerceProduct product;
  final bool showFinancialDetails;
  @override
  Widget build(BuildContext context) => Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
          color: const Color(0xFFFAFBF9),
          borderRadius: BorderRadius.circular(10)),
      child: Row(children: [
        Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(product.name,
              style:
                  const TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
          Text('${product.sku} · ${product.category}',
              style: const TextStyle(fontSize: 10, color: Color(0xFF81877F)))
        ])),
        Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Text('${product.stock} ${product.unit}',
              style:
                  const TextStyle(fontSize: 12, fontWeight: FontWeight.w800)),
          if (showFinancialDetails)
            Text(_money((product.stock * product.cost).round()),
                style: const TextStyle(fontSize: 9, color: Color(0xFF81877F))),
        ]),
        const SizedBox(width: 8),
        _StockBadge(product: product)
      ]));
}

class _StockBadge extends StatelessWidget {
  const _StockBadge({required this.product});
  final CommerceProduct product;
  @override
  Widget build(BuildContext context) {
    final (label, fg, bg) = product.stock <= 0
        ? ('Hết hàng', const Color(0xFFDC2626), const Color(0xFFFEE2E2))
        : product.stock <= product.minimum
            ? ('Sắp hết', const Color(0xFFD97706), const Color(0xFFFEF3C7))
            : product.stock > product.minimum * 4
                ? ('Vượt tồn', const Color(0xFF0284C7), const Color(0xFFE0F2FE))
                : (
                    'Còn hàng',
                    const Color(0xFF16A34A),
                    const Color(0xFFDCFCE7)
                  );
    return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration:
            BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
        child: Text(label,
            style: TextStyle(
                fontSize: 9, color: fg, fontWeight: FontWeight.w700)));
  }
}

class _DebtPage extends StatelessWidget {
  const _DebtPage({
    required this.store,
    required this.canWrite,
    this.api,
    this.onRefresh,
  });
  final CommerceMemoryStore store;
  final bool canWrite;
  final CommerceApi? api;
  final Future<void> Function()? onRefresh;
  @override
  Widget build(BuildContext context) => DefaultTabController(
      length: 2,
      child: _PageFrame(children: [
        const _PageHeading('Công nợ phải thu & phải trả',
            'Theo dõi số tiền còn lại theo khách hàng và nhà cung cấp.'),
        _MiniSummaryRow(items: [
          (
            'Khách hàng còn nợ',
            _money(store.receivableTotal),
            Icons.call_received_rounded
          ),
          (
            'Nhà cung cấp cần trả',
            _money(store.payableTotal),
            Icons.call_made_rounded
          ),
          (
            'Đơn cần thu',
            '${store.receivables.length}',
            Icons.receipt_long_outlined
          ),
          (
            'Phiếu cần trả',
            '${store.payables.length}',
            Icons.request_quote_outlined
          )
        ]),
        const SizedBox(height: 18),
        Container(
            decoration: _cardDecoration(),
            child: Column(children: [
              const TabBar(
                  isScrollable: true,
                  tabAlignment: TabAlignment.start,
                  labelColor: Color(0xFF6848BC),
                  unselectedLabelColor: Color(0xFF7F857D),
                  indicatorColor: Color(0xFF6848BC),
                  tabs: [
                    Tab(text: 'Phải thu khách hàng'),
                    Tab(text: 'Phải trả nhà cung cấp')
                  ]),
              SizedBox(
                  height: 480,
                  child: TabBarView(children: [
                    _DebtList(
                        orders: store.receivables,
                        store: store,
                        canWrite: canWrite,
                        api: api,
                        onRefresh: onRefresh),
                    _DebtList(
                        orders: store.payables,
                        store: store,
                        canWrite: canWrite,
                        api: api,
                        onRefresh: onRefresh)
                  ]))
            ])),
      ]));
}

class _DebtList extends StatefulWidget {
  const _DebtList(
      {required this.orders,
      required this.store,
      required this.canWrite,
      this.api,
      this.onRefresh});
  final List<CommerceOrder> orders;
  final CommerceMemoryStore store;
  final bool canWrite;
  final CommerceApi? api;
  final Future<void> Function()? onRefresh;

  @override
  State<_DebtList> createState() => _DebtListState();
}

class _DebtListState extends State<_DebtList> {
  String _query = '';
  String _dueFilter = 'Tất cả hạn thanh toán';

  @override
  Widget build(BuildContext context) {
    final today = DateUtils.dateOnly(DateTime.now());
    final orders = widget.orders
        .where((order) =>
            order.code.toLowerCase().contains(_query.toLowerCase()) ||
            order.partyName.toLowerCase().contains(_query.toLowerCase()))
        .where((order) {
      final due =
          order.dueDate == null ? null : DateUtils.dateOnly(order.dueDate!);
      return switch (_dueFilter) {
        'Quá hạn' => due != null && due.isBefore(today),
        'Còn hạn' => due == null || !due.isBefore(today),
        _ => true,
      };
    }).toList()
      ..sort((a, b) {
        final aDue = a.dueDate ?? DateTime(9999);
        final bDue = b.dueDate ?? DateTime(9999);
        return aDue.compareTo(bDue);
      });
    final compact = MediaQuery.sizeOf(context).width < 720;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
          child: Row(
            children: [
              Expanded(
                child: SizedBox(
                  height: 38,
                  child: TextField(
                    onChanged: (value) => setState(() => _query = value),
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search, size: 17),
                      hintText: 'Tìm mã phiếu, khách hàng...',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              _OrderFilterSelect(
                value: _dueFilter,
                items: const [
                  'Tất cả hạn thanh toán',
                  'Quá hạn',
                  'Còn hạn',
                ],
                icon: Icons.schedule_rounded,
                onChanged: (value) => setState(() => _dueFilter = value),
              ),
            ],
          ),
        ),
        Expanded(
          child: orders.isEmpty
              ? const Center(
                  child: Padding(
                    padding: EdgeInsets.all(24),
                    child: Text('Không có khoản công nợ phù hợp.',
                        style:
                            TextStyle(fontSize: 12, color: Color(0xFF81877F))),
                  ),
                )
              : compact
                  ? ListView(
                      padding: const EdgeInsets.all(14),
                      children: [
                        for (final order in orders) _debtTile(order),
                      ],
                    )
                  : SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: SizedBox(
                        width: 1100,
                        child: DataTable(
                          headingRowHeight: 38,
                          dataRowMinHeight: 52,
                          dataRowMaxHeight: 62,
                          horizontalMargin: 8,
                          columnSpacing: 16,
                          headingTextStyle: const TextStyle(
                              fontSize: 10,
                              color: Color(0xFF737971),
                              fontWeight: FontWeight.w700),
                          columns: const [
                            DataColumn(label: Text('MÃ PHIẾU')),
                            DataColumn(label: Text('KHÁCH HÀNG / NCC')),
                            DataColumn(label: Text('NGÀY')),
                            DataColumn(label: Text('CÒN LẠI'), numeric: true),
                            DataColumn(label: Text('HẠN THANH TOÁN')),
                            DataColumn(label: Text('TRẠNG THÁI')),
                            DataColumn(label: Text('THAO TÁC')),
                          ],
                          rows: [
                            for (final order in orders)
                              DataRow(cells: [
                                DataCell(Text(order.code,
                                    style: const TextStyle(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w700,
                                        color: Color(0xFF6546BA)))),
                                DataCell(Text(order.partyName,
                                    style: const TextStyle(fontSize: 11))),
                                DataCell(Text(
                                    DateFormat('dd/MM/yyyy')
                                        .format(order.createdAt),
                                    style: const TextStyle(fontSize: 10))),
                                DataCell(Text(_money(order.outstanding),
                                    style: const TextStyle(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w800))),
                                DataCell(Text(
                                    order.dueDate == null
                                        ? 'Chưa hẹn'
                                        : DateFormat('dd/MM/yyyy')
                                            .format(order.dueDate!),
                                    style: const TextStyle(fontSize: 10))),
                                DataCell(_PaymentBadge(
                                    label: order.dueDate != null &&
                                            DateUtils.dateOnly(order.dueDate!)
                                                .isBefore(today)
                                        ? 'Quá hạn'
                                        : order.dueDate == null
                                            ? 'Chưa hẹn'
                                            : 'Còn hạn')),
                                DataCell(widget.canWrite
                                    ? TextButton(
                                        onPressed: () => _showPayment(
                                            context, widget.store, order,
                                            api: widget.api,
                                            onRefresh: widget.onRefresh),
                                        child: const Text('Ghi nhận'))
                                    : const Text('—')),
                              ]),
                          ],
                        ),
                      ),
                    ),
        ),
      ],
    );
  }

  Widget _debtTile(CommerceOrder order) => Container(
        margin: const EdgeInsets.only(bottom: 9),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
            color: const Color(0xFFFAFBF9),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: const Color(0xFFECEEEA))),
        child: Row(children: [
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text(order.partyName,
                    style: const TextStyle(
                        fontSize: 12, fontWeight: FontWeight.w700)),
                const SizedBox(height: 4),
                Text(
                    '${order.code} · ${DateFormat('dd/MM/yyyy').format(order.createdAt)}',
                    style: const TextStyle(
                        fontSize: 10, color: Color(0xFF81877F))),
                if (order.dueDate != null)
                  Text(
                    '${order.dueDate!.isBefore(DateTime.now()) ? 'Quá hạn · ' : 'Hạn · '}${DateFormat('dd/MM/yyyy').format(order.dueDate!)}',
                    style: TextStyle(
                      fontSize: 10,
                      color: order.dueDate!.isBefore(DateTime.now())
                          ? const Color(0xFFB34B43)
                          : const Color(0xFF81877F),
                      fontWeight: order.dueDate!.isBefore(DateTime.now())
                          ? FontWeight.w700
                          : FontWeight.w400,
                    ),
                  ),
              ])),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text('Còn ${_money(order.outstanding)}',
                style: const TextStyle(
                    fontSize: 12,
                    color: Color(0xFFB34B43),
                    fontWeight: FontWeight.w800)),
            Text('Tổng ${_money(order.total)}',
                style: const TextStyle(fontSize: 10, color: Color(0xFF81877F)))
          ]),
          if (widget.canWrite) ...[
            const SizedBox(width: 10),
            OutlinedButton(
                onPressed: () => _showPayment(context, widget.store, order,
                    api: widget.api, onRefresh: widget.onRefresh),
                child: const Text('Ghi nhận', style: TextStyle(fontSize: 10)))
          ]
        ]),
      );
}

class _ApprovalPage extends StatefulWidget {
  const _ApprovalPage(
      {required this.store,
      required this.api,
      required this.onRefresh,
      required this.canViewOwnerData});
  final CommerceMemoryStore store;
  final CommerceApi? api;
  final Future<void> Function()? onRefresh;
  final bool canViewOwnerData;

  @override
  State<_ApprovalPage> createState() => _ApprovalPageState();
}

class _ApprovalPageState extends State<_ApprovalPage> {
  late Future<List<Map<String, dynamic>>> _pending = _load();

  Future<List<Map<String, dynamic>>> _load() =>
      widget.api?.pendingApprovals() ?? Future.value(const []);

  Future<void> _approve(Map<String, dynamic> request) async {
    try {
      await widget.api!.approveInventoryRequest(request);
      await widget.onRefresh?.call();
      if (!mounted) return;
      setState(() => _pending = _load());
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('Đã duyệt phiếu ${request['invoice_no'] ?? ''}.')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('$error'), backgroundColor: const Color(0xFFB34B43)),
      );
    }
  }

  Future<void> _reject(Map<String, dynamic> request) async {
    final reason = TextEditingController();
    final value = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Từ chối phiếu'),
        content: TextField(
          controller: reason,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: 'Lý do',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Hủy')),
          FilledButton(
              onPressed: () => Navigator.pop(dialogContext, reason.text.trim()),
              child: const Text('Từ chối')),
        ],
      ),
    );
    reason.dispose();
    if (value == null) return;
    if (value.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Vui lòng nhập lý do từ chối.')));
      return;
    }
    try {
      await widget.api!.rejectInventoryRequest(request, value);
      await widget.onRefresh?.call();
      if (!mounted) return;
      setState(() => _pending = _load());
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('$error'), backgroundColor: const Color(0xFFB34B43)),
      );
    }
  }

  void _runDemoApproval(VoidCallback action) {
    try {
      action();
    } catch (error) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('$error')));
    }
  }

  Widget _approvalCard({
    required Widget title,
    required String detail,
    required VoidCallback onApprove,
    required VoidCallback onReject,
  }) =>
      LayoutBuilder(builder: (context, constraints) {
        final compact = constraints.maxWidth < 600;
        final description = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            title,
            const SizedBox(height: 4),
            Text(detail,
                style: const TextStyle(fontSize: 11, color: Color(0xFF81877F))),
          ],
        );
        final actions = Wrap(spacing: 8, children: [
          OutlinedButton(onPressed: onReject, child: const Text('Từ chối')),
          FilledButton(onPressed: onApprove, child: const Text('Duyệt')),
        ]);
        return Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(15),
          decoration: _cardDecoration(),
          child: compact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    description,
                    const SizedBox(height: 12),
                    Align(alignment: Alignment.centerRight, child: actions),
                  ],
                )
              : Row(children: [
                  const Icon(Icons.receipt_long_outlined,
                      color: Color(0xFF6848BC)),
                  const SizedBox(width: 12),
                  Expanded(child: description),
                  actions,
                ]),
        );
      });

  @override
  Widget build(BuildContext context) => _PageFrame(children: [
        _PageHeading('Phiếu chờ duyệt',
            'Duyệt đơn bán, phiếu nhập và kiểm kê theo phân quyền maker–checker.'),
        if (widget.api == null &&
            widget.store.pendingOrders.isEmpty &&
            widget.store.pendingStocktakes.isEmpty)
          const _EmptyCard('Không có phiếu chờ duyệt.'),
        if (widget.api == null)
          Column(children: [
            for (final order in widget.store.pendingOrders)
              _approvalCard(
                title: Text('${order.code} · ${order.partyName}',
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                detail: widget.canViewOwnerData
                    ? '${order.kind == 'sale' ? 'Đơn bán' : 'Phiếu nhập'} · ${_money(order.total)}'
                    : order.kind == 'sale'
                        ? 'Đơn bán · Phiếu chờ duyệt'
                        : 'Phiếu nhập · Phiếu chờ duyệt',
                onReject: () => _runDemoApproval(() {
                  widget.store.rejectOrder(order.id);
                  setState(() {});
                }),
                onApprove: () => _runDemoApproval(() {
                  widget.store.approveOrder(order.id);
                  setState(() {});
                }),
              ),
            for (final stocktake in widget.store.pendingStocktakes)
              _approvalCard(
                title: Text(
                    'Kiểm kê ${stocktake.id} · ${stocktake.counts.length} sản phẩm',
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                detail: 'Phiếu kiểm kê kho',
                onReject: () => _runDemoApproval(() {
                  widget.store.rejectStocktake(stocktake.id);
                  setState(() {});
                }),
                onApprove: () => _runDemoApproval(() {
                  widget.store.approveStocktake(stocktake.id);
                  setState(() {});
                }),
              ),
          ]),
        if (widget.api != null)
          FutureBuilder<List<Map<String, dynamic>>>(
            future: _pending,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const Center(child: CircularProgressIndicator());
              }
              if (snapshot.hasError)
                return _EmptyCard('Không tải được: ${snapshot.error}');
              final requests = snapshot.data ?? const [];
              if (requests.isEmpty)
                return const _EmptyCard('Không có phiếu chờ duyệt.');
              return Column(children: [
                for (final request in requests)
                  _approvalCard(
                    title: Text(
                        '${request['invoice_no'] ?? request['reason'] ?? 'Phiếu kho'}',
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    detail:
                        '${request['_type'] == 'stocktake' ? 'Kiểm kê' : request['kind'] ?? 'Phiếu kho'} · ${(request['lines'] as List? ?? const []).length} dòng hàng',
                    onApprove: () => _approve(request),
                    onReject: () => _reject(request),
                  ),
              ]);
            },
          ),
      ]);
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard(this.message);
  final String message;
  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(24),
        decoration: _cardDecoration(),
        child: Text(message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Color(0xFF81877F), fontSize: 12)),
      );
}

class _DraftLine {
  _DraftLine(this.productId, this.quantity);
  String productId;
  double quantity;
  String lotNo = '';
  String expiryDate = '';
}

Future<void> _showCreateProduct(BuildContext context, CommerceMemoryStore store,
    {CommerceApi? api,
    Future<void> Function()? onRefresh,
    required bool canViewOwnerData}) async {
  final requestKey = CommerceApi.newIdempotencyKey();
  final sku = TextEditingController();
  final name = TextEditingController();
  final category = TextEditingController();
  final unit = TextEditingController(text: 'cái');
  final cost = TextEditingController(text: '0');
  final price = TextEditingController(text: '0');
  final minimum = TextEditingController(text: '0');
  await showDialog<void>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('Thêm sản phẩm'),
      content: SizedBox(
        width: 440,
        child: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            _FormInput('Mã sản phẩm', sku),
            _FormInput('Tên sản phẩm', name),
            _FormInput('Nhóm hàng', category),
            _FormInput('Đơn vị', unit),
            if (canViewOwnerData)
              Row(children: [
                Expanded(child: _FormInput('Giá vốn', cost, numeric: true)),
                const SizedBox(width: 8),
                Expanded(child: _FormInput('Giá bán', price, numeric: true)),
              ]),
            _FormInput('Tồn tối thiểu', minimum, numeric: true),
          ]),
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Hủy')),
        FilledButton(
          onPressed: () async {
            try {
              if (sku.text.trim().isEmpty || name.text.trim().isEmpty) {
                throw StateError('Mã và tên sản phẩm là bắt buộc.');
              }
              final costValue = double.parse(cost.text);
              final priceValue = double.parse(price.text);
              final minimumValue = double.parse(minimum.text);
              if (api == null) {
                store.addProduct(
                  sku: sku.text,
                  name: name.text,
                  category: category.text,
                  unit: unit.text,
                  cost: costValue.round(),
                  price: priceValue.round(),
                  minimum: minimumValue,
                );
              } else {
                await api.createProduct(
                  sku: sku.text,
                  name: name.text,
                  category: category.text,
                  unit: unit.text,
                  cost: costValue,
                  price: priceValue,
                  minimum: minimumValue,
                  idempotencyKey: requestKey,
                );
              }
              if (!context.mounted) return;
              Navigator.pop(dialogContext);
              await onRefresh?.call();
            } catch (error) {
              if (!context.mounted) return;
              ScaffoldMessenger.of(context)
                  .showSnackBar(SnackBar(content: Text('$error')));
            }
          },
          child: const Text('Lưu sản phẩm'),
        ),
      ],
    ),
  );
  for (final controller in [sku, name, category, unit, cost, price, minimum]) {
    controller.dispose();
  }
}

Future<void> _showCreateLocation(BuildContext context, CommerceApi api,
    Future<void> Function()? onRefresh) async {
  final requestKey = CommerceApi.newIdempotencyKey();
  final code = TextEditingController();
  final name = TextEditingController();
  await showDialog<void>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('Thêm kho hàng'),
      content: SizedBox(
        width: 360,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          _FormInput('Mã kho', code),
          _FormInput('Tên kho', name),
        ]),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Hủy')),
        FilledButton(
          onPressed: () async {
            try {
              await api.createLocation(
                  code: code.text, name: name.text, idempotencyKey: requestKey);
              if (!context.mounted) return;
              Navigator.pop(dialogContext);
              await onRefresh?.call();
            } catch (error) {
              if (!context.mounted) return;
              ScaffoldMessenger.of(context)
                  .showSnackBar(SnackBar(content: Text('$error')));
            }
          },
          child: const Text('Lưu kho'),
        ),
      ],
    ),
  );
  code.dispose();
  name.dispose();
}

class _FormInput extends StatelessWidget {
  const _FormInput(this.label, this.controller, {this.numeric = false});
  final String label;
  final TextEditingController controller;
  final bool numeric;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 9),
        child: TextField(
          controller: controller,
          keyboardType: numeric
              ? const TextInputType.numberWithOptions(decimal: true)
              : TextInputType.text,
          decoration: InputDecoration(
            labelText: label,
            isDense: true,
            border: const OutlineInputBorder(),
          ),
        ),
      );
}

Future<(String, String)?> _showPartyDialog(
    BuildContext context, String label) async {
  final name = TextEditingController();
  final phone = TextEditingController();
  final result = await showDialog<(String, String)>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: Text('Thêm $label'),
      content: SizedBox(
        width: 360,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
            controller: name,
            autofocus: true,
            decoration: const InputDecoration(
              labelText: 'Tên',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: phone,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(
              labelText: 'Số điện thoại (không bắt buộc)',
              border: OutlineInputBorder(),
            ),
          ),
        ]),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Hủy')),
        FilledButton(
          onPressed: () {
            if (name.text.trim().isEmpty) return;
            Navigator.pop(dialogContext, (name.text.trim(), phone.text.trim()));
          },
          child: const Text('Lưu'),
        ),
      ],
    ),
  );
  name.dispose();
  phone.dispose();
  return result;
}

Future<void> _showCreateOrder(
    BuildContext context, CommerceMemoryStore store, String kind,
    {CommerceApi? api,
    Future<void> Function()? onRefresh,
    required bool canViewOwnerData}) async {
  final requestKey = CommerceApi.newIdempotencyKey();
  final sale = kind == 'sale';
  final quote = kind == 'quote';
  final customerDocument = sale || quote;
  final parties = [...(customerDocument ? store.customers : store.suppliers)];
  final lines = <_DraftLine>[];
  String? selectedParty = parties.isEmpty ? null : parties.first.name;
  final discount = TextEditingController(text: '0');
  final vat = TextEditingController(text: '0');
  final shipping = TextEditingController(text: '0');
  final dueDate = TextEditingController();
  final note = TextEditingController();
  await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(builder: (context, setState) {
            final width = MediaQuery.sizeOf(context).width;
            final subtotal = lines.fold<int>(
                0,
                (sum, line) =>
                    sum +
                    (line.quantity *
                            (customerDocument
                                ? store.product(line.productId).price
                                : store.product(line.productId).cost))
                        .round());
            final discountAmount = int.tryParse(discount.text) ?? 0;
            final vatPercent = double.tryParse(vat.text) ?? 0;
            final shippingAmount = int.tryParse(shipping.text) ?? 0;
            final taxable = (subtotal - discountAmount).clamp(0, subtotal);
            final vatAmount = (taxable * vatPercent / 100).round();
            final total = taxable + vatAmount + shippingAmount;
            return AlertDialog(
              title: Row(children: [
                Icon(
                    quote
                        ? Icons.request_quote_outlined
                        : sale
                            ? Icons.point_of_sale_outlined
                            : Icons.shopping_bag_outlined,
                    color: const Color(0xFF6B4BC3)),
                const SizedBox(width: 10),
                Expanded(
                    child: Text(
                        quote
                            ? 'Tạo báo giá'
                            : sale
                                ? 'Tạo đơn bán hàng'
                                : 'Tạo phiếu mua hàng',
                        style: const TextStyle(fontWeight: FontWeight.w800))),
                IconButton(
                    onPressed: () => Navigator.pop(dialogContext),
                    icon: const Icon(Icons.close))
              ]),
              content: SizedBox(
                  width: width < 700 ? width - 42 : 650,
                  child: SingleChildScrollView(
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                        Row(children: [
                          Expanded(
                            child: DropdownButtonFormField<String>(
                              initialValue: selectedParty,
                              decoration: InputDecoration(
                                  labelText: customerDocument
                                      ? 'Khách hàng'
                                      : 'Nhà cung cấp',
                                  border: const OutlineInputBorder(),
                                  isDense: true),
                              items: parties
                                  .map((party) => DropdownMenuItem(
                                      value: party.name,
                                      child: Text(party.name,
                                          overflow: TextOverflow.ellipsis)))
                                  .toList(),
                              onChanged: (v) =>
                                  setState(() => selectedParty = v),
                            ),
                          ),
                          IconButton(
                            tooltip: customerDocument
                                ? 'Thêm khách hàng'
                                : 'Thêm nhà cung cấp',
                            onPressed: () async {
                              final details = await _showPartyDialog(
                                  context,
                                  customerDocument
                                      ? 'khách hàng'
                                      : 'nhà cung cấp');
                              if (details == null) return;
                              try {
                                final partyRequestKey =
                                    CommerceApi.newIdempotencyKey();
                                final party = api == null
                                    ? store.addParty(
                                        name: details.$1,
                                        phone: details.$2,
                                        kind: customerDocument
                                            ? 'customer'
                                            : 'supplier',
                                      )
                                    : await api.createParty(
                                        name: details.$1,
                                        phone: details.$2,
                                        kind: customerDocument
                                            ? 'customer'
                                            : 'supplier',
                                        idempotencyKey: partyRequestKey,
                                      );
                                if (api != null) await onRefresh?.call();
                                parties.add(party);
                                setState(() => selectedParty = party.name);
                              } catch (error) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(content: Text('$error')));
                              }
                            },
                            icon: const Icon(Icons.person_add_alt_1_outlined),
                          ),
                        ]),
                        const SizedBox(height: 12),
                        Row(children: [
                          const Expanded(
                              child: Text('Sản phẩm',
                                  style: TextStyle(
                                      fontWeight: FontWeight.w700,
                                      fontSize: 12))),
                          TextButton.icon(
                              onPressed: store.products.isEmpty
                                  ? null
                                  : () => setState(() => lines.add(
                                      _DraftLine(store.products.first.id, 1))),
                              icon: const Icon(Icons.add, size: 16),
                              label: const Text('Thêm sản phẩm'))
                        ]),
                        if (store.products.isEmpty)
                          const _EmptyCard('Chưa có sản phẩm trong kho.')
                        else if (lines.isEmpty)
                          Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(18),
                              decoration: BoxDecoration(
                                  color: const Color(0xFFF7F7F5),
                                  borderRadius: BorderRadius.circular(10)),
                              child: const Text(
                                  'Thêm sản phẩm vào phiếu để tính tổng tiền.',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                      fontSize: 11, color: Color(0xFF81877F)))),
                        for (var i = 0; i < lines.length; i++)
                          Column(children: [
                            Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: Row(children: [
                                  Expanded(
                                      flex: 5,
                                      child: DropdownButtonFormField<String>(
                                          initialValue: lines[i].productId,
                                          decoration: const InputDecoration(
                                              labelText: 'Sản phẩm',
                                              border: OutlineInputBorder(),
                                              isDense: true),
                                          items: store.products
                                              .map((p) => DropdownMenuItem(
                                                  value: p.id,
                                                  child: Text(
                                                      '${p.sku} · ${p.name}',
                                                      overflow: TextOverflow
                                                          .ellipsis)))
                                              .toList(),
                                          onChanged: (v) => setState(() =>
                                              lines[i].productId =
                                                  v ?? lines[i].productId))),
                                  const SizedBox(width: 8),
                                  SizedBox(
                                      width: 92,
                                      child: TextFormField(
                                          initialValue: '${lines[i].quantity}',
                                          keyboardType: const TextInputType
                                              .numberWithOptions(decimal: true),
                                          decoration: const InputDecoration(
                                              labelText: 'Số lượng',
                                              border: OutlineInputBorder(),
                                              isDense: true),
                                          onChanged: (v) => setState(() =>
                                              lines[i].quantity =
                                                  double.tryParse(v) ?? 0))),
                                  IconButton(
                                      tooltip: 'Xóa sản phẩm',
                                      onPressed: () =>
                                          setState(() => lines.removeAt(i)),
                                      icon: const Icon(Icons.delete_outline,
                                          color: Color(0xFFB34B43), size: 19))
                                ])),
                            if (kind == 'purchase')
                              Padding(
                                padding:
                                    const EdgeInsets.only(bottom: 9, left: 4),
                                child: Row(children: [
                                  Expanded(
                                    child: TextFormField(
                                      initialValue: lines[i].lotNo,
                                      decoration: const InputDecoration(
                                        labelText: 'Số lô',
                                        border: OutlineInputBorder(),
                                        isDense: true,
                                      ),
                                      onChanged: (value) =>
                                          lines[i].lotNo = value,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: TextFormField(
                                      initialValue: lines[i].expiryDate,
                                      keyboardType: TextInputType.datetime,
                                      decoration: const InputDecoration(
                                        labelText: 'Hạn dùng (YYYY-MM-DD)',
                                        border: OutlineInputBorder(),
                                        isDense: true,
                                      ),
                                      onChanged: (value) =>
                                          lines[i].expiryDate = value,
                                    ),
                                  ),
                                ]),
                              ),
                          ]),
                        const SizedBox(height: 10),
                        Wrap(spacing: 10, runSpacing: 10, children: [
                          if (canViewOwnerData)
                            _MoneyInput(
                                label: 'Chiết khấu (₫)',
                                controller: discount,
                                onChanged: () => setState(() {})),
                          if (canViewOwnerData)
                            _MoneyInput(
                                label: 'VAT (%)',
                                controller: vat,
                                onChanged: () => setState(() {})),
                          if (canViewOwnerData)
                            _MoneyInput(
                                label: 'Vận chuyển (₫)',
                                controller: shipping,
                                onChanged: () => setState(() {})),
                          SizedBox(
                            width: 180,
                            child: TextField(
                              controller: dueDate,
                              keyboardType: TextInputType.datetime,
                              decoration: InputDecoration(
                                labelText: quote
                                    ? 'Hiệu lực đến (YYYY-MM-DD)'
                                    : 'Hạn thanh toán (YYYY-MM-DD)',
                                border: const OutlineInputBorder(),
                                isDense: true,
                              ),
                            ),
                          ),
                        ]),
                        const SizedBox(height: 10),
                        TextField(
                            controller: note,
                            decoration: const InputDecoration(
                                labelText: 'Ghi chú',
                                border: OutlineInputBorder(),
                                isDense: true)),
                        const SizedBox(height: 12),
                        if (canViewOwnerData)
                          Container(
                              padding: const EdgeInsets.all(13),
                              decoration: BoxDecoration(
                                  color: const Color(0xFFF7F5FC),
                                  borderRadius: BorderRadius.circular(10)),
                              child: Column(children: [
                                _TotalRow(
                                    label: 'Tạm tính', value: _money(subtotal)),
                                _TotalRow(
                                    label: 'Chiết khấu',
                                    value: '− ${_money(discountAmount)}'),
                                _TotalRow(
                                    label: 'VAT', value: _money(vatAmount)),
                                _TotalRow(
                                    label: 'Vận chuyển',
                                    value: _money(shippingAmount)),
                                const Divider(),
                                _TotalRow(
                                    label: quote
                                        ? 'Tổng báo giá'
                                        : sale
                                            ? 'Tổng đơn bán'
                                            : 'Tổng phiếu nhập',
                                    value: _money(total),
                                    bold: true)
                              ])),
                      ]))),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(dialogContext),
                    child: const Text('Hủy')),
                FilledButton.icon(
                    onPressed: () async {
                      try {
                        final dueRaw = dueDate.text.trim();
                        final parsedDueDate = DateTime.tryParse(dueRaw);
                        if (dueRaw.isNotEmpty && parsedDueDate == null) {
                          throw StateError(
                              'Ngày hạn cần theo định dạng YYYY-MM-DD.');
                        }
                        final orderLines = lines.map((line) {
                          final product = store.product(line.productId);
                          return CommerceLine(
                              productId: product.id,
                              name: product.name,
                              unit: product.unit,
                              quantity: line.quantity,
                              unitPrice: customerDocument
                                  ? product.price
                                  : product.cost,
                              unitCost: product.cost,
                              lotNo: line.lotNo.trim(),
                              expiryDate:
                                  DateTime.tryParse(line.expiryDate.trim()));
                        }).toList();
                        if (kind == 'purchase') {
                          for (final line in lines) {
                            final expiry = line.expiryDate.trim();
                            if (line.lotNo.trim().isEmpty ||
                                DateTime.tryParse(expiry) == null) {
                              throw StateError(
                                  'Phiếu mua cần số lô và hạn dùng (YYYY-MM-DD) cho từng sản phẩm.');
                            }
                          }
                        }
                        if (api != null) {
                          final party = parties.firstWhere(
                              (candidate) => candidate.name == selectedParty);
                          await api.createDocument(
                            kind: kind,
                            party: party,
                            lines: orderLines,
                            discount: int.tryParse(discount.text) ?? 0,
                            vatPercent: double.tryParse(vat.text) ?? 0,
                            shipping: int.tryParse(shipping.text) ?? 0,
                            note: note.text,
                            dueDate: parsedDueDate,
                            idempotencyKey: requestKey,
                          );
                          await onRefresh?.call();
                        } else {
                          store.createOrder(
                              kind: kind,
                              partyName: selectedParty ?? '',
                              lines: orderLines,
                              discount: int.tryParse(discount.text) ?? 0,
                              vatPercent: double.tryParse(vat.text) ?? 0,
                              shipping: int.tryParse(shipping.text) ?? 0,
                              note: note.text,
                              dueDate: parsedDueDate);
                        }
                        Navigator.pop(dialogContext);
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                            content: Text(quote
                                ? 'Đã tạo báo giá, chưa thay đổi tồn kho.'
                                : sale
                                    ? api != null
                                        ? 'Đã gửi đơn bán chờ duyệt kho.'
                                        : 'Đơn bán đang chờ duyệt trong phiên demo.'
                                    : api != null
                                        ? 'Đã gửi phiếu nhập chờ duyệt kho.'
                                        : 'Phiếu nhập đang chờ duyệt trong phiên demo.')));
                      } catch (error) {
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                            content: Text('$error'),
                            backgroundColor: const Color(0xFFB34B43)));
                      }
                    },
                    icon: const Icon(Icons.check, size: 17),
                    label: Text(quote
                        ? 'Tạo báo giá'
                        : sale
                            ? 'Hoàn tất đơn bán'
                            : 'Tạo phiếu nhập'),
                    style: FilledButton.styleFrom(
                        backgroundColor: const Color(0xFF6B4BC3)))
              ],
            );
          }));
  discount.dispose();
  vat.dispose();
  shipping.dispose();
  dueDate.dispose();
  note.dispose();
}

class _MoneyInput extends StatelessWidget {
  const _MoneyInput(
      {required this.label, required this.controller, required this.onChanged});
  final String label;
  final TextEditingController controller;
  final VoidCallback onChanged;
  @override
  Widget build(BuildContext context) => SizedBox(
      width: 148,
      child: TextField(
          controller: controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          onChanged: (_) => onChanged(),
          decoration: InputDecoration(
              labelText: label,
              border: const OutlineInputBorder(),
              isDense: true)));
}

class _TotalRow extends StatelessWidget {
  const _TotalRow(
      {required this.label, required this.value, this.bold = false});
  final String label;
  final String value;
  final bool bold;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(children: [
        Expanded(
            child: Text(label,
                style: TextStyle(
                    fontSize: 11,
                    fontWeight: bold ? FontWeight.w800 : FontWeight.w500))),
        Text(value,
            style: TextStyle(
                fontSize: bold ? 14 : 11,
                fontWeight: bold ? FontWeight.w800 : FontWeight.w500))
      ]));
}

Future<void> _showPayment(
    BuildContext context, CommerceMemoryStore store, CommerceOrder order,
    {CommerceApi? api, Future<void> Function()? onRefresh}) async {
  final requestKey = CommerceApi.newIdempotencyKey();
  final amount = TextEditingController(text: '${order.outstanding}');
  final reference = TextEditingController();
  var method = 'cash';
  await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
          builder: (dialogContext, setDialogState) => AlertDialog(
                  title: Text(order.kind == 'sale'
                      ? 'Ghi nhận thu nợ'
                      : 'Ghi nhận trả nợ'),
                  content: SizedBox(
                      width: 360,
                      child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('${order.partyName} · ${order.code}',
                                style: const TextStyle(fontSize: 12)),
                            const SizedBox(height: 5),
                            Text('Còn lại ${_money(order.outstanding)}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700, fontSize: 12)),
                            const SizedBox(height: 14),
                            TextField(
                                controller: amount,
                                autofocus: true,
                                keyboardType: TextInputType.number,
                                decoration: const InputDecoration(
                                    labelText: 'Số tiền thanh toán (₫)',
                                    border: OutlineInputBorder())),
                            const SizedBox(height: 10),
                            DropdownButtonFormField<String>(
                              initialValue: method,
                              decoration: const InputDecoration(
                                  labelText: 'Phương thức',
                                  border: OutlineInputBorder(),
                                  isDense: true),
                              items: const [
                                DropdownMenuItem(
                                    value: 'cash', child: Text('Tiền mặt')),
                                DropdownMenuItem(
                                    value: 'bank_transfer',
                                    child: Text('Chuyển khoản')),
                              ],
                              onChanged: (value) => setDialogState(
                                  () => method = value ?? 'cash'),
                            ),
                            const SizedBox(height: 10),
                            TextField(
                                controller: reference,
                                decoration: const InputDecoration(
                                    labelText: 'Mã giao dịch (không bắt buộc)',
                                    border: OutlineInputBorder(),
                                    isDense: true))
                          ])),
                  actions: [
                    TextButton(
                        onPressed: () => Navigator.pop(dialogContext),
                        child: const Text('Hủy')),
                    FilledButton(
                        onPressed: () async {
                          try {
                            if (api != null) {
                              await api.recordPayment(
                                  order.id, int.parse(amount.text),
                                  method: method,
                                  reference: reference.text,
                                  idempotencyKey: requestKey);
                              await onRefresh?.call();
                            } else {
                              store.recordPayment(
                                  order.id, int.parse(amount.text),
                                  method: method, reference: reference.text);
                            }
                            Navigator.pop(dialogContext);
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text(api == null
                                    ? 'Đã ghi nhận thanh toán trong phiên RAM.'
                                    : 'Đã ghi nhận thanh toán.'),
                              ),
                            );
                          } catch (error) {
                            ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(content: Text('$error')));
                          }
                        },
                        child: const Text('Lưu thanh toán'))
                  ])));
  amount.dispose();
  reference.dispose();
}

Future<void> _showStocktake(BuildContext context, CommerceMemoryStore store,
    {CommerceApi? api, Future<void> Function()? onRefresh}) async {
  final requestKey = CommerceApi.newIdempotencyKey();
  final countInputs = {
    for (final p in store.products)
      p.id: TextEditingController(text: '${p.stock}')
  };
  final noteController = TextEditingController();
  final dateText = DateFormat('dd/MM/yyyy').format(DateTime.now());

  await showDialog<void>(
    context: context,
    builder: (dialogContext) => StatefulBuilder(
      builder: (ctx, setDialogState) => AlertDialog(
        titlePadding: const EdgeInsets.fromLTRB(20, 20, 20, 10),
        contentPadding: const EdgeInsets.symmetric(horizontal: 20),
        title: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: const Color(0xFFEDE8FC),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(Icons.fact_check_outlined,
                  color: Color(0xFF6B4BC3), size: 20),
            ),
            const SizedBox(width: 12),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Tạo phiếu kiểm kê',
                      style:
                          TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                  Text('Đối chiếu tồn hệ thống và tồn thực tế',
                      style: TextStyle(fontSize: 11, color: Color(0xFF7F857D))),
                ],
              ),
            ),
            IconButton(
              icon: const Icon(Icons.close, size: 20),
              onPressed: () => Navigator.pop(dialogContext),
            ),
          ],
        ),
        content: SizedBox(
          width: 580,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF9FAFB),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: const Color(0xFFE5E7EB)),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.calendar_today_outlined,
                                size: 16, color: Color(0xFF6B4BC3)),
                            const SizedBox(width: 8),
                            Text('Ngày kiểm kê: $dateText',
                                style: const TextStyle(
                                    fontSize: 12, fontWeight: FontWeight.w600)),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF3F4F6),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: const Row(
                    children: [
                      Expanded(
                          flex: 5,
                          child: Text('SẢN PHẨM',
                              style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700,
                                  color: Color(0xFF4B5563)))),
                      Expanded(
                          flex: 2,
                          child: Text('HỆ THỐNG',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700,
                                  color: Color(0xFF4B5563)))),
                      Expanded(
                          flex: 3,
                          child: Text('THỰC TẾ',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700,
                                  color: Color(0xFF4B5563)))),
                      Expanded(
                          flex: 2,
                          child: Text('LỆCH',
                              textAlign: TextAlign.right,
                              style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700,
                                  color: Color(0xFF4B5563)))),
                    ],
                  ),
                ),
                const SizedBox(height: 6),
                for (final p in store.products) ...[
                  Builder(builder: (_) {
                    final actual =
                        double.tryParse(countInputs[p.id]?.text ?? '') ??
                            p.stock;
                    final diff = actual - p.stock;
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Row(
                        children: [
                          Expanded(
                            flex: 5,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(p.name,
                                    style: const TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.w600)),
                                Text('${p.sku} · ${p.unit}',
                                    style: const TextStyle(
                                        fontSize: 9.5,
                                        color: Color(0xFF81877F))),
                              ],
                            ),
                          ),
                          Expanded(
                            flex: 2,
                            child: Text(
                              '${p.stock}',
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                  fontSize: 12, fontWeight: FontWeight.w700),
                            ),
                          ),
                          Expanded(
                            flex: 3,
                            child: SizedBox(
                              height: 36,
                              child: TextField(
                                controller: countInputs[p.id],
                                textAlign: TextAlign.center,
                                keyboardType:
                                    const TextInputType.numberWithOptions(
                                        decimal: true),
                                onChanged: (_) => setDialogState(() {}),
                                decoration: const InputDecoration(
                                  isDense: true,
                                  contentPadding: EdgeInsets.symmetric(
                                      horizontal: 8, vertical: 8),
                                  border: OutlineInputBorder(),
                                ),
                              ),
                            ),
                          ),
                          Expanded(
                            flex: 2,
                            child: Text(
                              diff == 0
                                  ? '0'
                                  : diff > 0
                                      ? '+$diff'
                                      : '$diff',
                              textAlign: TextAlign.right,
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                color: diff == 0
                                    ? const Color(0xFF6B7280)
                                    : diff > 0
                                        ? const Color(0xFF16A34A)
                                        : const Color(0xFFDC2626),
                              ),
                            ),
                          ),
                        ],
                      ),
                    );
                  }),
                  const Divider(height: 1, color: Color(0xFFF3F4F6)),
                ],
                const SizedBox(height: 12),
                TextField(
                  controller: noteController,
                  decoration: const InputDecoration(
                    labelText: 'Ghi chú kiểm kê (lý do chênh lệch...)',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Hủy'),
          ),
          FilledButton.icon(
            style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF6B4BC3)),
            onPressed: () async {
              try {
                final quantities = {
                  for (final p in store.products)
                    p.id: double.parse(countInputs[p.id]!.text),
                };
                if (api != null) {
                  await api.submitStocktake(quantities,
                      idempotencyKey: requestKey);
                  await onRefresh?.call();
                } else {
                  store.recordDirectStocktake(quantities,
                      note: noteController.text);
                }
                if (!context.mounted) return;
                Navigator.pop(dialogContext);
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content:
                        Text('Đã lưu kết quả kiểm kê và điều chỉnh tồn kho.'),
                    backgroundColor: Color(0xFF16A34A),
                  ),
                );
              } catch (error) {
                ScaffoldMessenger.of(context)
                    .showSnackBar(SnackBar(content: Text('$error')));
              }
            },
            icon: const Icon(Icons.save_outlined, size: 16),
            label: const Text('Lưu kiểm kê'),
          ),
        ],
      ),
    ),
  );

  for (final controller in countInputs.values) {
    controller.dispose();
  }
  noteController.dispose();
}

BoxDecoration _cardDecoration() => BoxDecoration(
    color: Colors.white,
    borderRadius: BorderRadius.circular(13),
    border: Border.all(color: const Color(0xFFE9EBE7)));

String _money(int amount) =>
    '${NumberFormat.decimalPattern('vi_VN').format(amount)} ₫';

Future<void> _printOrder(BuildContext context, CommerceOrder order) async {
  try {
    await Printing.layoutPdf(
      onLayout: (format) => _buildOrderPdf(order),
      name: '${order.code}.pdf',
    );
  } catch (error) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Không tạo được phiếu PDF: $error')),
    );
  }
}

Future<void> _shareOrder(BuildContext context, CommerceOrder order) async {
  try {
    await Printing.sharePdf(
      bytes: await _buildOrderPdf(order),
      filename: '${order.code}.pdf',
    );
  } catch (error) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Không chia sẻ được phiếu PDF: $error')),
    );
  }
}

Future<Uint8List> _buildOrderPdf(CommerceOrder order) async {
  final fontBytes = await rootBundle.load('assets/fonts/Roboto-Regular.ttf');
  final font = pw.Font.ttf(fontBytes);
  final document = pw.Document(theme: pw.ThemeData.withFont(base: font));
  final title = switch (order.kind) {
    'purchase' => 'PHIẾU MUA HÀNG',
    'quote' => 'BÁO GIÁ',
    _ => 'HÓA ĐƠN BÁN HÀNG',
  };
  document.addPage(pw.MultiPage(
    pageFormat: PdfPageFormat.a4,
    margin: const pw.EdgeInsets.all(36),
    footer: (context) => pw.Align(
      alignment: pw.Alignment.centerRight,
      child: pw.Text('Trang ${context.pageNumber}/${context.pagesCount}',
          style: const pw.TextStyle(fontSize: 8, color: PdfColors.grey600)),
    ),
    build: (pageContext) => [
      pw.Column(
        crossAxisAlignment: pw.CrossAxisAlignment.stretch,
        children: [
          pw.Row(
            mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
            crossAxisAlignment: pw.CrossAxisAlignment.start,
            children: [
              pw.Column(
                crossAxisAlignment: pw.CrossAxisAlignment.start,
                children: [
                  pw.Text('CÔNG TY TNHH QUẢN LÝ KHO VIỆT NAM',
                      style: pw.TextStyle(
                          font: font,
                          fontSize: 12,
                          fontWeight: pw.FontWeight.bold,
                          color: PdfColor.fromHex('#6B4BC3'))),
                  pw.SizedBox(height: 3),
                  pw.Text('Địa chỉ: Tòa nhà CMC, Duy Tân, Cầu Giấy, Hà Nội',
                      style: pw.TextStyle(font: font, fontSize: 8)),
                  pw.Text('MST: 0109988776 · Hotline: 1900 6868',
                      style: pw.TextStyle(font: font, fontSize: 8)),
                ],
              ),
              pw.Column(
                crossAxisAlignment: pw.CrossAxisAlignment.end,
                children: [
                  pw.Text('Mã phiếu: ${order.code}',
                      style: pw.TextStyle(
                          font: font,
                          fontSize: 10,
                          fontWeight: pw.FontWeight.bold)),
                  pw.Text(
                      'Ngày in: ${DateFormat('dd/MM/yyyy HH:mm').format(DateTime.now())}',
                      style: pw.TextStyle(font: font, fontSize: 8)),
                  pw.Text('Đơn vị tiền tệ: Việt Nam Đồng',
                      style: pw.TextStyle(font: font, fontSize: 8)),
                ],
              ),
            ],
          ),
          pw.SizedBox(height: 14),
          pw.Divider(color: PdfColors.grey400, thickness: .8),
          pw.SizedBox(height: 8),
          pw.Center(
              child: pw.Text(title,
                  style: pw.TextStyle(
                      font: font,
                      fontSize: 18,
                      fontWeight: pw.FontWeight.bold,
                      color: PdfColor.fromHex('#1F2937')))),
          pw.SizedBox(height: 14),
          pw.Container(
            padding: const pw.EdgeInsets.all(10),
            decoration: pw.BoxDecoration(
              color: PdfColors.grey100,
              borderRadius: const pw.BorderRadius.all(pw.Radius.circular(4)),
            ),
            child: pw.Row(
              children: [
                pw.Expanded(
                  child: pw.Column(
                    crossAxisAlignment: pw.CrossAxisAlignment.start,
                    children: [
                      pw.Text(
                          '${order.kind == 'purchase' ? 'Nhà cung cấp' : 'Khách hàng'}: ${order.partyName}',
                          style: pw.TextStyle(
                              font: font,
                              fontSize: 10,
                              fontWeight: pw.FontWeight.bold)),
                      pw.SizedBox(height: 3),
                      pw.Text(
                          'Ngày chứng từ: ${DateFormat('dd/MM/yyyy').format(order.createdAt)}',
                          style: pw.TextStyle(font: font, fontSize: 9)),
                    ],
                  ),
                ),
                if (order.dueDate != null) ...[
                  pw.Column(
                    crossAxisAlignment: pw.CrossAxisAlignment.end,
                    children: [
                      pw.Text(
                          'Hạn thanh toán: ${DateFormat('dd/MM/yyyy').format(order.dueDate!)}',
                          style: pw.TextStyle(
                              font: font,
                              fontSize: 9,
                              fontWeight: pw.FontWeight.bold,
                              color: PdfColor.fromHex('#DC2626'))),
                      pw.SizedBox(height: 3),
                      pw.Text('Trạng thái: ${order.paymentStatus}',
                          style: pw.TextStyle(font: font, fontSize: 9)),
                    ],
                  ),
                ],
              ],
            ),
          ),
          pw.SizedBox(height: 14),
          pw.TableHelper.fromTextArray(
            headers: const [
              'STT',
              'Mã hàng',
              'Tên hàng hóa',
              'ĐVT',
              'SL',
              'Đơn giá',
              'Thành tiền'
            ],
            data: [
              for (var index = 0; index < order.lines.length; index++)
                [
                  '${index + 1}',
                  order.lines[index].productId,
                  order.lines[index].name,
                  order.lines[index].unit,
                  NumberFormat.decimalPattern('vi_VN')
                      .format(order.lines[index].quantity),
                  _money(order.lines[index].unitPrice),
                  _money(order.lines[index].amount),
                ],
            ],
            headerStyle: pw.TextStyle(
                font: font, fontWeight: pw.FontWeight.bold, fontSize: 9),
            headerDecoration: const pw.BoxDecoration(color: PdfColors.grey200),
            cellStyle: pw.TextStyle(font: font, fontSize: 8.5),
            cellAlignment: pw.Alignment.centerLeft,
            border: pw.TableBorder.all(color: PdfColors.grey400, width: .5),
            cellPadding:
                const pw.EdgeInsets.symmetric(horizontal: 6, vertical: 5),
          ),
          pw.SizedBox(height: 12),
          pw.Align(
            alignment: pw.Alignment.centerRight,
            child: pw.SizedBox(
              width: 250,
              child: pw.Column(children: [
                _pdfTotal('Tạm tính', order.subtotal, font),
                if (order.discount > 0)
                  _pdfTotal('Chiết khấu', -order.discount, font),
                if (order.vat > 0) _pdfTotal('VAT', order.vat, font),
                if (order.shipping > 0)
                  _pdfTotal('Vận chuyển', order.shipping, font),
                pw.Divider(thickness: .5),
                _pdfTotal('TỔNG CỘNG', order.total, font, bold: true),
                _pdfTotal('Đã thanh toán', order.paid, font),
                _pdfTotal('Còn phải thu/trả', order.outstanding, font,
                    bold: true),
              ]),
            ),
          ),
          if (order.kind == 'sale' && order.outstanding > 0) ...[
            pw.SizedBox(height: 14),
            pw.Container(
              padding: const pw.EdgeInsets.all(10),
              decoration: pw.BoxDecoration(
                border: pw.TableBorder.all(
                    color: PdfColor.fromHex('#6B4BC3'), width: .8),
                borderRadius: const pw.BorderRadius.all(pw.Radius.circular(6)),
                color: PdfColor.fromHex('#FAF8FE'),
              ),
              child: pw.Row(
                children: [
                  pw.BarcodeWidget(
                    data:
                        'https://img.vietqr.io/image/970422-0988776655-compact2.png?amount=${order.outstanding}&addInfo=${order.code}',
                    barcode: pw.Barcode.qrCode(),
                    width: 64,
                    height: 64,
                  ),
                  pw.SizedBox(width: 12),
                  pw.Column(
                    crossAxisAlignment: pw.CrossAxisAlignment.start,
                    children: [
                      pw.Text('QUÉT MÃ VIETQR ĐỂ THANH TOÁN',
                          style: pw.TextStyle(
                              font: font,
                              fontWeight: pw.FontWeight.bold,
                              fontSize: 9.5,
                              color: PdfColor.fromHex('#6B4BC3'))),
                      pw.SizedBox(height: 3),
                      pw.Text(
                          'Ngân hàng: MB Bank · STK: 0988776655 · Chủ TK: NGUYEN VAN AN',
                          style: pw.TextStyle(font: font, fontSize: 8)),
                      pw.Text(
                          'Số tiền: ${_money(order.outstanding)} · Nội dung: ${order.code}',
                          style: pw.TextStyle(
                              font: font,
                              fontSize: 8.5,
                              fontWeight: pw.FontWeight.bold)),
                    ],
                  ),
                ],
              ),
            ),
          ],
          if (order.note.isNotEmpty) ...[
            pw.SizedBox(height: 12),
            pw.Text('Ghi chú: ${order.note}',
                style: pw.TextStyle(
                    font: font, fontSize: 8.5, fontStyle: pw.FontStyle.italic)),
          ],
          pw.SizedBox(height: 24),
          if (order.kind == 'purchase')
            pw.Row(
              mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
              children: [
                pw.Column(children: [
                  pw.Text('Người lập phiếu',
                      style: pw.TextStyle(
                          font: font,
                          fontSize: 9,
                          fontWeight: pw.FontWeight.bold)),
                  pw.SizedBox(height: 44),
                  pw.Text('(Ký, họ tên)',
                      style: pw.TextStyle(font: font, fontSize: 7.5)),
                ]),
                pw.Column(children: [
                  pw.Text('Người giao hàng',
                      style: pw.TextStyle(
                          font: font,
                          fontSize: 9,
                          fontWeight: pw.FontWeight.bold)),
                  pw.SizedBox(height: 44),
                  pw.Text('(Ký, họ tên)',
                      style: pw.TextStyle(font: font, fontSize: 7.5)),
                ]),
                pw.Column(children: [
                  pw.Text('Thủ kho',
                      style: pw.TextStyle(
                          font: font,
                          fontSize: 9,
                          fontWeight: pw.FontWeight.bold)),
                  pw.SizedBox(height: 44),
                  pw.Text('(Ký, họ tên)',
                      style: pw.TextStyle(font: font, fontSize: 7.5)),
                ]),
                pw.Column(children: [
                  pw.Text('Kế toán trưởng',
                      style: pw.TextStyle(
                          font: font,
                          fontSize: 9,
                          fontWeight: pw.FontWeight.bold)),
                  pw.SizedBox(height: 44),
                  pw.Text('(Ký, đóng dấu)',
                      style: pw.TextStyle(font: font, fontSize: 7.5)),
                ]),
              ],
            )
          else
            pw.Row(
              mainAxisAlignment: pw.MainAxisAlignment.spaceAround,
              children: [
                pw.Column(children: [
                  pw.Text('Người lập phiếu',
                      style: pw.TextStyle(
                          font: font,
                          fontSize: 9,
                          fontWeight: pw.FontWeight.bold)),
                  pw.SizedBox(height: 44),
                  pw.Text('(Ký và ghi rõ họ tên)',
                      style: pw.TextStyle(font: font, fontSize: 7.5)),
                ]),
                pw.Column(children: [
                  pw.Text(
                      order.kind == 'quote'
                          ? 'Đại diện khách hàng'
                          : 'Khách hàng',
                      style: pw.TextStyle(
                          font: font,
                          fontSize: 9,
                          fontWeight: pw.FontWeight.bold)),
                  pw.SizedBox(height: 44),
                  pw.Text('(Ký và ghi rõ họ tên)',
                      style: pw.TextStyle(font: font, fontSize: 7.5)),
                ]),
              ],
            ),
        ],
      ),
    ],
  ));
  return document.save();
}

pw.Widget _pdfTotal(String label, int amount, pw.Font font,
        {bool bold = false}) =>
    pw.Padding(
      padding: const pw.EdgeInsets.symmetric(vertical: 2.5),
      child: pw.Row(
        mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
        children: [
          pw.Text(label,
              style: pw.TextStyle(
                  font: font,
                  fontSize: 8.5,
                  fontWeight: bold ? pw.FontWeight.bold : null)),
          pw.Text(_money(amount),
              style: pw.TextStyle(
                  font: font,
                  fontSize: 8.5,
                  fontWeight: bold ? pw.FontWeight.bold : null)),
        ],
      ),
    );
