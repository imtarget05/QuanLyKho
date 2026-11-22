"""GraphQL layer for QuanLyKho banking & inventory domain.

Replaces REST API banking endpoints with a single GraphQL endpoint (/graphql).
All business logic delegates to existing services:
- general_ledger (double-entry)
- concurrency_service (pessimistic/optimistic locking)
- saga_orchestrator (distributed saga with compensation)
- audit_service / audit_chain (immutable hash-chain audit)
- outbox_service (transactional outbox)
- idempotency_service (strict idempotency key)
"""