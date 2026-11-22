# Implementation Plan - B2 Authorization Scope Bypass Fixes

**Date:** 2026-11 (implemented)
**Project:** QuanLyKho (backend)
**Scope:** `reports.py` (GET /inventory-daily, /inventory-summary) và `reconciliations.py` (POST /reconciliations, GET /dashboard/summary)
**Pattern ngân hàng:** Authorization scope enforcement, negative-path testing, financial data access control.

---

## 1. Bối cảnh bài toán

Dự án `QuanLyKho` phải đáp ứng **MITM/Invariant 2**: tính toàn vẹn và bảo mật dữ liệu tài chính, mỗi người dùng chỉ được nhìn thấy dữ liệu của phân nhánh/location/account mà họ được phép truy cập.

**Cụm lỗi (B2)**: Một số endpoint GET/POST trong `reports.py` và `reconciliations.py` dùng `location_id` / `cashbox_id` từ request để lọc kết quả, nhưng:
- Chúng được sử dụng để **MỞ RỘNG** phạm vi (whitelisting), không phải **RÀNG BUỘC RÀNG GIỚI HẠN** (blacklisting).
- Một user giả mạo/bị tấn công có thể truyền `?location_id=<branch-B>` và nhìn thấy dữ liệu của nhánh B.
- Trong `reconciliations.py`, đoạn code đang truy vấn toàn bộ `CashJournal` trước khi lọc - có thể rò thông tin ngoài scope.

**Riêng các endpoints:**
- `# S6/B2` trong `app/api/routes/reconciliations.py` đã được sửa -> chỉ đối soát các journall thuộc cashbox user được phép, và `location_id` chỉ thu hẹp phạm vi, không mở rộng.

---

## 2. File thay đổi

### 2.1 `app/api/routes/reports.py`
- `inventory_daily`: Thêm `get_accessible_location_ids(db, current_user)` và `_narrow_to_location()` để lọc `Movement.location_id`.
- `inventory_summary`: Tương tự, thêm lọc `location_id` theo scope.

### 2.2 `app/api/routes/reconciliations.py`
- `run_reconciliation`: Thêm lọc `CashJournal` theo `CashRequest.cashbox_id` thuộc `allowed_cashbox_ids` (lookup trước khi query).
- `get_reconciliation_dashboard`: Thêm lọc `Movement.location_id` và `Balance.location_id` theo `get_accessible_location_ids`.

### 2.3 `tests/test_b2_authorization_scope.py` *(new)*
- **Negative-path scope tests**: user không có capability → 403; user logined nhưng `location_id` ngoài scope → không thấy data; user branch-A không thấy exception của branch-B; admin thấy tất cả.
- Tạo users độc lập (role `no_view_role`), không phụ thuộc vào demo seed data.

---

## 3. Kết quả chạy thử

```bash
$ timeout 120 .venv/bin/python -m pytest tests/test_b2_authorization_scope.py -v
======================== 7 passed, 7 warnings in 9.33s =========================
```

| TestCase | Result |
|----------|--------|
| `test_activity_endpoints_require_capability` | ✅ PASS |
| `test_activity_endpoints_deny_anonymous_access` | ✅ PASS |
| `test_403_for_no_capability_user` | ✅ PASS |
| `test_location_id_param_cannot_widen_scope` | ✅ PASS |
| `test_cash_reconciliation_respects_cashbox_scope` | ✅ PASS |
| `test_dashboard_exception_counters_respect_cashbox_scope` | ✅ PASS |
| `test_dashboard_exception_counters_admin_sees_all` | ✅ PASS |

---

## 4. Documentation

- QA branch coverage: `docs/QA_REPORT.md` (Phiên 10, vòng 10-11)
- Test coverage: `tests/test_b2_authorization_scope.py` (7 tests)
- Audit log: `tests/test_b2_authorization_scope.py` (all 7 tests PASS)
