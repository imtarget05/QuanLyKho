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
