#!/usr/bin/env python3
"""给新应用生成 GitOps 骨架：overlay（stg/prod）+ Application + AppProject。

为什么要有这个脚本
------------------
一个新应用要同时出现在 6 个地方（两层 overlay、两套 Application、两套 AppProject，
外加 base），手写必然漏。漏了不会报错，只会表现为"Argo CD 里看不到这个应用"
或者"STG 能发、生产发不了"，排查半天。

镜像名的坑
----------
CI 里的 IMAGE_NAME 默认是 $CI_PROJECT_PATH_SLUG，所以镜像名是
    <REGISTRY_HOST>/<GitLab 项目路径，非字母数字换成 -> 
例如项目路径 vendors/acme/order-api → harbor.../vendors-acme-order-api
本脚本按这个规则算，不要手改 overlay 里的 name，改了就匹配不上、tag 永远不更新。

用法
----
    python3 tools/add_app.py --project-key acme --app order-api --language java \
        --registry-host harbor.internal --server-stg https://10.0.0.11:6443 \
        --server-prod https://10.0.0.21:6443 --gitops-url https://gitlab.internal/platform/gitops-deployments.git
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PORTS = {"java": 8080, "python": 8080, "go": 8080, "node": 8080}


def slugify(project_path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", project_path.lower()).strip("-")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        sys.exit(f"已存在，拒绝覆盖：{path.relative_to(ROOT)}（先删掉或改名）")
    path.write_text(text, encoding="utf-8")
    print(f"  + {path.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-key", required=True)
    ap.add_argument("--app", required=True)
    ap.add_argument("--language", required=True, choices=sorted(PORTS))
    ap.add_argument("--registry-host", required=True)
    ap.add_argument("--gitlab-project-path", required=True,
                    help="GitLab 里的完整项目路径，如 vendors/acme/order-api")
    ap.add_argument("--server-stg", required=True)
    ap.add_argument("--server-prod", required=True)
    ap.add_argument("--gitops-url", required=True)
    args = ap.parse_args()

    image = f"{args.registry_host}/{slugify(args.gitlab_project_path)}"
    port = PORTS[args.language]
    app, key = args.app, args.project_key
    app_dir = ROOT / "apps" / key / app

    for env, server, digest in (
        ("stg", args.server_stg, None),
        ("prod", args.server_prod, "sha256:" + "0" * 64),
    ):
        images = (
            f"- name: {image}\n  newName: {image}\n  newTag: 0.0.0"
            if digest is None
            else f"- name: {image}\n  digest: {digest}"
        )
        write(app_dir / "overlays" / env / "kustomization.yaml", f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: {app}-{env}

resources:
  - ../../base

labels:
  - pairs:
      app.kubernetes.io/env: {env}

# STG 按 tag 自动晋级；生产按 digest，只能由发布流程写入。
images:
{images}
""")

    write(app_dir / "base" / "kustomization.yaml", f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml
""")

    write(app_dir / "base" / "deployment.yaml", f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app}
  labels:
    app.kubernetes.io/name: {app}
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {app}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {app}
    spec:
      # 运行时安全基线：与平台 POD_SECURITY=restricted 对齐
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: {app}
          image: {image}
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: {port}
              protocol: TCP
          env:
            - name: APP_ENV
              value: base
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
            readOnlyRootFilesystem: false
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 20
            periodSeconds: 20
""")

    write(app_dir / "base" / "service.yaml", f"""apiVersion: v1
kind: Service
metadata:
  name: {app}
  labels:
    app.kubernetes.io/name: {app}
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: {app}
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
""")

    for env, server in (("stg", args.server_stg), ("prod", args.server_prod)):
        write(ROOT / "argocd" / "projects" / env / f"{app}.yaml", f"""apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: {key}-{app}-{env}
  namespace: argocd
spec:
  description: "{key}/{app} {env}"
  sourceRepos:
    - "{args.gitops_url}"
  destinations:
    - server: {server}
      namespace: {app}-{env}
  # 业务项目不允许创建集群级资源，命名空间由 platform-{env} 统一管
  clusterResourceWhitelist: []
  namespaceResourceBlacklist:
    - group: ""
      kind: ResourceQuota
    - group: ""
      kind: LimitRange
  orphanedResources:
    warn: true
  syncWindows:
""" + ("""    - kind: allow
      schedule: "0 10 * * 1-5"
      duration: 8h
      timeZone: "Asia/Shanghai"
      applications:
        - "{app}-prod"
      # false = 窗口外人工也没法越窗同步；紧急发布走另开的临时窗口并留痕
      manualSync: false
""" if env == "prod" else "    []
"))

        sync = """    automated:
      prune: true
      selfHeal: true
""" if env == "stg" else "    # 生产刻意为空：不自动同步，只在窗口内由授权人员人工 Sync
"
        write(ROOT / "argocd" / "applications" / env / f"{app}.yaml", f"""apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {app}-{env}
  namespace: argocd
  labels:
    platform.modernkemo/project: {key}
    platform.modernkemo/app: {app}
    platform.modernkemo/env: {env}
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: {key}-{app}-{env}
  source:
    repoURL: {args.gitops_url}
    targetRevision: main
    path: apps/{key}/{app}/overlays/{env}
  destination:
    server: {server}
    namespace: {app}-{env}
  revisionHistoryLimit: 10
  syncPolicy:
{sync}""")

    print("\n下一步：")
    print("  1. kustomize build apps/%s/%s/overlays/stg" % (key, app))
    print("  2. python3 tools/validate_repo.py --root .")
    print("  3. 提 MR；GitOps 仓库的流水线会校验策略，通过后再合")
    return 0


if __name__ == "__main__":
    sys.exit(main())
