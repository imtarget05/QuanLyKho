# QuanLyKho synthetic frontend Preview — 2026-11-04 UTC

| Field | Value |
| --- | --- |
| Source SHA | `2f976dd55ed6e183d70d602f5bda08229523b006` |
| Environment | Cloudflare Pages Preview; branch `codex-portfolio-evidence-20261104` |
| Deployment ID | `e7d10857-4c58-4525-be79-3c1ac9a39841` |
| URL | https://e7d10857.quan-ly-kho-tra-sua.pages.dev |
| Build | `flutter build web --release --no-tree-shake-icons --dart-define=OFFLINE_DEMO=true --no-wasm-dry-run` |
| Mode | Synthetic, device-local CommerceMemoryStore; no API or database release |
| Production Pages rollback target | Existing `main` deployment `31d82259-31a2-46f1-bb5b-7906f292388b`, source `2ea8fae`, remained unchanged |

The [sanitized raw probe](2026-11-04-cloudflare-preview-2f976dd.txt) records HTTP results and the published `release-manifest.json` with matching SHA. An asset path that did not exist returned the SPA fallback and is explicitly excluded from the pass result. In a browser, the landing page identified its figures as illustrative, the **Trải nghiệm demo** button opened the commerce workspace, and the workspace displayed a persistent banner that its data is simulated on this device and does not use a real API or database.

The first preview at `18bd344` showed a defect: **Trải nghiệm demo** opened the login form, and the landing page called example values “Live ERP System.” Source `027f0af` corrected the entry action and labels; source `2f976dd` added the workspace banner. Flutter analyze passed, all 355 widget tests passed after the entry fix, and the targeted workspace test passed after the banner change. CI for the final source SHA is [running here](https://github.com/imtarget05/QuanLyKho/actions/runs/41853141712); do not call that CI green until complete.

**Acceptance scope:** frontend preview and synthetic navigation only. This does not close any of the 21 MVP cloud IDs, migration `034` on the deployed backend, maker–checker, three-shift operation, FEFO, RBAC, device offline UAT, backup/restore or rollback. No production Pages deployment was changed. Incremental billed amount was unavailable in Wrangler and remains OPEN for owner billing review.
