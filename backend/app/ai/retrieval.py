"""Small, inspectable retrieval index over the approved BankOps process documents."""

import os
import re
from pathlib import Path


def _get_docs_root() -> Path:
    env_dir = os.environ.get("DOCS_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p
    candidates = [
        Path(__file__).resolve().parents[3] / "docs",
        Path(__file__).resolve().parents[2] / "docs",
        Path(__file__).resolve().parents[1] / "docs",
        Path("/app/docs"),
        Path("/app/backend/docs"),
        Path("/root/quanlykho/docs"),
        Path("/root/docs"),
        Path.cwd() / "docs",
        Path.cwd().parent / "docs",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


DOCS_ROOT = _get_docs_root()
SOURCE_FILES = (
    "00-decisions.md",
    "01-prd.md",
    "05-workflows.md",
    "06-api.md",
    "08-security.md",
    "09-integrations-jobs.md",
    "12-glossary.md",
    "gap-register.md",
    "gap-summary.md",
)
_STOP = {
    "cho", "cua", "cac", "voi", "trong", "khi", "nhung", "duoc", "theo",
    "khong", "khotrasua", "nhu", "mot", "thoi", "hom", "nay", "noi", "the",
    "nao", "bao", "nhieu", "day", "do", "tai", "qua", "lai", "den", "ve",
    "hay", "hoac", "neu", "thi", "ma", "chua", "roi", "rat", "lam",
    "minh", "ban", "anh", "chi", "em", "ong", "ba", "sao", "dau", "co",
    "chut", "dung", "biet", "xem"
}

BUILTIN_SOP_KNOWLEDGE = [
    {
        "keywords": {"lap", "duyet", "phieu", "kho", "quyen", "maker", "checker", "staff", "approver"},
        "source": "docs/05-workflows.md",
        "section": "Quy định kiểm soát kép Maker - Checker và thẩm quyền duyệt phiếu",
        "content": (
            "📌 **Quy trình áp dụng**: Phân quyền & Kiểm soát kép Dual Control (Maker - Checker SOP).\n\n"
            "👤 **Người lập (Maker)**: Nhân viên ca trực, Pha chế chính, Thủ kho (role `staff`/`maker`) có quyền tạo phiếu yêu cầu (nhập, xuất, chuyển kho, điều chỉnh).\n\n"
            "🛡️ **Người duyệt (Checker)**: Quản lý cửa hàng, Kiểm soát viên, Admin (role `approver`/`admin`) kiểm tra thực tế và phê duyệt ghi sổ. Bắt buộc tuân thủ nguyên tắc `created_by != approved_by` (người tạo không được tự duyệt phiếu của chính mình).\n\n"
            "📑 **Căn cứ & Bằng chứng**: Mã phiếu kho hệ thống (REQ/STK), biên bản giao nhận đủ 2 chữ ký Maker & Checker, mã xác thực Audit Stamp SHA-256 đối soát trên sổ cái."
        ),
    },
    {
        "keywords": {"chot", "ca", "cong", "thuc", "ban", "giao", "ton", "so", "pos"},
        "source": "docs/05-workflows.md",
        "section": "Công thức đối soát và bàn giao ca trực",
        "content": (
            "📌 **Quy trình áp dụng**: Bàn giao ca trực & Kiểm đếm tồn quầy pha chế (Shift Handover SOP).\n\n"
            "📐 **Công thức tính toán**: `Tồn đầu ca + Nhập bổ sung trong ca - Tiêu hao định mức theo đơn POS - Xuất hủy/hỏng = Tồn cuối ca lý thuyết`. So sánh đối chiếu với số lượng kiểm đếm thực tế.\n\n"
            "👤 **Người lập (Maker)**: Trưởng ca hiện tại lập phiếu kiểm đếm và biên bản bàn giao ca.\n\n"
            "🛡️ **Người duyệt (Checker)**: Trưởng ca tiếp nhận hoặc Quản lý ca trực kiểm tra đối chiếu và ký xác nhận.\n\n"
            "📑 **Căn cứ & Bằng chứng**: Báo cáo tổng kết ca từ máy POS, biên bản kiểm đếm két tiền và nguyên vật liệu có chữ ký xác nhận của cả 2 ca."
        ),
    },
    {
        "keywords": {"min", "max", "lech", "kiem", "ke", "dinh", "muc", "xu", "ly", "chenh"},
        "source": "docs/05-workflows.md",
        "section": "Quy định xử lý chạm định mức Min/Max và lệch kiểm kê",
        "content": (
            "📌 **Quy trình áp dụng**: Quản trị an toàn tồn kho (Min/Max Safety Levels) & Xử lý sai lệch kiểm kê.\n\n"
            "⚠️ **Nguyên tắc xử lý**: Khi tồn khả dụng chạm hoặc dưới ngưỡng Min, hệ thống tự động cảnh báo để lập phiếu nhập/chuyển kho bổ sung. Khi phát hiện chênh lệch kiểm kê (lệch ≥ 10 đơn vị hoặc giá trị lớn), xếp loại High Risk, lập tức đếm lại và giải trình nguyên nhân.\n\n"
            "👤 **Người lập (Maker)**: Trưởng ca lập biên bản giải trình chênh lệch và tạo phiếu điều chỉnh (Adjustment).\n\n"
            "🛡️ **Người duyệt (Checker)**: Quản lý cửa hàng (Store Manager) hoặc Admin xem xét thực tế và duyệt phiếu.\n\n"
            "📑 **Căn cứ & Bằng chứng**: Phiếu kiểm kê kho (STK), biên bản giải trình nguyên nhân (đong hao hụt, đổ vỡ, lỗi pha chế), dấu kiểm toán hệ thống."
        ),
    },
    {
        "keywords": {"sua", "tuoi", "can", "date", "hsd", "fefo", "lo", "hang", "het", "han"},
        "source": "docs/05-workflows.md",
        "section": "Quy chuẩn bảo quản và quản lý hạn sử dụng FEFO",
        "content": (
            "📌 **Quy trình áp dụng**: Nguyên tắc nhập trước xuất trước theo hạn sử dụng (FEFO - First Expired, First Out).\n\n"
            "🥛 **Quy định xử lý sữa tươi / nguyên liệu tươi**: Lô sữa tươi cận date (còn ≤ 24-48 giờ) phải dán tem cảnh báo màu cam và ưu tiên dùng ngay trong ca. Nếu đã quá hạn sử dụng, nghiêm cấm pha chế cho khách, phải lập phiếu xuất hủy (Disposal Request).\n\n"
            "👤 **Người lập (Maker)**: Nhân viên quầy phát hiện và lập phiếu đề xuất xuất hủy nguyên liệu cận/quá hạn.\n\n"
            "🛡️ **Người duyệt (Checker)**: Quản lý cửa hàng kiểm tra thực tế tình trạng hàng hóa và ký duyệt tiêu hủy.\n\n"
            "📑 **Căn cứ & Bằng chứng**: Tem nhãn phụ lô hàng (Lot/Batch ID), mã HSD in trên bao bì nhà sản xuất, phiếu xuất hủy nguyên liệu có phê duyệt."
        ),
    },
]


def _terms(value: str) -> set[str]:
    import unicodedata

    plain = unicodedata.normalize("NFD", value.lower())
    plain = "".join(ch for ch in plain if unicodedata.category(ch) != "Mn")
    return {word for word in re.findall(r"[a-z0-9_]{3,}", plain) if word not in _STOP}


def retrieve(message: str, limit: int = 3) -> list[dict[str, str]]:
    query = _terms(message)
    if not query:
        return []
    docs_root = _get_docs_root()
    matches: list[tuple[int, dict[str, str]]] = []
    for filename in SOURCE_FILES:
        path = docs_root / filename
        if not path.is_file():
            continue
        heading = ""
        for paragraph in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
            if paragraph.startswith("#"):
                heading = paragraph.splitlines()[0].lstrip("# ").strip()
                continue
            content = paragraph.strip()
            if not content or content.startswith("```") or len(content) > 1800:
                continue
            heading_matches = len(query & _terms(heading))
            content_matches = len(query & _terms(content))
            score = heading_matches * 3 + content_matches
            # Require minimum relevance score of 3 to avoid single incidental word collisions
            if score >= 3:
                matches.append((score, {"source": f"docs/{filename}", "section": heading, "content": content[:1200]}))

    # Built-in SOP rules fallback when docs folder is incomplete or for standard operational questions
    if not matches:
        for item in BUILTIN_SOP_KNOWLEDGE:
            overlap = len(query & item["keywords"])
            if overlap >= 2 or (overlap >= 1 and len(query) <= 3):
                matches.append((overlap * 3, {"source": item["source"], "section": item["section"], "content": item["content"]}))

    matches.sort(key=lambda match: match[0], reverse=True)
    return [item for _, item in matches[:limit]]


def grounded_prompt(message: str, sources: list[dict[str, str]]) -> str:
    context = "\n\n".join(
        f"[{index}] {item['source']} — {item['section']}\n{item['content']}"
        for index, item in enumerate(sources, 1)
    )
    return (
        "Bạn là Khai — Trợ lý nghiệp vụ Quản Lý Kho Trà Sữa. "
        "Dựa vào các tài liệu nghiệp vụ được cung cấp bên dưới, hãy trả lời câu hỏi theo cấu trúc chuẩn nghiệp vụ ngân hàng & bán lẻ sau:\n"
        "1. 📌 **Quy trình áp dụng**: Nêu rõ tên quy chế hoặc quy trình chuẩn (SOP).\n"
        "2. 👤 **Người lập (Maker)**: Nêu rõ chức vụ/vai trò có thẩm quyền lập phiếu.\n"
        "3. 🛡️ **Người duyệt (Checker)**: Nêu rõ chức vụ có thẩm quyền phê duyệt (nhấn mạnh nguyên tắc bất di bất dịch Maker ≠ Checker).\n"
        "4. 📑 **Căn cứ & Bằng chứng**: Nêu các chứng từ, mã phiếu, biên bản hoặc mã băm đối soát.\n"
        "Trả lời súc tích, chuyên nghiệp, rõ ràng. Không tự ý bịa đặt thông tin ngoài tài liệu.\n\n"
        f"Tài liệu nghiệp vụ:\n{context}\n\nCâu hỏi: {message}"
    )
