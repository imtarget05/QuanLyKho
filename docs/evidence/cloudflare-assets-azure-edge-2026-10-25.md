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
requires the repository's manual `DEPLOY_CLOUDFLARE_ASSETS` workflow dispatch;
this local fix has not been published to Cloudflare.

RED checkpoint: `c19e6fd`. GREEN checkpoint: `f93770e`. The unit test covers
the release URL contract; it does not prove the new Flutter bundle has been
published or exercised in a browser.
