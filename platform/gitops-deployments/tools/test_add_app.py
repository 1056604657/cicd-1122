"""离线生成第五个应用，验证两个环境的 Argo CD 入口和部署清单。"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
KUSTOMIZE = ["kustomize", "build"] if shutil.which("kustomize") else ["kubectl", "kustomize"]


def render(path):
    output = subprocess.check_output([*KUSTOMIZE, str(path)], text=True)
    return list(yaml.safe_load_all(output))


class OnboardingTest(unittest.TestCase):
    def check_app(self, lang, stg, prod):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "gitops"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            command = [sys.executable, str(root / "tools/add_app.py"), "--project-key", "vendor",
                       "--app", "order-api", "--language", lang, "--registry-host", "registry.test",
                       "--gitlab-project-path", "vendors/acme/orders", "--robot", "order-bot",
                       "--server-stg", stg, "--server-prod", prod, "--gitops-url", "https://git.test/ops.git"]
            subprocess.run(command, check=True)
            sources = json.loads((root / "policies/promotion-sources.json").read_text())
            self.assertEqual(sources["order-bot"], ["vendors/acme/orders", "vendor/order-api",
                                                   {"java": "java-maven", "node": "frontend"}.get(lang, lang)])
            for env, server in (("stg", stg), ("prod", prod)):
                ns = "order-api-" + env
                docs = render(root / "argocd/bootstrap" / env)
                objects = {(d["kind"], d["metadata"]["name"]): d["spec"] for d in docs}
                for name in (ns, "platform-" + ns):
                    spec = objects["Application", name]
                    destination = {"server": server, "namespace": ns}
                    self.assertEqual(spec["destination"], destination)
                    self.assertEqual(spec["source"]["repoURL"], "https://git.test/ops.git")
                    self.assertEqual("automated" in spec["syncPolicy"], env == "stg")
                    project = objects["AppProject", spec["project"]]
                    self.assertEqual(project["destinations"], [destination])
                    self.assertEqual(project["sourceRepos"], [spec["source"]["repoURL"]])
                    if env == "prod":
                        self.assertEqual(project["syncWindows"], objects["AppProject", "platform-prod"]["syncWindows"])
                    built = render(root / spec["source"]["path"])
                    if name == ns:
                        self.assertEqual(project["clusterResourceWhitelist"], [])
                        deployment = next(d for d in built if d["kind"] == "Deployment")
                        self.assertEqual(deployment["metadata"]["name"], "order-api")
                        self.assertEqual(deployment["metadata"]["namespace"], ns)
                        container = deployment["spec"]["template"]["spec"]["containers"][0]
                        self.assertEqual(container["image"], "registry.test/vendors-acme-orders@sha256:" + "0" * 64)
                    else:
                        self.assertEqual({d["kind"] for d in built},
                                         {"Namespace", "ResourceQuota", "LimitRange", "NetworkPolicy"})
                        for d in built:
                            meta = d["metadata"]
                            self.assertEqual(meta.get("namespace", meta["name"]), ns)
                self.assertFalse(any(d["metadata"].get("namespace", d["metadata"]["name"]) == ns
                                     for d in render(root / "platform" / env)))
            def snapshot():
                return {p.relative_to(root): hashlib.sha256(p.read_bytes()).digest()
                        for p in root.rglob("*") if p.is_file()}
            before = snapshot()
            for overrides in ([], ["--app", "other", "--robot", "new-bot"],
                              ["--app", "other", "--gitlab-project-path", "vendor/other"]):
                self.assertNotEqual(subprocess.run(command + overrides, capture_output=True).returncode, 0)
                self.assertEqual(snapshot(), before)

    def test_same_cluster(self):
        for lang in ("node", "go"):
            with self.subTest(language=lang):
                self.check_app(lang, "https://kubernetes.default.svc", "https://kubernetes.default.svc")

    def test_separate_clusters(self):
        for lang in ("java", "python"):
            with self.subTest(language=lang):
                self.check_app(lang, "https://stg.test", "https://prod.test")


if __name__ == "__main__":
    unittest.main()
