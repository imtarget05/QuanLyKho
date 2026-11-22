-- ==============================================================================
-- Migration: 0001_create_sop_schema.sql
-- Description: D1 schema for SOP Documents in Cloudflare Worker Lab
-- Target Database: sop-lab-db
-- ==============================================================================

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
