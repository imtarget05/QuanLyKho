"""Prevent a merge to main from promoting the legacy cloud release paths."""

import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE_JOBS = {
    "deploy.yml": ("DEPLOY_LEGACY_ACA", ("build-and-push", "deploy-azure-container-apps")),
    "deploy-pages.yml": ("DEPLOY_CLOUDFLARE_ASSETS", ("build-and-deploy",)),
    "ci-gitops.yml": ("PUBLISH_AKS_IMAGES", ("build-and-push",)),
}


def validate_release_workflow(source: str, confirmation: str, release_jobs: tuple[str, ...]) -> None:
    workflow = yaml.load(source, Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    events = workflow["on"]
    assert set(events) == {"workflow_dispatch"}, "release must never run on push or PR"
    confirm = events["workflow_dispatch"]["inputs"]["confirm"]
    assert confirm["required"] == "true"
    assert confirm.get("default") != confirmation

    for name in release_jobs:
        job = workflow["jobs"][name]
        condition = job.get("if", "")
        assert "github.event_name == 'workflow_dispatch'" in condition, name
        assert f"inputs.confirm == '{confirmation}'" in condition, name
        assert job.get("environment"), f"{name} must name its protected environment"
    if confirmation == "PUBLISH_AKS_IMAGES":
        assert "git push origin main" not in source
        assert ":latest" not in source
        assert "gitops-deploy" not in workflow["jobs"]
        assert workflow["jobs"]["build-and-push"]["permissions"] == {
            "contents": "read",
            "packages": "write",
        }


def validate_kind_publish_workflow(source: str) -> None:
    workflow = yaml.load(source, Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"push", "pull_request", "workflow_dispatch"}
    for event in ("push", "pull_request"):
        assert workflow["on"][event]["branches"] == ["main"]
        paths = workflow["on"][event]["paths"]
        assert ".github/workflows/s9-k8s-cloud-ci.yml" in paths
        assert "scripts/verify_tested_image_artifact.py" in paths
    kind = workflow["jobs"]["cloud-ci-kind-verified"]
    assert kind["permissions"]["packages"] != "write"
    for step in kind["steps"]:
        assert "docker push " not in step.get("run", ""), "Kind CI must not publish"
        assert step.get("with", {}).get("push") != "true"
    preserve = next(step for step in kind["steps"] if step.get("name") == "Preserve exact image bytes for manual publication")
    assert "docker save" in preserve["run"]
    assert "verify_tested_image_artifact.py" in preserve["run"]
    upload = next(step for step in kind["steps"] if step.get("name") == "Upload tested image only after Kind verification")
    assert upload["with"]["name"] == "s9-tested-image-${{ github.sha }}"
    assert upload["if"] == "success()"

    publish = workflow["jobs"]["publish-model-serving"]
    condition = publish["if"]
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert "inputs.confirm == 'PUBLISH_MODEL_SERVING'" in condition
    assert publish.get("environment")
    assert publish["needs"] == "cloud-ci-kind-verified"
    assert publish["permissions"]["packages"] == "write"
    download = next(step for step in publish["steps"] if step.get("uses") == "actions/download-artifact@v4")
    assert download["with"]["name"] == upload["with"]["name"]
    runs = "\n".join(step.get("run", "") for step in publish["steps"])
    assert "verify_tested_image_artifact.py" in runs
    assert "docker load -i" in runs
    assert "docker image inspect" in runs
    assert "docker push" in runs
    assert "digest:" in runs
    assert any(
        step.get("uses") == "docker/login-action@c94ce9fb468520275223c153574b00df6fe4bcc9"
        for step in publish["steps"]
    ), "Registry login action must be pinned to its reviewed commit"
    assert all("docker/build-push-action" not in step.get("uses", "") for step in publish["steps"])
    assert "latest" not in str(publish["steps"]), "Only immutable SHA tags may be published"


class ReleaseWorkflowGateTests(unittest.TestCase):
    def test_all_external_release_paths_are_manual_and_explicit(self) -> None:
        for filename, (confirmation, jobs) in RELEASE_JOBS.items():
            with self.subTest(filename=filename):
                validate_release_workflow(
                    (WORKFLOWS / filename).read_text(), confirmation, jobs
                )
        validate_kind_publish_workflow((WORKFLOWS / "s9-k8s-cloud-ci.yml").read_text())

    def test_push_trigger_or_missing_confirmation_is_rejected(self) -> None:
        for filename, (confirmation, jobs) in RELEASE_JOBS.items():
            source = (WORKFLOWS / filename).read_text()
            with self.subTest(filename=filename, mutation="push"):
                bad = source.replace("on:\n", "on:\n  push:\n    branches: [main]\n", 1)
                with self.assertRaises(AssertionError):
                    validate_release_workflow(bad, confirmation, jobs)
            with self.subTest(filename=filename, mutation="confirmation"):
                bad = source.replace(f"inputs.confirm == '{confirmation}'", "true")
                with self.assertRaises(AssertionError):
                    validate_release_workflow(bad, confirmation, jobs)
            if filename == "ci-gitops.yml":
                with self.assertRaises(AssertionError):
                    validate_release_workflow(source + "\n# git push origin main\n", confirmation, jobs)
                with self.assertRaises(AssertionError):
                    validate_release_workflow(source + "\n# ghcr.io/example:latest\n", confirmation, jobs)

        s9 = (WORKFLOWS / "s9-k8s-cloud-ci.yml").read_text()
        bad_publish = s9.replace(
            "      - name: Install kind\n",
            "      - name: Illicit push on main\n"
            "        run: docker push ghcr.io/example/model-serving:latest\n"
            "      - name: Install kind\n",
            1,
        )
        self.assertNotEqual(bad_publish, s9)
        with self.assertRaisesRegex(AssertionError, "Kind CI must not publish"):
            validate_kind_publish_workflow(bad_publish)
        writable_kind = s9.replace("packages: read", "packages: write", 1)
        with self.assertRaises(AssertionError):
            validate_kind_publish_workflow(writable_kind)
        missing_confirmation = s9.replace("inputs.confirm == 'PUBLISH_MODEL_SERVING'", "true", 1)
        with self.assertRaises(AssertionError):
            validate_kind_publish_workflow(missing_confirmation)
        publish_on_pr = s9.replace(
            "github.event_name == 'workflow_dispatch'", "github.event_name == 'pull_request'", 1
        )
        with self.assertRaises(AssertionError):
            validate_kind_publish_workflow(publish_on_pr)
        unverified_artifact = s9.replace(
            "python3 scripts/verify_tested_image_artifact.py", "echo unverified", 1
        )
        with self.assertRaises(AssertionError):
            validate_kind_publish_workflow(unverified_artifact)

    def test_quality_ci_still_runs_for_main_and_pull_requests(self) -> None:
        ci = yaml.load((WORKFLOWS / "ci.yml").read_text(), Loader=yaml.BaseLoader)
        assert set(ci["on"]) == {"push", "pull_request"}
        assert "test" in ci["jobs"]
        assert "frontend-web" in ci["jobs"]

    def test_cloudflare_assets_use_the_azure_edge(self) -> None:
        workflow = yaml.load(
            (WORKFLOWS / "deploy-pages.yml").read_text(), Loader=yaml.BaseLoader
        )
        edge_url = "https://portfolio-api-edge.tanmainguyenbinh.workers.dev/quanlykho"
        self.assertEqual(workflow["env"]["API_BASE_URL"], edge_url)

        auth_service = (
            ROOT / "frontend/lib/src/features/auth/auth_service.dart"
        ).read_text()
        self.assertIn(f"'{edge_url}'", auth_service)

    def test_cloudflare_assets_use_quanlykho_name(self) -> None:
        title = "Kho Trà Sữa · QuanLyKho"
        index = (ROOT / "frontend/web/index.html").read_text()
        manifest = json.loads((ROOT / "frontend/web/manifest.json").read_text())
        self.assertTrue(
            f"<title>{title}</title>" in index,
            "Flutter Web title must use QuanLyKho",
        )
        self.assertEqual(manifest["name"], title)


if __name__ == "__main__":
    unittest.main()
