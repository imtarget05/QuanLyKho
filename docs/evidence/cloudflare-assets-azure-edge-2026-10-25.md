# Cloudflare assets → Azure edge URL fix (2026-10-25)

User journey: when the Flutter Web assets are published to Cloudflare, the
production client must call QuanLyKho FastAPI through the same Azure-backed
Cloudflare Edge path that the app declares as canonical.

| Guarantee | Check | Result |
| --- | --- | --- |
| Deployment URL equals `AuthService.canonicalProductionBaseUrl` | `python3 -m unittest scripts.test_release_workflow_gates.ReleaseWorkflowGateTests.test_cloudflare_assets_use_the_azure_edge -v` | RED before fix: workflow pointed at `kho-tra-sua-api.../api/v1`; GREEN after fix |
| Release still requires explicit manual dispatch | `python3 -m unittest scripts.test_release_workflow_gates -v` | 4/4 pass |
| Exact health path resolves through Cloudflare to Azure | `curl -fsS https://portfolio-api-edge.tanmainguyenbinh.workers.dev/quanlykho/api/v1/health/live` | HTTP 200, `status=alive` |

The client normalizes the base URL by appending `/api/v1`; the workflow now
builds with `https://portfolio-api-edge.tanmainguyenbinh.workers.dev/quanlykho`.
The post-deploy smoke check uses the same normalized path and no longer skips
when the backend URL is empty. No Docker run was used. Publishing assets still
requires the repository's manual `DEPLOY_CLOUDFLARE_ASSETS` workflow dispatch.
That dispatch succeeded in [run 40198763957](https://github.com/imtarget05/QuanLyKho/actions/runs/40198763957)
from merge commit `c62dca2`; public `/version.json` showed the same build
number, and the workflow's Azure Edge health smoke passed.

RED checkpoint: `c19e6fd`. GREEN checkpoint: `f93770e`. The unit test covers
the release URL contract; browser behavior was not exercised by the unit test.

## Public PWA name follow-up

The first published bundle (`c62dca2`, workflow run `40198763957`) passed
Cloudflare deployment and API smoke, but a public read of `/` still returned
`<title>Kho Trà Sữa · BankOps</title>`. `frontend/web/manifest.json` carried the
same legacy product name. A second regression test now asserts both static
assets use `Kho Trà Sữa · QuanLyKho`.

RED: `python3 -m unittest scripts.test_release_workflow_gates.ReleaseWorkflowGateTests.test_cloudflare_assets_use_quanlykho_name -v` failed because the title was old (`e383b29`). GREEN: all five release workflow tests passed after updating both assets (`7fbf831`). The follow-up was published by [run 40200251829](https://github.com/imtarget05/QuanLyKho/actions/runs/40200251829) from merge commit `a098d32`. Public `/version.json` returned `a098d32`; `/` returned `<title>Kho Trà Sữa · QuanLyKho</title>` and `/manifest.json` named the PWA `Kho Trà Sữa · QuanLyKho`.
