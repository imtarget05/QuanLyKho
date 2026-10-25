# QuanLyKho Device Channel Strategy & Persona Mapping

## 1. Executive Summary
This document defines the production channel allocation for QuanLyKho, matching user personas in milk tea operations with target runtime devices, network resilience requirements, and delivery mechanisms.

---

## 2. Persona & Channel Matrix

```mermaid
flowchart TD
    subgraph Users ["Operations Personas"]
        Staff["Barista / Floor Staff"]
        Manager["Shift Manager / Store Leader"]
        Auditor["Finance & HQ Auditor"]
    end

    subgraph Channels ["Application Delivery Channels"]
        Mobile["Mobile Native / Tablet (Flutter Android/iOS)"]
        WebDesktop["Desktop Web PWA (Cloudflare Pages)"]
    end

    subgraph Services ["Backend Services (FastAPI)"]
        API["REST API (Inventory, Shifts, Vouchers)"]
        Push["Push Gateway (FCM / APNs)"]
        SSE["SSE Event Bus (/activity/events_stream)"]
    end

    Staff -->|Offline Stocktake & Barcode| Mobile
    Manager -->|Fast Approvals & Handover| Mobile
    Manager -->|End-of-day Lock & Adjustments| WebDesktop
    Auditor -->|Audit Trails & Big Ledger Reports| WebDesktop

    Mobile --> API
    WebDesktop --> API
    Push -->|Background Alerts| Mobile
    SSE -->|Live In-Tab Updates| WebDesktop
```

---

## 3. Offline & Sync Resilience Specification
- **Storage:** Offline entries are stored in encrypted client storage using `StocktakeOutbox`.
- **Auto-flush:** On network restoration (`connectivity_plus`), `offline_ui.dart` triggers `tryFlush()`.
- **Conflict Prevention:** If a shift was already locked by another manager, the server returns `409 Conflict`, prompting the user to view the server's locked snapshot instead of overwriting.

---

## 4. Push Notification Architecture
- **Registration:** Clients register their device token upon login via `POST /api/v1/notifications/devices/register`.
- **De-registration:** Clean logout calls `DELETE /api/v1/notifications/devices/{token}`.
- **Provider Gateway:** In production, FCM v1 HTTP API is used. In automated tests and staging without FCM secrets, the system seamlessly uses the verified simulated provider (`fcm-simulated`).
