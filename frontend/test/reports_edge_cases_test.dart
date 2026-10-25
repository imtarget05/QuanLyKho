import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/core/widgets/state_views.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/bankops_repository.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/reports/reports_screen.dart';
import 'package:kho_tra_sua/src/features/reports/widgets/cashflow_chart.dart';
import 'package:kho_tra_sua/src/features/reports/widgets/executive_kpi_deck.dart';
import 'package:kho_tra_sua/src/features/reports/widgets/inventory_chart.dart';
import 'package:kho_tra_sua/src/features/reports/widgets/stagnation_list.dart';

/// Repository that returns empty buckets for testing empty state
class _EmptyBucketsRepository extends FakeBankOpsRepository {
  _EmptyBucketsRepository() : super(latency: Duration.zero);

  @override
  Future<List<InventoryBucket>> getInventoryDaily({
    String? dateFrom,
    String? dateTo,
  }) async => [];

  @override
  Future<List<InventoryBucket>> getInventoryMonthly({
    String? dateFrom,
    String? dateTo,
  }) async => [];

  @override
  Future<List<CashflowBucket>> getCashflowDaily({
    String? dateFrom,
    String? dateTo,
  }) async => [];

  @override
  Future<List<CashflowBucket>> getCashflowMonthly({
    String? dateFrom,
    String? dateTo,
  }) async => [];

  @override
  Future<List<StagnationItem>> getStagnation({
    int watchDays = 30,
    int stagnantDays = 60,
    int criticalDays = 90,
  }) async => [];

  @override
  Future<List<ConsumptionTopItem>> getConsumptionTop({
    String? dateFrom,
    String? dateTo,
    int limit = 10,
  }) async => [];

  @override
  Future<List<ShiftHistoryItem>> getShiftHistory({
    String? dateFrom,
    String? dateTo,
    String? shiftCode,
  }) async => [];

  @override
  Future<List<ReconciliationRun>> getReconciliations() async => [];
}

/// Repository that returns buckets with negative values
class _NegativeValuesRepository extends FakeBankOpsRepository {
  _NegativeValuesRepository() : super(latency: Duration.zero);

  @override
  Future<List<InventoryBucket>> getInventoryDaily({
    String? dateFrom,
    String? dateTo,
  }) async => [
    InventoryBucket(
      bucket: '2026-10-01',
      inboundQty: '-100',
      outboundQty: '50',
      netQty: '-150',
      receiptCount: 2,
      issueCount: 1,
    ),
    InventoryBucket(
      bucket: '2026-10-02',
      inboundQty: '0',
      outboundQty: '0',
      netQty: '0',
      receiptCount: 0,
      issueCount: 0,
    ),
  ];

  @override
  Future<List<InventoryBucket>> getInventoryMonthly({
    String? dateFrom,
    String? dateTo,
  }) async => [
    InventoryBucket(
      bucket: '2026-10',
      inboundQty: '-500',
      outboundQty: '300',
      netQty: '-800',
      receiptCount: 10,
      issueCount: 8,
    ),
  ];

  @override
  Future<List<CashflowBucket>> getCashflowDaily({
    String? dateFrom,
    String? dateTo,
  }) async => [
    CashflowBucket(
      bucket: '2026-10-01',
      totalIn: '-2000000',
      totalOut: '1000000',
      net: '-3000000',
      journalCount: 2,
    ),
  ];

  @override
  Future<List<CashflowBucket>> getCashflowMonthly({
    String? dateFrom,
    String? dateTo,
  }) async => [
    CashflowBucket(
      bucket: '2026-10',
      totalIn: '-10000000',
      totalOut: '5000000',
      net: '-15000000',
      journalCount: 8,
    ),
  ];

  @override
  Future<List<StagnationItem>> getStagnation({
    int watchDays = 30,
    int stagnantDays = 60,
    int criticalDays = 90,
  }) async => [];

  @override
  Future<List<ConsumptionTopItem>> getConsumptionTop({
    String? dateFrom,
    String? dateTo,
    int limit = 10,
  }) async => [];

  @override
  Future<List<ShiftHistoryItem>> getShiftHistory({
    String? dateFrom,
    String? dateTo,
    String? shiftCode,
  }) async => [];

  @override
  Future<List<ReconciliationRun>> getReconciliations() async => [];
}

/// Repository that throws errors to simulate malformed JSON/server errors
class _MalformedDataRepository extends FakeBankOpsRepository {
  _MalformedDataRepository() : super(latency: Duration.zero);

  @override
  Future<List<InventoryBucket>> getInventoryDaily({
    String? dateFrom,
    String? dateTo,
  }) async {
    throw ApiException('MALFORMED_JSON', 'Invalid JSON response from server');
  }

  @override
  Future<List<InventoryBucket>> getInventoryMonthly({
    String? dateFrom,
    String? dateTo,
  }) async {
    throw ApiException('MALFORMED_JSON', 'Invalid JSON response from server');
  }

  @override
  Future<List<CashflowBucket>> getCashflowDaily({
    String? dateFrom,
    String? dateTo,
  }) async {
    throw ApiException('SERVER_ERROR', 'Internal server error');
  }

  @override
  Future<List<CashflowBucket>> getCashflowMonthly({
    String? dateFrom,
    String? dateTo,
  }) async {
    throw ApiException('SERVER_ERROR', 'Internal server error');
  }

  @override
  Future<List<StagnationItem>> getStagnation({
    int watchDays = 30,
    int stagnantDays = 60,
    int criticalDays = 90,
  }) async {
    throw ApiException('SERVER_ERROR', 'Internal server error');
  }

  @override
  Future<List<ConsumptionTopItem>> getConsumptionTop({
    String? dateFrom,
    String? dateTo,
    int limit = 10,
  }) async {
    throw ApiException('SERVER_ERROR', 'Internal server error');
  }

  @override
  Future<List<ShiftHistoryItem>> getShiftHistory({
    String? dateFrom,
    String? dateTo,
    String? shiftCode,
  }) async {
    throw ApiException('SERVER_ERROR', 'Internal server error');
  }

  @override
  Future<List<ReconciliationRun>> getReconciliations() async {
    throw ApiException('FORBIDDEN', 'Access denied');
  }
}

/// Repository that returns mixed valid/invalid data
class _PartialDataRepository extends FakeBankOpsRepository {
  _PartialDataRepository() : super(latency: Duration.zero);

  @override
  Future<List<InventoryBucket>> getInventoryDaily({
    String? dateFrom,
    String? dateTo,
  }) async => [
    InventoryBucket(
      bucket: '2026-10-01',
      inboundQty: '100',
      outboundQty: '50',
      netQty: '50',
      receiptCount: 2,
      issueCount: 1,
    ),
  ];

  @override
  Future<List<InventoryBucket>> getInventoryMonthly({
    String? dateFrom,
    String? dateTo,
  }) async => [];

  @override
  Future<List<CashflowBucket>> getCashflowDaily({
    String? dateFrom,
    String? dateTo,
  }) async {
    throw ApiException('MALFORMED_JSON', 'Invalid cashflow data');
  }

  @override
  Future<List<CashflowBucket>> getCashflowMonthly({
    String? dateFrom,
    String? dateTo,
  }) async => [];

  @override
  Future<List<StagnationItem>> getStagnation({
    int watchDays = 30,
    int stagnantDays = 60,
    int criticalDays = 90,
  }) async => [
    StagnationItem(
      itemId: 'item-1',
      sku: 'TEST-001',
      name: 'Test Item',
      quantity: '100',
      daysSinceLastIssue: 45,
      severity: 'watch',
    ),
  ];

  @override
  Future<List<ConsumptionTopItem>> getConsumptionTop({
    String? dateFrom,
    String? dateTo,
    int limit = 10,
  }) async => [];

  @override
  Future<List<ShiftHistoryItem>> getShiftHistory({
    String? dateFrom,
    String? dateTo,
    String? shiftCode,
  }) async => [];

  @override
  Future<List<ReconciliationRun>> getReconciliations() async => [];
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('ReportsScreen shows empty state when all buckets are empty', (WidgetTester tester) async {
    final repo = _EmptyBucketsRepository();
    await tester.pumpWidget(
      RepositoryScope(
        repository: repo,
        child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: ReportsScreen()),
        ),
      ),
    );
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    await tester.pumpAndSettle();

    // Should show empty state for inventory tab
    expect(find.byKey(const Key('tab-reports-inventory')), findsOneWidget);
    await tester.tap(find.byKey(const Key('tab-reports-inventory')));
    await tester.pumpAndSettle();

    // Should show EmptyView for empty inventory data
    expect(find.byType(EmptyView), findsOneWidget);
    expect(find.textContaining('Chưa có dữ liệu'), findsOneWidget);

    // Cashflow tab should also show empty state
    await tester.tap(find.byKey(const Key('tab-reports-cashflow')));
    await tester.pumpAndSettle();
    expect(find.byType(EmptyView), findsOneWidget);

    // Stagnation tab should show empty state
    await tester.tap(find.byKey(const Key('tab-reports-stagnation')));
    await tester.pumpAndSettle();
    expect(find.byType(EmptyView), findsOneWidget);
  });

  testWidgets('ReportsScreen handles negative values without crashing', (WidgetTester tester) async {
    final repo = _NegativeValuesRepository();
    await tester.pumpWidget(
      RepositoryScope(
        repository: repo,
        child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: ReportsScreen()),
        ),
      ),
    );
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    await tester.pumpAndSettle();

    // Should render without crashing
    expect(find.byKey(const Key('tab-reports-inventory')), findsOneWidget);
    await tester.tap(find.byKey(const Key('tab-reports-inventory')));
    await tester.pumpAndSettle();

    // InventoryChart should handle negative values (uses double.tryParse)
    expect(find.byType(InventoryChart), findsOneWidget);

    // Cashflow tab with negative values
    await tester.tap(find.byKey(const Key('tab-reports-cashflow')));
    await tester.pumpAndSettle();
    expect(find.byType(CashflowChart), findsOneWidget);

    // KPI deck should display negative values correctly
    expect(find.byType(ExecutiveKpiDeck), findsOneWidget);
  });

  testWidgets('ReportsScreen shows error state when API returns malformed data', (WidgetTester tester) async {
    final repo = _MalformedDataRepository();
    await tester.pumpWidget(
      RepositoryScope(
        repository: repo,
        child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: ReportsScreen()),
        ),
      ),
    );
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    await tester.pumpAndSettle();

    // Should show error view
    expect(find.byType(ErrorView), findsOneWidget);
    expect(find.textContaining('MALFORMED_JSON'), findsOneWidget);
  });

  testWidgets('ReportsScreen shows error state when any API returns malformed data', (WidgetTester tester) async {
    final repo = _PartialDataRepository();
    await tester.pumpWidget(
      RepositoryScope(
        repository: repo,
        child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: ReportsScreen()),
        ),
      ),
    );
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    await tester.pumpAndSettle();

    // Should show error view because cashflow API throws
    expect(find.byType(ErrorView), findsOneWidget);
    expect(find.textContaining('MALFORMED_JSON'), findsOneWidget);
  });

  testWidgets('ReportsScreen handles zero/empty stagnation list', (WidgetTester tester) async {
    final repo = _EmptyBucketsRepository();
    await tester.pumpWidget(
      RepositoryScope(
        repository: repo,
        child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: ReportsScreen()),
        ),
      ),
    );
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('tab-reports-stagnation')));
    await tester.pumpAndSettle();

    // StagnationList should show empty state
    expect(find.byType(StagnationList), findsOneWidget);
    expect(find.byType(EmptyView), findsOneWidget);
  });

  testWidgets('ReportsScreen handles zero/empty consumption top list', (WidgetTester tester) async {
    final repo = _EmptyBucketsRepository();
    await tester.pumpWidget(
      RepositoryScope(
        repository: repo,
        child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: ReportsScreen()),
        ),
      ),
    );
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('tab-reports-consumption-top')));
    await tester.pumpAndSettle();

    // Should show empty message
    expect(find.textContaining('Chưa có dữ liệu'), findsOneWidget);
  });

  testWidgets('ReportsScreen handles zero/empty shift history', (WidgetTester tester) async {
    final repo = _EmptyBucketsRepository();
    await tester.pumpWidget(
      RepositoryScope(
        repository: repo,
        child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: ReportsScreen()),
        ),
      ),
    );
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('tab-reports-shift-history')));
    await tester.pumpAndSettle();

    // Should show empty message
    expect(find.textContaining('Chưa có lịch sử'), findsOneWidget);
  });

  testWidgets('ReportsScreen handles reconciliation tab with no runs', (WidgetTester tester) async {
    final repo = _EmptyBucketsRepository();
    await tester.pumpWidget(
      RepositoryScope(
        repository: repo,
        child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: ReportsScreen()),
        ),
      ),
    );
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('tab-reports-reconciliation')));
    await tester.pumpAndSettle();

    // Should show empty state for reconciliations
    expect(find.byType(EmptyView), findsOneWidget);
    expect(find.textContaining('Chưa có lượt đối soát'), findsOneWidget);
  });
}