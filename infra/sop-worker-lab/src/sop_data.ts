// ==============================================================================
// Canonical SOP Knowledge Dataset & Deterministic 768-Dimension Embeddings
// Sourced from:
//   - QuanLyKho/backend/app/services/ai_retrieval.py (BUILTIN_SOP_KNOWLEDGE)
//   - QuanLyKho/backend/tests/data/golden_sop_agent.json
// ==============================================================================

import type { SOPDocument } from "./types.js";

export const CANONICAL_INDEX_DIMENSION = 768;

export interface CanonicalSOPSeed extends SOPDocument {
  keywords: string[];
  vector: number[];
}

/**
 * Deterministically generates a normalized L2 vector of specified dimension
 * using token hashing and term frequency weighting.
 */
export function generateDeterministicEmbedding(text: string, dimension: number = CANONICAL_INDEX_DIMENSION): number[] {
  const vector = new Array<number>(dimension).fill(0);
  if (!text || text.trim().length === 0) {
    return vector;
  }

  // Normalize text: lowercase, remove special characters
  const normalized = text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, ""); // remove accents for robust matching

  const tokens = normalized.match(/[\p{L}\p{N}]+/gu) || [];
  if (tokens.length === 0) {
    return vector;
  }

  // Hash each token and 2-gram into dimension space
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    applyTokenToVector(token, vector, dimension, 1.0);

    if (i < tokens.length - 1) {
      const biGram = `${token}_${tokens[i + 1]}`;
      applyTokenToVector(biGram, vector, dimension, 1.5);
    }
  }

  // L2 normalize
  let norm = 0;
  for (let i = 0; i < dimension; i++) {
    norm += vector[i] * vector[i];
  }
  norm = Math.sqrt(norm);

  if (norm > 0) {
    for (let i = 0; i < dimension; i++) {
      vector[i] = Number((vector[i] / norm).toFixed(6));
    }
  }

  return vector;
}

function applyTokenToVector(term: string, vector: number[], dimension: number, weight: number): void {
  // FNV-1a 32-bit hash
  let hash = 2166136261;
  for (let i = 0; i < term.length; i++) {
    hash ^= term.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }

  const primaryIndex = Math.abs(hash) % dimension;
  const sign = (hash & 1) === 0 ? 1 : -1;
  vector[primaryIndex] += sign * weight;

  // Secondary projection for density
  const secondaryHash = Math.imul(hash ^ (hash >>> 16), 2246822507);
  const secondaryIndex = Math.abs(secondaryHash) % dimension;
  const secondarySign = (secondaryHash & 1) === 0 ? 1 : -1;
  vector[secondaryIndex] += secondarySign * (weight * 0.5);
}

export const CANONICAL_SOPS: CanonicalSOPSeed[] = [
  {
    id: "doc-sop-01",
    code: "SOP-01",
    title: "Quy trình kiểm soát kép Maker - Checker và thẩm quyền duyệt phiếu",
    category: "Dual Control",
    source_file: "docs/05-workflows.md",
    section: "Quy định kiểm soát kép Maker - Checker và thẩm quyền duyệt phiếu",
    keywords: ["maker", "checker", "dual", "control", "kiem", "soat", "kep", "duyet", "phieu", "staff", "approver"],
    content:
      "📌 **Quy trình áp dụng**: Phân quyền & Kiểm soát kép Dual Control (Maker - Checker SOP).\n\n" +
      "👤 **Người lập (Maker)**: Nhân viên ca trực, Pha chế chính, Thủ kho (role `staff`/`maker`) có quyền tạo phiếu yêu cầu (nhập, xuất, chuyển kho, điều chỉnh).\n\n" +
      "🛡️ **Người duyệt (Checker)**: Quản lý cửa hàng, Kiểm soát viên, Admin (role `approver`/`admin`) kiểm tra thực tế và phê duyệt ghi sổ. Bắt buộc tuân thủ nguyên tắc `created_by != approved_by` (người tạo không được tự duyệt phiếu của chính mình).\n\n" +
      "📑 **Căn cứ & Bằng chứng**: Mã phiếu kho hệ thống (REQ/STK), biên bản giao nhận đủ 2 chữ ký Maker & Checker, mã xác thực Audit Stamp SHA-256 đối soát trên sổ cái.",
    vector_id: "vec-sop-01",
    vector: [] // computed below
  },
  {
    id: "doc-sop-02",
    code: "SOP-02",
    title: "Công thức đối soát và bàn giao ca trực",
    category: "Shift Handover",
    source_file: "docs/05-workflows.md",
    section: "Công thức đối soát và bàn giao ca trực",
    keywords: ["shift", "handover", "ban", "giao", "ca", "truc", "chot", "pos", "ton", "ly", "thuyet"],
    content:
      "📌 **Quy trình áp dụng**: Bàn giao ca trực & Kiểm đếm tồn quầy pha chế (Shift Handover SOP).\n\n" +
      "📐 **Công thức tính toán**: `Tồn đầu ca + Nhập bổ sung trong ca - Tiêu hao định mức theo đơn POS - Xuất hủy/hỏng = Tồn cuối ca lý thuyết`. So sánh đối chiếu với số lượng kiểm đếm thực tế.\n\n" +
      "👤 **Người lập (Maker)**: Trưởng ca hiện tại lập phiếu kiểm đếm và biên bản bàn giao ca.\n\n" +
      "🛡️ **Người duyệt (Checker)**: Trưởng ca tiếp nhận hoặc Quản lý ca trực kiểm tra đối chiếu và ký xác nhận.\n\n" +
      "📑 **Căn cứ & Bằng chứng**: Báo cáo tổng kết ca từ máy POS, biên bản kiểm đếm két tiền và nguyên vật liệu có chữ ký xác nhận của cả 2 ca.",
    vector_id: "vec-sop-02",
    vector: [] // computed below
  },
  {
    id: "doc-sop-03",
    code: "SOP-03",
    title: "Quy định xử lý chạm định mức Min/Max và lệch kiểm kê",
    category: "Inventory Safety",
    source_file: "docs/05-workflows.md",
    section: "Quy định xử lý chạm định mức Min/Max và lệch kiểm kê",
    keywords: ["min", "max", "safety", "levels", "discrepancy", "lech", "kiem", "ke", "dinh", "muc", "adjustment"],
    content:
      "📌 **Quy trình áp dụng**: Quản trị an toàn tồn kho (Min/Max Safety Levels) & Xử lý sai lệch kiểm kê.\n\n" +
      "⚠️ **Nguyên tắc xử lý**: Khi tồn khả dụng chạm hoặc dưới ngưỡng Min, hệ thống tự động cảnh báo để lập phiếu nhập/chuyển kho bổ sung. Khi phát hiện chênh lệch kiểm kê (lệch ≥ 10 đơn vị hoặc giá trị lớn), xếp loại High Risk, lập tức đếm lại và giải trình nguyên nhân.\n\n" +
      "👤 **Người lập (Maker)**: Trưởng ca lập biên bản giải trình chênh lệch và tạo phiếu điều chỉnh (Adjustment).\n\n" +
      "🛡️ **Người duyệt (Checker)**: Quản lý cửa hàng (Store Manager) hoặc Admin xem xét thực tế và duyệt phiếu.\n\n" +
      "📑 **Căn cứ & Bằng chứng**: Phiếu kiểm kê kho (STK), biên bản giải trình nguyên nhân (đong hao hụt, đổ vỡ, lỗi pha chế), dấu kiểm toán hệ thống.",
    vector_id: "vec-sop-03",
    vector: [] // computed below
  },
  {
    id: "doc-sop-04",
    code: "SOP-04",
    title: "Quy chuẩn bảo quản và quản lý hạn sử dụng FEFO",
    category: "FEFO Expiration",
    source_file: "docs/05-workflows.md",
    section: "Quy chuẩn bảo quản và quản lý hạn sử dụng FEFO",
    keywords: ["fefo", "first", "expired", "first", "out", "sua", "tuoi", "can", "date", "hsd", "het", "han", "xuat", "huy"],
    content:
      "📌 **Quy trình áp dụng**: Nguyên tắc nhập trước xuất trước theo hạn sử dụng (FEFO - First Expired, First Out).\n\n" +
      "🥛 **Quy định xử lý sữa tươi / nguyên liệu tươi**: Lô sữa tươi cận date (còn ≤ 24-48 giờ) phải dán tem cảnh báo màu cam và ưu tiên dùng ngay trong ca. Nếu đã quá hạn sử dụng, nghiêm cấm pha chế cho khách, phải lập phiếu xuất hủy (Disposal Request).\n\n" +
      "👤 **Người lập (Maker)**: Nhân viên quầy phát hiện và lập phiếu đề xuất xuất hủy nguyên liệu cận/quá hạn.\n\n" +
      "🛡️ **Người duyệt (Checker)**: Quản lý cửa hàng kiểm tra thực tế tình trạng hàng hóa và ký duyệt tiêu hủy.\n\n" +
      "📑 **Căn cứ & Bằng chứng**: Tem nhãn phụ lô hàng (Lot/Batch ID), mã HSD in trên bao bì nhà sản xuất, phiếu xuất hủy nguyên liệu có phê duyệt.",
    vector_id: "vec-sop-04",
    vector: [] // computed below
  }
];

// Precompute 768-dim vectors for each canonical SOP
for (const sop of CANONICAL_SOPS) {
  const fullText = `${sop.code} ${sop.title} ${sop.category} ${sop.keywords.join(" ")} ${sop.section} ${sop.content}`;
  sop.vector = generateDeterministicEmbedding(fullText, CANONICAL_INDEX_DIMENSION);
}
