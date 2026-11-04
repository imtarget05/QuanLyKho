# Runtime integrations

## Redis

Production login rate limiting requires `REDIS_URL` to use `rediss://` and
requires a reachable Redis service during startup. Redis errors return
`503 LOGIN_RATE_LIMIT_UNAVAILABLE`; the process-local counter is only a
development/test fallback. Configure the managed endpoint and credentials
through the deployment secret manager.

## Kafka

The worker publishes committed `outbox_events` to
`quanlykho.<event_type>` with Kafka idempotence and `acks=all`. The outbox row
is marked published only after `send_and_wait` succeeds, so a database or
worker failure leaves the row retryable (at-least-once delivery). Configure
`KAFKA_BOOTSTRAP_SERVERS` in production. Test/demo mode may run without Kafka
and continues to materialize local activity events.

Kafka events are integration notifications, not authorization. A downstream
consumer must create a maker-checker request for financial actions and must
not execute a transfer solely because an event was received.
