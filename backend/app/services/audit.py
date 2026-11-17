"""Audit service module alias (re-exports app.services.audit_service)."""

from app.services.audit_service import (
    GENESIS_HASH,
    AuditEntry,
    AuditImmutabilityException,
    AuditVerificationResult,
    compute_audit_hash,
    compute_canonical_hash,
    get_audit_entry_by_id,
    get_audit_trail,
    record_audit_entry,
    verify_audit_chain_integrity,
)

__all__ = [
    "GENESIS_HASH",
    "AuditEntry",
    "AuditImmutabilityException",
    "AuditVerificationResult",
    "compute_audit_hash",
    "compute_canonical_hash",
    "get_audit_entry_by_id",
    "get_audit_trail",
    "record_audit_entry",
    "verify_audit_chain_integrity",
]
