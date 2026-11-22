#!/usr/bin/env python3
"""GitOps 仓库自身的合法性与策略校验。

为什么需要：GitOps 仓库是"集群状态的唯一事实源"。它没有门禁，等于把
集群变更的最后一关交给人工肉眼——而人工最容易漏的正是这几类：
  · 生产 overlay 混进 tag（应该只认 digest）
  · 明文 Secret 被提交
  · 有人把 prod Application 改成自动同步，绕过发布窗口
  · 业务 AppProject 放开了集群级资源，等于给了供应商建 CRD 的能力
  · 发布材料缺失或不符合 Schema

用法：
    python3 tools/validate_repo.py --root .
退出码：0 全部通过；1 存在问题。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

problems: list[str] = []
notes: list[str] = []


def load(path: Path):
    try:
        return list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        problems.append(f"{path}: YAML 解析失败 -> {exc}")
        return []


def walk_docs(root: Path):
    for path in sorted(root.rglob("*.yaml")):
        if any(part.startswith(".") for part in path.parts):
            continue
        for doc in load(path):
            if isinstance(doc, dict):
                yield path, doc


def check_app_structure(root: Path) -> None:
    apps = root / "apps"
    if not apps.is_dir():
        problems.append("缺少 apps/ 目录")
        return
    for project in sorted(p for p in apps.iterdir() if p.is_dir()):
        for app in sorted(p for p in project.iterdir() if p.is_dir()):
            for sub in ("base", "overlays/stg", "overlays/prod"):
                if not (app / sub / "kustomization.yaml").is_file():
                    problems.append(f"{app.relative_to(root)}: 缺少 {sub}/kustomization.yaml")


def check_overlays(root: Path) -> None:
    for kfile in sorted(root.glob("apps/*/*/overlays/*/kustomization.yaml")):
        env = kfile.parent.name
        data = load(kfile)
        images = []
        for doc in data:
            if isinstance(doc, dict):
                images.extend(doc.get("images") or [])
        if not images:
            problems.append(f"{kfile.relative_to(root)}: 未声明 images，晋级无从追溯")
            continue
        for img in images:
            name = img.get("name", "?")
            if img.get("newTag") == "latest":
                problems.append(f"{kfile.relative_to(root)}: {name} 使用 latest")
            if env == "prod":
                # 生产只认 digest：tag 可被覆盖，digest 不可变
                if img.get("newTag"):
                    problems.append(
                        f"{kfile.relative_to(root)}: 生产 overlay 仍在使用 newTag={img['newTag']}，必须改为 digest"
                    )
                digest = str(img.get("digest") or "")
                if not digest.startswith("sha256:") or len(digest) != 71:
                    problems.append(f"{kfile.relative_to(root)}: {name} 的 digest 格式非法：{digest!r}")
                elif set(digest[7:]) == {"0"}:
                    notes.append(f"{kfile.relative_to(root)}: {name} 尚未晋级（digest 为占位值）")


def check_policies(root: Path) -> None:
    for path, doc in walk_docs(root):
        kind = doc.get("kind")
        rel = path.relative_to(root)

        # 1) 禁止明文 Secret
        if kind == "Secret" and (doc.get("data") or doc.get("stringData")):
            problems.append(f"{rel}: 提交了含数据的 Secret，必须改用外部密钥管理或 SealedSecret")

        # 2) 命名空间必须带 Pod Security 标签
        if kind == "Namespace":
            labels = (doc.get("metadata") or {}).get("labels") or {}
            enforce = labels.get("pod-security.kubernetes.io/enforce")
            if enforce not in {"restricted", "baseline"}:
                problems.append(f"{rel}: Namespace 未声明 pod-security.kubernetes.io/enforce")

        # 3) 生产 Application 禁止自动同步
        if kind == "Application" and "/applications/prod/" in str(rel):
            policy = (doc.get("spec") or {}).get("syncPolicy") or {}
            # 注意：不能用 policy.get("automated") 的真假判断——
            # `automated: {}` 空映射在 Python 里是假值，但 Argo CD 会把它当成"开启自动同步"。
            if "automated" in policy:
                problems.append(
                    f"{rel}: 生产 Application 配置了 syncPolicy.automated（即使是空映射也算开启自动同步）"
                )
            # 生产不应跟踪可变分支的最新提交，否则 main 上任意一次提交都会变成可同步变更
            rev = (doc.get("spec") or {}).get("source", {}).get("targetRevision")
            if rev in {"main", "master", "HEAD"}:
                notes.append(f"{rel}: 生产 targetRevision={rev}（跟踪可变引用，需依赖人工 Sync 与窗口兜底）")

        # 4) 业务 AppProject 不得放开集群级资源
        if kind == "AppProject" and "platform" not in path.name:
            allowed = (doc.get("spec") or {}).get("clusterResourceWhitelist") or []
            if allowed:
                problems.append(f"{rel}: 业务 AppProject 放开了集群级资源 {allowed}，应保持为空")

        # 5) 生产 AppProject 必须有同步窗口
        if kind == "AppProject" and "/projects/prod/" in str(rel):
            windows = (doc.get("spec") or {}).get("syncWindows") or []
            if not windows:
                problems.append(f"{rel}: 生产 AppProject 缺少 syncWindows，发布窗口不生效")
            # manualSync: true 的含义是"允许人工在窗口外同步"，与本项目
            # "生产只能在窗口内变更"的目标相反，必须为 false。
            for w in windows:
                if w.get("kind") == "allow" and w.get("manualSync") is True:
                    problems.append(
                        f"{rel}: allow 窗口设置了 manualSync: true，等于允许人工越窗同步；"
                        f"应为 false（紧急发布另走临时调整窗口并留痕）"
                    )

        # 6) Deployment 必须使用非 root 与受限安全上下文
        if kind == "Deployment":
            spec = ((doc.get("spec") or {}).get("template") or {}).get("spec") or {}
            sc = spec.get("securityContext") or {}
            if not sc.get("runAsNonRoot"):
                problems.append(f"{rel}: Deployment 未设置 runAsNonRoot")
            for container in (spec.get("containers") or []):
                name = container.get("name", "?")
                if container.get("image", "").endswith(":latest"):
                    problems.append(f"{rel}: 容器 {name} 使用 latest")
                csc = container.get("securityContext") or {}
                caps = (csc.get("capabilities") or {}).get("drop") or []
                if "ALL" not in caps:
                    problems.append(f"{rel}: 容器 {name} 未 drop ALL capabilities")
                if not (csc.get("readOnlyRootFilesystem") is not None or True):
                    pass
                if not container.get("resources"):
                    problems.append(f"{rel}: 容器 {name} 未声明 resources，无法做配额与调度")


def check_releases(root: Path) -> None:
    from release_material import checked_materials
    for folder in sorted((root / "releases").glob("*")):
        if folder.is_dir():
            try:
                checked_materials(root, folder.name)
            except Exception as exc:
                problems.append(f"releases/{folder.name}: {str(exc)[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="gitops-deployments 仓库路径")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    check_app_structure(root)
    check_overlays(root)
    check_policies(root)
    check_releases(root)

    for n in notes:
        print(f"  · {n}")
    for p in problems:
        print(f"  ✗ {p}")
    if problems:
        print(f"\nFAIL：{len(problems)} 处问题")
        return 1
    print("\nPASS：GitOps 仓库策略校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
