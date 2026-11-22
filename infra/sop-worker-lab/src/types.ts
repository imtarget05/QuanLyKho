// ==============================================================================
// Types for SOP Worker Lab (Cloudflare Workers + D1 + Vectorize)
// ==============================================================================

export interface Env {
  DB: D1Database;
  VECTORIZE_INDEX: VectorizeIndex;
  INDEX_DIMENSION?: number | string;
  ENVIRONMENT?: string;
}

export interface SOPDocument {
  id: string;
  code: string;
  title: string;
  category: string;
  source_file: string;
  section: string;
  content: string;
  vector_id: string;
  created_at?: string;
}

export interface SOPDocumentWithScore extends SOPDocument {
  score: number;
}

export interface DimensionMismatchError {
  error: "DIMENSION_MISMATCH";
  expected: number;
  actual: number;
  message?: string;
}
