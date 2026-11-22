// ==============================================================================
// Cloudflare Worker Lab: SOP Retrieval Engine (D1 + Vectorize)
// Dedicated Standalone Project: infra/sop-worker-lab/
// (Isolated from retired infra/cloudflare-worker/ per ADR 0001)
// ==============================================================================

import { Hono } from "hono";
import { cors } from "hono/cors";
import type { Env, SOPDocument, SOPDocumentWithScore } from "./types.js";
import {
  CANONICAL_INDEX_DIMENSION,
  CANONICAL_SOPS,
  generateDeterministicEmbedding
} from "./sop_data.js";

const app = new Hono<{ Bindings: Env }>();

// Enable CORS for lab clients and tests
app.use("*", cors());

// Helper to determine the configured index dimension
function getExpectedDimension(env: Env): number {
  if (env.INDEX_DIMENSION) {
    const parsed = Number(env.INDEX_DIMENSION);
    if (!Number.isNaN(parsed) && parsed > 0) {
      return parsed;
    }
  }
  return CANONICAL_INDEX_DIMENSION;
}

// ------------------------------------------------------------------------------
// GET /health - Check D1 and Vectorize index bindings
// ------------------------------------------------------------------------------
app.get("/health", async (c) => {
  const env = c.env;
  let d1Healthy = false;
  let d1Error: string | null = null;
  let vectorizeHealthy = false;
  let vectorizeError: string | null = null;

  // Check D1 binding
  try {
    if (env.DB) {
      const probe = await env.DB.prepare("SELECT 1 AS alive").first<{ alive: number }>();
      d1Healthy = probe?.alive === 1;
    } else {
      d1Error = "DB binding missing";
    }
  } catch (err: any) {
    d1Error = err?.message || String(err);
  }

  // Check Vectorize binding
  try {
    if (env.VECTORIZE_INDEX) {
      vectorizeHealthy = true;
    } else {
      vectorizeError = "VECTORIZE_INDEX binding missing";
    }
  } catch (err: any) {
    vectorizeError = err?.message || String(err);
  }

  const dimension = getExpectedDimension(env);
  const status = d1Healthy && vectorizeHealthy ? "healthy" : "degraded";

  return c.json({
    status,
    lab: "sop-worker-lab",
    environment: env.ENVIRONMENT || "lab",
    dimension,
    bindings: {
      d1: {
        configured: Boolean(env.DB),
        healthy: d1Healthy,
        database: "sop-lab-db",
        error: d1Error
      },
      vectorize: {
        configured: Boolean(env.VECTORIZE_INDEX),
        healthy: vectorizeHealthy,
        index: "sop-lab-index",
        dimension,
        error: vectorizeError
      }
    },
    timestamp: new Date().toISOString()
  });
});

// ------------------------------------------------------------------------------
// GET /sop/documents - List all SOP records from D1
// ------------------------------------------------------------------------------
app.get("/sop/documents", async (c) => {
  const env = c.env;
  if (!env.DB) {
    return c.json({ error: "SERVICE_UNAVAILABLE", message: "D1 database binding DB is not available" }, 503);
  }

  try {
    const result = await env.DB.prepare(
      "SELECT id, code, title, category, source_file, section, content, vector_id, created_at FROM sop_documents ORDER BY code ASC"
    ).all<SOPDocument>();

    return c.json({
      total: result.results ? result.results.length : 0,
      documents: result.results || []
    });
  } catch (err: any) {
    return c.json({ error: "DATABASE_ERROR", message: err?.message || String(err) }, 500);
  }
});

// ------------------------------------------------------------------------------
// GET /sop/documents/:code - Get specific SOP document by code (e.g. SOP-01)
// ------------------------------------------------------------------------------
app.get("/sop/documents/:code", async (c) => {
  const env = c.env;
  const code = c.req.param("code").toUpperCase();

  if (!env.DB) {
    return c.json({ error: "SERVICE_UNAVAILABLE", message: "D1 database binding DB is not available" }, 503);
  }

  try {
    const doc = await env.DB.prepare(
      "SELECT id, code, title, category, source_file, section, content, vector_id, created_at FROM sop_documents WHERE UPPER(code) = ?"
    )
      .bind(code)
      .first<SOPDocument>();

    if (!doc) {
      return c.json({ error: "NOT_FOUND", message: `SOP document with code '${code}' not found` }, 404);
    }

    return c.json({ document: doc });
  } catch (err: any) {
    return c.json({ error: "DATABASE_ERROR", message: err?.message || String(err) }, 500);
  }
});

// ------------------------------------------------------------------------------
// POST /sop/seed - Seed canonical or custom SOP documents with dimension check
// ------------------------------------------------------------------------------
app.post("/sop/seed", async (c) => {
  const env = c.env;
  const expectedDim = getExpectedDimension(env);

  if (!env.DB) {
    return c.json({ error: "SERVICE_UNAVAILABLE", message: "D1 database binding DB is not available" }, 503);
  }
  if (!env.VECTORIZE_INDEX) {
    return c.json({ error: "SERVICE_UNAVAILABLE", message: "VECTORIZE_INDEX binding is not available" }, 503);
  }

  let itemsToSeed = CANONICAL_SOPS;

  // Optional custom items in request body
  try {
    const contentType = c.req.header("content-type") || "";
    if (contentType.includes("application/json")) {
      const body = await c.req.json().catch(() => null);
      if (body && Array.isArray(body.documents) && body.documents.length > 0) {
        itemsToSeed = body.documents.map((item: any, idx: number) => ({
          id: item.id || `doc-custom-${idx + 1}`,
          code: item.code || `SOP-CUSTOM-${idx + 1}`,
          title: item.title || "Custom SOP",
          category: item.category || "General",
          source_file: item.source_file || "docs/custom.md",
          section: item.section || "General Section",
          keywords: item.keywords || [],
          content: item.content || "",
          vector_id: item.vector_id || `vec-custom-${idx + 1}`,
          vector: item.vector || generateDeterministicEmbedding(item.content || "", expectedDim)
        }));
      }
    }
  } catch {
    // Fall back to CANONICAL_SOPS
  }

  // Enforce strict vector dimension validation for ALL items before seeding
  for (const item of itemsToSeed) {
    if (!Array.isArray(item.vector) || item.vector.length !== expectedDim) {
      return c.json(
        {
          error: "DIMENSION_MISMATCH",
          expected: expectedDim,
          actual: Array.isArray(item.vector) ? item.vector.length : 0,
          message: `Vector for document '${item.code}' has dimension ${item.vector?.length}, expected ${expectedDim}`
        },
        400
      );
    }
  }

  try {
    // 1. Seed into D1 sop_documents
    const d1Statements = itemsToSeed.map((doc) =>
      env.DB.prepare(
        `INSERT OR REPLACE INTO sop_documents (id, code, title, category, source_file, section, content, vector_id)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        doc.id,
        doc.code,
        doc.title,
        doc.category,
        doc.source_file,
        doc.section,
        doc.content,
        doc.vector_id
      )
    );
    await env.DB.batch(d1Statements);

    // 2. Seed vectors into Vectorize
    const vectorsToUpsert = itemsToSeed.map((doc) => ({
      id: doc.vector_id,
      values: doc.vector,
      metadata: {
        code: doc.code,
        title: doc.title,
        category: doc.category
      }
    }));
    await env.VECTORIZE_INDEX.upsert(vectorsToUpsert);

    return c.json({
      status: "SEEDED",
      seeded_count: itemsToSeed.length,
      dimension: expectedDim,
      documents: itemsToSeed.map((d) => ({
        id: d.id,
        code: d.code,
        title: d.title,
        category: d.category,
        vector_id: d.vector_id
      }))
    });
  } catch (err: any) {
    return c.json({ error: "SEED_FAILED", message: err?.message || String(err) }, 500);
  }
});

// ------------------------------------------------------------------------------
// Search Handler (GET & POST) - Similarity search against Vectorize & D1 Join
// ------------------------------------------------------------------------------
async function handleSearch(c: any) {
  const env: Env = c.env;
  const expectedDim = getExpectedDimension(env);

  if (!env.DB) {
    return c.json({ error: "SERVICE_UNAVAILABLE", message: "D1 database binding DB is not available" }, 503);
  }
  if (!env.VECTORIZE_INDEX) {
    return c.json({ error: "SERVICE_UNAVAILABLE", message: "VECTORIZE_INDEX binding is not available" }, 503);
  }

  let queryText: string | undefined;
  let rawVector: any = undefined;
  let topK = 5;

  if (c.req.method === "GET") {
    queryText = c.req.query("q");
    const rawVecParam = c.req.query("vector");
    if (rawVecParam) {
      try {
        rawVector = JSON.parse(rawVecParam);
      } catch {
        rawVector = rawVecParam.split(",").map((v: string) => Number(v.trim()));
      }
    }
    const topKParam = c.req.query("topK");
    if (topKParam) {
      const parsed = parseInt(topKParam, 10);
      if (!Number.isNaN(parsed) && parsed > 0) topK = parsed;
    }
  } else if (c.req.method === "POST") {
    const body = await c.req.json().catch(() => ({}));
    queryText = body.q;
    rawVector = body.vector;
    if (body.topK && typeof body.topK === "number") topK = body.topK;
  }

  let searchVector: number[];

  // If explicit vector is supplied, strictly validate dimension
  if (rawVector !== undefined) {
    if (!Array.isArray(rawVector) || rawVector.length !== expectedDim) {
      return c.json(
        {
          error: "DIMENSION_MISMATCH",
          expected: expectedDim,
          actual: Array.isArray(rawVector) ? rawVector.length : typeof rawVector === "object" ? -1 : 0
        },
        400
      );
    }
    searchVector = rawVector;
  } else if (queryText && queryText.trim().length > 0) {
    // Generate deterministic 768-dim embedding from query text
    searchVector = generateDeterministicEmbedding(queryText, expectedDim);
    if (searchVector.length !== expectedDim) {
      return c.json(
        {
          error: "DIMENSION_MISMATCH",
          expected: expectedDim,
          actual: searchVector.length
        },
        400
      );
    }
  } else {
    return c.json(
      {
        error: "BAD_REQUEST",
        message: "Missing search parameter: provide 'q' (text query) or 'vector' (array of 768 floats)"
      },
      400
    );
  }

  try {
    // 1. Query Vectorize Index
    const vectorizeResponse = await env.VECTORIZE_INDEX.query(searchVector, {
      topK,
      returnMetadata: true
    });

    const matches = vectorizeResponse.matches || [];
    if (matches.length === 0) {
      return c.json({
        query: queryText || "(vector)",
        dimension: expectedDim,
        count: 0,
        results: []
      });
    }

    // 2. Fetch joined SOP document metadata from D1
    const vectorIds = matches.map((m) => m.id);
    const placeholders = vectorIds.map(() => "?").join(",");
    const d1Results = await env.DB.prepare(
      `SELECT id, code, title, category, source_file, section, content, vector_id, created_at
       FROM sop_documents WHERE vector_id IN (${placeholders})`
    )
      .bind(...vectorIds)
      .all<SOPDocument>();

    const docMap = new Map<string, SOPDocument>();
    for (const doc of d1Results.results || []) {
      docMap.set(doc.vector_id, doc);
    }

    // 3. Assemble scored results joined with D1
    const results: SOPDocumentWithScore[] = [];
    for (const match of matches) {
      const doc = docMap.get(match.id);
      if (doc) {
        results.push({
          ...doc,
          score: Number(match.score.toFixed(4))
        });
      }
    }

    return c.json({
      query: queryText || "(vector)",
      dimension: expectedDim,
      count: results.length,
      results
    });
  } catch (err: any) {
    return c.json({ error: "SEARCH_FAILED", message: err?.message || String(err) }, 500);
  }
}

app.get("/sop/search", handleSearch);
app.post("/sop/search", handleSearch);

export default app;
