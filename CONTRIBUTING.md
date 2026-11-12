# Contributing — QuanLyKho

Conventions: ECC (TDD, immutability, 80%+ coverage, conventional commits, security review, code review).

## Branch & commit
- Create branch from `main`: `feat/<scope>`, `fix/<scope>`, `refactor/<scope>`, `docs/<scope>`, `test/<scope>`, `chore/<scope>`, `ci/<scope>`.
- Commit message: `type(scope): summary` + optional body + `Signed-off-by: Name <email>`.
- No direct push to `main` — PR required, reviewed, CI green.

## TDD workflow
1. Write a failing test (RED).
2. Implement the smallest change to pass (GREEN).
3. Refactor (IMPROVE), keep coverage ≥ 80%.
4. Run `cd backend && poetry run pytest tests/ -v --cov=app --cov-report=xml` (backend) and `cd frontend && flutter test` (Flutter).

## Immutability
- Do not mutate input models; return a new copy.
- Python: Pydantic v2 `BaseModel`, SQLAlchemy 2.x `Mapped`/`mapped_column`; return new dict/list, avoid in-place ops on inputs.
- Dart: immutable value classes, `copyWith` pattern, no in-place list/map mutation on inputs.

## Security
- No hardcoded secrets. Env vars only; `.env` ignored. `.env.example` only contains `REPLACE_WITH_*` placeholders.
- `scripts/check_no_secrets.py` runs in CI (`secret-guard` job) and must pass before commit.
- Review `render.yaml` secrets (`sync: false` for `DATABASE_URL`, `REDIS_URL`, `SMTP_PASSWORD`, `BANKOPS_SIGNING_KEY`, `BANKOPS_SESSION_SECRET`).
- CI runs ruff 0.17.0, SonarCloud scan, pip-audit / npm audit equivalent.

## Code review
- Every PR needs ≥ 1 approval (`ecc:code-reviewer`).
- Auth / payment / user data changes additionally need `ecc:security-reviewer`.
- No merge with CI red or open security findings.

## File size
- Source file < 800 lines; split module if exceeded.

## Error handling
- Never swallow exceptions silently. Log detailed context server-side (structured JSON via `app/core/logger.py`); return safe, generic messages to the client.

## Repo-specific commands
- Backend: `cd backend && poetry install --with dev && poetry run ruff check . && DATABASE_URL=... poetry run alembic upgrade head && poetry run pytest tests/ -v --cov=app --cov-report=xml`
- Migrations: `poetry run alembic revision --autogenerate -m "desc"` then `poetry run alembic upgrade head`
- Frontend: `cd frontend && flutter pub get && flutter analyze --no-fatal-infos --no-fatal-warnings && flutter test && flutter build web --release`
- Local dev: `make dev` (docker compose up -d)
