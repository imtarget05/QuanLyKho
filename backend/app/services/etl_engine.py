"""ETL Processing Engine (Phase 2).

Provides:
  - Multi-format ingestion: CSV, JSON, XLSX, Google Sheets
  - Deterministic fingerprinting for idempotency
  - Flexible mapping, transformations, and duplicate handling
  - Row-level validation and detailed action preview (before/after/diff)
  - Non-destructive staging: human review required before posting
  - Transactional posting: never raw UPDATE balance, always via Movements and Requests
  - Single-admin self-approval with explicit auditability for balance adjustments
"""

import csv
import hashlib
import io
import json
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.models.activity import AuditEvent, OutboxEvent
from app.models.etl import EtlMappingVersion, EtlPipeline, EtlRun, EtlRunRow
from app.models.iam import Capability, RoleCapability, User, UserRole
from app.models.inventory import (
    Balance,
    InventoryRequest,
    InventoryRequestLine,
    Item,
    Movement,
)

# Capability review bắt buộc cho đường điều chỉnh tồn kho "single-admin".
_CAP_REVIEW = "etl:review"

_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_ROWS = 20_000
_ZERO = Decimal("0")
# Độ chính xác làm việc cho số lượng: 6 chữ số thập phân (lớn hơn độ chính xác
# lưu trữ của DB là Numeric(20,3)) — đủ để float không làm lệch số.
_QTY_SCALE = Decimal("0.000001")


def _to_decimal(value: Any) -> Decimal:
    """Chuyển giá trị sang Decimal mà KHÔNG đi qua float (R10).

    - Decimal -> giữ nguyên.
    - int -> Decimal(int).
    - float -> Decimal(repr(float)): `repr` cho dạng ngắn nhất khớp lại chính
      xác với float, nên 0.1 -> Decimal('0.1') (không phải 0.1000000000000000055).
    - str -> Decimal(str) (lỗi -> ValueError/ArithmeticError cho caller xử lý).

    Lý do: 0.3 - 0.1 bằng float ra 0.19999999999999998, tức phiếu điều chỉnh
    tồn bị lệch số so với giá trị người dùng nhập.
    """
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, bool):
        raise TypeError("bool không phải số lượng hợp lệ")
    elif isinstance(value, int):
        dec = Decimal(value)
    elif isinstance(value, float):
        dec = Decimal(repr(value))
    else:
        dec = Decimal(str(value).strip())
    return dec.quantize(_QTY_SCALE, rounding=ROUND_HALF_UP)


def utc_now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------
# 1. Ingestion Parsers
# --------------------------------------------------------------------------


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    if len(content) > _MAX_BYTES:
        raise AppError(422, "IMPORT_TOO_LARGE", f"File vượt quá giới hạn {_MAX_BYTES} bytes")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin1")
        except Exception as e:
            raise AppError(422, "IMPORT_ENCODING_ERROR", f"Không giải mã được định dạng file: {e}") from None

    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise AppError(422, "IMPORT_PARSE_ERROR", "CSV thiếu dòng tiêu đề (header)")
        rows = [dict(r) for r in reader]
    except AppError:
        raise
    except Exception as e:
        raise AppError(422, "IMPORT_PARSE_ERROR", f"Lỗi đọc định dạng CSV: {e}") from None

    if len(rows) > _MAX_ROWS:
        raise AppError(422, "IMPORT_TOO_LARGE", f"Số dòng ({len(rows)}) vượt quá giới hạn tối đa {_MAX_ROWS}")
    return rows


def parse_json(content: bytes) -> list[dict[str, Any]]:
    if len(content) > _MAX_BYTES:
        raise AppError(422, "IMPORT_TOO_LARGE", f"File vượt quá giới hạn {_MAX_BYTES} bytes")
    try:
        data = json.loads(content.decode("utf-8-sig"))
    except Exception as e:
        raise AppError(422, "IMPORT_PARSE_ERROR", f"JSON không hợp lệ: {e}") from None

    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        if "rows" in data and isinstance(data["rows"], list):
            rows = data["rows"]
        elif "data" in data and isinstance(data["data"], list):
            rows = data["data"]
        else:
            rows = [data]
    else:
        raise AppError(422, "IMPORT_PARSE_ERROR", "JSON phải chứa danh sách đối tượng dòng")

    if not all(isinstance(r, dict) for r in rows):
        raise AppError(422, "IMPORT_PARSE_ERROR", "Mọi dòng trong JSON phải là đối tượng dictionary")

    if len(rows) > _MAX_ROWS:
        raise AppError(422, "IMPORT_TOO_LARGE", f"Số dòng ({len(rows)}) vượt quá giới hạn tối đa {_MAX_ROWS}")
    return rows


def parse_xlsx(content: bytes) -> list[dict[str, Any]]:
    if len(content) > _MAX_BYTES:
        raise AppError(422, "IMPORT_TOO_LARGE", f"File vượt quá giới hạn {_MAX_BYTES} bytes")
    try:
        bio = io.BytesIO(content)
        with zipfile.ZipFile(bio, "r") as zf:
            # 1. Read shared strings
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                sst_xml = zf.read("xl/sharedStrings.xml")
                root = ET.fromstring(sst_xml)
                ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for si in root.findall(".//ns:si", ns) or root.findall(".//si"):
                    text_parts = [t.text or "" for t in (si.findall(".//ns:t", ns) or si.findall(".//t"))]
                    shared_strings.append("".join(text_parts))

            # 2. Find first worksheet
            sheet_files = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
            if not sheet_files:
                raise AppError(422, "IMPORT_PARSE_ERROR", "XLSX không có trang tính nào")
            sheet_files.sort()
            sheet_xml = zf.read(sheet_files[0])
            sheet_root = ET.fromstring(sheet_xml)

            # 3. Parse rows and cells
            # Namespace handling
            ns_url = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            rows_data: list[list[str]] = []
            row_nodes = sheet_root.findall(f".//{{{ns_url}}}row") or sheet_root.findall(".//row")

            for r_node in row_nodes:
                row_cells: list[str] = []
                c_nodes = r_node.findall(f"{{{ns_url}}}c") or r_node.findall("c")
                for c in c_nodes:
                    cell_type = c.get("t", "")
                    val_node = c.find(f"{{{ns_url}}}v") if c.find(f"{{{ns_url}}}v") is not None else c.find("v")
                    val_text = val_node.text if val_node is not None else ""
                    if cell_type == "s" and val_text.isdigit():
                        idx = int(val_text)
                        val = shared_strings[idx] if idx < len(shared_strings) else ""
                    elif cell_type == "inlineStr":
                        t_node = c.find(f".//{{{ns_url}}}t") or c.find(".//t")
                        val = t_node.text if t_node is not None else ""
                    else:
                        val = val_text or ""
                    row_cells.append(val.strip())
                if any(row_cells):
                    rows_data.append(row_cells)

            if not rows_data:
                raise AppError(422, "IMPORT_PARSE_ERROR", "Trang tính XLSX trống rỗng")

            headers = [h or f"col_{idx+1}" for idx, h in enumerate(rows_data[0])]
            result: list[dict[str, Any]] = []
            for r_idx in range(1, len(rows_data)):
                row_vals = rows_data[r_idx]
                row_dict = {}
                for c_idx, h in enumerate(headers):
                    val = row_vals[c_idx] if c_idx < len(row_vals) else ""
                    row_dict[h] = val
                result.append(row_dict)

            if len(result) > _MAX_ROWS:
                raise AppError(422, "IMPORT_TOO_LARGE", f"Số dòng ({len(result)}) vượt quá {_MAX_ROWS}")
            return result
    except AppError:
        raise
    except Exception as e:
        raise AppError(422, "IMPORT_PARSE_ERROR", f"Không thể giải mã file XLSX: {e}") from None


def parse_raw_source(content: bytes, source_type: str) -> list[dict[str, Any]]:
    st = source_type.lower()
    if st in ("csv", "text/csv"):
        return parse_csv(content)
    elif st in ("json", "application/json"):
        return parse_json(content)
    elif st in ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
        return parse_xlsx(content)
    elif st in ("google_sheets", "sheets"):
        # If content is already JSON rows from Sheets API
        try:
            return parse_json(content)
        except Exception:
            return parse_csv(content)
    else:
        # Fallback detection
        if content.startswith(b"PK\x03\x04"):
            return parse_xlsx(content)
        stripped = content.strip()
        if stripped.startswith(b"[") or stripped.startswith(b"{"):
            return parse_json(content)
        return parse_csv(content)


def compute_fingerprint(rows: list[dict[str, Any]]) -> str:
    canonical = json.dumps(rows, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 2. Field Transformations & Canonicalization
# --------------------------------------------------------------------------


def apply_transform(val: Any, transform_name: str | None) -> Any:
    if val is None:
        return None
    s = str(val)
    if not transform_name:
        return s.strip()
    t = transform_name.lower().strip()
    if t == "trim":
        return s.strip()
    elif t == "trim_upper":
        return s.strip().upper()
    elif t == "trim_lower":
        return s.strip().lower()
    elif t in ("int", "to_int"):
        try:
            cleaned = s.replace(",", "").replace(".", "").strip()
            return int(cleaned) if cleaned else None
        except Exception:
            return None
    elif t in ("float", "to_float"):
        try:
            cleaned = s.replace(",", "").strip()
            return float(cleaned) if cleaned else None
        except Exception:
            return None
    elif t in ("decimal", "to_decimal"):
        try:
            cleaned = s.replace(",", "").strip()
            return str(Decimal(cleaned)) if cleaned else None
        except Exception:
            return None
    elif t in ("bool", "to_bool"):
        lower = s.lower().strip()
        return lower in ("true", "1", "yes", "co", "có", "y", "đúng", "dung")
    return s.strip()


def canonicalize_row(
    raw_row: dict[str, Any],
    mapping_rules: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Maps a raw source dictionary to canonical fields based on mapping rules.

    Mapping rule structure:
      {
        "source_field": "Mã sản phẩm",
        "target_field": "sku",
        "required": true,
        "transform": "trim_upper",
        "default": null
      }
    """
    canonical: dict[str, Any] = {}
    errors: list[str] = []

    # Map raw fields with case-insensitive matching if exact not found
    raw_keys_lower = {k.strip().lower(): k for k in raw_row.keys()}

    for rule in mapping_rules:
        target = rule.get("target_field")
        if not target:
            continue
        src = rule.get("source_field")
        required = bool(rule.get("required", False))
        transform = rule.get("transform")
        default_val = rule.get("default")

        raw_val = None
        if src in raw_row:
            raw_val = raw_row[src]
        elif src and src.strip().lower() in raw_keys_lower:
            raw_val = raw_row[raw_keys_lower[src.strip().lower()]]
        elif target in raw_row:
            raw_val = raw_row[target]
        elif target.lower() in raw_keys_lower:
            raw_val = raw_row[raw_keys_lower[target.lower()]]

        if raw_val is None or str(raw_val).strip() == "":
            val = default_val
        else:
            val = apply_transform(raw_val, transform)

        if required and (val is None or str(val).strip() == ""):
            errors.append(f"Trường bắt buộc '{target}' (từ cột '{src}') không có dữ liệu")

        canonical[target] = val

    return canonical, errors


# --------------------------------------------------------------------------
# 3. Staging & Action Preview Generation
# --------------------------------------------------------------------------


async def generate_staging_run(
    db: AsyncSession,
    pipeline: EtlPipeline,
    mapping_version: EtlMappingVersion,
    raw_rows: list[dict[str, Any]],
    runner: User,
    external_event_id: str | None = None,
) -> tuple[EtlRun, list[EtlRunRow]]:
    """Validates raw data rows, runs duplicate checking, queries current state,

    generates action previews, and stores staged EtlRun and EtlRunRows.
    """
    fingerprint = compute_fingerprint(raw_rows)
    mapping_rules = mapping_version.mapping_json or []
    duplicate_policy = mapping_version.duplicate_policy or "reject"  # reject, skip, overwrite

    # 1. Preload Items for quick lookup
    item_rows = (await db.execute(select(Item))).scalars().all()
    item_by_sku = {i.sku.upper(): i for i in item_rows}

    # 2. Preload Balances if pipeline has a location_id
    balance_by_item_id: dict[uuid.UUID, Balance] = {}
    if pipeline.location_id:
        b_rows = (
            (await db.execute(select(Balance).where(Balance.location_id == pipeline.location_id))).scalars().all()
        )
        balance_by_item_id = {b.item_id: b for b in b_rows}

    # Preload destination balances if transfer
    dest_balance_by_item_id: dict[uuid.UUID, Balance] = {}
    if pipeline.destination_location_id:
        db_rows = (
            (await db.execute(select(Balance).where(Balance.location_id == pipeline.destination_location_id)))
            .scalars()
            .all()
        )
        dest_balance_by_item_id = {b.item_id: b for b in db_rows}

    run_id = uuid.uuid4()
    run = EtlRun(
        id=run_id,
        pipeline_id=pipeline.id,
        mapping_version_id=mapping_version.id,
        mapping_version_num=mapping_version.version,
        runner_id=runner.id,
        status="staged",
        progress_pct=100,
        total_rows=len(raw_rows),
        valid_rows=0,
        invalid_rows=0,
        source_fingerprint=fingerprint,
        external_event_id=external_event_id,
        single_admin_override=False,
    )
    db.add(run)

    seen_keys: set[str] = set()
    staged_rows: list[EtlRunRow] = []

    for idx, raw_row in enumerate(raw_rows, start=1):
        canonical, errors = canonicalize_row(raw_row, mapping_rules)
        business_key = str(canonical.get("sku") or canonical.get("code") or f"row_{idx}").strip().upper()

        # Duplicate detection within batch
        if business_key in seen_keys:
            if duplicate_policy == "reject":
                errors.append(f"Mã '{business_key}' bị trùng lặp trong tệp dữ liệu")
            elif duplicate_policy == "skip":
                # Mark as skipped or invalid
                errors.append(f"Mã '{business_key}' bị trùng lặp (chính sách bỏ qua)")
        else:
            seen_keys.add(business_key)

        action_preview: dict[str, Any] = {}

        # Target-specific domain validation & action preview computation
        target = pipeline.target

        if target == "catalog_upsert":
            sku = str(canonical.get("sku") or "").strip().upper()
            name = str(canonical.get("name") or "").strip()
            if not sku:
                errors.append("Thiếu SKU sản phẩm")
            if not name:
                errors.append("Thiếu tên sản phẩm")
            exists = sku in item_by_sku
            action_preview = {
                "action": "update" if exists else "create",
                "sku": sku,
                "name": name,
                "unit": canonical.get("unit") or "đơn vị",
            }

        elif target == "balance_adjustment_admin":
            sku = str(canonical.get("sku") or "").strip().upper()
            if not sku:
                errors.append("Thiếu SKU sản phẩm để điều chỉnh tồn")
            elif sku not in item_by_sku:
                errors.append(f"SKU '{sku}' không tồn tại trong danh mục hệ thống")
            else:
                item = item_by_sku[sku]
                current_bal = balance_by_item_id.get(item.id)
                current_qty = _to_decimal(current_bal.quantity) if current_bal else _ZERO

                target_qty = None
                delta = None

                if canonical.get("target_quantity") is not None:
                    try:
                        target_qty = _to_decimal(canonical["target_quantity"])
                        delta = target_qty - current_qty
                    except (ValueError, TypeError, ArithmeticError):
                        errors.append(f"Giá trị target_quantity không hợp lệ: {canonical.get('target_quantity')}")
                elif canonical.get("delta_quantity") is not None:
                    try:
                        delta = _to_decimal(canonical["delta_quantity"])
                        target_qty = current_qty + delta
                    except (ValueError, TypeError, ArithmeticError):
                        errors.append(f"Giá trị delta_quantity không hợp lệ: {canonical.get('delta_quantity')}")
                else:
                    errors.append("Cần cung cấp 'target_quantity' hoặc 'delta_quantity'")

                if target_qty is not None and target_qty < _ZERO:
                    errors.append(f"Tồn kho mục tiêu ({target_qty}) không thể âm")

                if delta is not None:
                    direction = "increase" if delta > 0 else ("decrease" if delta < 0 else "none")
                    action_preview = {
                        "action": "balance_adjustment",
                        "sku": sku,
                        "item_name": item.name,
                        "location_id": str(pipeline.location_id) if pipeline.location_id else None,
                        "current_quantity": float(current_qty),
                        "target_quantity": float(target_qty),
                        "delta_quantity": float(delta),
                        "direction": direction,
                        "reason": canonical.get("reason") or "Điều chỉnh tồn qua ETL Admin",
                    }

        elif target == "inventory_receipt":
            sku = str(canonical.get("sku") or "").strip().upper()
            if not sku:
                errors.append("Thiếu SKU")
            elif sku not in item_by_sku:
                errors.append(f"SKU '{sku}' không tồn tại trong danh mục")
            else:
                item = item_by_sku[sku]
                try:
                    qty = _to_decimal(canonical.get("quantity", 0))
                    if qty <= _ZERO:
                        errors.append("Số lượng nhập phải lớn hơn 0")
                except (ValueError, TypeError, ArithmeticError):
                    qty = _ZERO
                    errors.append("Số lượng không hợp lệ")

                current_bal = balance_by_item_id.get(item.id)
                current_qty = _to_decimal(current_bal.quantity) if current_bal else _ZERO
                action_preview = {
                    "action": "receipt",
                    "sku": sku,
                    "item_name": item.name,
                    "quantity": float(qty),
                    "current_quantity": float(current_qty),
                    "projected_quantity": float(current_qty + qty),
                }

        elif target == "inventory_issue":
            sku = str(canonical.get("sku") or "").strip().upper()
            if not sku:
                errors.append("Thiếu SKU")
            elif sku not in item_by_sku:
                errors.append(f"SKU '{sku}' không tồn tại trong danh mục")
            else:
                item = item_by_sku[sku]
                try:
                    qty = _to_decimal(canonical.get("quantity", 0))
                    if qty <= _ZERO:
                        errors.append("Số lượng xuất phải lớn hơn 0")
                except (ValueError, TypeError, ArithmeticError):
                    qty = _ZERO
                    errors.append("Số lượng không hợp lệ")

                current_bal = balance_by_item_id.get(item.id)
                current_qty = _to_decimal(current_bal.quantity) if current_bal else _ZERO
                avail_qty = _to_decimal(current_bal.available_quantity) if current_bal else _ZERO

                if qty > avail_qty:
                    errors.append(f"Không đủ tồn khả dụng (cần {qty}, tồn khả dụng {avail_qty})")

                action_preview = {
                    "action": "issue",
                    "sku": sku,
                    "item_name": item.name,
                    "quantity": float(qty),
                    "available_quantity": float(avail_qty),
                    "projected_quantity": float(max(_ZERO, current_qty - qty)),
                }

        elif target == "inventory_transfer":
            sku = str(canonical.get("sku") or "").strip().upper()
            if not sku:
                errors.append("Thiếu SKU")
            elif sku not in item_by_sku:
                errors.append(f"SKU '{sku}' không tồn tại")
            else:
                item = item_by_sku[sku]
                try:
                    qty = _to_decimal(canonical.get("quantity", 0))
                    if qty <= _ZERO:
                        errors.append("Số lượng điều chuyển phải lớn hơn 0")
                except (ValueError, TypeError, ArithmeticError):
                    qty = _ZERO
                    errors.append("Số lượng không hợp lệ")

                current_bal = balance_by_item_id.get(item.id)
                avail_qty = _to_decimal(current_bal.available_quantity) if current_bal else _ZERO
                if qty > avail_qty:
                    errors.append(f"Không đủ tồn khả dụng tại kho nguồn (cần {qty}, còn {avail_qty})")

                dest_bal = dest_balance_by_item_id.get(item.id)
                dest_qty = _to_decimal(dest_bal.quantity) if dest_bal else _ZERO
                current_qty = _to_decimal(current_bal.quantity) if current_bal else _ZERO

                action_preview = {
                    "action": "transfer",
                    "sku": sku,
                    "quantity": float(qty),
                    "source_location_id": str(pipeline.location_id) if pipeline.location_id else None,
                    "dest_location_id": str(pipeline.destination_location_id) if pipeline.destination_location_id else None,
                    "source_projected": float(max(_ZERO, current_qty - qty)),
                    "dest_projected": float(dest_qty + qty),
                }

        elif target == "stocktake":
            sku = str(canonical.get("sku") or "").strip().upper()
            if not sku:
                errors.append("Thiếu SKU")
            elif sku not in item_by_sku:
                errors.append(f"SKU '{sku}' không tồn tại")
            else:
                item = item_by_sku[sku]
                current_bal = balance_by_item_id.get(item.id)
                book_qty = _to_decimal(current_bal.quantity) if current_bal else _ZERO
                try:
                    counted_qty = _to_decimal(canonical.get("counted_quantity", 0))
                except (ValueError, TypeError, ArithmeticError):
                    counted_qty = _ZERO
                    errors.append("counted_quantity không hợp lệ")

                variance = counted_qty - book_qty
                action_preview = {
                    "action": "stocktake",
                    "sku": sku,
                    "item_name": item.name,
                    "book_quantity": float(book_qty),
                    "counted_quantity": float(counted_qty),
                    "variance": float(variance),
                    "direction": "increase" if variance > 0 else ("decrease" if variance < 0 else "none"),
                }

        is_valid = len(errors) == 0
        if is_valid:
            run.valid_rows += 1
        else:
            run.invalid_rows += 1

        row_entry = EtlRunRow(
            id=uuid.uuid4(),
            run_id=run.id,
            row_number=idx,
            source_row_key=business_key,
            raw_data_json=raw_row,
            canonical_data_json=canonical,
            valid=is_valid,
            errors_json=errors if errors else None,
            action_preview=action_preview,
        )
        db.add(row_entry)
        staged_rows.append(row_entry)

    await db.flush()
    return run, staged_rows


async def _actor_capabilities(db: AsyncSession, user_id: Any) -> set[str]:
    """Capability của user, đọc trực tiếp từ DB (không tin JWT cache)."""
    result = await db.execute(
        select(Capability.code)
        .join(RoleCapability, RoleCapability.capability_code == Capability.code)
        .join(UserRole, UserRole.role_code == RoleCapability.role_code)
        .where(UserRole.user_id == user_id)
    )
    return {row[0] for row in result.all()}


async def _create_pending_balance_adjustment(
    *,
    db: AsyncSession,
    run: EtlRun,
    pipeline: EtlPipeline,
    actor: User,
    valid_rows: list[EtlRunRow],
    item_by_sku: dict[str, Item],
    now: datetime,
) -> dict[str, Any]:
    """Override single-admin hợp lệ: tạo phiếu DRAFT chờ duyệt độc lập.

    Runner tự post phiếu của chính mình là vi phạm maker ≠ checker. Thay vì
    tự tạo phiếu `approved` (và tự bị chính mình là approver), phiếu được tạo ở
    trạng thái `draft`, KHÔNG ghi movement, KHÔNG đụng tồn — người duyệt độc lập
    sẽ submit/approve theo luồng kho bình thường. Override được ghi nhận rõ
    bằng audit event + outbox event.
    """
    req_id = uuid.uuid4()
    req = InventoryRequest(
        id=req_id,
        kind="adjustment",
        status="draft",
        maker_id=run.runner_id,
        approver_id=None,
        source_id=pipeline.location_id,
        dest_id=pipeline.location_id,
        reason=(
            f"ETL Run {run.id} - Điều chỉnh tồn bởi {actor.username} "
            "[Single-Admin Override - chờ duyệt độc lập]"
        ),
        version=1,
        created_by=run.runner_id,
        submitted_at=None,
    )
    db.add(req)
    await db.flush()

    lines_count = 0
    affected_items: set[uuid.UUID] = set()
    for r in valid_rows:
        preview = r.action_preview or {}
        sku = str(preview.get("sku") or "").upper()
        delta = Decimal(str(preview.get("delta_quantity", 0)))
        if delta == _ZERO:
            continue
        item = item_by_sku.get(sku)
        if not item:
            continue
        affected_items.add(item.id)
        db.add(
            InventoryRequestLine(
                id=uuid.uuid4(),
                request_id=req.id,
                item_id=item.id,
                quantity=abs(delta),
                direction="increase" if delta > 0 else "decrease",
            )
        )
        lines_count += 1

    # Ensure a balance row exists for the affected item/location even though no
    # movement is written yet (pending approval).  Balance rows otherwise only
    # appear after a posted receipt/issue; keep the same quantity (0 if absent).
    if pipeline.location_id is not None:
        for item_id in affected_items:
            existing = (
                await db.execute(
                    select(Balance).where(
                        Balance.location_id == pipeline.location_id,
                        Balance.item_id == item_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    Balance(
                        location_id=pipeline.location_id,
                        item_id=item_id,
                        quantity=Decimal("0"),
                        reserved_quantity=Decimal("0"),
                        version=1,
                    )
                )
        await db.flush()

    run.status = "pending_approval"
    run.reviewer_id = actor.id
    run.single_admin_override = True
    run.generated_reference_type = "inventory_request"
    run.generated_reference_id = str(req.id)

    audit = AuditEvent(
        id=uuid.uuid4(),
        action="etl.balance_adjustment.override_pending",
        actor_id=actor.id,
        subject=f"etl_run:{run.id}",
        metadata_json={
            "pipeline_id": str(pipeline.id),
            "request_id": str(req.id),
            "location_id": str(pipeline.location_id),
            "maker_id": str(run.runner_id),
            "actor_id": str(actor.id),
            "self_approval": True,
            "single_admin_override": True,
            "request_status": "draft",
            "lines_count": lines_count,
            "note": "Runner tự post: phiếu để ở draft chờ duyệt độc lập, chưa ghi movement.",
        },
        occurred_at=now,
    )
    db.add(audit)

    outbox = OutboxEvent(
        id=uuid.uuid4(),
        event_type="inventory.balance_adjustment.pending_approval",
        aggregate_id=str(run.id),
        payload_json={
            "run_id": str(run.id),
            "request_id": str(req.id),
            "location_id": str(pipeline.location_id),
            "single_admin_override": True,
        },
        created_at=now,
    )
    db.add(outbox)

    await db.commit()
    return {
        "status": "pending_approval",
        "run_id": str(run.id),
        "target": pipeline.target,
        "request_id": str(req.id),
        "request_status": "draft",
        "movements_count": 0,
        "single_admin_override": True,
    }


# --------------------------------------------------------------------------
# 4. Posting Execution (Transactional & Invariant Preserving)
# --------------------------------------------------------------------------


async def execute_etl_posting(
    db: AsyncSession,
    run: EtlRun,
    pipeline: EtlPipeline,
    actor: User,
    single_admin_override: bool = False,
) -> dict[str, Any]:
    """Posts a validated staging run into the canonical ledger or catalog.

    Invariants strictly enforced:
      1. Zero raw UPDATE to balance tables; all balance mutations create Movements.
      2. balance_adjustment_admin requires etl:post_balance capability.
      3. Full audit event and outbox event created for every posting.
      4. Idempotent: once posted, run cannot be posted again.
    """
    if run.status == "posted":
        raise AppError(409, "RUN_ALREADY_POSTED", f"ETL Run {run.id} đã được thực thi và hạch toán trước đó")

    if run.status == "pending_approval":
        raise AppError(
            409,
            "RUN_ALREADY_POSTED",
            f"ETL Run {run.id} đã tạo phiếu chờ duyệt; không thể post lại.",
        )

    if run.status in ("rejected", "cancelled", "failed"):
        raise AppError(409, "INVALID_RUN_STATE", f"Không thể post Run ở trạng thái {run.status}")

    # Load all valid rows
    row_stmt = select(EtlRunRow).where(EtlRunRow.run_id == run.id, EtlRunRow.valid.is_(True)).order_by(EtlRunRow.row_number)
    valid_rows = (await db.execute(row_stmt)).scalars().all()

    if not valid_rows:
        raise AppError(422, "NO_VALID_ROWS", "ETL Run không có dòng dữ liệu hợp lệ nào để hạch toán")

    now = utc_now()
    target = pipeline.target

    # Preload Items
    item_rows = (await db.execute(select(Item))).scalars().all()
    item_by_sku = {i.sku.upper(): i for i in item_rows}

    # 1. Target: Catalog Upsert
    if target == "catalog_upsert":
        created_count = 0
        updated_count = 0
        for r in valid_rows:
            canon = r.canonical_data_json or {}
            sku = str(canon.get("sku") or "").strip().upper()
            name = str(canon.get("name") or "").strip()
            unit = str(canon.get("unit") or "đơn vị").strip()
            tracked_serial = bool(canon.get("tracked_serial", False))

            if sku in item_by_sku:
                item = item_by_sku[sku]
                item.name = name
                item.unit = unit
                item.tracked_serial = tracked_serial
                updated_count += 1
            else:
                new_item = Item(
                    id=uuid.uuid4(),
                    sku=sku,
                    name=name,
                    unit=unit,
                    tracked_serial=tracked_serial,
                    active=True,
                )
                db.add(new_item)
                item_by_sku[sku] = new_item
                created_count += 1

        run.status = "posted"
        run.posted_at = now
        run.reviewer_id = actor.id
        run.generated_reference_type = "catalog_upsert"
        run.generated_reference_id = str(run.id)

        audit = AuditEvent(
            id=uuid.uuid4(),
            action="etl.catalog_upsert.posted",
            actor_id=actor.id,
            subject=f"etl_run:{run.id}",
            metadata_json={
                "pipeline_id": str(pipeline.id),
                "created_count": created_count,
                "updated_count": updated_count,
            },
            occurred_at=now,
        )
        db.add(audit)

        outbox = OutboxEvent(
            id=uuid.uuid4(),
            event_type="catalog.upsert",
            aggregate_id=str(run.id),
            payload_json={
                "run_id": str(run.id),
                "pipeline_id": str(pipeline.id),
                "created_count": created_count,
                "updated_count": updated_count,
            },
            created_at=now,
        )
        db.add(outbox)

        await db.commit()
        return {
            "status": "posted",
            "run_id": str(run.id),
            "target": target,
            "created_count": created_count,
            "updated_count": updated_count,
        }

    # For inventory-related targets, location_id is mandatory
    if not pipeline.location_id:
        raise AppError(422, "MISSING_LOCATION", f"Pipeline '{pipeline.name}' thiếu cấu hình location_id")

    # 2. Target: Balance Adjustment Admin (Single-admin override allowed with etl:post_balance)
    if target == "balance_adjustment_admin":
        # R11 — maker ≠ checker. Người chạy pipeline (runner) KHÔNG được tự
        # phê duyệt phiếu điều chỉnh tồn của chính mình.
        if str(run.runner_id) == str(actor.id):
            caps = await _actor_capabilities(db, actor.id)
            if _CAP_REVIEW not in caps:
                raise AppError(
                    403,
                    "MAKER_CHECKER_CONFLICT",
                    "Người chạy pipeline không được tự phê duyệt phiếu điều chỉnh tồn "
                    "của chính mình; cần một người duyệt độc lập có capability "
                    f"'{_CAP_REVIEW}'.",
                )
            return await _create_pending_balance_adjustment(
                db=db,
                run=run,
                pipeline=pipeline,
                actor=actor,
                valid_rows=valid_rows,
                item_by_sku=item_by_sku,
                now=now,
            )

        # Create canonical InventoryRequest for this adjustment
        req_id = uuid.uuid4()
        req = InventoryRequest(
            id=req_id,
            kind="adjustment",
            status="approved",
            maker_id=run.runner_id,
            approver_id=actor.id,
            source_id=pipeline.location_id,
            dest_id=pipeline.location_id,
            reason=f"ETL Run {run.id} - Điều chỉnh tồn bởi {actor.username}" + (" [Single-Admin Override]" if single_admin_override else ""),
            version=1,
            created_by=run.runner_id,
            submitted_at=now,
        )
        db.add(req)
        await db.flush()

        # Lock and load existing balances for this location
        b_stmt = select(Balance).where(Balance.location_id == pipeline.location_id).with_for_update()
        loc_balances = {b.item_id: b for b in (await db.execute(b_stmt)).scalars().all()}

        movements_count = 0
        for r in valid_rows:
            preview = r.action_preview or {}
            sku = str(preview.get("sku") or "").upper()
            delta = _to_decimal(preview.get("delta_quantity", 0))
            direction = "increase" if delta > 0 else "decrease"
            qty_abs = abs(delta)

            if delta == _ZERO:
                continue

            item = item_by_sku.get(sku)
            if not item:
                continue

            # Create request line
            line_id = uuid.uuid4()
            line = InventoryRequestLine(
                id=line_id,
                request_id=req.id,
                item_id=item.id,
                quantity=qty_abs,
                direction=direction,
            )
            db.add(line)

            # Create immutable Movement record
            mv = Movement(
                id=uuid.uuid4(),
                request_id=req.id,
                line_id=line_id,
                item_id=item.id,
                location_id=pipeline.location_id,
                quantity_signed=delta,
                posted_at=now,
            )
            db.add(mv)

            # Update Balance atomically
            bal = loc_balances.get(item.id)
            if bal is None:
                bal = Balance(
                    location_id=pipeline.location_id,
                    item_id=item.id,
                    quantity=_to_decimal(preview.get("target_quantity", 0)),
                    reserved_quantity=_ZERO,
                    version=1,
                )
                db.add(bal)
                loc_balances[item.id] = bal
            else:
                bal.quantity = Decimal(str(bal.quantity)) + delta
                bal.version += 1

            movements_count += 1

        run.status = "posted"
        run.posted_at = now
        run.reviewer_id = actor.id
        run.single_admin_override = single_admin_override
        run.generated_reference_type = "inventory_request"
        run.generated_reference_id = str(req.id)

        audit = AuditEvent(
            id=uuid.uuid4(),
            action="etl.balance_adjustment.posted",
            actor_id=actor.id,
            subject=f"etl_run:{run.id}",
            metadata_json={
                "pipeline_id": str(pipeline.id),
                "request_id": str(req.id),
                "location_id": str(pipeline.location_id),
                "movements_count": movements_count,
                "single_admin_override": single_admin_override,
            },
            occurred_at=now,
        )
        db.add(audit)

        outbox = OutboxEvent(
            id=uuid.uuid4(),
            event_type="inventory.balance_adjustment.posted",
            aggregate_id=str(run.id),
            payload_json={
                "run_id": str(run.id),
                "request_id": str(req.id),
                "location_id": str(pipeline.location_id),
                "movements_count": movements_count,
                "single_admin_override": single_admin_override,
            },
            created_at=now,
        )
        db.add(outbox)

        await db.commit()
        return {
            "status": "posted",
            "run_id": str(run.id),
            "target": target,
            "request_id": str(req.id),
            "movements_count": movements_count,
            "single_admin_override": single_admin_override,
        }

    # 3. Target: Inventory Receipt
    if target == "inventory_receipt":
        req_id = uuid.uuid4()
        req = InventoryRequest(
            id=req_id,
            kind="receipt",
            status="approved",
            maker_id=run.runner_id,
            approver_id=actor.id,
            dest_id=pipeline.location_id,
            reason=f"ETL Run {run.id} - Nhập kho qua ETL",
            version=1,
            created_by=run.runner_id,
            submitted_at=now,
        )
        db.add(req)
        await db.flush()

        b_stmt = select(Balance).where(Balance.location_id == pipeline.location_id).with_for_update()
        loc_balances = {b.item_id: b for b in (await db.execute(b_stmt)).scalars().all()}

        movements_count = 0
        for r in valid_rows:
            preview = r.action_preview or {}
            sku = str(preview.get("sku") or "").upper()
            qty = _to_decimal(preview.get("quantity", 0))
            if qty <= _ZERO:
                continue
            item = item_by_sku.get(sku)
            if not item:
                continue

            line_id = uuid.uuid4()
            line = InventoryRequestLine(
                id=line_id,
                request_id=req.id,
                item_id=item.id,
                quantity=qty,
                direction="increase",
            )
            db.add(line)

            mv = Movement(
                id=uuid.uuid4(),
                request_id=req.id,
                line_id=line_id,
                item_id=item.id,
                location_id=pipeline.location_id,
                quantity_signed=qty,
                posted_at=now,
            )
            db.add(mv)

            bal = loc_balances.get(item.id)
            if bal is None:
                bal = Balance(
                    location_id=pipeline.location_id,
                    item_id=item.id,
                    quantity=qty,
                    reserved_quantity=_ZERO,
                    version=1,
                )
                db.add(bal)
                loc_balances[item.id] = bal
            else:
                bal.quantity = Decimal(str(bal.quantity)) + qty
                bal.version += 1
            movements_count += 1

        run.status = "posted"
        run.posted_at = now
        run.reviewer_id = actor.id
        run.generated_reference_type = "inventory_request"
        run.generated_reference_id = str(req.id)

        audit = AuditEvent(
            id=uuid.uuid4(),
            action="etl.receipt.posted",
            actor_id=actor.id,
            subject=f"etl_run:{run.id}",
            metadata_json={"request_id": str(req.id), "movements_count": movements_count},
            occurred_at=now,
        )
        db.add(audit)
        outbox = OutboxEvent(
            id=uuid.uuid4(),
            event_type="inventory.receipt.posted",
            aggregate_id=str(run.id),
            payload_json={"run_id": str(run.id), "request_id": str(req.id)},
            created_at=now,
        )
        db.add(outbox)

        await db.commit()
        return {"status": "posted", "run_id": str(run.id), "request_id": str(req.id), "movements_count": movements_count}

    # 4. Target: Inventory Issue
    if target == "inventory_issue":
        req_id = uuid.uuid4()
        req = InventoryRequest(
            id=req_id,
            kind="issue",
            status="approved",
            maker_id=run.runner_id,
            approver_id=actor.id,
            source_id=pipeline.location_id,
            reason=f"ETL Run {run.id} - Xuất kho qua ETL",
            version=1,
            created_by=run.runner_id,
            submitted_at=now,
        )
        db.add(req)
        await db.flush()

        b_stmt = select(Balance).where(Balance.location_id == pipeline.location_id).with_for_update()
        loc_balances = {b.item_id: b for b in (await db.execute(b_stmt)).scalars().all()}

        movements_count = 0
        for r in valid_rows:
            preview = r.action_preview or {}
            sku = str(preview.get("sku") or "").upper()
            qty = _to_decimal(preview.get("quantity", 0))
            if qty <= _ZERO:
                continue
            item = item_by_sku.get(sku)
            if not item:
                continue

            bal = loc_balances.get(item.id)
            have = Decimal(str(bal.quantity)) if bal else _ZERO
            if have < qty:
                raise AppError(409, "INSUFFICIENT_STOCK", f"Không đủ tồn cho SKU '{sku}' (cần {qty}, còn {have})")

            line_id = uuid.uuid4()
            line = InventoryRequestLine(
                id=line_id,
                request_id=req.id,
                item_id=item.id,
                quantity=qty,
                direction="decrease",
            )
            db.add(line)

            mv = Movement(
                id=uuid.uuid4(),
                request_id=req.id,
                line_id=line_id,
                item_id=item.id,
                location_id=pipeline.location_id,
                quantity_signed=-qty,
                posted_at=now,
            )
            db.add(mv)
            bal.quantity = Decimal(str(bal.quantity)) - qty
            bal.version += 1
            movements_count += 1

        run.status = "posted"
        run.posted_at = now
        run.reviewer_id = actor.id
        run.generated_reference_type = "inventory_request"
        run.generated_reference_id = str(req.id)

        audit = AuditEvent(
            id=uuid.uuid4(),
            action="etl.issue.posted",
            actor_id=actor.id,
            subject=f"etl_run:{run.id}",
            metadata_json={"request_id": str(req.id), "movements_count": movements_count},
            occurred_at=now,
        )
        db.add(audit)
        outbox = OutboxEvent(
            id=uuid.uuid4(),
            event_type="inventory.issue.posted",
            aggregate_id=str(run.id),
            payload_json={"run_id": str(run.id), "request_id": str(req.id)},
            created_at=now,
        )
        db.add(outbox)

        await db.commit()
        return {"status": "posted", "run_id": str(run.id), "request_id": str(req.id), "movements_count": movements_count}

    # 5. Target: Inventory Transfer
    if target == "inventory_transfer":
        if not pipeline.destination_location_id:
            raise AppError(422, "MISSING_DESTINATION", "Pipeline điều chuyển yêu cầu cấu hình destination_location_id")

        req_id = uuid.uuid4()
        req = InventoryRequest(
            id=req_id,
            kind="transfer",
            status="approved",
            maker_id=run.runner_id,
            approver_id=actor.id,
            source_id=pipeline.location_id,
            dest_id=pipeline.destination_location_id,
            reason=f"ETL Run {run.id} - Điều chuyển kho qua ETL",
            version=1,
            created_by=run.runner_id,
            submitted_at=now,
        )
        db.add(req)
        await db.flush()

        src_balances = {
            b.item_id: b
            for b in (
                await db.execute(
                    select(Balance).where(Balance.location_id == pipeline.location_id).with_for_update()
                )
            ).scalars().all()
        }
        dest_balances = {
            b.item_id: b
            for b in (
                await db.execute(
                    select(Balance)
                    .where(Balance.location_id == pipeline.destination_location_id)
                    .with_for_update()
                )
            ).scalars().all()
        }

        movements_count = 0
        for r in valid_rows:
            preview = r.action_preview or {}
            sku = str(preview.get("sku") or "").upper()
            qty = _to_decimal(preview.get("quantity", 0))
            if qty <= _ZERO:
                continue
            item = item_by_sku.get(sku)
            if not item:
                continue

            src_bal = src_balances.get(item.id)
            have = Decimal(str(src_bal.quantity)) if src_bal else _ZERO
            if have < qty:
                raise AppError(409, "INSUFFICIENT_STOCK", f"Kho nguồn không đủ tồn cho SKU '{sku}'")

            line_id = uuid.uuid4()
            line = InventoryRequestLine(
                id=line_id,
                request_id=req.id,
                item_id=item.id,
                quantity=qty,
                direction="increase",
            )
            db.add(line)

            # Movement at source (negative)
            db.add(
                Movement(
                    id=uuid.uuid4(),
                    request_id=req.id,
                    line_id=line_id,
                    item_id=item.id,
                    location_id=pipeline.location_id,
                    quantity_signed=-qty,
                    posted_at=now,
                )
            )
            src_bal.quantity = Decimal(str(src_bal.quantity)) - qty
            src_bal.version += 1

            # Movement at destination (positive)
            db.add(
                Movement(
                    id=uuid.uuid4(),
                    request_id=req.id,
                    line_id=line_id,
                    item_id=item.id,
                    location_id=pipeline.destination_location_id,
                    quantity_signed=qty,
                    posted_at=now,
                )
            )
            dest_bal = dest_balances.get(item.id)
            if dest_bal is None:
                dest_bal = Balance(
                    location_id=pipeline.destination_location_id,
                    item_id=item.id,
                    quantity=qty,
                    reserved_quantity=_ZERO,
                    version=1,
                )
                db.add(dest_bal)
                dest_balances[item.id] = dest_bal
            else:
                dest_bal.quantity = Decimal(str(dest_bal.quantity)) + qty
                dest_bal.version += 1

            movements_count += 2

        run.status = "posted"
        run.posted_at = now
        run.reviewer_id = actor.id
        run.generated_reference_type = "inventory_request"
        run.generated_reference_id = str(req.id)

        audit = AuditEvent(
            id=uuid.uuid4(),
            action="etl.transfer.posted",
            actor_id=actor.id,
            subject=f"etl_run:{run.id}",
            metadata_json={"request_id": str(req.id), "movements_count": movements_count},
            occurred_at=now,
        )
        db.add(audit)
        outbox = OutboxEvent(
            id=uuid.uuid4(),
            event_type="inventory.transfer.posted",
            aggregate_id=str(run.id),
            payload_json={"run_id": str(run.id), "request_id": str(req.id)},
            created_at=now,
        )
        db.add(outbox)

        await db.commit()
        return {"status": "posted", "run_id": str(run.id), "request_id": str(req.id), "movements_count": movements_count}

    # 6. Target: Stocktake
    if target == "stocktake":
        # Create adjustment request from stocktake variance
        req_id = uuid.uuid4()
        req = InventoryRequest(
            id=req_id,
            kind="adjustment",
            status="approved",
            maker_id=run.runner_id,
            approver_id=actor.id,
            source_id=pipeline.location_id,
            dest_id=pipeline.location_id,
            reason=f"ETL Run {run.id} - Kiểm kê kho qua ETL",
            version=1,
            created_by=run.runner_id,
            submitted_at=now,
        )
        db.add(req)
        await db.flush()

        b_stmt = select(Balance).where(Balance.location_id == pipeline.location_id).with_for_update()
        loc_balances = {b.item_id: b for b in (await db.execute(b_stmt)).scalars().all()}

        movements_count = 0
        for r in valid_rows:
            preview = r.action_preview or {}
            sku = str(preview.get("sku") or "").upper()
            variance = Decimal(str(preview.get("variance", 0)))
            if variance == _ZERO:
                continue
            item = item_by_sku.get(sku)
            if not item:
                continue

            line_id = uuid.uuid4()
            line = InventoryRequestLine(
                id=line_id,
                request_id=req.id,
                item_id=item.id,
                quantity=abs(variance),
                direction="increase" if variance > 0 else "decrease",
            )
            db.add(line)

            mv = Movement(
                id=uuid.uuid4(),
                request_id=req.id,
                line_id=line_id,
                item_id=item.id,
                location_id=pipeline.location_id,
                quantity_signed=variance,
                posted_at=now,
            )
            db.add(mv)

            bal = loc_balances.get(item.id)
            if bal is None:
                bal = Balance(
                    location_id=pipeline.location_id,
                    item_id=item.id,
                    quantity=Decimal(str(preview.get("counted_quantity", 0))),
                    reserved_quantity=_ZERO,
                    version=1,
                )
                db.add(bal)
                loc_balances[item.id] = bal
            else:
                bal.quantity = Decimal(str(bal.quantity)) + variance
                bal.version += 1
            movements_count += 1

        run.status = "posted"
        run.posted_at = now
        run.reviewer_id = actor.id
        run.generated_reference_type = "inventory_request"
        run.generated_reference_id = str(req.id)

        audit = AuditEvent(
            id=uuid.uuid4(),
            action="etl.stocktake.posted",
            actor_id=actor.id,
            subject=f"etl_run:{run.id}",
            metadata_json={"request_id": str(req.id), "movements_count": movements_count},
            occurred_at=now,
        )
        db.add(audit)
        outbox = OutboxEvent(
            id=uuid.uuid4(),
            event_type="inventory.stocktake.posted",
            aggregate_id=str(run.id),
            payload_json={"run_id": str(run.id), "request_id": str(req.id)},
            created_at=now,
        )
        db.add(outbox)

        await db.commit()
        return {"status": "posted", "run_id": str(run.id), "request_id": str(req.id), "movements_count": movements_count}

    raise AppError(422, "UNSUPPORTED_TARGET", f"Mục tiêu ETL '{target}' chưa được hỗ trợ hạch toán")
