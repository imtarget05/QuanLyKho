# QuanLyKho — Enterprise Inventory & Treasury Operations Platform

[![Python 3.11](https://img.shields.io/badge/Python-3.11.15-blue.svg?logo=python&logoColor=white)](backend/pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16_tmpfs-4169E1.svg?logo=postgresql&logoColor=white)](docker-compose.yml)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0.35+-red.svg)](https://www.sqlalchemy.org)
[![Docker](https://img.shields.io/badge/Docker-Multi--stage_Non--root-2496ED.svg?logo=docker&logoColor=white)](backend/Dockerfile)
[![ArgoCD](https://img.shields.io/badge/GitOps-ArgoCD_Job-orange.svg?logo=argo&logoColor=white)](infra/k8s/base/migration-job.yaml)
[![Backend Tests](https://img.shields.io/badge/Backend_Tests-988_Passed_|_0_Failed-success.svg)](backend/tests/)
[![Frontend Tests](https://img.shields.io/badge/Frontend_Tests-355_Passed_|_0_Failed-success.svg)](frontend/test/)
[![Ruff](https://img.shields.io/badge/Linter-Ruff_0.17.0_Clean-black.svg)](backend/pyproject.toml)
[![Security Guard](https://img.shields.io/badge/Secrets_Guard-Passed-brightgreen.svg)](scripts/check_no_secrets.py)

> Enterprise inventory lifecycle and multi-branch treasury operations platform engineered in **Python 3.11**, **FastAPI**, **SQLAlchemy 2 (AsyncSession)**, and **PostgreSQL 16**. Features a mathematical **Double-Entry General Ledger** ($\sum \text{Debit} \equiv \sum \text{Credit}$), strict **Maker-Checker Dual Control** with anti-self-approval invariants, temporal role-based access control (**RBAC**) with instant cluster-wide session revocation, durable database idempotency, and a **Transactional Outbox** asynchronous worker pattern.

---

## 1. Executive Summary & 60-Second Overview

### The Problem
Multi-branch commercial operations face severe operational vulnerabilities when managing physical assets and cash drawers:
1. **Inventory Shrinkage & Overselling:** Uncoordinated concurrent transactions cause negative stock balances and race conditions.
2. **Untracked Cash Drawer Variance:** Disconnected cash receipts lack formal financial accounting and reconciliation against bank deposits.
3. **Internal Fraud & Rogue Overrides:** Unrestricted administrator access allows operators to approve their own transactions or alter audit histories.
4. **Cross-Branch Data Leakage:** Insecure direct object references (IDOR) expose sensitive tenant data across physical locations.
5. **Distributed Processing Failures:** Network partitions cause duplicate transaction submissions and inconsistent asynchronous broker events.

### The Engineering Solution
QuanLyKho was built from first principles to solve these challenges using bank-grade accounting principles, deterministic database state machines, and resilient asynchronous patterns:

| Engineering Dimension | Technical Implementation & Architectural Pattern |
| :--- | :--- |
| **Double-Entry Accounting** | Mathematical balance invariant ($\text{Debit} \equiv \text{Credit}$) enforced by PostgreSQL `CheckConstraint` and atomic sub-ledger-to-GL posting services. |
| **Maker-Checker Dual Control** | Invariant A1 (`maker_id != approver_id`) enforced across domain and route layers, blocking self-approval even for root administrators. |
| **Approval Security Gate** | Secondary Supervisor PIN gate for high-risk operations ($\ge 50$ units, $\ge 500\text{k VND}$) with a 5-attempt / 15-minute brute-force lockout. |
| **Temporal IAM & Branch Scoping** | Time-bounded `ScopeGrant` entities with automated database query scoping preventing cross-branch IDOR leaks. |
| **Instant Session Revocation** | Cluster-wide JWT revocation via atomic `auth_version` checks on every authenticated request, invalidating sessions immediately upon credential changes. |
| **Concurrency & Deadlock Prevention**| Ordered pessimistic row locks (`SELECT ... FOR UPDATE`), optimistic concurrency (`version_id_col`), and First-Expired, First-Out (FEFO) batch allocation. |
| **Durable Idempotency** | PostgreSQL-backed `idempotency_keys` table with SHA-256 payload validation, surviving node crashes and multi-replica restarts. |
| **Transactional Outbox Pattern** | Atomic dual-write of domain state and `outbox_events`, drained via a background worker using `SELECT ... FOR UPDATE SKIP LOCKED`. |
| **Append-Only Tamper-Evident Audit** | `audit_events` store protected by SQLAlchemy DBAPI-level event listeners physically intercepting and rejecting `UPDATE` and `DELETE` mutations. |
| **Zero-Downtime Database Evolutions**| 33 sequential Alembic migrations (spanning 001 to 034, 023 omitted) decoupled from pod autoscaling via Kubernetes ArgoCD migration jobs. |

### Quick Facts & Verified Quality Metrics

```
+-----------------------------------+--------------------------------------------------------------+
| Metric / Component                | Verified Status                                              |
+-----------------------------------+--------------------------------------------------------------+
| Backend Test Suite                | 988 PASSED, 8 skipped, 1 xfailed, 0 FAILED (997 test cases)  |
| Frontend Test Suite               | 355 PASSED, 0 FAILED (Flutter 3.24+ / Dart SDK ^3.4.0)       |
| Static Code Analysis              | Ruff 0.17.0: 100% clean (backend/ & ai/)                     |
| Security & Secret Guard           | Automated scanner: 0 credential patterns in tracked files    |
| Database Schema Migrations        | 33 sequential zero-downtime Alembic migrations (001 to 034, 023 omitted) |
| Primary Database Engine           | PostgreSQL 16 on tmpfs (ACID isolation, UUID PKs, Numeric)   |
| Distributed Cache & Backplane     | Redis 5.0+ (SSE pub/sub backplane & rate-limiting)           |
| Deployment Model                  | Multi-stage Docker (non-root appuser), ArgoCD GitOps, K8s    |
+-----------------------------------+--------------------------------------------------------------+
```

---

## 2. System Architecture & Request Lifecycle

The platform follows a clean hexagonal architecture decoupled from external infrastructure. Core business rules reside in pure domain services, while storage, messaging, and presentation communicate through strictly typed interfaces.

```
                              +---------------------------------------+
                              |   Flutter 3.24+ Web / Mobile Client   |
                              |   (Provider State, Secure Storage)    |
                              +---------------------------------------+
                                                  |
                                                  | HTTPS / SSE
                                                  v
                              +---------------------------------------+
                              |   Edge Reverse Proxy / Cloudflare     |
                              |   (IP Header Forwarding, SSL Term)    |
                              +---------------------------------------+
                                                  |
                                                  v
+-------------------------------------------------------------------------------------------------------+
| FastAPI Monolith Application (Python 3.11 / AsyncSession)                                             |
|                                                                                                       |
|  +--------------------+     +------------------------+     +---------------------------------------+  |
|  | Route Controllers  | --> | IAM & Branch Scoping   | --> | Dual-Control (Maker-Checker) Engine   |  |
|  | (/api/v1/...)      |     | (auth_version, Grants) |     | (Invariant A1, Supervisor PIN Gate)   |  |
|  +--------------------+     +------------------------+     +---------------------------------------+  |
|                                                                                |                      |
|  +-----------------------------------------------------------------------------+                      |
|  |                                                                                                    |
|  v                                                                                                    |
|  +------------------------+     +------------------------+     +-----------------------------------+  |
|  | Concurrency Controller | --> | Sub-Ledger Posting     | --> | General Ledger Posting Service    |  |
|  | (Ordered Row Locks)    |     | (Cash, Inventory, Lots)|     | (Debit == Credit Zero-Sum Check)  |  |
|  +------------------------+     +------------------------+     +-----------------------------------+  |
|                                                                                |                      |
+--------------------------------------------------------------------------------|----------------------+
                                                                                 |
                                       +-----------------------------------------+
                                       | Atomic Database Transaction (ACID)
                                       v
+-------------------------------------------------------------------------------------------------------+
| PostgreSQL 16 (tmpfs / High-Performance ACID Storage)                                                |
|                                                                                                       |
|  [coa_accounts]         [gl_journals]          [gl_journal_entries]   (CheckConstraints: Debit==Credit)
|  [inv_balances]         [inv_movements]        [inv_lot_balances]     (CheckConstraint: qty >= 0)     |
|  [cash_boxes]           [cash_journals]        [cash_entries]         (CheckConstraint: amount >= 0)  |
|  [iam_users]            [iam_scope_grants]     [org_branches]         (auth_version, Branch Scopes)   |
|  [idempotency_keys]     [audit_events]         [outbox_events]        (Append-Only DBAPI Listeners)   |
+-------------------------------------------------------------------------------------------------------+
               |                                                                    ^
               | Redis Pub/Sub (approval:events)                                    | SELECT FOR UPDATE
               v                                                                    | SKIP LOCKED
+-------------------------------+                                                   v
| Redis 5.0 Cluster Backplane   |                                +--------------------------------------+
| (Real-time SSE Notification   |                                | Distributed Background Worker Daemon |
| Broadcast Across Multi-Pods)  |                                | (app/worker.py: Heartbeat Leases)    |
+-------------------------------+                                +--------------------------------------+
                                                                                    |
                                                                                    | At-Least-Once Delivery
                                                                                    v
                                                                 +--------------------------------------+
                                                                 | Apache Kafka Event Broker            |
                                                                 | (Downstream Integration Pipelines)   |
                                                                 +--------------------------------------+
```

### Maker-Checker & Dual-Entry Ledger Request Flow

```
Maker User               FastAPI Gateway               PostgreSQL 16               Checker User
    |                           |                            |                          |
    | 1. POST /requests (Draft) |                            |                          |
    |-------------------------->|                            |                          |
    |                           | 2. INSERT request (status=pending)                    |
    |                           |--------------------------->|                          |
    |                           | 3. Broadcast SSE Event via Redis                      |
    |                           |------------------------------------------------------>| (Real-time Alert)
    |                           |                            |                          |
    |                           |                            | 4. POST /approve         |
    |                           |                            |    (With Idempotency-Key)|
    |                           |                            |<-------------------------|
    |                           | 5. Validate A1 Invariant:  |                          |
    |                           |    maker_id != approver_id |                          |
    |                           | 6. Verify Supervisor PIN   |                          |
    |                           |    (5-attempt lockout check|                          |
    |                           | 7. SELECT ... FOR UPDATE   |                          |
    |                           |    (Order locks on balances|                          |
    |                           |--------------------------->|                          |
    |                           | 8. Verify Debit == Credit  |                          |
    |                           |    Zero-sum posting        |                          |
    |                           | 9. Commit Transaction:     |                          |
    |                           |    - Update Balances       |                          |
    |                           |    - Insert GL Journals    |                          |
    |                           |    - Append Audit Event    |                          |
    |                           |    - Insert Outbox Row     |                          |
    |                           |--------------------------->|                          |
    |                           | 10. Return 200 OK          |                          |
    |                           |------------------------------------------------------>|
```

---

## 3. Core Engineering Problems & Technical Depth

### 3.1 Financial-Grade Double-Entry General Ledger & Sub-Ledger Engine

A fundamental challenge in enterprise resource planning is eliminating silent balance discrepancies between operational inventory/cash transactions and financial reports. 

#### Mathematical Invariant Enforcement
In QuanLyKho, financial accounting is governed by strict mathematical axioms implemented directly in the relational schema and domain services:
$$\sum_{i=1}^{n} \text{Debit}_i - \sum_{i=1}^{n} \text{Credit}_i = 0 \quad \text{where } \text{Debit}_i \ge 0, \; \text{Credit}_i \ge 0, \; (\text{Debit}_i > 0) \oplus (\text{Credit}_i > 0)$$

1. **Relational Constraints:** In `backend/app/models/ledger.py`, `GeneralLedgerEntry` enforces positive amounts and single-sided posting via PostgreSQL `CheckConstraint`:
   ```python
   __table_args__ = (
       CheckConstraint("debit >= 0 AND credit >= 0", name="debit_credit_non_negative"),
       CheckConstraint("(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)", name="exactly_one_positive"),
   )
   ```
2. **Chart of Accounts (COA) Validation:** In `coa_accounts`, `account_type` is restricted to `('asset', 'liability', 'equity', 'revenue', 'expense')` with valid `normal_balance` values (`'debit'` or `'credit'`). Standard Vietnamese accounting standard accounts are pre-seeded (`111`, `112`, `152`, `156`, `331`, `511`, `632`).
3. **Atomic Posting Service:** When sub-ledgers post entries to the General Ledger (`backend/app/services/general_ledger.py`), `post_subledger_journal` aggregates debits and credits, raising an unhandled `ValueError` if `debit_total != credit_total`. Journals are copied idempotently using PostgreSQL `on_conflict_do_nothing(index_elements=['source_type', 'source_journal_id'])`.
4. **Historical Immutability & Compensating Reversals:** Journal rows are strictly immutable. Corrections never execute an in-place `UPDATE`. Instead, a compensating journal entry is created with a foreign key pointer `reversal_of` linking back to the original entry (`backend/app/models/cash_sim.py`, `backend/app/models/inventory.py`).
5. **Reconciliation Engine:** Periodic automated jobs (`backend/app/api/routes/reconciliations.py`) cross-verify movement deltas against physical balance snapshots, isolating discrepancies into `reconciliation_exceptions` without silent automated patching.

---

### 3.2 Maker-Checker Dual Control & Anti-Self-Approval Architecture

To mitigate insider fraud and operational error, high-consequence operations (stock adjustments, inbound inventory acceptance, cash withdrawals) require dual authorization ("4-Eyes Principle").

```
+---------------------------------------------------------------------------------------+
| Maker-Checker Invariant A1: anti_self_approval                                        |
+---------------------------------------------------------------------------------------+
|  maker = request.maker_id                                                             |
|  approver = current_user.id                                                           |
|                                                                                       |
|  if str(maker) == str(approver):                                                      |
|      raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Self-approval is forbidden.")    |
+---------------------------------------------------------------------------------------+
```

1. **Unconditional Domain Rule:** Enforced at both the domain layer (`backend/app/domain/inventory.py`) and API routing layer (`backend/app/api/routes/inventory.py` and `backend/app/api/routes/cash_sim.py`). Even root administrative accounts (`role == 'admin'`) are strictly prohibited from approving tickets they originated.
2. **High-Risk Supervisor PIN Gate:** For movements exceeding threshold parameters ($\ge 50$ inventory units, or cash transactions $\ge 500{,}000\text{ VND}$), approvals require a secondary credential (`backend/app/services/approval_controls.py`).
   - Constant-time comparison via `hmac.compare_digest` prevents timing side-channel attacks.
   - Brute-force protection limits failed attempts to 5 within a 15-minute sliding window (`PIN_RATE_LIMIT_ATTEMPTS = 5`, `PIN_RATE_LIMIT_WINDOW_SECONDS = 900`), locking the approver out upon threshold breach.
3. **Real-Time Distributed SSE Event Bus:** The platform integrates an asynchronous `ApprovalEventBus` (`backend/app/services/approval_events.py`). When an approval event occurs, it publishes to a Redis Pub/Sub channel (`approval:events`). Multi-pod replicas forward events to connected Server-Sent Events (SSE) clients in real time, with graceful degradation to in-process async queues if Redis is unavailable.

---

### 3.3 IAM, Temporal Branch Scoping & Instant Session Revocation

The Identity and Access Management (IAM) layer combines Role-Based Access Control (RBAC) with granular spatial and temporal data tenancy.

1. **Multi-Tenant Branch & Location Scoping:** Rather than relying on frontend view filtering, authorization is enforced at the database query generation layer (`backend/app/api/routes/auth_utils.py`). The helper functions `get_accessible_location_ids` and `get_accessible_cashbox_ids` inspect the user's active `ScopeGrant` entities (`backend/app/models/iam.py`), injecting `WHERE branch_id IN (...)` clauses directly into SQLAlchemy select statements.
2. **Temporal Scope Grants:** Access permissions can be time-bounded using `valid_from` and `valid_to` timestamps on `ScopeGrant`, enabling temporary duty assignments and audit-compliant contractor provisioning.
3. **Instant Session Revocation via `auth_version`:**
   - Stateless JWT tokens typically introduce a vulnerability window during credential compromise or privilege changes.
   - QuanLyKho resolves this by embedding an integer `auth_version` within the JWT payload and user record (`User.auth_version`, `backend/app/models/iam.py`).
   - On every authenticated API invocation, `get_current_user` compares the token's `auth_version` against the live database record (`auth_utils.py:541-548`).
   - Administrative revocation, password resets, or single-session logins increment `auth_version += 1`, immediately invalidating all active tokens across the entire cluster without waiting for JWT TTL expiration.

---

### 3.4 Concurrency, Overselling Prevention & Transaction Integrity

Under high-frequency order placement or multi-terminal inventory operations, naive balance checks produce severe race conditions, deadlocks, and negative stock balances.

1. **Ordered Pessimistic Row Locking:** To prevent deadlocks, all database entities are locked in deterministic order. Critical balance reads execute with `select(...).with_for_update()`, guaranteeing sequential execution of competing mutations.
2. **Optimistic Versioning:** Long-running workflows utilize optimistic concurrency via integer `version` columns mapped to SQLAlchemy's `version_id_col` on `InventoryRequest`, `Balance`, `CashRequest`, and `CashBalance`. Clients submit HTTP `If-Match` headers, and version mismatches return HTTP 412 / 409 conflicts.
3. **Perishable Lot Allocation (FEFO):** Outbound stock allocations execute First-Expired, First-Out (FEFO) logic across `inv_lot_balances`, sorted by expiration date and creation timestamp, decrementing stock accurately while enforcing `qty >= 0` check constraints.
4. **Durable Idempotency Store:**
   - Network timeouts frequently cause clients to retry mutations. QuanLyKho implements a persistent `idempotency_keys` table (`backend/app/models/idempotency.py`).
   - The middleware hashes incoming request payloads (SHA-256). Identical subsequent requests return the cached response atomically. If a subsequent request reuses the key with an altered payload, the server rejects it with an HTTP 409 Conflict (`backend/app/services/idempotency.py`).
5. **Transactional Outbox Pattern & Background Worker:**
   - To prevent distributed dual-write inconsistencies between the relational database and downstream message brokers, domain events are committed to `outbox_events` within the primary business transaction (`backend/app/models/activity.py`).
   - A dedicated background worker daemon (`backend/app/worker.py`) polls and claims unpublished events using PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`.
   - Worker leases use heartbeat tokens (`lease_token`, `lease_until`) to ensure at-least-once delivery to Kafka while preventing redundant execution across worker replicas.

---

### 3.5 Tamper-Evident Append-Only Audit Trail

Regulatory compliance demands that operational activity logs cannot be pruned, altered, or retroactively falsified by malicious actors or compromised application logic.

1. **Audit Event Structure:** Every critical lifecycle action records an immutable row in `audit_events` capturing `actor_id`, `action`, `subject`, `before_hash`, `after_hash`, `request_id`, `occurred_at`, and structured JSON metadata.
2. **DBAPI-Level Mutation Interception:** To guarantee append-only semantics, SQLAlchemy event listeners are attached directly to the `AuditEvent` model (`backend/app/models/activity.py`):
   ```python
   def _reject_audit_mutation(connection, clause, operation):
       raise DBAPIError(clause, {"message": f"audit_events is append-only: {operation} forbidden"}, ...)

   @event.listens_for(AuditEvent, "before_update", propagate=True)
   def _block_audit_update(mapper, connection, target):
       _reject_audit_mutation(connection, None, "UPDATE")

   @event.listens_for(AuditEvent, "before_delete", propagate=True)
   def _block_audit_delete(mapper, connection, target):
       _reject_audit_mutation(connection, None, "DELETE")
   ```
   Any runtime attempt to issue an `UPDATE` or `DELETE` statement against `audit_events` is intercepted before execution and raises a fatal `DBAPIError`.

---

### 3.6 Database Schema Evolutions & GitOps Delivery

1. **33 Sequential Alembic Migrations:** Exactly 33 database migrations (`backend/alembic/versions/` spanning `001_initial.py` to `034_general_ledger_coa.py`, with revision 023 omitted and 024 linking directly to 022) follow expand/contract patterns, managing custom UUID generation, check constraints, composite partial indexes, and financial charts of accounts.
2. **Decoupling Migrations from Pod Scaling:** Pod entrypoints commonly execute migrations at startup, which causes severe database lock contention and race conditions when Kubernetes Horizontal Pod Autoscaler (HPA) scales pods out under load.
   - In QuanLyKho, `backend/entrypoint.sh` explicitly bypasses `alembic upgrade head`.
   - Migrations are decoupled and orchestrated via a dedicated Kubernetes migration Job (`infra/k8s/base/migration-job.yaml`, managed by ArgoCD), guaranteeing that schema evolution completes successfully before new application pods are deployed.
3. **Hardened Multi-Stage Container:** The backend `Dockerfile` utilizes a two-stage build (`python:3.11-slim`), pruning compiler toolchains from the final image, and executes under a dedicated non-root Linux user (`appuser`, UID 10001).
4. **Fail-Fast Entrypoint Security:** The entrypoint script (`backend/entrypoint.sh`) enforces strict configuration validation. In `APP_ENV=production` or `staging`, the container terminates immediately if `BANKOPS_SIGNING_KEY` is omitted, eliminating the risk of accidental deployment with ephemeral, insecure secrets.

---

## 4. Verifiable Claims-to-Evidence Matrix

To maintain strict engineering integrity, every architectural claim is verified against concrete source code, relational constraints, and executable test suites:

| # | Architectural Domain | Portfolio Claim | Verifiable Source Code & Line Numbers | Verification Command / Evidence |
| :-: | :--- | :--- | :--- | :--- |
| **1** | **Accounting Ledger** | Double-entry balance invariant ($\text{Debit} \equiv \text{Credit}$, non-negative debits/credits, exactly one positive side) | `backend/app/models/ledger.py:37-45, 101-109`<br>`backend/app/models/cash_sim.py:86-90`<br>`backend/app/models/inventory.py:351-355`<br>`backend/app/services/general_ledger.py:32-65` | `pytest tests/test_double_entry_ledger.py`<br>`pytest tests/test_general_ledger_unit.py` |
| **2** | **Ledger Immutability** | Historical journals are strictly immutable; corrections create new compensating records linked via `reversal_of` FK | `backend/app/models/inventory.py:341`<br>`backend/app/models/cash_sim.py:76`<br>`backend/app/models/ledger.py:69-73` | `pytest tests/test_cash_sim_money_path.py` |
| **3** | **Dual Control (Maker-Checker)** | Anti-self-approval invariant A1 (`maker_id != approver_id`) enforced domain-wide; administrators cannot self-approve | `backend/app/api/routes/inventory.py:1838-1839, 1860-1861`<br>`backend/app/api/routes/cash_sim.py:799-800`<br>`backend/app/domain/inventory.py:315-316` | `pytest tests/test_b01_foundation.py`<br>`pytest tests/test_business_journey_full.py` |
| **4** | **Approval Security** | High-risk movements ($\ge 50$ units, $\ge 500\text{k VND}$) require Supervisor PIN with 5-attempt / 15-minute brute-force lockout | `backend/app/services/approval_controls.py:15-16, 43-48, 57-71`<br>`backend/app/api/routes/inventory.py:1914-1919` | `pytest tests/test_approval_controls.py`<br>`pytest tests/test_approval_controls_service.py` |
| **5** | **Real-Time SSE & Redis** | Server-Sent Events bus with distributed Redis Pub/Sub backplane (`approval:events`) across multi-pod replicas | `backend/app/services/approval_events.py:19-120`<br>`backend/app/api/routes/inventory.py:2365-2372` | `pytest tests/test_approval_events_redis.py`<br>`pytest tests/test_sse_approvals.py` |
| **6** | **IAM & Branch Scoping** | Fine-grained RBAC with temporal `ScopeGrant` entities; database queries auto-filter by branch/location to prevent IDOR leaks | `backend/app/models/iam.py:27-43, 69-95`<br>`backend/app/api/routes/auth_utils.py:553-635` | `pytest tests/test_b2_authorization_scope.py`<br>`pytest tests/test_iam_admin.py` |
| **7** | **Session Revocation** | Cluster-wide instant token revocation via `auth_version`; credential changes immediately invalidate all active JWTs | `backend/app/models/iam.py:63`<br>`backend/app/api/routes/auth_utils.py:541-548`<br>`backend/app/api/routes/auth.py:163, 474-476` | `pytest tests/test_single_session_and_alerts.py`<br>`pytest tests/test_security_wave2_identity.py` |
| **8** | **Concurrency & Overselling** | Elimination of race conditions and overselling via ordered `SELECT ... FOR UPDATE` locks and optimistic `version_id_col` | `backend/app/api/routes/inventory.py:1850-1854, 1874, 1993, 2137`<br>`backend/app/models/inventory.py:99-101`<br>`backend/app/models/cash_sim.py:62-64` | `pytest tests/test_phase2b_fefo_outbound.py`<br>`pytest tests/test_reserved_inventory_and_return.py` |
| **9** | **Durable Idempotency** | Persistent PostgreSQL `idempotency_keys` table surviving pod crashes; returns cached response or 409 on altered payloads | `backend/app/models/idempotency.py:23-44`<br>`backend/app/services/idempotency.py:1-250`<br>`backend/app/api/routes/inventory.py:1831-1833, 2374` | `pytest tests/test_idempotency_durable.py`<br>`pytest tests/test_idempotency_key_header.py` |
| **10** | **Transactional Outbox** | Atomic dual-write of domain changes and outbox rows in single DB transaction; worker leases via `FOR UPDATE SKIP LOCKED` | `backend/app/models/activity.py:56-69`<br>`backend/app/worker.py:68-98, 369-409`<br>`backend/app/api/routes/inventory.py:2353` | `pytest tests/test_kafka_outbox.py`<br>`pytest tests/test_worker_jobs.py` |
| **11** | **Append-Only Audit** | Tamper-evident audit logs with SQLAlchemy event listeners physically intercepting and blocking `UPDATE` and `DELETE` at DBAPI level | `backend/app/models/activity.py:20-54` (`_block_audit_update`, `_block_audit_delete` raising `DBAPIError`) | `pytest tests/test_audit_events_pagination.py` |
| **12** | **Database Migrations** | 33 sequential zero-downtime Alembic migrations (spanning 001 to 034, 023 omitted) managing UUIDs, CheckConstraints, and partial indexes | `backend/alembic/versions/` (33 files from `001_initial.py` to `034_general_ledger_coa.py`) | `alembic upgrade head`<br>`pytest tests/test_migration_cost_price.py` |
| **13** | **GitOps & Delivery** | Multi-stage Docker container (non-root `appuser`), ArgoCD migration job decoupling, fail-fast signing key check | `backend/Dockerfile:1-50`<br>`backend/entrypoint.sh:18-43, 45-51`<br>`infra/k8s/base/migration-job.yaml:1-47` | `docker build backend/`<br>`kubectl kustomize infra/k8s/base` |
| **14** | **Observability** | End-to-end OpenTelemetry instrumentation for FastAPI routes, SQLAlchemy queries, and worker queue loops | `backend/app/api/telemetry.py:1-120`<br>`backend/app/worker.py:34-46, 426-444`<br>`backend/pyproject.toml:26-33` | `pytest tests/test_observability.py` |
| **15** | **Test Discipline** | 988 backend tests + 355 frontend tests verified; Ruff 0.17.0 clean; automated secret scan in CI | `backend/tests/` (127 test modules)<br>`frontend/test/` (355 unit tests)<br>`.github/workflows/ci.yml:1-122` | `pytest tests -q`<br>`flutter test`<br>`ruff check backend/ ai/`<br>`python3 scripts/check_no_secrets.py` |

---

## 5. Test Suite & Verification Results

The platform enforces rigorous automated testing across state transitions, race condition simulations, financial invariants, and boundary conditions.

### Test Execution Summary

```
========================================================================================
LIVE VERIFICATION RUN (2026-11-07):
Backend:  988 passed, 8 skipped, 1 xfailed, 0 failed in 779.54s (~12m 59s across 997 tests)
Frontend: 355 passed, 0 failed in 1m 15s (Flutter test)
Linter:   Ruff 0.17.0 clean (All checks passed across backend/ and ai/)
Secrets:  Secret guard scanner passed (0 credential patterns detected)
========================================================================================
```

### Reproducing Tests Locally

#### 1. Backend Automated Test Suite
The backend test harness uses PostgreSQL 16 on tmpfs. A safeguard fixture (`conftest.py:40-60`) actively rejects running mutations against any database not containing `_test` in its name.

```bash
# Navigate to backend directory
cd backend

# Configure environment variables pointing to test database and local Redis
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5433/bankops_test" \
REDIS_URL="redis://127.0.0.1:56379/0" \
APP_ENV=demo DEMO_MODE=true \
poetry run pytest tests -q

# Expected Output: 988 passed, 8 skipped, 1 xfailed, 0 failed
```

#### 2. Frontend Test Suite
```bash
# Navigate to frontend directory
cd frontend

# Execute Flutter tests
flutter test

# Expected Output: 00:01:15 +355: All tests passed!
```

#### 3. Static Analysis & Code Formatting
```bash
# Verify Ruff compliance
poetry run ruff check backend/ ai/
# Expected Output: All checks passed!
```

#### 4. Credential & Secret Scanner
```bash
# Run the local secret detection guard
python3 scripts/check_no_secrets.py
# Expected Output: Secret guard passed: no known credential patterns in tracked files.
```

---

## 6. Cloud & DevOps Infrastructure

The deployment infrastructure is designed according to modern GitOps and Twelve-Factor App principles.

```
+-----------------------------------------------------------------------------------+
| Kubernetes Cluster Deployment Topology                                            |
|                                                                                   |
|  [ArgoCD Migration Job]                                                           |
|       |                                                                           |
|       v                                                                           |
|  +--------------------+                                                           |
|  | Migration Job      | ---> Applies 33 Alembic Migrations to 034 (runs to completion) |
|  +--------------------+                                                           |
|       |                                                                           |
|       v (Post-Sync Deployment Rollout)                                            |
|  +--------------------+      +--------------------+      +---------------------+  |
|  | BankOps API Pod 1  |      | BankOps API Pod 2  |      | Background Worker   |  |
|  | (FastAPI Runtime)  |      | (FastAPI Runtime)  |      | (SKIP LOCKED Queue) |  |
|  +--------------------+      +--------------------+      +---------------------+  |
|            |                          |                             |             |
|            +------------+-------------+                             |             |
|                         |                                           |             |
|                         v                                           v             |
|             +-----------------------+                   +-----------------------+ |
|             | PostgreSQL 16 (State) |                   | Redis Pub/Sub & Cache | |
|             +-----------------------+                   +-----------------------+ |
+-----------------------------------------------------------------------------------+
```

### Kubernetes & ArgoCD GitOps
- **Manifest Directory:** Declarative Kustomize overlays in `infra/k8s/base/` define API deployments, worker daemons, config maps, and ingress configurations.
- **Decoupled Migration Job:** `infra/k8s/base/migration-job.yaml` runs migrations as a dedicated Kubernetes Job managed by ArgoCD (`app.kubernetes.io/managed-by: argocd`), executing `alembic upgrade head` independently of pod lifecycle to eliminate database lock contention.
- **Worker Separation:** Asynchronous job processing runs as a dedicated workload decoupled from customer-facing API request pools, preventing long-running queue drains from starving HTTP worker threads.

### Container Security
- **Multi-Stage Build:** `backend/Dockerfile` separates dependency compilation from the execution image, keeping the attack surface minimal.
- **Non-Root Execution:** Containers run under unprivileged user `appuser` (UID 10001, GID 10001).
- **Fail-Fast Entrypoint:** `backend/entrypoint.sh` blocks container startup in staging and production if `BANKOPS_SIGNING_KEY` is missing.
- **Proxy IP Resolution:** `FORWARDED_ALLOW_IPS` configuration guarantees accurate client IP rate limiting when operating behind Cloudflare or Nginx reverse proxies.

---

## 7. Operational Boundaries & Engineering Integrity

In adherence to evidence-first engineering standards, the boundary between production-grade application architecture and preview deployment infrastructure is explicitly documented:

| Component | Production-Ready Core Engine | Demo Preview Environment |
| :--- | :--- | :--- |
| **Transaction Processing** | Full ACID guarantees, ordered row locking, mathematical double-entry invariants, and tamper-evident audit logs. | Seeded with 10 demo users, 30 catalog items, 33 balances, and 3 cashboxes for live scenario evaluation. |
| **Hosting Infrastructure** | Containerized for Kubernetes / AKS deployment via declarative Kustomize manifests and ArgoCD GitOps. | Currently hosted on Render Free tier (`kho-tra-sua-fastapi`) and Cloudflare Pages (`quan-ly-kho-tra-sua.pages.dev`). |
| **Simulation Scope** | Full accounting chart (`coa_accounts`), sub-ledger posting, and cashier balance management. | Food-and-beverage retail items and cash drawers are simulated; no active integration with external banking networks (e.g. SWIFT, NAPAS) or payment gateways. |
| **Cache & Event Bus** | Production clusters utilize distributed Redis clusters for SSE backplane and Celery/Kafka message queues. | Demo mode supports fail-open graceful degradation to in-process async queues when Redis is not provisioned. |

---

## 8. Repository Structure

```
QuanLyKho/
├── backend/                             # Core FastAPI Application & Services
│   ├── alembic/                         # Database Migration Scripts
│   │   ├── versions/                    # 33 sequential migrations (001 to 034, 023 omitted)
│   │   └── env.py                       # Migration runtime configuration
│   ├── app/
│   │   ├── api/                         # HTTP routing & API controllers
│   │   │   ├── routes/                  # inventory.py, cash_sim.py, auth_utils.py, ...
│   │   │   └── telemetry.py             # OpenTelemetry metrics & distributed tracing
│   │   ├── domain/                      # Pure business logic & invariant definitions
│   │   ├── models/                      # SQLAlchemy 2.0 ORM schema definitions
│   │   │   ├── activity.py              # OutboxEvent, AuditEvent (DBAPI append-only)
│   │   │   ├── cash_sim.py              # CashBox, CashJournal, CashEntry
│   │   │   ├── iam.py                   # User, ScopeGrant (auth_version)
│   │   │   ├── idempotency.py           # IdempotencyKey durable store
│   │   │   ├── inventory.py             # InventoryRequest, Balance, LotBalance
│   │   │   ├── ledger.py                # ChartOfAccounts, GeneralLedgerJournal
│   │   │   └── reconciliation.py        # Discrepancy models & exception journals
│   │   ├── services/                    # General ledger posting, approval events, PIN
│   │   ├── worker.py                    # SKIP LOCKED asynchronous job processor
│   │   └── main.py                      # FastAPI application entrypoint
│   ├── tests/                           # 127 test modules (988 passing test cases)
│   ├── Dockerfile                       # Hardened multi-stage non-root container
│   ├── entrypoint.sh                    # Secret fail-fast & ArgoCD migration decoupling
│   ├── pyproject.toml                   # Poetry canonical dependencies & toolchain
│   └── poetry.lock                      # Locked dependency tree
├── frontend/                            # Flutter 3.24+ Web & Mobile Application
│   ├── lib/                             # Application screens, state providers, widgets
│   ├── test/                            # 355 unit, widget, and state management tests
│   └── pubspec.yaml                     # Flutter package dependencies
├── infra/                               # Infrastructure as Code & GitOps Delivery
│   └── k8s/base/                        # Kubernetes Kustomize manifests & migration jobs
├── scripts/                             # Utility scripts (secret guard scanner, seeding)
├── docker-compose.yml                   # Local production-like development cluster
├── docker-compose.test.yml              # Isolated tmpfs PostgreSQL test environment
└── README.md                            # Portfolio technical documentation
```

---

## 9. Author & Engineering Contact

**Mai Nguyen Binh Tan**  
*Backend Software Engineer | Cloud & Platform Engineering*  
- Portfolio Projects: [AKS-SRE-Platform](https://github.com/imtarget05/AKS-SRE-Platform) | [FlashSale-Backend](https://github.com/imtarget05/FlashSale-Backend) | [QuanLyKho](https://github.com/imtarget05/QuanLyKho)  
- Live Preview: [Cloudflare Pages Preview](https://quan-ly-kho-tra-sua.pages.dev/)  
- API Health & Status: `https://kho-tra-sua-fastapi.onrender.com/health/ready`
