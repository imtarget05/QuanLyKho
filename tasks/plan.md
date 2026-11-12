# Kế hoạch CV 2027: ba repo, ba thế mạnh

## Mục tiêu

Dùng IncidentIQ, Smart Document Chatbot và QuanLyKho làm ba dự án tiêu biểu. QuanLyKho chứng minh năng lực xây sản phẩm nghiệp vụ kho: Flutter, FastAPI, PostgreSQL, quyền theo vai trò, giao dịch đúng và kiểm thử. Kế hoạch này cải thiện bằng chứng và cách trình bày; không đặt mục tiêu thêm tính năng chỉ để tăng số công nghệ.

## Phạm vi và quyết định

- IncidentIQ: xử lý sự cố dựa trên tài liệu, retrieval và ranh giới MCP.
- Smart Document Chatbot: nền tảng tài liệu doanh nghiệp, Spring Boot/React và RAG.
- QuanLyKho: luồng nhập/xuất kho, maker-checker, tính đúng đắn giao dịch và Flutter. Quỹ/ledger chỉ là mô phỏng; AI chỉ tư vấn.
- CV theo từng JD chọn thứ tự và câu chữ khác nhau. Ba repo này không chứng minh mọi chuyên ngành như mobile native, QA chuyên biệt hay data science.
- `tasks/current.md` và các kế hoạch sản phẩm cũ vẫn là lịch sử/bảng việc riêng. Kế hoạch này chỉ theo dõi việc chuẩn bị portfolio 2027.

## Trạng thái khi clone

- Bản clone sạch ở `f65f962` trên `main` trước khi tạo nhánh kế hoạch.
- Có sẵn `DEMO.md`, `docs/INTERVIEW_KIT.md`, `docs/INTERVIEW_RELEASE.md`, CI và bài test demo.
- README ghi 988 backend / 355 Flutter tests; `tasks/current.md` ghi 735 / 261 ở mốc 2026-11-01. Các con số thuộc các mốc khác nhau; phải chạy lại hoặc dùng CI đúng commit trước khi đưa vào CV.
- Tài liệu hiện có nêu rõ chưa chứng minh production deployment và không có giao dịch ngân hàng thật. Giữ ranh giới đó trong CV.

## Thứ tự thực hiện

### P0 — Bằng chứng và câu chuyện chính

1. Chụp baseline đúng commit: trạng thái CI, lint, test, build Flutter, migration và demo; ghi lệnh, môi trường, kết quả, ngày và commit. Không dùng số test lịch sử làm kết quả hiện tại.
2. Kiểm tra một hành trình nghiệp vụ có thể kể trong 5 phút: maker tạo phiếu nhập theo lô → checker khác người duyệt → số dư và audit thay đổi đúng; thử duyệt bởi chính maker và thử lặp idempotency key. Dùng DB test riêng.
3. Nếu hành trình không chạy, sửa đúng lỗi ngăn demo bằng test hồi quy. Không mở rộng sang tính năng ngoài hành trình.

### P1 — Đóng gói cho CV

4. Viết một trang portfolio ngắn cho QuanLyKho: vấn đề, vai trò cá nhân, luồng, 2–3 quyết định kỹ thuật, bằng chứng đúng commit, giới hạn. Liên kết demo và test cụ thể. Giảm các tuyên bố rộng không có bằng chứng.
5. Chuẩn bị một CV lõi ba repo và ba biến thể câu chữ: Backend, Fullstack/Product, AI/Platform. Mỗi biến thể có tối đa 2 bullet mỗi repo, ưu tiên dự án phù hợp JD; không nhận là đáp ứng mọi vị trí.
6. Tạo bảng claim → bằng chứng → câu trả lời phỏng vấn cho ba repo. Riêng hai repo ngoài QuanLyKho phải kiểm tra tại checkout/CI của chính repo trước khi dùng số liệu.

### P2 — Chỉ làm nếu bằng chứng P0 chỉ ra nhu cầu

7. Cải thiện demo Flutter nếu luồng maker/checker hiện chỉ được chứng minh bằng API test: chọn một luồng UI ngắn, ghi hình/chụp màn hình từ build hiện tại và kiểm tra ở kích thước desktop + mobile. Không thêm màn hình mới khi màn hình hiện có đã đủ.
8. Chạy lại CI trên nhánh/PR và rà soát README so với artifact mới. Không gắn nhãn production-ready nếu chưa có kiểm chứng vận hành thực tế.

## Tiêu chí hoàn thành

- Người xem hiểu trong 30 giây vì sao QuanLyKho khác hai repo RAG.
- Demo nghiệp vụ chạy lại được bằng một lệnh hoặc có hướng dẫn ngắn với dữ liệu giả.
- Mỗi bullet CV có đường dẫn tới code, test, demo hoặc CI của đúng commit.
- Không có claim về ngân hàng thật, production, AI tự quyết định, hay Flutter offline nếu chưa chứng minh.
- CV được thử với ít nhất ba JD thực tế; thứ tự và bullet thay đổi theo JD nhưng không thay repo cho đủ stack.

## Rủi ro

| Rủi ro | Cách xử lý |
|---|---|
| Tài liệu lịch sử mâu thuẫn số liệu | Chốt commit và artifact mới; gỡ số cũ khỏi bản giới thiệu |
| Demo cần cloud hoặc dữ liệu thật | Dùng DB và dữ liệu giả cô lập; nêu rõ giới hạn |
| Hai repo đầu đều là RAG | QuanLyKho dẫn câu chuyện sản phẩm nghiệp vụ/giao dịch, không nhấn AI |
| CV quá dài vì ba repo lớn | Tối đa hai bullet mỗi repo, dẫn chi tiết qua GitHub |

## Câu hỏi còn mở

- Ba nhóm JD cụ thể nào sẽ được dùng để chốt các biến thể CV? Nếu chưa có, dùng Backend, Fullstack/Product và AI/Platform làm mẫu.
