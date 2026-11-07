# QuanLyKho

This repository is a warehouse operations and finance-simulation application for a milk tea / ingredients warehouse. It combines a FastAPI backend, PostgreSQL persistence, a Flutter web/app interface, and optional AI integration for demo workflows such as maker-checker review and risk scoring.

## What is implemented

- warehouse and inventory operation flows
- maker-checker approval process with dual-control validation
- dual-entry ledger / journal-style simulation for financial operations
- real-time event notifications and dashboard badges
- AI-based risk review and audit-stamp logic for demo scenarios
- FastAPI service with RBAC and PostgreSQL-backed workflows

This is intentionally a simulation for product demonstration and operations training. It is not a real banking system, and it does not process real customer funds or real payment rails.

## Stack

- Flutter front end / web app
- FastAPI backend
- PostgreSQL 16
- Cloudflare AI / Worker usage as optional provider integration
- Docker Compose and local validation scripts

## Repository evidence

The repo includes:

- architecture notes in `docs/03-architecture.md`
- employee app design notes in `docs/employee-app/README.md`
- backend validation scripts in `backend/tests/` and `scripts/`
- CI workflow in GitHub Actions

The project also documents where FastAPI is the canonical backend and where Cloudflare Worker code is kept only for compatibility/reference, not as the production API.

## Run locally

```bash
cd /Users/mainguyenbinhtan/Projects/QuanLyKho
make up
```

This starts the demo interface locally. For the backend + PostgreSQL flow, use:

```bash
make up-backend
```

The API and Swagger docs are available on the local stack, and the repo includes verification scripts for live E2E flows.

## Validation examples

```bash
python3 backend/tests/verify_live_e2e.py
```

The repo contains automation for live verification and smoke tests, but those are still portfolio-evidence checks rather than production SLA or compliance proof.

## Boundaries

- not a real bank or treasury system
- not using real customer data
- not claiming production deployment in Cloudflare or a live production backend
- AI features are demo-oriented and should be described as such in interviews

The correct story for this project is: a working operations simulation with evidence-backed backend and UI workflows, plus clearly documented boundaries and non-production assumptions.
