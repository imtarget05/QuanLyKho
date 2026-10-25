import 'dart:async';

import '../models/dtos.dart';

/// Kết quả lỗi API demo (409/422…).
/// Tiền tố lý do phiếu điều chỉnh số dư quỹ — dùng để nhận diện phiếu điều
/// chỉnh (kể cả chiều TĂNG số dư, vì backend chỉ có `kind=receipt` cho dòng
/// tiền vào quỹ — xem `backend/app/api/routes/cash_sim.py`).
const String kCashAdjustmentReasonPrefix = 'Điều chỉnh số dư quỹ';

class ApiException implements Exception {
  ApiException(this.code, this.message, {this.requestId});

  final String code;
  final String message;
  final String? requestId;

  @override
  String toString() => 'ApiException($code): $message';
}

/// Trạng thái sức khoẻ backend (`GET /health/live`, public, không cần auth).
class HealthStatus {
  const HealthStatus({
    required this.alive,
    required this.version,
    required this.latencyMs,
    this.error,
  });

  final bool alive;
  final String version;
  final int latencyMs;
  final String? error;
}

/// Kết quả yêu cầu khôi phục mật khẩu (bước 1 qua OTP).
class PasswordResetResult {
  const PasswordResetResult({
    required this.username,
    required this.message,
    this.otpDemo,
    this.expiresInSeconds = 900,
  });

  final String username;
  final String message;
  final String? otpDemo;
  final int expiresInSeconds;
}

/// Hợp đồng repository theo docs/06-api.md. UI chỉ phụ thuộc interface này;
/// backend FastAPI có thể nối sau bằng cùng contract.
abstract class BankOpsRepository {
  // GET /health/live (public) — sức khoẻ backend cho màn Cài đặt.
  Future<HealthStatus> getHealth();

  // POST /auth/login, GET /me
  Future<List<AppUser>> loadUsers();
  Future<AppUser> login(String username);
  Future<void> changePassword({
    required String oldPassword,
    required String newPassword,
  });
  Future<void> changePin({
    required String currentPassword,
    required String newPin,
  });
  Future<PasswordResetResult> requestPasswordReset(String username);
  Future<void> resetPassword({
    required String username,
    required String otp,
    required String newPassword,
  });
  Future<AppUser> updateProfile({
    required String displayName,
    String? email,
    String? phoneNumber,
    String? branch,
    String? avatarUrl,
  });

  // GET /inventory/locations, /items, /balances, /assets
  Future<List<InventoryLocation>> getLocations();
  Future<List<InventoryItem>> getItems();
  Future<List<StockBalance>> getBalances({String? locationId});
  Future<List<AssetRecord>> getAssets({String? locationId});
  Future<List<AssetLogItem>> getAssetHistory(String assetId);
  Future<void> handoverAsset(
    String assetId, {
    String? toLocationId,
    String? toAssignee,
    String? status,
    String? notes,
  });
  Future<List<StockMovement>> getMovements({String? itemId});

  // CRUD Inventory Items & Locations
  Future<InventoryItem> createItem({
    required String sku,
    required String name,
    required String unit,
    bool trackedSerial = false,
    String? category,
    String? packaging,
    double? costPrice,
    double? sellingPrice,
    double? minStock,
  });
  Future<BatchItemImportResult> createItemsBatch(
    List<Map<String, dynamic>> items,
  );
  Future<InventoryItem> updateItem({
    required String id,
    String? name,
    String? unit,
    bool? trackedSerial,
    String? category,
    String? packaging,
    double? costPrice,
    double? sellingPrice,
    double? minStock,
  });
  Future<void> deleteItem(String id);
  Future<void> deleteItemsBatch(List<String> itemIds);
  Future<void> resetStoreData({bool keepCatalog = true});

  Future<InventoryLocation> createLocation({
    required String code,
    required String name,
  });
  Future<InventoryLocation> updateLocation({
    required String id,
    String? name,
  });
  Future<void> deleteLocation(String id);

  // Stock Levels & Low Stock Alerts
  Future<List<StockLevelItem>> getStockLevels(
      {String? locationId, String? itemId});
  Future<StockLevelItem> putStockLevel({
    required String locationId,
    required String itemId,
    required String minQty,
    String? maxQty,
  });
  Future<List<LowStockAlertItem>> getLowStockAlerts({String? locationId});

  // Stocktakes (Kiểm kê định kỳ & đối soát)
  Future<List<StocktakeItem>> getStocktakes({String? locationId});
  Future<StocktakeItem> getStocktake(String id);
  Future<StocktakeItem> createStocktake({
    required String locationId,
    String? note,
    String? shiftCode,
    String? businessDate,
    String? idempotencyKey,
  });
  Future<StocktakeItem> updateStocktakeLines(
      String id, List<Map<String, dynamic>> lines,
      {String? idempotencyKey, int? expectedVersion});
  Future<StocktakeItem> submitStocktake(String id,
      {String? idempotencyKey, int? expectedVersion});
  Future<StocktakeItem> approveStocktake(String id);
  Future<StocktakeItem> rejectStocktake(String id, {String? reason});

  // GET /inventory/requests, POST /inventory/requests
  Future<List<StockRequest>> getStockRequests();
  Future<StockRequest> createStockRequest({
    required RequestKind kind,
    String? sourceLocationId,
    String? destLocationId,
    String? supplier,
    String? supplierName,
    String? invoiceNo,
    String? subKind,
    required List<StockRequestLine> lines,
    String? reason,
  });
  Future<void> deleteStockRequest(String id);
  // POST /inventory/requests/{id}/submit|approve|reject|return
  Future<StockRequest> submitStockRequest(String id);
  Future<StockRequest> approveStockRequest(String id, {String? supervisorPin});
  Future<StockRequest> rejectStockRequest(String id, String reason);
  Future<StockRequest> returnStockRequest(String id, {required String reason});

  // GET /cash-sim/boxes, /balances, /journals, /requests
  Future<List<Cashbox>> getCashboxes();
  Future<Cashbox> createCashbox({
    required String code,
    required String name,
    String currency = 'VND',
    String openingBalance = '0.00',
  });
  /// Sửa THÔNG TIN két (tên / trạng thái) — KHÔNG sửa được số dư.
  ///
  /// Số dư quỹ chỉ đổi qua journal (phiếu) đã được duyệt; backend chặn 422
  /// `DIRECT_BALANCE_WRITE_FORBIDDEN` nếu client gửi field số dư vào đây.
  Future<Cashbox> updateCashbox({
    required String id,
    String? name,
    bool? active,
  });
  Future<void> deleteCashbox(String id);

  /// Tạo phiếu quỹ ĐIỀU CHỈNH (journal) — luồng có kiểm soát + duyệt.
  ///
  /// - [amount]: số tiền TUYỆT ĐỐI (> 0).
  /// - [increase]: `true` = quỹ TĂNG (tiền vào quỹ), `false` = quỹ GIẢM.
  ///
  /// Backend (`backend/app/api/routes/cash_sim.py`) coi `kind=adjustment` là
  /// bút toán RA quỹ (chi) và chỉ `kind=receipt` mới là dòng tiền VÀO quỹ,
  /// nên hệ thống ánh xạ hướng điều chỉnh sang kind tương ứng.
  Future<CashRequest> createCashAdjustmentRequest({
    required String cashboxId,
    required String amount,
    required bool increase,
    String? reason,
  });

  Future<List<CashBalance>> getCashBalances();
  Future<List<JournalEntry>> getJournals();
  Future<List<CashRequest>> getCashRequests();
  Future<CashRequest> createCashRequest({
    required String cashboxId,
    required RequestKind kind,
    required String amount,
    String? reason,
  });
  Future<void> deleteCashRequest(String id);
  Future<CashRequest> submitCashRequest(String id);
  Future<CashRequest> approveCashRequest(String id, {String? supervisorPin});
  Future<CashRequest> rejectCashRequest(String id, String reason);
  Future<CashRequest> returnCashRequest(String id, {required String reason});

  // GET /approvals/inbox & AI Thẩm định rủi ro
  Future<List<ApprovalItem>> getApprovalInbox();
  Future<AiRiskAssessment> assessApprovalItem(ApprovalItem item);
  Stream<String> get approvalNotifications;
  void dispose();

  // GET /activity, GET /events/stream
  Future<List<ActivityEvent>> getActivity({String? cursor});

  // GET /integrations/connections, /integration-runs
  Future<List<IntegrationConnection>> getConnections();
  Future<IntegrationConnection> createConnection({
    required String name,
    required String type,
    String? endpoint,
    Map<String, dynamic>? config,
  });
  Future<IntegrationConnection> updateConnection({
    required String id,
    String? name,
    String? endpoint,
    String? status,
  });
  Future<void> deleteConnection(String id);
  Future<Map<String, dynamic>> testConnection(String id);
  Future<List<IntegrationRun>> getIntegrationRuns();
  Future<StagingPreview> uploadImportFile({
    required String filename,
    required List<int> bytes,
    required String type,
  });
  Future<StagingPreview> fetchGoogleSheet({
    required String sheetId,
    String tab = 'Sheet1',
  });
  Future<StagingPreview> getRunPreview(String runId);
  Future<ConfirmRunResult> confirmRun(String runId);

  // GET /reconciliations, POST /reconciliations
  Future<List<ReconciliationRun>> getReconciliations();
  Future<ReconciliationRun> runReconciliation({String scope = 'cash'});

  // GET /reports/*
  Future<List<InventoryBucket>> getInventoryDaily({
    String? dateFrom,
    String? dateTo,
  });
  Future<List<InventoryBucket>> getInventoryMonthly({
    String? dateFrom,
    String? dateTo,
  });
  Future<List<CashflowBucket>> getCashflowDaily({
    String? dateFrom,
    String? dateTo,
  });
  Future<List<CashflowBucket>> getCashflowMonthly({
    String? dateFrom,
    String? dateTo,
  });
  Future<List<StagnationItem>> getStagnation({
    int watchDays = 30,
    int stagnantDays = 60,
    int criticalDays = 90,
  });

  // --- SRS Trà Sữa (Cảnh báo & Báo cáo F&B) ---
  Future<List<ExpiryAlertItem>> getExpiryAlerts({int days = 7});
  Future<List<ConsumptionTopItem>> getConsumptionTop({
    String? dateFrom,
    String? dateTo,
    int limit = 10,
  });
  Future<List<ShiftHistoryItem>> getShiftHistory({
    String? dateFrom,
    String? dateTo,
    String? shiftCode,
  });

  // --- Admin IAM (Phase 1) ---
  Future<List<BranchDto>> getBranches();
  Future<List<RoleDto>> getRoles();
  Future<List<EmployeeUserDto>> getEmployees({
    String? search,
    String? branchId,
    String? role,
    String? status,
  });
  Future<EmployeeUserDto> createEmployee({
    required String username,
    required String displayName,
    String? email,
    String? phoneNumber,
    String? branchId,
    List<String> roles = const ['staff'],
    List<Map<String, dynamic>> scopes = const [],
    String onboardingMethod = 'temporary_password',
  });
  Future<EmployeeUserDto> updateEmployeeStatus(
    String userId,
    String status, {
    String? reason,
  });
  Future<EmployeeUserDto> updateEmployeeRoles(
      String userId, List<String> roles);
  Future<EmployeeUserDto> updateEmployeeScopes(
    String userId,
    List<Map<String, dynamic>> scopes,
  );
  Future<void> revokeEmployeeSessions(String userId);
  Future<String> resetEmployeePassword(String userId);
  Future<String> reinviteEmployee(String userId);

  // --- ETL Pipeline (Phase 2) ---
  Future<List<EtlConnectionDto>> getEtlConnections({String? branchId});
  Future<EtlConnectionDto> createEtlConnection({
    required String name,
    required String type,
    String? secretRef,
    List<String>? allowlistSheets,
    String? branchId,
  });
  Future<List<EtlPipelineDto>> getEtlPipelines({
    String? target,
    String? branchId,
  });
  Future<EtlPipelineDto> createEtlPipeline({
    required String name,
    required String target,
    required String connectionId,
    String? branchId,
    String? locationId,
    String? destinationLocationId,
    String? scheduleCron,
  });
  Future<List<EtlMappingVersionDto>> getEtlMappingVersions(String pipelineId);
  Future<EtlMappingVersionDto> createEtlMappingVersion(
    String pipelineId, {
    required List<Map<String, dynamic>> mappingRules,
    String duplicatePolicy = 'reject',
  });
  Future<EtlMappingVersionDto> publishEtlMappingVersion(
    String pipelineId,
    String versionId,
  );
  Future<EtlRunDto> triggerEtlRun(
    String pipelineId, {
    List<Map<String, dynamic>>? rawRows,
    List<int>? fileBytes,
    String? filename,
    String? externalEventId,
  });
  Future<List<EtlRunDto>> getEtlRuns({
    String? pipelineId,
    String? status,
  });
  Future<EtlRunDto> getEtlRun(String runId);
  Future<Map<String, dynamic>> getEtlRunRows(
    String runId, {
    bool? valid,
    String? search,
    int page = 1,
    int pageSize = 50,
  });
  Future<EtlRunDto> reviewEtlRun(
    String runId, {
    required String decision,
    String? note,
  });
  Future<Map<String, dynamic>> postEtlRun(String runId);
  Future<String> getEtlErrorReport(String runId);
  Future<DashboardSummaryDto> getDashboardSummary({bool canApprove = false});
}
