"""Banking API entry point matching dispatch write ownership (Milestones M2-M5).

Exports the banking APIRouter containing:
- /banking/transfer (legacy TCC transfer)
- /banking/transfers/concurrent (M4: transfer with resource ordering & concurrency control)
- /banking/reserve (TCC reserve)
- /banking/confirm (TCC confirm)
- /banking/cancel (TCC cancel)
- /banking/saga/execute (M4: triggers distributed saga with automated compensation)
- /banking/saga/{saga_id} (M4: retrieves saga status & step audit log)
- /banking/audit/record (M5: records cryptographic audit entry)
- /banking/audit/verify (M5: scans and verifies cryptographic audit chain integrity)
- /banking/audit/trail (M5: lists audit records with sequence and hashes)
- /banking/idempotency/execute (M3: idempotent operation execution)
- /banking/idempotency/{key} (M3: query idempotency status & cached response)
- /banking/outbox/emit (M3: transactional outbox event emission)
- /banking/outbox/drain (M3: async outbox drain worker)
- /banking/outbox/events (M3: list outbox events)
"""

from app.api.routes.banking import router

__all__ = ["router"]
