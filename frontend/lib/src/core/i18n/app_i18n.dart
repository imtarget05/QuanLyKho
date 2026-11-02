import 'package:flutter/widgets.dart';
import 'package:provider/provider.dart';
import 'locale_controller.dart';

/// Hệ thống từ điển đa ngôn ngữ (Tiếng Việt & English).
class AppI18n {
  const AppI18n(this.locale);

  final Locale locale;

  bool get isVietnamese => locale.languageCode == 'vi';

  static const Map<String, Map<String, String>> _localizedValues = {
    'vi': {
      // Navigation
      'nav_dashboard': 'Tổng quan',
      'nav_inventory': 'Kho',
      'nav_shift_work': 'Ca làm việc',
      'nav_requests': 'Yêu cầu',
      'nav_approvals': 'Duyệt',
      'nav_integrations': 'Tích hợp',
      'nav_activity': 'Hoạt động',
      'nav_reports': 'Báo cáo',
      'nav_settings': 'Cài đặt',
      'nav_employees': 'Nhân viên',
      'nav_more': 'Thêm',
      'nav_section_ops': 'VẬN HÀNH KHO TRÀ SỮA',
      'nav_section_control': 'KIỂM SOÁT PHÊ DUYỆT',
      'nav_section_system': 'HỆ THỐNG & ĐỐI SOÁT',
      'nav_brand_title': 'Quản Lý Kho',
      'nav_brand_sub': 'BÁN HÀNG & KHO',
      'nav_select_workspace': 'Chọn phân hệ làm việc',
      'nav_access_denied_title': 'Từ chối quyền truy cập',
      'nav_access_denied_back': 'Quay lại Tổng quan',
      'nav_auditor_denied':
          'Tài khoản kiểm toán viên chỉ xem nhật ký kiểm toán và báo cáo, không truy cập phân hệ phê duyệt chứng từ.',
      'nav_admin_denied':
          'Phân hệ Quản trị nhân viên chỉ dành riêng cho Quản trị viên (Admin).',
      'nav_badge_pending': '{count} CHỜ DUYỆT',
      'nav_badge_approvals': 'PHÊ DUYỆT',

      // Sidebar collapsible
      'nav_collapse_sidebar': 'Thu gọn menu',
      'nav_expand_sidebar': 'Mở rộng menu',

      // Breadcrumb
      'breadcrumb_home': 'Trang chủ',
      'nav_home': 'Trang chủ',

      // Additional section headers
      'nav_section_inventory': 'KHO & KIỂM KÊ',
      'nav_section_transactions': 'GIAO DỊCH',
      'nav_section_finance': 'SỔ QUỸ',
      'nav_section_reports': 'BÁO CÁO & ĐỐI SOÁT',
      'nav_section_activity': 'HOẠT ĐỘNG',
      'nav_section_admin': 'QUẢN TRỊ',

      // Branding & Shell
      'app_title': 'Quản Lý Bán Hàng & Kho',
      'branch_badge': 'CN Quận 1 · Quán Trà Sữa Đô Thị',
      'live_online': 'Trực tuyến',
      'search_placeholder': 'Tìm nguyên liệu, phiếu kho, ca trực... (Ctrl+K)',
      'quick_shift_alert':
          '⚡ Ca sáng đang mở kiểm kê · 3 nguyên liệu sắp đến hạn FEFO · 2 mặt hàng dưới định mức',

      // TopBar & Tooltips
      'topbar_search_tooltip': 'Tìm kiếm toàn cục (Ctrl+K)',
      'topbar_refresh_tooltip': 'Làm mới dữ liệu',
      'topbar_approvals_tooltip': 'Hộp thư duyệt: {count} yêu cầu',
      'topbar_theme_tooltip': 'Chuyển giao diện Sáng / Tối',
      'topbar_lang_tooltip': 'Chuyển sang English',
      'topbar_settings_tooltip': 'Cài đặt hệ thống',
      'topbar_guest': 'Khách',
      'topbar_account': 'Tài khoản',
      'topbar_dismiss_ticker': 'Tắt thanh thông báo',

      // Common Actions
      'btn_save': 'Lưu thay đổi',
      'btn_cancel': 'Hủy bỏ',
      'btn_confirm': 'Xác nhận',
      'btn_approve': 'Phê duyệt',
      'btn_reject': 'Từ chối',
      'btn_search': 'Tìm kiếm',
      'btn_export': 'Xuất báo cáo',
      'btn_refresh': 'Làm mới',
      'btn_logout': 'Đăng xuất',
      'btn_edit_profile': 'Chỉnh sửa hồ sơ',
      'btn_change_password': 'Đổi mật khẩu',
      'btn_change_pin': 'Đổi mã PIN kiểm soát viên',
      'btn_close': 'Đóng',

      // Reports Screen Tabs & Headers
      'reports_title': 'Báo cáo & Biểu đồ',
      'reports_subtitle':
          'Giám sát chỉ số tài chính, xuất nhập tồn nguyên liệu và kiểm soát thất thoát',
      'reports_tab_inventory': 'Nhập/Xuất kho',
      'reports_tab_cashflow': 'Sổ Quỹ Tiền Mặt',
      'reports_tab_stagnation': 'Tồn đọng',
      'reports_tab_consumption': 'Top Tiêu Hao F&B',
      'reports_tab_shift_history': 'Lịch Sử Chốt Ca',
      'reports_tab_reconciliation': 'Đối soát',
      'reports_tab_meeting_notes': 'Báo Cáo Tổng Hợp',

      // Inventory Screen
      'inventory_title_stock': 'Quản Lý Nhập Xuất Tồn Nguyên Vật Liệu',
      'inventory_subtitle_stock':
          'Theo dõi nguyên liệu theo ca, định mức tồn và chênh lệch kiểm kê',
      'inventory_title_shift': 'Quản Lý Ca Làm Việc & Kiểm Kê Ca Pha Chế',
      'inventory_subtitle_shift':
          'Kiểm kê đầu ca, chốt số liệu cuối ca và đối chiếu chênh lệch định lượng nguyên liệu',
      'inventory_btn_new_stocktake': 'Mở Đợt Kiểm Kê Mới',
      'inventory_btn_add_item': 'Thêm mặt hàng',
      'inventory_btn_import_items': 'Import mặt hàng',
      'inventory_btn_create_stock_req': 'Tạo phiếu kho',
      'inventory_kpi_total_stock': 'TỔNG LƯỢNG TỒN KHO',
      'inventory_kpi_total_sku': 'TỔNG SẢN PHẨM (SKU)',
      'inventory_kpi_stock_alerts': 'CẢNH BÁO TỒN KHO',
      'inventory_kpi_total_valuation': 'TỔNG GIÁ TRỊ KHO',
      'inventory_kpi_shift_pending': 'CHỜ DUYỆT',
      'inventory_kpi_shift_approved': 'ĐÃ DUYỆT',
      'inventory_kpi_shift_discrepancy': 'CHÊNH LỆCH',
      'inventory_view_sheet': 'Bảng tính Google Sheet',
      'inventory_view_grid': 'Lưới thẻ sản phẩm',
      'inventory_cat_all': 'Tất cả',
      'inventory_stocktake_section_title':
          'Kiểm Kê Kho Định Kỳ & Đối Soát Chênh Lệch',
      'inventory_stocktake_section_sub':
          'Kiểm đếm thực tế, đối chiếu định mức và tự động sinh phiếu điều chỉnh',
      'inventory_btn_batch_select': 'Chọn nhiều',
      'inventory_btn_batch_cancel': 'Hủy chọn',
      'inventory_btn_select_all': 'Chọn tất cả',
      'inventory_btn_deselect_all': 'Bỏ chọn',
      'inventory_btn_batch_delete': 'Xóa đã chọn',

      // Requests Screen
      'requests_header_title': 'Quản Lý & Lập Phiếu Yêu Cầu',
      'requests_header_subtitle':
          'Lập phiếu nhập xuất kho nguyên liệu và phiếu điều chỉnh định mức',
      'requests_filter_all': 'Tất cả',
      'requests_filter_rework': 'Cần chỉnh sửa',
      'requests_filter_pending': 'Chờ duyệt',
      'requests_filter_draft': 'Bản nháp',
      'requests_filter_posted': 'Đã ghi sổ',
      'requests_section_stock': 'Phiếu Kho Nguyên Liệu',
      'requests_section_cash': 'Phiếu Điều Chỉnh Kho',
      'requests_btn_create_stock': 'Tạo Phiếu Kho Mới',
      'requests_btn_create_cash': 'Tạo Phiếu Điều Chỉnh',

      // Approvals Screen
      'approvals_header_title': 'Hộp Thư Phê Duyệt Yêu Cầu',
      'approvals_header_subtitle':
          'Quản lý kiểm tra chứng từ và quyết định phê duyệt ghi sổ',
      'approvals_badge_pending': '{count} YÊU CẦU CHỜ DUYỆT',
      'approvals_btn_batch_approve': 'Duyệt nhanh đã chọn',
      'approvals_empty_title': 'Hộp thư phê duyệt hoàn toàn trống',
      'approvals_empty_sub':
          'Tất cả các phiếu xuất/nhập kho và nạp/rút quỹ đã được kiểm soát xử lý xong.',

      // Activity Screen
      'activity_header_title': 'Hoạt động & Tiến trình nền',
      'activity_header_subtitle':
          'Toàn bộ lịch sử thao tác lập lệnh, phê duyệt, đối soát và tiến trình nền bất biến',
      'activity_btn_resync': 'Đồng bộ lại',
      'activity_empty_title': 'Chưa có hoạt động nào được ghi nhận',

      // Dashboard Screen
      'dashboard_header_title': 'Tổng Quan Vận Hành Quán Trà Sữa',
      'dashboard_header_subtitle':
          'Theo dõi dòng tiền quầy thu ngân, tồn kho nguyên vật liệu và tiến độ ca trực',
      'dashboard_quick_actions': 'Thao tác nhanh',
      'dashboard_action_stocktake': 'Kiểm kê ca',
      'dashboard_action_stock_request': 'Tạo phiếu kho',
      'dashboard_action_approvals': 'Hộp thư duyệt',
      'dashboard_action_reports': 'Báo cáo',
      'dashboard_cash_distribution': 'Phân Bổ Tiền Mặt & Két Quỹ Cửa Hàng',
      'dashboard_kpi_revenue': 'DOANH THU HÔM NAY',
      'dashboard_kpi_inventory_value': 'GIÁ TRỊ TỒN KHO',
      'dashboard_kpi_pending_approvals': 'CHỜ PHÊ DUYỆT',
      'dashboard_kpi_low_stock': 'TỒN DƯỚI ĐỊNH MỨC',

      // Settings Screen
      'settings_title': 'Cài đặt',
      'settings_language_section': 'Ngôn ngữ hiển thị',
      'settings_app_language_desc': 'Tùy chọn ngôn ngữ ứng dụng',
      'settings_instant_apply': 'Hệ thống tự động áp dụng và lưu cấu hình',
      'settings_appearance_section': 'Giao diện & Bố cục',
      'settings_theme_mode': 'Chế độ hiển thị',
      'settings_theme_system': 'Hệ thống',
      'settings_theme_light': 'Sáng',
      'settings_theme_dark': 'Tối',
      'settings_brand_color': 'Màu sắc thương hiệu (Theme Color)',
      'settings_color_matcha': 'Xanh Matcha',
      'settings_color_milktea': 'Trà Sữa Cổ Điển',
      'settings_color_oolong': 'Ô Long Hoàng Gia',
      'settings_color_berry': 'Trà Dâu Sakura',
      'settings_density': 'Mật độ hiển thị',
      'settings_density_comfortable': 'Tiêu chuẩn (Màn hình POS cảm ứng)',
      'settings_density_compact': 'Gọn gàng (Kiểm kho & Báo cáo)',
      'settings_ticker_toggle':
          'Hiển thị thanh cảnh báo trực tiếp (Live Ticker)',
      'settings_profile_section': 'Hồ Sơ Của Tôi',
      'settings_security_section': 'Bảo Mật Tài Khoản & Kiểm Soát Viên',
      'settings_system_section': 'Trạng thái kết nối hệ thống',
      'settings_copy_success': 'Đã sao chép vào bộ nhớ tạm',

      // Status & Shifts
      'shift_morning': 'Ca Sáng (07:30 - 15:00)',
      'shift_afternoon': 'Ca Chiều (15:00 - 23:00)',
      'shift_split': 'Ca Lỡ (07:30 - 18:00)',
      'status_draft': 'Bản nháp',
      'status_pending': 'Chờ duyệt',
      'status_approved': 'Đã duyệt',
      'status_rejected': 'Từ chối',
      'status_posted': 'Đã vào sổ',
      'status_low_stock': 'Dưới định mức',
      'status_expiring_soon': 'Sắp hết hạn',
      'status_normal': 'An toàn',

      // Commerce Workspace & Navigation
      'workspace_overview': 'Tổng quan',
      'workspace_sales': 'Bán hàng',
      'workspace_purchases': 'Mua hàng',
      'workspace_inventory': 'Kho hàng',
      'workspace_debt': 'Công nợ',
      'workspace_reports': 'Báo cáo',
      'workspace_approvals': 'Duyệt phiếu',
      'workspace_settings': 'Cài đặt',
      'workspace_more': 'Thêm',
      'action_cash_in': 'Thu tiền',
      'action_cash_out': 'Trả tiền',
      'action_deduction': 'Trừ tiền / Giảm trừ',
      'workspace_create_sale': 'Tạo phiếu bán',
      'workspace_create_purchase': 'Tạo phiếu nhập',
      'workspace_connected_server': 'KẾT NỐI MÁY CHỦ',
      'workspace_account': 'Tài khoản',
      'workspace_logout': 'Đăng xuất',
      'settings_system_title': 'Cài đặt hệ thống',
      'settings_system_subtitle':
          'Tùy chỉnh tài khoản, giao diện hiển thị, cấu hình máy in và quản lý phân quyền.',
      'settings_account_security': 'Tài khoản & Bảo mật',
      'settings_account_subtitle': 'Thông tin tài khoản đăng nhập hiện tại',
      'settings_account_role_hint': 'Vai trò và quyền truy cập theo tài khoản',
      'settings_edit_btn': 'Chỉnh sửa',
      'settings_change_pwd_desc': 'Định kỳ thay đổi mật khẩu để bảo mật tài khoản',
      'settings_change_btn': 'Thay đổi',
      'settings_appearance_locale': 'Giao diện & Ngôn ngữ',
      'settings_appearance_subtitle':
          'Tùy chỉnh chế độ hiển thị, màu chủ đạo và ngôn ngữ',
      'settings_theme_mode_label': 'Chế độ giao diện',
      'settings_app_language_label': 'Ngôn ngữ ứng dụng',
      'settings_lang_vi': '🇻🇳 Tiếng Việt',
      'settings_lang_en': '🇬🇧 English',
      'settings_hr_rbac': 'Nhân sự & Phân quyền',
      'settings_hr_subtitle':
          'Quản lý danh sách nhân viên, tài khoản thu ngân và thủ kho',
      'settings_rbac_list': 'Danh sách nhân viên & vai trò (RBAC)',
      'settings_rbac_desc':
          'Cấp quyền, tạo mã nhân viên và kích hoạt / vô hiệu hóa tài khoản',
      'settings_manage_employees': 'Quản lý nhân viên',
      'settings_printer_invoice': 'Máy in & Hóa đơn',
      'settings_printer_subtitle':
          'Cấu hình thông số in phiếu bán hàng và nhập hàng',
      'settings_paper_size': 'Khổ giấy in nhiệt',
      'settings_auto_print': 'Tự động bật cửa sổ in sau khi tạo phiếu',
      'settings_system_data': 'Quản trị hệ thống & Dữ liệu',
      'settings_system_data_subtitle':
          'Khởi tạo lại dữ liệu demo hoặc đăng xuất khỏi phiên làm việc',
      'settings_reset_data': 'Khởi tạo lại dữ liệu demo',
      'settings_reset_desc':
          'Làm mới toàn bộ danh mục sản phẩm, đơn hàng và công nợ về trạng thái mẫu ban đầu.',
      'settings_reset_btn': 'Khởi tạo lại',
      'settings_signout_title': 'Đăng xuất phiên làm việc',
      'settings_signout_desc': 'Đăng xuất khỏi tài khoản trên thiết bị này',
      'settings_signout_btn': 'Đăng xuất',

      // Banking & Financial / Debt Deduction (Công nợ & Trừ tiền)
      'debt_title': 'Công nợ phải thu & phải trả',
      'debt_subtitle': 'Theo dõi số tiền còn lại theo khách hàng và nhà cung cấp.',
      'debt_kpi_receivable': 'Khách hàng còn nợ',
      'debt_kpi_payable': 'Nhà cung cấp cần trả',
      'debt_kpi_orders_to_collect': 'Đơn cần thu',
      'debt_kpi_bills_to_pay': 'Phiếu cần trả',
      'debt_tab_receivable': 'Phải thu khách hàng',
      'debt_tab_payable': 'Phải trả nhà cung cấp',
      'debt_search_hint': 'Tìm mã phiếu, khách hàng, nhà cung cấp...',
      'debt_filter_all': 'Tất cả hạn thanh toán',
      'debt_filter_overdue': 'Quá hạn',
      'debt_filter_due': 'Còn hạn',
      'debt_empty': 'Không có khoản công nợ phù hợp.',
      'debt_col_code': 'MÃ PHIẾU',
      'debt_col_party': 'KHÁCH HÀNG / NCC',
      'debt_col_date': 'NGÀY',
      'debt_col_remaining': 'CÒN LẠI',
      'debt_col_due_date': 'HẠN THANH TOÁN',
      'debt_col_status': 'TRẠNG THÁI',
      'debt_col_action': 'THAO TÁC',
      'debt_action_collect': 'Thu nợ',
      'debt_action_deduct': 'Trừ tiền / Chi trả',
      'debt_action_record': 'Ghi nhận',
      'debt_status_not_set': 'Chưa hẹn',
      'debt_remaining_prefix': 'Còn',
      'debt_total_prefix': 'Tổng',
      'debt_record_receipt': 'Ghi nhận thu nợ (Thu tiền)',
      'debt_record_deduction': 'Khấu trừ công nợ / Trừ tiền nhà cung cấp',
      'debt_dialog_remaining': 'Còn lại {amount}',
      'debt_dialog_amount_label': 'Số tiền khấu trừ / thanh toán (₫)',
      'debt_dialog_method': 'Phương thức thanh toán',
      'debt_method_cash': 'Tiền mặt',
      'debt_method_transfer': 'Chuyển khoản',
      'debt_dialog_ref': 'Mã giao dịch đối soát (không bắt buộc)',
      'debt_dialog_btn_save': 'Lưu đối trừ công nợ',
      'debt_snack_ram': 'Đã ghi nhận đối trừ công nợ trong phiên RAM.',
      'debt_snack_saved': 'Đã ghi nhận đối trừ công nợ thành công.',

      // Overview & Analytics
      'overview_title': 'Tổng quan vận hành',
      'overview_subtitle': 'Theo dõi doanh thu, chi phí, mua bán và công nợ theo thời gian thực.',
      'overview_kpi_net_revenue': 'Doanh thu thuần',
      'overview_kpi_gross_profit': 'Lợi nhuận gộp',
      'overview_kpi_sales_count': 'Số đơn hàng',
      'overview_kpi_inventory_value': 'Giá trị tồn kho',
      'overview_kpi_profit_margin': 'Tỷ suất lợi nhuận',
      'overview_kpi_stock_warning': 'Cảnh báo tồn kho',
      'overview_kpi_receivable': 'Công nợ phải thu KH',
      'overview_kpi_payable': 'Công nợ phải trả NCC',
      'overview_action_create_sale': 'Tạo đơn bán',
      'overview_action_create_purchase': 'Tạo phiếu nhập',
      'overview_action_stocktake': 'Kiểm kê kho',
      'overview_action_debt': 'Theo dõi công nợ',
      'overview_action_reports': 'Xem báo cáo',
      'overview_action_approvals': 'Phiếu chờ duyệt',

      // Orders (Sales / Purchases)
      'orders_sale_title': 'Quản lý bán hàng',
      'orders_purchase_title': 'Quản lý mua hàng',
      'orders_quote_title': 'Quản lý báo giá',
      'orders_customers_title': 'Khách hàng',
      'orders_suppliers_title': 'Nhà cung cấp',
      'orders_filter_all': 'Tất cả trạng thái',
      'orders_filter_pending': 'Chờ duyệt',
      'orders_filter_unpaid': 'Chưa thanh toán',
      'orders_filter_partial': 'Thanh toán một phần',
      'orders_filter_paid': 'Đã thanh toán',
      'orders_filter_rejected': 'Đã từ chối',
      'orders_filter_period_all': 'Mọi thời gian',
      'orders_filter_today': 'Hôm nay',
      'orders_filter_7d': '7 ngày qua',
      'orders_filter_30d': '30 ngày qua',

      // Reports
      'reports_lenakolia_title': 'Báo cáo Xuất Nhập Tồn NVL & TP',
      'reports_lenakolia_subtitle': 'Tổng hợp doanh thu, giá vốn, lợi nhuận gộp và sổ kho nguyên vật liệu - thành phẩm.',
      'reports_export_xlsx': 'Xuất Excel (XLSX)',
      'reports_period_this_year': 'Năm nay',
      'reports_period_custom': 'Tùy chỉnh',
      'reports_cat_all': 'Tất cả phân loại',
      'reports_cat_raw': 'Nguyên vật liệu (NVL)',
      'reports_cat_finished': 'Thành phẩm (TP)',
    },
    'en': {
      // Navigation
      'nav_dashboard': 'Dashboard',
      'nav_inventory': 'Inventory',
      'nav_shift_work': 'Shifts',
      'nav_requests': 'Requests',
      'nav_approvals': 'Approvals',
      'nav_integrations': 'Integrations',
      'nav_activity': 'Activity',
      'nav_reports': 'Reports',
      'nav_settings': 'Settings',
      'nav_employees': 'Employees',
      'nav_more': 'More',
      'nav_section_ops': 'OPERATIONS & INVENTORY',
      'nav_section_control': 'AUDIT & APPROVALS',
      'nav_section_system': 'SYSTEM & RECONCILIATION',
      'nav_brand_title': 'Milk Tea Ops',
      'nav_brand_sub': 'INVENTORY & SALES',
      'nav_select_workspace': 'Select Workspace',
      'nav_access_denied_title': 'Access Denied',
      'nav_access_denied_back': 'Back to Dashboard',
      'nav_auditor_denied':
          'Auditor role is restricted to audit trails and reports only; voucher approvals are unavailable.',
      'nav_admin_denied':
          'Employee Management module is reserved for Administrators (Admin) only.',
      'nav_badge_pending': '{count} PENDING',
      'nav_badge_approvals': 'APPROVALS',

      // Sidebar collapsible
      'nav_collapse_sidebar': 'Collapse menu',
      'nav_expand_sidebar': 'Expand menu',

      // Breadcrumb
      'breadcrumb_home': 'Home',
      'nav_home': 'Home',

      // Additional section headers
      'nav_section_inventory': 'INVENTORY & STOCKTAKE',
      'nav_section_transactions': 'TRANSACTIONS',
      'nav_section_finance': 'CASH LEDGER',
      'nav_section_reports': 'REPORTS & RECONCILIATION',
      'nav_section_activity': 'ACTIVITY',
      'nav_section_admin': 'ADMINISTRATION',

      // Branding & Shell
      'app_title': 'Milk Tea Inventory Ops',
      'branch_badge': 'Branch 1 · Urban Milk Tea Shop',
      'live_online': 'Online',
      'search_placeholder': 'Search ingredients, vouchers, shifts... (Ctrl+K)',
      'quick_shift_alert':
          '⚡ Morning shift active · 3 items near expiry (FEFO) · 2 items low stock',

      // TopBar & Tooltips
      'topbar_search_tooltip': 'Global Search (Ctrl+K)',
      'topbar_refresh_tooltip': 'Refresh Data',
      'topbar_approvals_tooltip': 'Approval Inbox: {count} requests',
      'topbar_theme_tooltip': 'Toggle Light / Dark Mode',
      'topbar_lang_tooltip': 'Switch to Tiếng Việt',
      'topbar_settings_tooltip': 'System Settings',
      'topbar_guest': 'Guest',
      'topbar_account': 'Account',
      'topbar_dismiss_ticker': 'Dismiss alert ticker',

      // Common Actions
      'btn_save': 'Save Changes',
      'btn_cancel': 'Cancel',
      'btn_confirm': 'Confirm',
      'btn_approve': 'Approve',
      'btn_reject': 'Reject',
      'btn_search': 'Search',
      'btn_export': 'Export Report',
      'btn_refresh': 'Refresh',
      'btn_logout': 'Sign Out',
      'btn_edit_profile': 'Edit Profile',
      'btn_change_password': 'Change Password',
      'btn_change_pin': 'Change Supervisor PIN',
      'btn_close': 'Close',

      // Reports Screen Tabs & Headers
      'reports_title': 'Management & Reconciliation Reports',
      'reports_subtitle':
          'Monitor financial KPIs, material stock balances, and discrepancy controls',
      'reports_tab_inventory': 'Stock In/Out',
      'reports_tab_cashflow': 'Cash Ledger',
      'reports_tab_stagnation': 'Stagnation',
      'reports_tab_consumption': 'Top Consumption',
      'reports_tab_shift_history': 'Shift History',
      'reports_tab_reconciliation': 'Reconciliation',
      'reports_tab_meeting_notes': 'Executive Summary',

      // Inventory Screen
      'inventory_title_stock': 'Inventory & Material Stockflow',
      'inventory_subtitle_stock':
          'Track ingredients by shift, stock quotas, and variance controls',
      'inventory_title_shift': 'Shift Management & Bar Stocktake',
      'inventory_subtitle_shift':
          'Opening stocktake, shift closing, and recipe variance reconciliation',
      'inventory_btn_new_stocktake': 'New Stocktake',
      'inventory_btn_add_item': 'Add Item',
      'inventory_btn_import_items': 'Import Items',
      'inventory_btn_create_stock_req': 'New Stock Voucher',
      'inventory_kpi_total_stock': 'TOTAL INVENTORY',
      'inventory_kpi_total_sku': 'TOTAL PRODUCTS (SKU)',
      'inventory_kpi_stock_alerts': 'STOCK ALERTS',
      'inventory_kpi_total_valuation': 'TOTAL VALUATION',
      'inventory_kpi_shift_pending': 'PENDING REVIEW',
      'inventory_kpi_shift_approved': 'APPROVED',
      'inventory_kpi_shift_discrepancy': 'VARIANCE',
      'inventory_view_sheet': 'Sheet Table View',
      'inventory_view_grid': 'Card Grid View',
      'inventory_cat_all': 'All Categories',
      'inventory_stocktake_section_title':
          'Periodic Stocktake & Variance Audit',
      'inventory_stocktake_section_sub':
          'Physical count, quota matching, and auto-generated adjustment vouchers',
      'inventory_btn_batch_select': 'Batch Select',
      'inventory_btn_batch_cancel': 'Cancel Selection',
      'inventory_btn_select_all': 'Select All',
      'inventory_btn_deselect_all': 'Deselect All',
      'inventory_btn_batch_delete': 'Delete Selected',

      // Requests Screen
      'requests_header_title': 'Vouchers & Material Requests',
      'requests_header_subtitle':
          'Submit stock intake/issues and quota adjustment vouchers',
      'requests_filter_all': 'All',
      'requests_filter_rework': 'Needs Revision',
      'requests_filter_pending': 'Pending',
      'requests_filter_draft': 'Draft',
      'requests_filter_posted': 'Posted',
      'requests_section_stock': 'Material Stock Vouchers',
      'requests_section_cash': 'Inventory Adjustment Vouchers',
      'requests_btn_create_stock': 'New Stock Voucher',
      'requests_btn_create_cash': 'New Adjustment Voucher',

      // Approvals Screen
      'approvals_header_title': 'Approval Inbox',
      'approvals_header_subtitle':
          'Supervisors review vouchers and authorize ledger postings',
      'approvals_badge_pending': '{count} PENDING REQUESTS',
      'approvals_btn_batch_approve': 'Approve Selected',
      'approvals_empty_title': 'No pending requests',
      'approvals_empty_sub': 'All stock vouchers and requests are processed.',

      // Activity Screen
      'activity_header_title': 'Activity & Background Feed',
      'activity_header_subtitle':
          'Full immutable audit log of requests, approvals, and system events',
      'activity_btn_resync': 'Resync',
      'activity_empty_title': 'No activity recorded yet',

      // Dashboard Screen
      'dashboard_header_title': 'Milk Tea Operations Dashboard',
      'dashboard_header_subtitle':
          'Live register cashflow, ingredient stock balances, and shift progress',
      'dashboard_quick_actions': 'Quick Actions',
      'dashboard_action_stocktake': 'Shift Stocktake',
      'dashboard_action_stock_request': 'New Stock Voucher',
      'dashboard_action_approvals': 'Approval Inbox',
      'dashboard_action_reports': 'Reports',
      'dashboard_cash_distribution': 'Store Cash & Safe Distribution',
      'dashboard_kpi_revenue': 'TODAY REVENUE',
      'dashboard_kpi_inventory_value': 'INVENTORY VALUE',
      'dashboard_kpi_pending_approvals': 'PENDING APPROVAL',
      'dashboard_kpi_low_stock': 'LOW STOCK ITEMS',

      // Settings Screen
      'settings_title': 'Settings',
      'settings_language_section': 'Display Language',
      'settings_app_language_desc': 'Application Language Option',
      'settings_instant_apply': 'Changes apply instantly and are saved',
      'settings_appearance_section': 'Appearance & Layout',
      'settings_theme_mode': 'Display Mode',
      'settings_theme_system': 'System',
      'settings_theme_light': 'Light',
      'settings_theme_dark': 'Dark',
      'settings_brand_color': 'Brand Color Theme',
      'settings_color_matcha': 'Matcha Green',
      'settings_color_milktea': 'Classic Milk Tea',
      'settings_color_oolong': 'Royal Oolong',
      'settings_color_berry': 'Sakura Berry',
      'settings_density': 'Layout Density',
      'settings_density_comfortable': 'Comfortable (POS Touchscreen)',
      'settings_density_compact': 'Compact (Inventory & Auditing)',
      'settings_ticker_toggle': 'Show Live Alert Ticker Bar',
      'settings_profile_section': 'My Profile',
      'settings_security_section': 'Account & Supervisor Security',
      'settings_system_section': 'System Connection Status',
      'settings_copy_success': 'Copied to clipboard',

      // Status & Shifts
      'shift_morning': 'Morning Shift (07:30 - 15:00)',
      'shift_afternoon': 'Afternoon Shift (15:00 - 23:00)',
      'shift_split': 'Split Shift (07:30 - 18:00)',
      'status_draft': 'Draft',
      'status_pending': 'Pending',
      'status_approved': 'Approved',
      'status_rejected': 'Rejected',
      'status_posted': 'Posted',
      'status_low_stock': 'Low Stock',
      'status_expiring_soon': 'Expiring Soon',
      'status_normal': 'Normal',

      // Commerce Workspace & Navigation
      'workspace_overview': 'Overview',
      'workspace_sales': 'Sales',
      'workspace_purchases': 'Purchases',
      'workspace_inventory': 'Inventory',
      'workspace_debt': 'Debt Ledger',
      'workspace_reports': 'Reports',
      'workspace_approvals': 'Approvals',
      'workspace_settings': 'Settings',
      'workspace_more': 'More',
      'action_cash_in': 'Receive Payment',
      'action_cash_out': 'Make Payment',
      'action_deduction': 'Deduction / Debit',
      'workspace_create_sale': 'New Sale Order',
      'workspace_create_purchase': 'New Purchase Order',
      'workspace_connected_server': 'CONNECTED TO SERVER',
      'workspace_account': 'Account',
      'workspace_logout': 'Sign Out',
      'settings_system_title': 'System Settings',
      'settings_system_subtitle':
          'Customize account, display theme, printer templates, and access permissions.',
      'settings_account_security': 'Account & Security',
      'settings_account_subtitle': 'Current signed-in user account information',
      'settings_account_role_hint': 'Assigned role and permission access',
      'settings_edit_btn': 'Edit',
      'settings_change_pwd_desc': 'Periodically update password for security',
      'settings_change_btn': 'Change',
      'settings_appearance_locale': 'Appearance & Language',
      'settings_appearance_subtitle':
          'Customize display theme, brand colors, and language',
      'settings_theme_mode_label': 'Theme Mode',
      'settings_app_language_label': 'Application Language',
      'settings_lang_vi': '🇻🇳 Tiếng Việt',
      'settings_lang_en': '🇬🇧 English',
      'settings_hr_rbac': 'HR & Permissions (RBAC)',
      'settings_hr_subtitle':
          'Manage employees, cashiers, and warehouse operators',
      'settings_rbac_list': 'Employee List & Roles (RBAC)',
      'settings_rbac_desc':
          'Grant roles, assign employee codes, and activate/deactivate accounts',
      'settings_manage_employees': 'Manage Employees',
      'settings_printer_invoice': 'Printer & Invoices',
      'settings_printer_subtitle':
          'Configure sales receipt and purchase order print formats',
      'settings_paper_size': 'Thermal Paper Size',
      'settings_auto_print': 'Auto-trigger print preview after document creation',
      'settings_system_data': 'System Administration & Data',
      'settings_system_data_subtitle':
          'Reset demo sample data or sign out of current workspace',
      'settings_reset_data': 'Reset Demo Data',
      'settings_reset_desc':
          'Refresh products, orders, and receivables back to default sample.',
      'settings_reset_btn': 'Reset Data',
      'settings_signout_title': 'Sign Out Session',
      'settings_signout_desc': 'Sign out of current account on this device',
      'settings_signout_btn': 'Sign Out',

      // Banking & Financial / Debt Deduction (Accounts Receivable / Payable)
      'debt_title': 'Accounts Receivable & Accounts Payable',
      'debt_subtitle': 'Monitor outstanding balances across customers and suppliers.',
      'debt_kpi_receivable': 'Total Receivables (A/R)',
      'debt_kpi_payable': 'Total Payables (A/P)',
      'debt_kpi_orders_to_collect': 'Orders to Collect',
      'debt_kpi_bills_to_pay': 'Bills to Settle',
      'debt_tab_receivable': 'Accounts Receivable (Customers)',
      'debt_tab_payable': 'Accounts Payable (Suppliers)',
      'debt_search_hint': 'Search code, customer, supplier...',
      'debt_filter_all': 'All Due Dates',
      'debt_filter_overdue': 'Overdue',
      'debt_filter_due': 'Current',
      'debt_empty': 'No matching debt records found.',
      'debt_col_code': 'CODE',
      'debt_col_party': 'CUSTOMER / VENDOR',
      'debt_col_date': 'DATE',
      'debt_col_remaining': 'OUTSTANDING',
      'debt_col_due_date': 'DUE DATE',
      'debt_col_status': 'STATUS',
      'debt_col_action': 'ACTIONS',
      'debt_action_collect': 'Collect',
      'debt_action_deduct': 'Deduct / Pay',
      'debt_action_record': 'Settle',
      'debt_status_not_set': 'No Date',
      'debt_remaining_prefix': 'Bal',
      'debt_total_prefix': 'Total',
      'debt_record_receipt': 'Record Cash Receipt (A/R)',
      'debt_record_deduction': 'Disburse Payment / Debit Deduction (A/P)',
      'debt_dialog_remaining': 'Remaining {amount}',
      'debt_dialog_amount_label': 'Settlement / Deduction Amount (₫)',
      'debt_dialog_method': 'Payment Method',
      'debt_method_cash': 'Cash',
      'debt_method_transfer': 'Bank Transfer',
      'debt_dialog_ref': 'Reference / Transaction ID (Optional)',
      'debt_dialog_btn_save': 'Save Debt Deduction',
      'debt_snack_ram': 'Deduction recorded in local RAM session.',
      'debt_snack_saved': 'Debt deduction successfully posted.',

      // Overview & Analytics
      'overview_title': 'Operations Overview',
      'overview_subtitle': 'Real-time tracking of revenue, costs, purchases, sales, and debt ledger.',
      'overview_kpi_net_revenue': 'Net Revenue',
      'overview_kpi_gross_profit': 'Gross Profit',
      'overview_kpi_sales_count': 'Order Count',
      'overview_kpi_inventory_value': 'Inventory Value',
      'overview_kpi_profit_margin': 'Profit Margin',
      'overview_kpi_stock_warning': 'Low Stock Alert',
      'overview_kpi_receivable': 'A/R Receivables',
      'overview_kpi_payable': 'A/P Payables',
      'overview_action_create_sale': 'New Sale',
      'overview_action_create_purchase': 'New Purchase',
      'overview_action_stocktake': 'Stocktake',
      'overview_action_debt': 'Debt Ledger',
      'overview_action_reports': 'View Reports',
      'overview_action_approvals': 'Approvals',

      // Orders (Sales / Purchases)
      'orders_sale_title': 'Sales Management',
      'orders_purchase_title': 'Purchase Management',
      'orders_quote_title': 'Quotation Management',
      'orders_customers_title': 'Customers',
      'orders_suppliers_title': 'Suppliers',
      'orders_filter_all': 'All Statuses',
      'orders_filter_pending': 'Pending Approval',
      'orders_filter_unpaid': 'Unpaid',
      'orders_filter_partial': 'Partially Paid',
      'orders_filter_paid': 'Paid',
      'orders_filter_rejected': 'Rejected',
      'orders_filter_period_all': 'All Time',
      'orders_filter_today': 'Today',
      'orders_filter_7d': 'Last 7 Days',
      'orders_filter_30d': 'Last 30 Days',

      // Reports
      'reports_lenakolia_title': 'Inventory & P&L Statement (Raw Materials & FG)',
      'reports_lenakolia_subtitle': 'Consolidated revenue, COGS, gross profit, and stock ledger for raw materials and finished goods.',
      'reports_export_xlsx': 'Export Excel (XLSX)',
      'reports_period_this_year': 'This Year',
      'reports_period_custom': 'Custom',
      'reports_cat_all': 'All Categories',
      'reports_cat_raw': 'Raw Materials (NVL)',
      'reports_cat_finished': 'Finished Goods (TP)',
    },
  };

  String tr(String key, [Map<String, String>? params]) {
    final lang = locale.languageCode;
    var value =
        _localizedValues[lang]?[key] ?? _localizedValues['vi']?[key] ?? key;
    if (params != null) {
      params.forEach((paramKey, paramVal) {
        value = value.replaceAll('{$paramKey}', paramVal);
      });
    }
    return value;
  }
}

/// Extension tiện lợi trên BuildContext để gọi `context.tr('key')` hoặc `context.isVietnamese`.
extension AppI18nExtension on BuildContext {
  Locale get currentLocale {
    try {
      final ctrl = Provider.of<LocaleController>(this, listen: false);
      return ctrl.locale;
    } catch (_) {
      try {
        final ctrl = Provider.of<LocaleController?>(this, listen: false);
        if (ctrl != null) return ctrl.locale;
      } catch (_) {}
    }
    return const Locale('vi');
  }

  bool get isVietnamese => currentLocale.languageCode == 'vi';

  String tr(String key, [Map<String, String>? params]) {
    return AppI18n(currentLocale).tr(key, params);
  }
}
