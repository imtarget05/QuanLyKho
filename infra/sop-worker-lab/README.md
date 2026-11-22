# Cloudflare Worker Lab: SOP Retrieval Engine (D1 + Vectorize)

## Architecture & Overview
Dedicated standalone Cloudflare Worker lab for QuanLyKho SOP knowledge retrieval and semantic search.

> **CRITICAL ARCHITECTURAL BOUNDARY (ADR 0001)**:
> This lab is completely separate and isolated in `infra/sop-worker-lab/`. It does NOT add endpoints or modify the retired compatibility Worker (`infra/cloudflare-worker/`), which remains deprecated per ADR 0001.

### Technologies
- **Runtime**: Cloudflare Workers (TypeScript, Node.js compatibility)
- **API Framework**: Hono v4.6.0
- **Relational Storage**: Cloudflare D1 (`database_name = "sop-lab-db"`)
- **Vector Search**: Cloudflare Vectorize (`index_name = "sop-lab-index"`, dimension 768)
- **Embedding Specification**: 768-dimensional normalized vectors matching canonical transformer models

## D1 Schema
Migration file: `migrations/0001_create_sop_schema.sql`
```sql
CREATE TABLE IF NOT EXISTS sop_documents (
  id TEXT PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  category TEXT NOT NULL,
  source_file TEXT NOT NULL,
  section TEXT NOT NULL,
  content TEXT NOT NULL,
  vector_id TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sop_documents_code ON sop_documents(code);
CREATE INDEX IF NOT EXISTS idx_sop_documents_category ON sop_documents(category);
CREATE INDEX IF NOT EXISTS idx_sop_documents_vector_id ON sop_documents(vector_id);
```

## Vector Dimension Validation
The Worker enforces strict vector dimension validation before any insertion or search.
If an input vector dimension does not match 768, the Worker returns HTTP 400 Bad Request:
```json
{
  "error": "DIMENSION_MISMATCH",
  "expected": 768,
  "actual": 512
}
```

## API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check for D1 and Vectorize index bindings |
| `GET` | `/sop/documents` | Lists all SOP documents stored in D1 |
| `GET` | `/sop/documents/:code` | Retrieves a specific SOP document by code (e.g. `SOP-01`, `SOP-04`) |
| `POST` | `/sop/seed` | Seeds canonical or custom SOPs with dimension verification into D1 and Vectorize |
| `GET` | `/sop/search?q=...` | Semantic search against Vectorize with joined D1 metadata |
| `POST` | `/sop/search` | Vector or text search with payload `{"q": "..."}` or `{"vector": [...]}` |

## Canonical SOP Knowledge Base
Sourced from `QuanLyKho/backend/app/services/ai_retrieval.py` and `tests/data/golden_sop_agent.json`:
1. **SOP-01**: Quy trình kiểm soát kép Maker - Checker và thẩm quyền duyệt phiếu (Dual Control)
2. **SOP-02**: Công thức đối soát và bàn giao ca trực (Shift Handover)
3. **SOP-03**: Quy định xử lý chạm định mức Min/Max và lệch kiểm kê (Inventory Safety)
4. **SOP-04**: Quy chuẩn bảo quản và quản lý hạn sử dụng FEFO (FEFO Expiration)

## Verification
Run the automated test suite:
```bash
npm run typecheck
npm test
```
Verification evidence is exported to `QuanLyKho/docs/evidence/sop_worker_lab_verification.json`.
