# Kế hoạch làm mới trải nghiệm giao diện QuanLyKho

**Trạng thái:** Handoff để bắt đầu khảo sát và lập kế hoạch triển khai; chưa phải xác nhận rằng các màn hình hay nghiệp vụ dưới đây đã tồn tại.
**Phạm vi của tài liệu:** Định hướng UX/UI và các nguyên tắc cần kiểm chứng với repository. Đây không phải quyết định thay đổi PRD, kiến trúc hay nghiệp vụ MVP hiện hành.
**Tham chiếu:** Cấu trúc thông tin của vkho.vn, theo yêu cầu người dùng ngày 2026-10-26. Chỉ học cách tổ chức trải nghiệm; không sao chép thương hiệu, câu chữ, hình ảnh hoặc thiết kế nhận diện.

Ảnh tham chiếu trong hội thoại cho thấy shell quản trị với sidebar dọc, mục hiện hành được nhấn mạnh, các nhóm nghiệp vụ như bán hàng, sửa chữa, trả hàng, nhà cung cấp, khách hàng, báo cáo, sổ quỹ, chi nhánh và người dùng. Đây chỉ là gợi ý về cách gom nhóm điều hướng; không phải danh sách module mặc định cho QuanLyKho. Trang vkho.vn khi kiểm tra trực tiếp chỉ trả về trạng thái tải dữ liệu, nên kế hoạch này không suy diễn thêm nội dung website ngoài ảnh và yêu cầu người dùng đã cung cấp.

## 1. Mục tiêu

Làm mới toàn bộ trải nghiệm web quản lý kho theo hướng rõ ràng, dễ học và có thể mở rộng thành nhiều phân hệ. Đây là yêu cầu trên toàn sản phẩm, không phải chỉnh sửa một tab hay một trang đơn lẻ. Cần có cả hành trình khách chưa đăng nhập và shell ứng dụng sau đăng nhập.

Trước khi thiết kế hoặc viết lại, khảo sát các route, màn hình, component, API, model, phân quyền và tài liệu hiện có. Tận dụng phần đang hoạt động; chỉ đề xuất thay thế khi audit cho thấy lý do cụ thể. Không tuyên bố tính năng tồn tại hoặc đã hoàn tất nếu chưa đối chiếu code và bằng chứng nghiệm thu.

## 2. Hướng trải nghiệm

### Khu vực công khai

- Trang chào khách giải thích sản phẩm, lợi ích và các khả năng quản lý kho bằng nội dung, hình ảnh và nhận diện riêng của QuanLyKho.
- CTA dễ thấy: đăng nhập, tạo tài khoản/đăng ký nếu chính sách và backend hỗ trợ, và trải nghiệm demo miễn phí nếu demo hiện có được xác minh là an toàn.
- Hành trình đăng nhập, đăng ký và demo phải có trạng thái tải/lỗi/thành công rõ ràng; không trình bày demo như dữ liệu thật hay tự ý tạo cam kết miễn phí chưa được sản phẩm xác nhận.
- Trên màn hình nhỏ, nội dung và CTA vẫn dễ đọc, dễ thao tác.

### Ứng dụng sau đăng nhập

- Khung quản trị nhất quán: sidebar nhiều cấp có thể thu gọn/mở rộng; header có tìm kiếm, thông báo và hồ sơ người dùng; breadcrumb; vùng nội dung theo route.
- Điều hướng thể hiện rõ mục đang chọn, hỗ trợ nhóm menu và quyền hiện hành. Ẩn/hiện trên giao diện không thay thế việc kiểm tra quyền ở backend.
- Bố cục responsive cho desktop, tablet và điện thoại; các bảng dữ liệu có cách dùng phù hợp màn hình hẹp, không chỉ thu nhỏ nguyên xi.
- Mỗi trang cần trạng thái rỗng, tải, lỗi, thành công và quyền truy cập phù hợp; thao tác quan trọng có phản hồi và xác nhận theo mức rủi ro.

## 3. Phân hệ đề xuất để khảo sát

Đây là bản đồ khả năng sản phẩm để audit route/API và thảo luận thứ tự. Không tạo route giả hoặc menu trỏ vào màn hình chưa có.

1. **Tổng quan:** KPI tồn kho, cảnh báo, hoạt động gần đây và lối tắt theo quyền.
2. **Danh mục & kho:** sản phẩm, danh mục, đơn vị tính/quy cách, kho/địa điểm, mức tồn tối thiểu/tối đa.
3. **Nhập hàng:** phiếu nhập, nhà cung cấp, lô và hạn dùng nếu được hỗ trợ trong phạm vi nghiệp vụ.
4. **Xuất hàng:** phiếu xuất/tiêu hao và khách hàng nếu mô hình sản phẩm thực sự cần khách hàng.
5. **Kiểm kê & điều chỉnh:** phiên kiểm kê, chênh lệch, phiếu điều chỉnh và lịch sử biến động.
6. **Sổ biến động tồn:** tra cứu movement theo mặt hàng, kho, chứng từ, người thao tác và thời gian.
7. **Giá vốn:** hiển thị giá vốn bình quân gia quyền nếu semantics hiện tại và quyền truy cập cho phép.
8. **Báo cáo & đối soát:** nhập-xuất-tồn, tiêu hao, cảnh báo, đối soát giữa ledger và số dư; chỉ dùng báo cáo có API/dữ liệu đáng tin cậy.
9. **Người dùng & kiểm soát:** người dùng, vai trò, quyền, phê duyệt và audit trail theo đúng RBAC hiện hành.
10. **Cài đặt:** cấu hình danh mục/đơn vị/kho và tùy chọn đã được sản phẩm hỗ trợ.

Sửa chữa/đổi trả, công nợ, sổ quỹ, nhiều chi nhánh và các phân hệ tài chính khác để ngoài đợt đầu, trừ khi audit cho thấy đã có phạm vi được phê duyệt và cần thiết cho luồng chính. PRD hiện hành tập trung vào vận hành kho trà sữa theo ca; tài liệu này không tự mở rộng sản phẩm thành ERP tổng quát.

## 4. Các nguyên tắc nghiệp vụ cần bảo toàn hoặc xác minh

### Tồn kho và audit

- Biến động tồn phải có lịch sử truy nguyên. Movement đã ghi nhận không bị sửa/xóa để “chữa số”; sai sót được xử lý bằng reversal hoặc adjustment mới theo quy trình được duyệt.
- Ledger là nguồn giải thích biến động; bảng số dư nếu có chỉ là cache/tổng hợp và phải đối soát được với movements.
- Ghi movement, cập nhật balance, audit event và outbox liên quan trong cùng transaction. Khóa/cập nhật số dư theo cách chống tranh chấp đồng thời; unique constraint và idempotency bảo vệ trước retry/nhấp lặp.
- Chỉ phiếu ở trạng thái hợp lệ mới được post. Tham chiếu `Draft → Completed → Cancelled` trong yêu cầu ban đầu cần đối chiếu state machine hiện tại (có thể có Pending/Approved/Posted/Returned). Không rút gọn hoặc đổi trạng thái chỉ để khớp nhãn giao diện.
- Hủy phiếu đã post phải tạo bút toán đảo/reversal tương ứng, không xóa lịch sử. Phân biệt hủy bản nháp với đảo nghiệp vụ đã hoàn tất.

### Đơn vị tính

- Nếu hỗ trợ quy đổi, lưu lượng tồn theo đơn vị cơ sở (base unit). Mỗi dòng chứng từ ghi đơn vị người dùng chọn, lượng nhập và hệ số quy đổi được chụp tại thời điểm lập/duyệt để lịch sử không thay đổi khi cấu hình quy cách được sửa.
- Quy tắc làm tròn, độ chính xác, đơn vị không thể chia nhỏ và chuyển đổi giữa các nhóm thứ nguyên cần được xác minh, không suy diễn từ nhãn UI.

### Giá vốn bình quân gia quyền (Moving Average Cost, MAC)

- Công thức tham chiếu sau khi nhập hàng: `giá vốn mới = (số lượng tồn trước × giá vốn trước + số lượng nhập quy đổi × đơn giá nhập theo đơn vị cơ sở) / (số lượng tồn trước + số lượng nhập quy đổi)`.
- Chỉ tính trên số lượng/cost basis nhất quán, trong giao dịch hoàn tất và theo thứ tự nghiệp vụ xác định. Quy định riêng cho tồn bằng 0, tồn âm bị cấm hay cho phép, giá trị thiếu, trả hàng, điều chỉnh và độ chính xác tiền tệ.
- Công thức là yêu cầu cần audit với implementation hiện tại; không hiển thị như đã được hỗ trợ chỉ vì có trường `cost_price` hoặc test tài liệu.

### Phê duyệt và phân quyền

- Giữ maker-checker, idempotency, optimistic locking và quyền theo kho/chi nhánh như tài liệu hiện hành yêu cầu.
- Backend là nguồn chuẩn cho quyền. UI không cho phép tự duyệt, xem dữ liệu nhạy cảm hoặc vượt scope chỉ bằng thao tác đổi URL.

## 5. Các giai đoạn đề xuất

Các giai đoạn là thứ tự triển khai gợi ý; cổng bắt buộc đầu tiên là audit. Chia nhỏ theo lát cắt có thể review và giữ tương thích với kiến trúc Flutter/FastAPI hiện có.

### Giai đoạn 0 — Khảo sát và baseline

- Đọc AGENTS.md, PRD/SRS, roadmap, acceptance hiện hành và tài liệu quyết định liên quan.
- Lập danh sách route/screen, component dùng chung, route API, mô hình dữ liệu, quyền theo vai trò, trạng thái nghiệp vụ và bằng chứng QA.
- Kiểm tra riêng landing/auth/demo, shell điều hướng, dashboard, catalog, receipt/issue, stocktake, movements, reports, users/roles và settings.
- Phân loại từng khả năng: đã có và được nghiệm thu; đã có một phần; chưa thấy bằng chứng; ngoài phạm vi. Ghi file/route/test làm bằng chứng.
- Chụp baseline vấn đề UI/UX, thiết bị/kích thước cần hỗ trợ và những rủi ro tương thích API.

### Giai đoạn 1 — Nền tảng giao diện

- Chốt user flow, sitemap, design tokens và mẫu component theo convention hiện có.
- Tạo/hoàn thiện public layout và authenticated app shell, sidebar đa cấp, header, breadcrumb, responsive navigation.
- Bảo đảm route guard, loading/error/empty states và accessibility cơ bản.

### Giai đoạn 2 — Điều hướng và trang cốt lõi

- Gắn menu với route/page/API đã xác minh.
- Ưu tiên tổng quan, danh mục/kho, danh sách phiếu, chi tiết phiếu, thông báo và hồ sơ theo persona hiện có.
- Không dựng số liệu giả như dữ liệu thực; fixture/demo phải được ghi rõ.

### Giai đoạn 3 — Luồng nghiệp vụ kho

- Làm rõ và hoàn thiện nhập, xuất/tiêu hao, kiểm kê, điều chỉnh, xem ledger và vòng đời chứng từ theo backend hiện có.
- Xác minh base unit, snapshot conversion factor, maker-checker, idempotency, transaction atomicity, reversal và MAC trước khi UI dựa vào chúng.
- Thêm lọc/tìm kiếm/phân trang và thông báo trạng thái phù hợp với API.

### Giai đoạn 4 — Quyền, báo cáo, responsive và phát hành

- Hoàn thiện ma trận vai trò × thao tác, audit trail, báo cáo và đối soát.
- Kiểm tra trải nghiệm desktop/tablet/mobile, accessibility, hiệu năng, luồng lỗi/mạng và các route trực tiếp.
- Thực hiện QA theo quy trình dự án, cập nhật acceptance evidence và hướng dẫn triển khai trước khi phát hành.

## 6. Tiêu chí nghiệm thu

- Hành trình công khai → đăng nhập/đăng ký/demo (chỉ các nhánh backend hỗ trợ) → vào ứng dụng có thể hoàn tất, có thông báo lỗi/thành công và quyền truy cập rõ.
- Tất cả mục điều hướng đã bật đều trỏ tới trang hoạt động hoặc trạng thái “chưa hỗ trợ” được chủ động thiết kế; không có liên kết chết hay menu khẳng định sai năng lực.
- Sidebar đa cấp hoạt động bằng chuột và bàn phím, thu gọn/mở rộng, giữ chỉ báo route hiện hành; header và breadcrumb nhất quán.
- Layout được kiểm tra ở các mốc mục tiêu theo PRD hiện hành (360, 768, 1280 px), không mất thao tác cốt lõi hoặc tạo tràn ngang ngoài chủ đích.
- Giao diện role-aware khớp quyền server; kiểm tra trực tiếp API/route vẫn chặn đúng các thao tác trái quyền.
- Phiếu nháp không làm đổi tồn. Chỉ luồng hoàn tất hợp lệ ghi một lần movement; retry không nhân đôi; hủy/sửa sau post dùng reversal/adjustment theo state machine được xác nhận.
- Balance sau giao dịch khớp ledger; đồng thời cập nhật movement, balance, audit và outbox có tính nguyên tử; kiểm tra tranh chấp đồng thời và đối soát.
- Quy đổi đơn vị dùng hệ số chụp trên dòng chứng từ; MAC đúng công thức và edge cases đã được product/backend chấp thuận.
- Báo cáo có lọc/phân trang và số liệu khớp nguồn chuẩn; trạng thái empty/loading/error và dữ liệu demo được phân biệt.
- Các luồng chính và ma trận vai trò được QA trên cấu hình/thiết bị được hỗ trợ; cập nhật tài liệu/bằng chứng theo chuẩn repo.

## 7. Chỉ dẫn cho Codex ở lượt triển khai kế tiếp

> Đọc `AGENTS.md`, tài liệu handoff này, `docs/01-prd.md`, `docs/SRS_QUAN_LY_KHO_TRA_SUA.md`, `docs/02-roadmap.md`, `docs/00-decisions.md`, `docs/03-architecture.md`, `docs/04-database.md`, `docs/05-workflows.md`, `docs/06-api.md`, `docs/10-qa.md` và acceptance mới nhất. Trước khi sửa code, kiểm tra `git status` và giữ nguyên mọi thay đổi có sẵn. Audit frontend Flutter routes/screens/components, backend routes/schemas/services/models/migrations, auth/RBAC, tests và UI acceptance evidence. Lập ma trận hiện trạng có đường dẫn/bằng chứng, xác định gaps đối với từng giai đoạn và đối chiếu mâu thuẫn với MVP ca trà sữa. Không giả định tính năng đã tồn tại từ tài liệu kế hoạch hoặc tên trường; không thêm module ngoài phạm vi đã được chấp thuận. Sau audit, đề xuất lát cắt đầu tiên nhỏ, giữ API/kiến trúc đang chạy, kèm acceptance và rủi ro trước khi triển khai. Khi triển khai được yêu cầu, sửa theo convention repo, chỉ thêm/sửa test phù hợp thay đổi và báo cáo chính xác phần đã kiểm chứng cùng phần còn thiếu bằng chứng. Dùng vkho.vn làm cảm hứng về cấu trúc thông tin; thiết kế nhận diện, nội dung và hình ảnh riêng cho QuanLyKho.

## 8. Tài liệu repository đã đối chiếu khi tạo handoff

- `AGENTS.md` — stack, cấu trúc, convention và quy trình.
- `docs/01-prd.md`, `docs/SRS_QUAN_LY_KHO_TRA_SUA.md` — MVP hiện tập trung vận hành kho trà sữa và ca làm.
- `docs/00-decisions.md`, `docs/02-roadmap.md` — ranh giới backend/UI và roadmap hiện có.
- `docs/04-database.md`, `docs/05-workflows.md`, `docs/06-api.md` — ledger, giao dịch và state machine hiện hành.
- `docs/acceptance/2026-10-26-milk-tea-baseline.md` — bằng chứng acceptance gần nhất, gồm trạng thái partial/needs UAT.
- `backend/app/api/routes/inventory.py` — code inventory có routes cho items, locations, balances, movements, requests và xử lý costing; điều này chưa tự chứng minh toàn bộ UX web đã hoàn tất.

Tài liệu này chỉ ghi nhận đề bài và kế hoạch audit/triển khai; không thực hiện thay đổi mã ứng dụng hay xác nhận các luồng đã đạt nghiệm thu.
