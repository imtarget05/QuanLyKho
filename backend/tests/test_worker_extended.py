"""Tests for worker parity (P7) - extended coverage."""

from __future__ import annotations

import asyncio
import uuid

from app import worker


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value


class _Session:
    def __init__(self, result):
        self.result = result
        self.statements = []
        self.added = []
        self.commits = 0

    async def execute(self, statement):
        self.statements.append(statement)
        return _ScalarResult(self.result)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


def test_worker_has_claim_job_function():
    assert hasattr(worker, "claim_job")
    assert hasattr(worker, "run_job_with_retry")
    assert hasattr(worker, "dispatch_outbox")
    assert hasattr(worker, "poll_once")
    assert hasattr(worker, "process_jobs")


def test_worker_has_lease_columns():
    from app.models.activity import Job
    expected = {"lease_owner", "lease_token", "lease_until", "heartbeat_at", "retry_count", "next_attempt"}
    assert expected <= set(Job.__table__.columns.keys())


def test_worker_job_claim_skip_locked():
    job = type("Job", (), {"id": uuid.uuid4(), "type": "sla_reminder", "status": "queued"})()
    session = _Session(job)
    claimed = asyncio.run(worker.claim_job(session))
    assert claimed is job
