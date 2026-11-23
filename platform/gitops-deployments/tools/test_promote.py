import unittest

from unittest.mock import patch
from pathlib import Path

from promote import production_image, verified_source
from stg_receipt import healthy_application

SHA = "1" * 40
DIGEST = "sha256:" + "2" * 64
IMAGE = "registry.test/demo-go-api"


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.pipe = {"sha": SHA, "tag": False, "ref": "main", "source": "push"}
        self.jobs = {name: "success" for name in (
            "go-test", "coverage-gate", "secret-scan", "sast", "dependency-scan", "license-scan",
            "license-gate", "dockerfile-policy", "go-build", "build-image", "image-scan", "sbom")}
        self.jobs["stg-promotion"] = "running"
        self.head = SHA
        self.artifact = f"IMAGE_REF={IMAGE}@{DIGEST}\n"

    def api(self, path, raw=False):
        if raw:
            return self.artifact
        if path.endswith("/jobs?per_page=100&page=1"):
            return [{"id": i, "name": k, "status": v} for i, (k, v) in enumerate(self.jobs.items())]
        if path.startswith(("/repository/branches/", "/repository/tags/")):
            return {"protected": True, "commit": {"id": self.head}}
        return self.pipe if path else {"default_branch": "main"}

    def verify(self):
        return verified_source(self.api, "42", "stg", "go", IMAGE)

    def test_stg(self):
        self.assertEqual(self.verify(), (SHA, IMAGE + "@" + DIGEST))

    def test_failed_scan(self):
        self.jobs["image-scan"] = "failed"
        with self.assertRaises(ValueError):
            self.verify()

    def test_stale_commit(self):
        self.head = "3" * 40
        with self.assertRaises(ValueError):
            self.verify()

    def test_wrong_image(self):
        self.artifact = self.artifact.replace(IMAGE, "other")
        with self.assertRaises(ValueError):
            self.verify()

    def test_historical_prod(self):
        self.head = "3" * 40
        self.jobs.update({"prod-promotion": "running", "release-candidate": "success", "stg-promotion": "success"})
        self.artifact = "REL-20261122-001\n"
        self.assertEqual(verified_source(self.api, "42", "prod", "go", IMAGE), (SHA, self.artifact.strip()))
        self.jobs["release-candidate"] = "failed"
        with self.assertRaises(ValueError):
            verified_source(self.api, "42", "prod", "go", IMAGE)

    def test_release_must_match_pipeline_and_health_receipt(self):
        ref = IMAGE + "@" + DIGEST
        item = {"image": ref, "dependencies": [], "downtime": False}
        record = dict(project="vendor/go", app="demo/go-api", pipeline="42", commit=SHA, image=ref,
                      application="go-api-stg", destination={"server": "stg"}, observedAt="2026-11-22",
                      gitopsRevision="2" * 40)
        with patch("promote.checked_materials", return_value=("demo", {"go-api": item})):
            def verify():
                return production_image(Path("."), "REL-20261122-001", "vendor/go", "demo/go-api", "42", SHA, record)
            self.assertEqual(verify(), ref)
            record["pipeline"] = "43"
            with self.assertRaises(ValueError):
                verify()
            record["pipeline"] = "42"
            item["sourcePipeline"] = "43"
            with self.assertRaises(ValueError):
                verify()
            item["sourcePipeline"] = "42"
            record.pop("gitopsRevision")
            with self.assertRaises(ValueError):
                verify()

    def test_only_exact_healthy_revision_counts(self):
        declared = {"metadata": {"name": "go-api-stg"},
                    "spec": {"project": "demo", "source": {"path": "stg"}, "destination": {"server": "stg"}}}
        status = {"sync": {"revision": SHA, "status": "Synced"}, "health": {"status": "Healthy"},
                  "summary": {"images": [IMAGE + "@" + DIGEST]}}
        app = dict(declared, status=status)
        self.assertTrue(healthy_application(app, declared, SHA, IMAGE + "@" + DIGEST))
        self.assertFalse(healthy_application(app, declared, "3" * 40, IMAGE + "@" + DIGEST))
        self.assertFalse(healthy_application(app, declared, SHA, "other"))
        status["health"]["status"] = "Progressing"
        self.assertFalse(healthy_application(app, declared, SHA, IMAGE + "@" + DIGEST))


if __name__ == "__main__":
    unittest.main()
