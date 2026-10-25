# QuanLyKho release authority

The pilot release path is the production overlay consumed by AKS Argo CD. A
push to `main` runs quality CI; it does not publish a new cloud release. The
external publication requires a manual dispatch with an exact confirmation
input:

| Workflow | Confirmation | Effect |
| --- | --- | --- |
| `ci-gitops.yml` | `PUBLISH_AKS_IMAGES` | Build and push immutable API/frontend images; no overlay mutation. |
| `deploy-pages.yml` | `DEPLOY_CLOUDFLARE_ASSETS` | Publish Flutter Web assets to Cloudflare. |
| `deploy.yml` | `DEPLOY_LEGACY_ACA` | Deploy the legacy Azure Container App; it is not the AKS pilot authority. |
| `s9-k8s-cloud-ci.yml` | `PUBLISH_MODEL_SERVING` | Publish the SHA-tagged model-serving image, only after Kind verification passes. |

Dispatch from `main` only after reviewing the exact source SHA, CI results,
rendered overlay, image tags or digest, migration, expected cost and rollback.
The workload workflow does not update Argo CD manifests. Promotion requires a
separate reviewed release-ref PR in the AKS platform repo; do not dispatch the
image publication workflow before its release-ref and approval gates are ready.
`ci.yml` remains the automatic test and local-build pipeline for both PRs and
`main`.
The S9 Kind job also runs automatically on PRs and main for its path-filtered
source or workflow changes; it builds and loads its image locally but cannot
publish to GHCR on either event.

Each release job names a GitHub Environment. **An environment name by itself is
not an approval gate.** Required reviewers are not configured in this
repository at this time. Until they are configured and tested with a held-job
negative control, the exact dispatch confirmation is the only human action
required by GitHub. Do not describe these workflows as two-person approval or
production-ready cloud promotion. High-impact Agent Hub commands remain
disabled on AKS while there is only one real operator.

Further release blockers: legacy ACA still publishes branch/short-SHA tags;
`ci-gitops.yml` runs Trivy with `exit-code: '0'` (advisory only); and no
Environment has a required reviewer. Future promotion must pin image digests,
set a reviewed vulnerability policy, and prove reviewer protection before
claiming an approved production release.

The policy regression test is `python3 -m unittest
scripts.test_release_workflow_gates -v`; its mutation cases prove that a push
trigger or a missing confirmation is rejected. It runs in the `ci.yml` lint
job as well.
