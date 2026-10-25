export 'domain_models.dart';
export 'report_dtos.dart';

import 'domain_models.dart';

/// User model (demo).
class AppUser {
  const AppUser({
    required this.id,
    required this.username,
    required this.displayName,
    required this.roles,
    this.capabilities = const [],
    this.email,
    this.phoneNumber,
    this.branch,
    this.employeeCode,
    this.avatarUrl,
  });

  final String id;
  final String username;
  final String displayName;
  final List<String> roles;
  final List<String> capabilities;
  final String? email;
  final String? phoneNumber;
  final String? branch;
  final String? employeeCode;
  final String? avatarUrl;

  String get effectiveEmail => (email != null && email!.trim().isNotEmpty)
      ? email!.trim()
      : '$username@khotrasua.local';

  String get effectivePhone =>
      (phoneNumber != null && phoneNumber!.trim().isNotEmpty)
          ? phoneNumber!.trim()
          : '0901 234 567';

  String get effectiveBranch => (branch != null && branch!.trim().isNotEmpty)
      ? branch!.trim()
      : 'Chi nhánh Bến Thành (Hội sở)';

  String get effectiveEmployeeCode {
    if (employeeCode != null && employeeCode!.trim().isNotEmpty) {
      return employeeCode!.trim();
    }
    final clean = id.replaceAll('-', '');
    final code =
        clean.length >= 4 ? clean.substring(0, 4).toUpperCase() : '8892';
    return 'BO-$code';
  }

  AppUser copyWith({
    String? id,
    String? username,
    String? displayName,
    List<String>? roles,
    List<String>? capabilities,
    String? email,
    String? phoneNumber,
    String? branch,
    String? employeeCode,
    String? avatarUrl,
  }) {
    return AppUser(
      id: id ?? this.id,
      username: username ?? this.username,
      displayName: displayName ?? this.displayName,
      roles: roles ?? this.roles,
      capabilities: capabilities ?? this.capabilities,
      email: email ?? this.email,
      phoneNumber: phoneNumber ?? this.phoneNumber,
      branch: branch ?? this.branch,
      employeeCode: employeeCode ?? this.employeeCode,
      avatarUrl: avatarUrl ?? this.avatarUrl,
    );
  }
}

/// Kho/địa điểm.
class InventoryLocation {
  const InventoryLocation({
    required this.id,
    required this.code,
    required this.name,
  });

  final String id;
  final String code;
  final String name;
}

/// Vật tư/mặt hàng.
class InventoryItem {
  const InventoryItem({
    required this.id,
    required this.sku,
    required this.name,
    required this.unit,
    required this.trackedSerial,
    this.category,
    this.packaging,
    this.costPrice,
    this.sellingPrice,
    this.minStock,
    this.imageUrl,
  });

  final String id;
  final String sku;
  final String name;
  final String unit;
  final bool trackedSerial;
  final String? category;
  final String? packaging;
  final double? costPrice;
  final double? sellingPrice;
  final double? minStock;
  final String? imageUrl;
}

/// Kết quả import mặt hàng hàng loạt.
class BatchItemImportResult {
  const BatchItemImportResult({
    required this.createdCount,
    required this.skippedCount,
    required this.items,
  });

  final int createdCount;
  final int skippedCount;
  final List<InventoryItem> items;
}

/// Số tồn kho theo location + item.
class StockBalance {
  const StockBalance({
    required this.locationId,
    required this.itemId,
    required this.quantity,
    this.reservedQuantity = '0',
    this.availableQuantity,
  });

  final String locationId;
  final String itemId;
  final String quantity;
  final String reservedQuantity;
  final String? availableQuantity;

  double get qtyNumber => double.tryParse(quantity) ?? 0.0;
  double get reservedNumber => double.tryParse(reservedQuantity) ?? 0.0;
  double get availableNumber => availableQuantity != null
      ? (double.tryParse(availableQuantity!) ?? 0.0)
      : (qtyNumber - reservedNumber > 0 ? qtyNumber - reservedNumber : 0.0);
}

/// Định mức tồn kho (min_qty, max_qty).
class StockLevelItem {
  const StockLevelItem({
    required this.id,
    required this.locationId,
    required this.itemId,
    required this.minQty,
    this.maxQty,
  });

  final String id;
  final String locationId;
  final String itemId;
  final String minQty;
  final String? maxQty;
}

/// Cảnh báo thiếu tồn kho.
class LowStockAlertItem {
  const LowStockAlertItem({
    required this.locationId,
    required this.locationCode,
    required this.locationName,
    required this.itemId,
    required this.sku,
    required this.itemName,
    required this.unit,
    required this.currentQty,
    required this.minQty,
    this.maxQty,
    required this.status,
    required this.deficit,
    required this.suggestedAction,
  });

  final String locationId;
  final String locationCode;
  final String locationName;
  final String itemId;
  final String sku;
  final String itemName;
  final String unit;
  final String currentQty;
  final String minQty;
  final String? maxQty;
  final String status; // 'low' | 'empty'
  final String deficit;
  final String suggestedAction;
}

/// Dòng kiểm kê kho.
class StocktakeLineItem {
  const StocktakeLineItem({
    required this.id,
    required this.itemId,
    required this.bookQty,
    required this.countedQty,
    required this.variance,
    this.openingQty = '0',
    this.receivedQty = '0',
    this.usedQty = '0',
    this.theoreticalQty = '0',
    this.reason,
  });

  final String id;
  final String itemId;
  final String bookQty;
  final String countedQty;
  final String variance;
  final String openingQty;
  final String receivedQty;
  final String usedQty;
  final String theoreticalQty;
  final String? reason;
}

/// Đợt kiểm kê định kỳ & đối soát.
class StocktakeItem {
  const StocktakeItem({
    required this.id,
    required this.locationId,
    required this.status,
    this.note,
    required this.makerId,
    this.approverId,
    this.adjustmentRequestId,
    required this.createdAt,
    this.completedAt,
    this.lines = const [],
    this.shiftCode,
    this.businessDate,
    this.version = 1,
  });

  final String id;
  final String locationId;
  final String status; // 'open' | 'submitted' | 'closed'
  final String? note;
  final String makerId;
  final String? approverId;
  final String? adjustmentRequestId;
  final DateTime createdAt;
  final DateTime? completedAt;
  final List<StocktakeLineItem> lines;
  final String? shiftCode;
  final String? businessDate;
  final int version;

  int get discrepancyCount => lines
      .where((l) => (double.tryParse(l.variance) ?? 0).abs() > 0.0001)
      .length;
}

/// Tài sản theo serial.
class AssetRecord {
  const AssetRecord({
    this.id,
    required this.serial,
    required this.itemId,
    required this.locationId,
    required this.status,
    this.assignee,
  });

  final String? id;
  final String serial;
  final String itemId;
  final String locationId;
  final AssetStatus status;
  final String? assignee;
}

/// Nhật ký vòng đời và bàn giao nguyên liệu.
class AssetLogItem {
  const AssetLogItem({
    required this.id,
    required this.serial,
    this.fromLocationId,
    this.fromLocationName,
    this.toLocationId,
    this.toLocationName,
    this.fromAssignee,
    this.toAssignee,
    this.statusBefore,
    required this.statusAfter,
    this.actorId,
    this.actorName,
    this.requestId,
    this.notes,
    required this.createdAt,
  });

  final String id;
  final String serial;
  final String? fromLocationId;
  final String? fromLocationName;
  final String? toLocationId;
  final String? toLocationName;
  final String? fromAssignee;
  final String? toAssignee;
  final String? statusBefore;
  final String statusAfter;
  final String? actorId;
  final String? actorName;
  final String? requestId;
  final String? notes;
  final DateTime createdAt;
}

/// Movement ledger.
class StockMovement {
  const StockMovement({
    required this.id,
    required this.itemId,
    required this.locationId,
    required this.quantity,
    required this.kind,
    required this.createdAt,
  });

  final String id;
  final String itemId;
  final String locationId;
  final String quantity;
  final String kind;
  final DateTime createdAt;
}

/// Line item trong stock request.
class StockRequestLine {
  const StockRequestLine({
    required this.itemId,
    required this.quantity,
    this.unitPrice,
    this.lineTotal,
    this.lotNo,
    this.expiryDate,
    this.unit,
    this.conversionRate,
    this.itemName,
  });

  final String itemId;
  final String quantity;
  final String? unitPrice;
  final String? lineTotal;
  final String? lotNo;
  final String? expiryDate;
  final String? unit;
  final String? conversionRate;
  final String? itemName;

  double get totalAmount {
    if (lineTotal != null && lineTotal!.isNotEmpty) {
      final parsed = double.tryParse(lineTotal!);
      if (parsed != null) return parsed;
    }
    final q = double.tryParse(quantity) ?? 0.0;
    final p = double.tryParse(unitPrice ?? '') ?? 0.0;
    return q * p;
  }
}

/// Stock request.
class StockRequest {
  const StockRequest({
    required this.id,
    required this.kind,
    required this.status,
    required this.version,
    required this.createdBy,
    required this.createdByName,
    required this.locationId,
    required this.items,
    required this.reason,
    required this.createdAt,
    this.approvedBy,
    this.approvedByName,
    this.rejectReason,
    this.returnReason,
    this.destinationLocationId,
    this.supplier,
    this.supplierName,
    this.invoiceNo,
    this.subKind,
    this.receivedAt,
  });

  final String id;
  final RequestKind kind;
  final RequestStatus status;
  final int version;
  final String createdBy;
  final String createdByName;
  final String locationId;
  final List<StockRequestLine> items;
  final String reason;
  final DateTime createdAt;
  final String? approvedBy;
  final String? approvedByName;
  final String? rejectReason;
  final String? returnReason;
  final String? destinationLocationId;
  final String? supplier;
  final String? supplierName;
  final String? invoiceNo;
  final String? subKind;
  final DateTime? receivedAt;

  String? get effectiveSupplier => supplierName ?? supplier;

  double get totalCost => items.fold(0.0, (sum, line) => sum + line.totalAmount);

  bool get isMultiline => items.length > 1;

  String get subKindLabel {
    switch (subKind) {
      case 'spoilage':
        return 'Hủy / Hao hụt';
      case 'internal':
        return 'Dùng nội bộ';
      case 'transfer':
        return 'Chuyển kho';
      case 'sale':
      default:
        return kind == RequestKind.receipt ? 'Nhập hàng' : 'Bán hàng';
    }
  }
}

/// Cash box.
class Cashbox {
  const Cashbox({
    required this.id,
    required this.code,
    required this.name,
    required this.openingBalance,
  });

  final String id;
  final String code;
  final String name;
  final String openingBalance;
}

/// Cash balance.
class CashBalance {
  const CashBalance({
    required this.cashboxId,
    required this.amount,
    required this.currency,
  });

  final String cashboxId;
  final String amount;
  final String currency;
}

/// Journal entry.
class JournalEntry {
  const JournalEntry({
    required this.id,
    required this.cashboxId,
    required this.kind,
    required this.amount,
    required this.currency,
    required this.reason,
    required this.createdAt,
  });

  final String id;
  final String cashboxId;
  final String kind;
  final String amount;
  final String currency;
  final String reason;
  final DateTime createdAt;
}

/// Cash request.
class CashRequest {
  const CashRequest({
    required this.id,
    required this.kind,
    required this.status,
    required this.version,
    required this.cashboxId,
    required this.amount,
    required this.currency,
    required this.reason,
    required this.createdBy,
    required this.createdByName,
    required this.createdAt,
    this.approvedBy,
    this.approvedByName,
    this.rejectReason,
    this.returnReason,
  });

  final String id;
  final RequestKind kind;
  final RequestStatus status;
  final int version;
  final String cashboxId;
  final String amount;
  final String currency;
  final String reason;
  final String createdBy;
  final String createdByName;
  final DateTime createdAt;
  final String? approvedBy;
  final String? approvedByName;
  final String? rejectReason;
  final String? returnReason;
}

/// Approval inbox item.
class ApprovalItem {
  const ApprovalItem({
    required this.id,
    required this.kind,
    required this.maker,
    required this.impact,
    required this.detail,
    this.approvalDetail,
    this.status = 'pending',
  });

  final String id;
  final String kind;
  final String maker;
  final String impact;
  final String detail;
  final Map<String, dynamic>? approvalDetail;
  final String status;
}

/// Activity event.
class ActivityEvent {
  const ActivityEvent({
    required this.id,
    required this.occurredAt,
    required this.subjectId,
    required this.status,
    required this.messageKey,
    this.processed,
    this.total,
  });

  final String id;
  final DateTime occurredAt;
  final String subjectId;
  final String status;
  final String messageKey;
  final int? processed;
  final int? total;
}

/// Integration connection.
class IntegrationConnection {
  const IntegrationConnection({
    required this.id,
    required this.name,
    required this.endpoint,
    required this.status,
    this.lastTestedAt,
    this.lastError,
  });

  final String id;
  final String name;
  final String endpoint;
  final String status;
  final DateTime? lastTestedAt;
  final String? lastError;
}

/// Integration run.
class IntegrationRun {
  const IntegrationRun({
    required this.id,
    required this.connectionId,
    required this.status,
    required this.startedAt,
    required this.phase,
    this.processed,
    this.errorCount,
    this.total,
    this.error,
    this.endedAt,
  });

  final String id;
  final String connectionId;
  final String status;
  final String phase;
  final DateTime startedAt;
  final int? processed;
  final int? errorCount;
  final int? total;
  final String? error;
  final DateTime? endedAt;
}

/// Reconciliation run.
class ReconciliationRun {
  const ReconciliationRun({
    required this.id,
    required this.status,
    required this.scope,
    required this.startedAt,
    this.exceptions = const [],
    this.exceptionCount = 0,
    this.openExceptionCount = 0,
    this.autoFixed = false,
  });

  factory ReconciliationRun.fromJson(Map<String, dynamic> json) {
    return ReconciliationRun(
      id: json['id'] as String,
      status: json['status'] as String,
      scope: json['scope'] as String? ?? 'cash',
      startedAt: DateTime.parse(json['startedAt'] as String),
      exceptions: (json['exceptions'] as List? ?? const [])
          .cast<String>()
          .toList(),
      exceptionCount: json['exception_count'] as int? ?? 0,
      openExceptionCount: json['open_exception_count'] as int? ?? 0,
      autoFixed: json['auto_fixed'] as bool? ?? false,
    );
  }

  final String id;
  final String status;
  final String scope;
  final DateTime startedAt;
  final List<String> exceptions;
  final int exceptionCount;
  final int openExceptionCount;
  final bool autoFixed;
}

/// Kết quả thẩm định rủi ro Maker-Checker AI Copilot.
class AiRiskAssessment {
  const AiRiskAssessment({
    required this.requestId,
    required this.riskLevel,
    required this.riskScore,
    required this.summary,
    this.flaggedRules = const [],
    this.recommendations = const [],
    required this.auditStamp,
    this.assessmentSource = 'unknown',
  });

  final String requestId;
  final String riskLevel; // 'low' | 'medium' | 'high'
  final int riskScore; // 0 - 100
  final String summary;
  final List<String> flaggedRules;
  final List<String> recommendations;
  final String auditStamp;
  final String assessmentSource;

  bool get isHighRisk => riskLevel == 'high' || riskScore >= 70;
  bool get isMediumRisk => riskLevel == 'medium';
  bool get isLowRisk => riskLevel == 'low';

  factory AiRiskAssessment.fromJson(Map<String, dynamic> json) {
    return AiRiskAssessment(
      requestId: json['request_id'] as String? ?? '',
      riskLevel: (json['risk_level'] as String? ?? 'low').toLowerCase(),
      riskScore: (json['risk_score'] as num?)?.toInt() ?? 20,
      summary: json['summary'] as String? ?? '',
      flaggedRules:
          (json['flagged_rules'] as List?)?.map((e) => e.toString()).toList() ??
              const [],
      recommendations: (json['recommendations'] as List?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      auditStamp: json['audit_stamp'] as String? ?? '',
      assessmentSource: json['assessment_source'] as String? ?? 'unknown',
    );
  }
}

/// Cửa hàng / điểm vận hành.
class BranchDto {
  const BranchDto({
    required this.id,
    required this.code,
    required this.name,
    this.address,
    this.active = true,
  });

  final String id;
  final String code;
  final String name;
  final String? address;
  final bool active;

  factory BranchDto.fromJson(Map<String, dynamic> json) {
    return BranchDto(
      id: json['id'] as String? ?? '',
      code: json['code'] as String? ?? '',
      name: json['name'] as String? ?? '',
      address: json['address'] as String?,
      active: json['active'] as bool? ?? true,
    );
  }
}

/// Vai trò và danh sách capability tương ứng.
class RoleDto {
  const RoleDto({
    required this.code,
    required this.name,
    this.description,
    this.capabilities = const [],
  });

  final String code;
  final String name;
  final String? description;
  final List<String> capabilities;

  factory RoleDto.fromJson(Map<String, dynamic> json) {
    return RoleDto(
      code: json['code'] as String? ?? '',
      name: json['name'] as String? ?? '',
      description: json['description'] as String?,
      capabilities:
          (json['capabilities'] as List?)?.map((e) => e.toString()).toList() ??
              const [],
    );
  }
}

/// Phạm vi dữ liệu cấp phát cho nhân viên (Scope Grant).
class ScopeGrantDto {
  const ScopeGrantDto({
    required this.id,
    required this.userId,
    this.branchId,
    this.branchName,
    this.locationId,
    this.locationName,
    this.capability,
    this.validFrom,
    this.validTo,
  });

  final String id;
  final String userId;
  final String? branchId;
  final String? branchName;
  final String? locationId;
  final String? locationName;
  final String? capability;
  final DateTime? validFrom;
  final DateTime? validTo;

  factory ScopeGrantDto.fromJson(Map<String, dynamic> json) {
    return ScopeGrantDto(
      id: json['id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      branchId: json['branch_id'] as String?,
      branchName: json['branch_name'] as String?,
      locationId: json['location_id'] as String?,
      locationName: json['location_name'] as String?,
      capability: json['capability'] as String?,
      validFrom: json['valid_from'] != null
          ? DateTime.tryParse(json['valid_from'].toString())
          : null,
      validTo: json['valid_to'] != null
          ? DateTime.tryParse(json['valid_to'].toString())
          : null,
    );
  }
}

/// Nhân viên cửa hàng được quản trị bởi Quản lý.
class EmployeeUserDto {
  const EmployeeUserDto({
    required this.id,
    required this.username,
    required this.displayName,
    this.email,
    this.phoneNumber,
    required this.status,
    this.branchId,
    this.branchName,
    this.roles = const [],
    this.capabilities = const [],
    this.mustChangePassword = false,
    this.hasPendingInvite = false,
    this.inviteExpiresAt,
    this.authVersion = 1,
    this.scopes = const [],
    this.lastInviteLink,
    this.lastInviteToken,
    this.lastInviteEmailSent,
    this.lastEmailDeliveryMessage,
    this.lastTemporaryPassword,
  });

  final String id;
  final String username;
  final String displayName;
  final String? email;
  final String? phoneNumber;
  final String status;
  final String? branchId;
  final String? branchName;
  final List<String> roles;
  final List<String> capabilities;
  final bool mustChangePassword;
  final bool hasPendingInvite;
  final DateTime? inviteExpiresAt;
  final int authVersion;
  final List<ScopeGrantDto> scopes;
  final String? lastInviteLink;
  final String? lastInviteToken;
  final bool? lastInviteEmailSent;
  final String? lastEmailDeliveryMessage;
  final String? lastTemporaryPassword;

  bool get isActive => status == 'active';
  bool get isLocked => status == 'locked';

  factory EmployeeUserDto.fromJson(Map<String, dynamic> json) {
    return EmployeeUserDto(
      id: json['id'] as String? ?? '',
      username: json['username'] as String? ?? '',
      displayName: (json['display_name'] ?? json['username'] ?? '') as String,
      email: json['email'] as String?,
      phoneNumber: json['phone_number'] as String?,
      status: json['status'] as String? ?? 'active',
      branchId: json['branch_id'] as String?,
      branchName: json['branch_name'] as String?,
      roles: (json['roles'] as List?)?.map((e) => e.toString()).toList() ??
          const [],
      capabilities:
          (json['capabilities'] as List?)?.map((e) => e.toString()).toList() ??
              const [],
      mustChangePassword: json['must_change_password'] as bool? ?? false,
      hasPendingInvite: json['has_pending_invite'] as bool? ?? false,
      inviteExpiresAt: json['invite_expires_at'] != null
          ? DateTime.tryParse(json['invite_expires_at'].toString())
          : null,
      authVersion: (json['auth_version'] as num?)?.toInt() ?? 1,
      scopes: (json['scopes'] as List?)
              ?.map((e) => ScopeGrantDto.fromJson(e as Map<String, dynamic>))
              .toList() ??
          const [],
      lastInviteLink: json['last_invite_link'] as String? ?? json['invite_link'] as String?,
      lastInviteToken: json['last_invite_token'] as String? ?? json['invite_token'] as String?,
      lastInviteEmailSent: json['last_invite_email_sent'] as bool? ?? json['invite_email_sent'] as bool?,
      lastEmailDeliveryMessage: json['last_email_delivery_message'] as String? ?? json['email_delivery_message'] as String?,
      lastTemporaryPassword: json['last_temporary_password'] as String? ?? json['temporary_password'] as String?,
    );
  }
}

/// ETL Connection.
class EtlConnectionDto {
  const EtlConnectionDto({
    required this.id,
    required this.name,
    required this.type,
    required this.status,
    this.secretRef,
    this.allowlistSheets = const [],
    this.configJson = const {},
    this.branchId,
    this.createdAt,
  });

  final String id;
  final String name;
  final String type;
  final String status;
  final String? secretRef;
  final List<String> allowlistSheets;
  final Map<String, dynamic> configJson;
  final String? branchId;
  final DateTime? createdAt;

  factory EtlConnectionDto.fromJson(Map<String, dynamic> json) {
    return EtlConnectionDto(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      type: json['type'] as String? ?? 'csv',
      status: json['status'] as String? ?? 'active',
      secretRef: json['secret_ref'] as String?,
      allowlistSheets: (json['allowlist_sheets'] as List?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      configJson: (json['config_json'] as Map<String, dynamic>?) ?? const {},
      branchId: json['branch_id'] as String?,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'].toString())
          : null,
    );
  }
}

/// ETL Pipeline.
class EtlPipelineDto {
  const EtlPipelineDto({
    required this.id,
    required this.name,
    required this.target,
    required this.connectionId,
    this.branchId,
    this.locationId,
    this.destinationLocationId,
    this.scheduleCron,
    required this.status,
    this.configJson = const {},
    this.createdAt,
  });

  final String id;
  final String name;
  final String target;
  final String connectionId;
  final String? branchId;
  final String? locationId;
  final String? destinationLocationId;
  final String? scheduleCron;
  final String status;
  final Map<String, dynamic> configJson;
  final DateTime? createdAt;

  factory EtlPipelineDto.fromJson(Map<String, dynamic> json) {
    return EtlPipelineDto(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? '',
      target: json['target'] as String? ?? 'catalog_upsert',
      connectionId: json['connection_id'] as String? ?? '',
      branchId: json['branch_id'] as String?,
      locationId: json['location_id'] as String?,
      destinationLocationId: json['destination_location_id'] as String?,
      scheduleCron: json['schedule_cron'] as String?,
      status: json['status'] as String? ?? 'active',
      configJson: (json['config_json'] as Map<String, dynamic>?) ?? const {},
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'].toString())
          : null,
    );
  }
}

/// ETL Mapping Version.
class EtlMappingVersionDto {
  const EtlMappingVersionDto({
    required this.id,
    required this.pipelineId,
    required this.version,
    required this.status,
    required this.mappingJson,
    this.validationRulesJson = const {},
    required this.duplicatePolicy,
    this.publishedAt,
    this.createdAt,
  });

  final String id;
  final String pipelineId;
  final int version;
  final String status;
  final List<dynamic> mappingJson;
  final Map<String, dynamic> validationRulesJson;
  final String duplicatePolicy;
  final DateTime? publishedAt;
  final DateTime? createdAt;

  factory EtlMappingVersionDto.fromJson(Map<String, dynamic> json) {
    return EtlMappingVersionDto(
      id: json['id'] as String? ?? '',
      pipelineId: json['pipeline_id'] as String? ?? '',
      version: (json['version'] as num?)?.toInt() ?? 1,
      status: json['status'] as String? ?? 'draft',
      mappingJson: (json['mapping_json'] as List?) ?? const [],
      validationRulesJson:
          (json['validation_rules_json'] as Map<String, dynamic>?) ?? const {},
      duplicatePolicy: json['duplicate_policy'] as String? ?? 'reject',
      publishedAt: json['published_at'] != null
          ? DateTime.tryParse(json['published_at'].toString())
          : null,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'].toString())
          : null,
    );
  }
}

/// ETL Run.
class EtlRunDto {
  const EtlRunDto({
    required this.id,
    required this.pipelineId,
    this.mappingVersionId,
    required this.mappingVersionNum,
    required this.runnerId,
    required this.status,
    required this.progressPct,
    required this.totalRows,
    required this.validRows,
    required this.invalidRows,
    required this.sourceFingerprint,
    this.singleAdminOverride = false,
    this.reviewerId,
    this.reviewDecision,
    this.reviewNote,
    this.postedAt,
    this.generatedReferenceType,
    this.generatedReferenceId,
    this.errorCode,
    this.errorMessage,
    this.createdAt,
  });

  final String id;
  final String pipelineId;
  final String? mappingVersionId;
  final int mappingVersionNum;
  final String runnerId;
  final String status;
  final int progressPct;
  final int totalRows;
  final int validRows;
  final int invalidRows;
  final String sourceFingerprint;
  final bool singleAdminOverride;
  final String? reviewerId;
  final String? reviewDecision;
  final String? reviewNote;
  final DateTime? postedAt;
  final String? generatedReferenceType;
  final String? generatedReferenceId;
  final String? errorCode;
  final String? errorMessage;
  final DateTime? createdAt;

  bool get isStaged => status == 'staged' || status == 'reviewing';
  bool get isPosted => status == 'posted';
  bool get isRejected => status == 'rejected';

  factory EtlRunDto.fromJson(Map<String, dynamic> json) {
    return EtlRunDto(
      id: json['id'] as String? ?? '',
      pipelineId: json['pipeline_id'] as String? ?? '',
      mappingVersionId: json['mapping_version_id'] as String?,
      mappingVersionNum: (json['mapping_version_num'] as num?)?.toInt() ?? 1,
      runnerId: json['runner_id'] as String? ?? '',
      status: json['status'] as String? ?? 'staged',
      progressPct: (json['progress_pct'] as num?)?.toInt() ?? 0,
      totalRows: (json['total_rows'] as num?)?.toInt() ?? 0,
      validRows: (json['valid_rows'] as num?)?.toInt() ?? 0,
      invalidRows: (json['invalid_rows'] as num?)?.toInt() ?? 0,
      sourceFingerprint: json['source_fingerprint'] as String? ?? '',
      singleAdminOverride: json['single_admin_override'] as bool? ?? false,
      reviewerId: json['reviewer_id'] as String?,
      reviewDecision: json['review_decision'] as String?,
      reviewNote: json['review_note'] as String?,
      postedAt: json['posted_at'] != null
          ? DateTime.tryParse(json['posted_at'].toString())
          : null,
      generatedReferenceType: json['generated_reference_type'] as String?,
      generatedReferenceId: json['generated_reference_id'] as String?,
      errorCode: json['error_code'] as String?,
      errorMessage: json['error_message'] as String?,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'].toString())
          : null,
    );
  }
}

/// ETL Run Row.
class EtlRunRowDto {
  const EtlRunRowDto({
    required this.id,
    required this.runId,
    required this.rowNumber,
    this.sourceRowKey,
    required this.rawDataJson,
    this.canonicalDataJson,
    required this.valid,
    this.errorsJson = const [],
    this.actionPreview = const {},
  });

  final String id;
  final String runId;
  final int rowNumber;
  final String? sourceRowKey;
  final Map<String, dynamic> rawDataJson;
  final Map<String, dynamic>? canonicalDataJson;
  final bool valid;
  final List<String> errorsJson;
  final Map<String, dynamic> actionPreview;

  factory EtlRunRowDto.fromJson(Map<String, dynamic> json) {
    return EtlRunRowDto(
      id: json['id'] as String? ?? '',
      runId: json['run_id'] as String? ?? '',
      rowNumber: (json['row_number'] as num?)?.toInt() ?? 0,
      sourceRowKey: json['source_row_key'] as String?,
      rawDataJson: (json['raw_data_json'] as Map<String, dynamic>?) ?? const {},
      canonicalDataJson: json['canonical_data_json'] as Map<String, dynamic>?,
      valid: json['valid'] as bool? ?? true,
      errorsJson:
          (json['errors_json'] as List?)?.map((e) => e.toString()).toList() ??
              const [],
      actionPreview:
          (json['action_preview'] as Map<String, dynamic>?) ?? const {},
    );
  }
}

/// Cảnh báo cận date (SRS §3.4).
class ExpiryAlertItem {
  const ExpiryAlertItem({
    required this.itemId,
    required this.sku,
    required this.itemName,
    required this.unit,
    this.lotNo,
    required this.expiryDate,
    required this.daysLeft,
    required this.quantity,
    required this.severity,
    required this.message,
  });

  final String itemId;
  final String sku;
  final String itemName;
  final String unit;
  final String? lotNo;
  final String expiryDate;
  final int daysLeft;
  final String quantity;
  final String severity; // 'critical' | 'warning' | 'watch'
  final String message;

  factory ExpiryAlertItem.fromJson(Map<String, dynamic> json) {
    return ExpiryAlertItem(
      itemId: json['item_id'] as String? ?? '',
      sku: json['sku'] as String? ?? '',
      itemName: json['item_name'] as String? ?? '',
      unit: json['unit'] as String? ?? '',
      lotNo: json['lot_no'] as String?,
      expiryDate: json['expiry_date'] as String? ?? '',
      daysLeft: (json['days_left'] as num?)?.toInt() ?? 0,
      quantity: json['quantity']?.toString() ?? '0',
      severity: json['severity'] as String? ?? 'warning',
      message: json['message'] as String? ?? '',
    );
  }
}

/// Top nguyên liệu tiêu hao (SRS §3.5).
class ConsumptionTopItem {
  const ConsumptionTopItem({
    required this.itemId,
    required this.sku,
    required this.name,
    this.unit,
    this.category,
    required this.usedQty,
  });

  final String itemId;
  final String sku;
  final String name;
  final String? unit;
  final String? category;
  final String usedQty;

  double get usedQtyNumber => double.tryParse(usedQty) ?? 0.0;

  factory ConsumptionTopItem.fromJson(Map<String, dynamic> json) {
    return ConsumptionTopItem(
      itemId: json['item_id'] as String? ?? '',
      sku: json['sku'] as String? ?? '',
      name: json['name'] as String? ?? '',
      unit: json['unit'] as String?,
      category: json['category'] as String?,
      usedQty: json['used_qty']?.toString() ?? '0',
    );
  }
}

/// Lịch sử chốt ca (SRS §3.5).
class ShiftHistoryItem {
  const ShiftHistoryItem({
    required this.id,
    this.businessDate,
    this.shiftCode,
    required this.locationId,
    required this.status,
    required this.maker,
    required this.lineCount,
    required this.varianceLines,
    required this.totalAbsVariance,
    this.completedAt,
  });

  final String id;
  final String? businessDate;
  final String? shiftCode;
  final String locationId;
  final String status;
  final String maker;
  final int lineCount;
  final int varianceLines;
  final String totalAbsVariance;
  final String? completedAt;

  String get shiftName {
    switch (shiftCode) {
      case 'morning':
        return 'Ca Sáng (07:30 - 15:00)';
      case 'afternoon':
        return 'Ca Chiều (15:00 - 23:00)';
      case 'split':
        return 'Ca Lỡ (07:30 - 18:00)';
      default:
        return 'Kiểm kê thường';
    }
  }

  factory ShiftHistoryItem.fromJson(Map<String, dynamic> json) {
    return ShiftHistoryItem(
      id: json['id'] as String? ?? '',
      businessDate: json['business_date'] as String?,
      shiftCode: json['shift_code'] as String?,
      locationId: json['location_id'] as String? ?? '',
      status: json['status'] as String? ?? '',
      maker: json['maker'] as String? ?? '',
      lineCount: (json['line_count'] as num?)?.toInt() ?? 0,
      varianceLines: (json['variance_lines'] as num?)?.toInt() ?? 0,
      totalAbsVariance: json['total_abs_variance']?.toString() ?? '0',
      completedAt: json['completed_at'] as String?,
    );
  }
}

/// DTO tổng hợp toàn bộ 10 thành phần Dashboard chỉ trong 1 round-trip.
class DashboardSummaryDto {
  const DashboardSummaryDto({
    required this.locations,
    required this.items,
    required this.balances,
    required this.assets,
    required this.stockRequests,
    required this.inbox,
    required this.cashBalances,
    required this.cashboxes,
    required this.lowStockAlerts,
    required this.reconciliations,
  });

  final List<InventoryLocation> locations;
  final List<InventoryItem> items;
  final List<StockBalance> balances;
  final List<AssetRecord> assets;
  final List<StockRequest> stockRequests;
  final List<ApprovalItem> inbox;
  final List<CashBalance> cashBalances;
  final List<Cashbox> cashboxes;
  final List<LowStockAlertItem> lowStockAlerts;
  final List<ReconciliationRun> reconciliations;
}


