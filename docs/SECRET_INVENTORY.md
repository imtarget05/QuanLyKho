# Secret Inventory — QuanLyKho

Generated: 2026-11-12
Source: `.env.example`, `render.yaml`
Convention: env vars only, `.env` ignored, no hardcoded tokens. `sync: false` = supplied via Render dashboard; `generateValue: true` = Render-generated.

## Backend (kho-tra-sua-fastapi)
| Key | Source | Status | Notes |
|-----|--------|--------|-------|
| AI_PROVIDER | render.yaml | value: disabled | P3.3 must change to cloudflare/ollama |
| CLOUDFLARE_ACCOUNT_ID | .env.example | placeholder | REPLACE_WITH_YOUR_CLOUDFLARE_ACCOUNT_ID |
| CLOUDFLARE_API_TOKEN | .env.example | placeholder | REPLACE_WITH_YOUR_CLOUDFLARE_API_TOKEN |
| CLOUDFLARE_MODEL | .env.example | value | @cf/meta/llama-3.1-8b-instruct |
| OLLAMA_BASE_URL | .env.example | value | http://localhost:11434 |
| OLLAMA_MODEL | .env.example | value | qwen2.5:1.5b |
| DATABASE_URL | render.yaml | sync: false | PostgreSQL 16 connection string |
| REDIS_URL | render.yaml | sync: false | Required for production login (fail closed) |
| BANKOPS_SIGNING_KEY | .env.example / render.yaml | placeholder / generateValue: true | |
| BANKOPS_SESSION_SECRET | .env.example / render.yaml | placeholder / generateValue: true | |
| SUPERVISOR_PIN | .env.example | placeholder | |
| ALLOWED_ORIGINS | .env.example | placeholder | |
| SMTP_HOST | render.yaml | value | smtp.gmail.com |
| SMTP_PORT | render.yaml | value | 587 |
| SMTP_USER | render.yaml | value | binhtan5734@gmail.com (review: hardcoded email) |
| SMTP_PASSWORD | render.yaml | sync: false | Gmail app password |
| SMTP_FROM_NAME | render.yaml | value | Ban Quản Trị Hệ Thống |
| APP_ENV | render.yaml | value: production | |
| SERVER_RELOAD | render.yaml | value: false | |
| FORWARDED_ALLOW_IPS | render.yaml | value: * | |
| FRONTEND_BASE_URL | render.yaml | value | https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev |

## Hardcode check
SMTP_USER is hardcoded in render.yaml (binhtan5734@gmail.com) — low risk (email only), but consider moving to sync: false secret in production. No other hardcoded tokens found outside `.env.example` placeholders.
