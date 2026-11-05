# Cloudflare Pages preview — QuanLyKho synthetic frontend

- Observed UTC: 2026-11-05 05:08–05:13.
- Environment: Cloudflare Pages **Preview**; project `quan-ly-kho-tra-sua`; branch `codex-portfolio-evidence-20261104`.
- Source SHA: `21366a131415afa7f04c28cc677b1873327a0b8e`.
- Deployment ID: `cdf21402-2500-4bf0-9dfa-cfe461b6bfca`.
- URL: https://cdf21402.quan-ly-kho-tra-sua.pages.dev
- Build: `flutter build web --release --no-tree-shake-icons --dart-define=OFFLINE_DEMO=true --dart-define=APP_BUILD_COMMIT=21366a1 --build-number=21366a1 --no-wasm-dry-run`, then replace `__APP_BUILD_NUMBER__` in `index.html` and write `release-manifest.json` containing the full SHA and mode. The local build passed.
- Deploy: `wrangler pages deploy build/web --project-name quan-ly-kho-tra-sua --branch codex-portfolio-evidence-20261104 --commit-hash <source SHA> --commit-dirty=true` using the current OAuth session with `pages (write)`. The checkout contains an unrelated untracked status document; it was not part of the build.
- Expected/actual: `/`, `/main.dart.js` and `/release-manifest.json` returned HTTP 200; the manifest's `source_sha` equals the source SHA, `mode=offline-synthetic-demo`, `api_release=null`.
- Rollback boundary: production Pages remains branch `main`, deployment `31d82259-31a2-46f1-bb5b-7906f292388b`, source `2ea8fae`; this operation did not replace it.

This is a synthetic frontend preview, not a backend/database deployment or any of the 21 cloud MVP journey gates. The external SonarCloud quality gate was still under verification at this checkpoint. No actual billing amount was available in the Wrangler deployment output.
