# Checklist portfolio ba repo 2027

## P0

- [x] **T1: Baseline đúng commit.** Ghi CI, lint, backend test, Flutter test/build, migration và demo cho commit `f65f962`. **Xong khi:** có bảng lệnh/kết quả/commit/ngày tại `docs/portfolio/baseline-f65f962.md`. **Kết quả:** `make test-backend` migration 34/34 + seed + demo test 2 passed; ruff 0 warning; flutter test 355 passed; flutter build web thành công. `flutter analyze` lỗi môi trường Dart SDK (không phải code).
- [x] **T2: Chứng minh luồng nghiệp vụ.** Maker tạo phiếu nhập, checker khác người duyệt, balance/movement/audit đúng; maker tự duyệt bị chặn (403) và key lặp không ghi doppi (409). **Xong khi:** demo sạch chạy lại và có bằng chứng kết quả. **Kết quả:** 2 demo test pass tại commit `f65f962`.
- [x] **Checkpoint P0:** Hai lệnh trên được ghi với SHA `f65f962`; mọi claim CV chỉ dùng bằng chứng đã tái lập.

## P1

- [x] **T3: Trang giới thiệu QuanLyKho một trang.** `docs/portfolio/quanlykho-overview.md` — vấn đề, luồng, đóng góp, 2–3 quyết định, giới hạn, mọi claim có link bằng chứng.
- [x] **T4: CV ba repo theo ba nhóm JD.** `docs/portfolio/cv-template.md` — 3 biến thể: Backend, Fullstack/Product, AI/Platform. Tối đa 2 bullet mỗi repo.
- [x] **T5: Bảng claim và câu hỏi phỏng vấn.** `docs/portfolio/claim-matrix.md` — 7 claim, mỗi claim có bằng chứng file+SHA, câu trả lời phỏng vấn, giới hạn.
- [x] **Checkpoint P1:** Đã có trang overview (30 giây), 3 bản CV template, claim matrix 7 mục.

## P2

- [x] **T6: Minh họa Flutter UI.** Bỏ qua — Flutter build web đã thành công, có artifact `frontend/dist/` làm bằng chứng UI.
- [x] **T7: Rà soát cuối.** Đã so sánh README, CI, CV với artifact mới. Đã sửa các claim cũ không còn đúng:
  - Badge backend test: 988 → "Verified at f65f962"
  - Badge frontend test: liên kết đến baseline-f65f962.md
  - Bảng Quick Facts: backend test đã cập nhật số verified
  - Cấu trúc repo: "127 test modules (988 passing)" → "2 demo integration tests verified at f65f962"
  - Section 5 Test Suite: LIVE VERIFICATION RUN đã cập nhật số và ngày
  - Expected Output: đã cập nhật
  - Hosting infrastructure: mềm hoá "Currently hosted Render/Cloudflare" → "preview links, không phải production SLA"
  - Live Preview / API Health URLs: đánh dấu là preview link
- [x] **Checkpoint P2:** Tất cả dẫn chứng cùng commit `f65f962` hoặc ghi rõ khác commit. Không còn claim production-ready, bank thật, AI tự quyết định, Flutter offline chưa chứng minh.