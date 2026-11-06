# Render readiness gap — 2026-11-06

- Source SHA observed in Render Dashboard: `6f187147e89dd7f4bd77a877279e69b9177b0fe6`.
- Render deployment: [Live deploy](https://dashboard.render.com/web/srv-db8esj689jmc73d8b420/deploys/dep-dbmlq7ec6qcc73b8qghg).
- Environment: public Render Free mirror at `https://kho-tra-sua-fastapi.onrender.com`.
- Observation time: approximately 2026-11-06 05:20–05:25 UTC.

## Actual observations before this fix

| Request | Expected | Actual |
| --- | --- | --- |
| `GET /api/v1/health/live` | Service process alive | HTTP 200, `status=alive` |
| `GET /api/v1/health/ready` | Required login dependencies available | HTTP 200, `status=ready`, database `ready` |
| `POST /api/v1/auth/login` with a seeded synthetic demo account | Demo login available | HTTP 503, `LOGIN_RATE_LIMIT_UNAVAILABLE` |

The login request used only the repository's synthetic demo account. No token,
password, user record, database URL or response body is stored in this document.
The readiness check only probed PostgreSQL; production login requires a TLS
Redis rate limiter and correctly fails closed without it. The old readiness
response therefore overstated the service's usable state.

## Change and verification

Readiness now checks the rate limiter required by login, returns HTTP 503 when
it is unavailable, and reports only `ready` or `not_ready` for dependencies.
This keeps connection strings and other exception details out of the public
response. The check runs in a thread so a slow Redis ping does not block the
event loop.

`backend/tests/test_health_readiness_dependencies.py` was run before the fix:
3 failed, including a 200 response with Redis unavailable and a DB URL in the
error response. After the fix: 3 passed. Ruff passed on both changed Python
files. Full CI is required on this PR SHA before merging.

This change makes the health signal honest. It does not provision Redis or make
Render login available. The Modal demo API did accept the synthetic account,
but its deployed revision is from a different source commit and is not
same-SHA proof for this Render release.

The owner chose to keep Render in production profile. Configure a Redis URL
with the `rediss://` scheme in the service's Render Environment under the name
`REDIS_URL`; do not put its value in Git or this report. The Render blueprint
now declares that variable without a value and uses `/api/v1/health/ready` as
the health check. After updating the environment, redeploy and verify readiness,
demo login, a business journey and the deployed source SHA. Until then, the
Render API remains OPEN.
