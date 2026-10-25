# QuanLyKho — Azure End-to-End Architecture Alignment & Defense

Refer to the primary architectural defense document:
👉 [Azure Architecture Coverage & Senior Interview Defense](../../AKS-SRE-Platform/docs/architecture/azure-architecture-coverage-and-defense.md)

## Key Takeaways for QuanLyKho:
1. **Multi-Platform Delivery**: Flutter Web PWA for Desktop POS & Management paired with Flutter Mobile/Tablet for warehouse barcode scanning and offline-first stocktaking.
2. **Lean Data Pipeline**: Python async ETL with PostgreSQL analytical views provides sub-20ms reporting without the operational cost of Azure Data Factory ($300+/mo) or Azure Synapse ($1,000+/mo).
3. **Maker-Checker Security**: Dual-control approval boundaries (`canCreate` vs `canApprove`), full RBAC UAT matrix coverage, and zero direct mutation by AI agents.
4. **Cloudflare Edge**: Web PWA assets hosted via Cloudflare Pages with edge SSL and rate limiting, minimizing origin compute overhead on AKS.
