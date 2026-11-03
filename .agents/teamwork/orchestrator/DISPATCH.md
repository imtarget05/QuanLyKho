# Dispatch History

## 2026-11-02T14:44:13Z
From: 299711bf-33da-4961-9a6d-73073040615d

Nâng cấp và hoàn thiện ứng dụng QuanLyKho (https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev) cho môi trường triển khai thực tế: làm lại trang chủ đồng bộ nội dung các phân hệ, khắc phục triệt để lỗi component và đồng bộ giao diện trên mobile từ ngoài vào trong ứng dụng, đồng thời xây dựng dịch vụ đồng bộ hai chiều gồm nhập dữ liệu qua Google Sheets API và cơ chế xuất dữ liệu ra các định dạng file.

Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho
Integrity mode: development

## Requirements

### R1. Làm lại và đồng bộ trang chủ (Homepage)
Làm lại giao diện trang chủ hiện đại, trực quan và tối ưu trải nghiệm người dùng, đồng bộ nội dung và trạng thái từ trang chủ dẫn vào các phân hệ và dữ liệu bên dưới của ứng dụng.

### R2. Khắc phục lỗi component và đồng bộ trải nghiệm trên Mobile
Sửa chữa toàn bộ các component bị lỗi hiển thị hoặc lỗi tương tác khi chuyển sang giao diện mobile từ ngoài vào trong ứng dụng; đảm bảo trải nghiệm sử dụng và dữ liệu hiển thị đồng bộ nhất quán giữa phiên bản web và mobile.

### R3. Dịch vụ đồng bộ dữ liệu từ Google Sheets
Xây dựng tính năng đồng bộ dữ liệu từ bảng tính bên ngoài vào ứng dụng thông qua kết nối Google Sheets API (sử dụng Service Account hoặc OAuth credentials), đảm bảo ánh xạ và cập nhật dữ liệu vào hệ thống chính xác, tiện lợi và dễ sử dụng.

### R4. Cơ chế xuất dữ liệu ra file
Xây dựng cơ chế và logic rõ ràng cho phép người dùng xuất dữ liệu từ ứng dụng ra các định dạng tệp: Excel (.xlsx), CSV, và PDF, đảm bảo dữ liệu toàn vẹn và đúng cấu trúc.

## Acceptance Criteria

### Giao diện và Tương thích Mobile
- [ ] Trang chủ mới hiển thị đầy đủ thông tin, điều hướng trực quan đến các phân hệ và đồng bộ với nội dung/dữ liệu thực tế của hệ thống
- [ ] Kiểm thử trên các viewport mobile tiêu chuẩn (chiều rộng 375px, 390px, 414px) không gặp lỗi tràn viền, vỡ bố cục hay lỗi hiển thị component
- [ ] Toàn bộ các component và luồng thao tác trong ứng dụng hoạt động đầy đủ, mượt mà và nhất quán giữa giao diện web desktop và mobile

### Dịch vụ Đồng bộ Google Sheets và Xuất file
- [ ] Kết nối thành công với Google Sheets qua Google Sheets API, dữ liệu từ bảng tính được nhập và cập nhật chính xác vào cơ sở dữ liệu của ứng dụng
- [ ] Chức năng xuất dữ liệu tạo thành công file theo đúng định dạng được chọn (.xlsx, .csv, .pdf), nội dung file khớp chính xác với dữ liệu trong hệ thống
- [ ] Bộ kiểm thử tự động hiện có của dự án cùng các test mới bổ sung cho tính năng đồng bộ và xuất file đều vượt qua (pass) không có lỗi
