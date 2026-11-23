#!/usr/bin/env python3
"""生成一个应用的 GitOps 接入变更。运行示例见仓库 README。"""
import argparse
import fcntl
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = {
    "java": ("java-api", "java-maven"),
    "python": ("python-api", "python"),
    "go": ("go-api", "go"),
    "node": ("frontend-web", "frontend"),
}


def read_yaml(path):
    return yaml.safe_load(path.read_text())


def dump(data):
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def substitute(data, values):
    """只替换完整的标量值，避免相似名称和路径被部分替换。"""
    if isinstance(data, dict):
        return {k: substitute(v, values) for k, v in data.items()}
    if isinstance(data, list):
        return [substitute(v, values) for v in data]
    return values.get(data, data)


def slug(path):
    return re.sub("[^a-z0-9]", "-", path.lower())[:63].strip("-")


def generate(root, args):
    app, key = args.app, args.project_key
    sample, job = LANGUAGES[args.language]
    source = args.gitlab_project_path
    for name in (app, key):
        if not re.fullmatch("[a-z][a-z0-9-]*[a-z0-9]|[a-z]", name) or len(name) > 58:
            raise ValueError("应用和项目名须为小写 DNS 标签，最长 58 位")
    if not re.fullmatch(r"[\w.-]+(?:/[\w.-]+)+", source, re.ASCII) or any(
        part in (".", "..") for part in source.split("/")
    ):
        raise ValueError("请填写完整 GitLab 项目路径")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.robot):
        raise ValueError("请填写该项目机器人的实际 GitLab 登录名")
    for server in (args.server_stg, args.server_prod):
        url = urlsplit(server)
        if url.scheme != "https" or not url.hostname or url.username or url.query or url.fragment:
            raise ValueError("目标集群须使用在 Argo CD 登记的 HTTPS 地址")
    mapping_path = root / "policies/promotion-sources.json"
    mapping = json.loads(mapping_path.read_text())
    if args.robot in mapping or any(slug(repo) == slug(source) or dest.split("/")[-1] == app
                                    for repo, dest, _ in mapping.values()):
        raise ValueError("机器人、业务仓库、镜像名或应用名已经登记")

    destination = f"apps/{key}/{app}"
    if (root / destination).exists():
        raise ValueError("应用目录已存在")
    sample_dir = root / "apps/demo" / sample
    image = f"{args.registry_host}/{slug(source)}"
    sample_image = read_yaml(sample_dir / "base/deployment.yaml")["spec"]["template"]["spec"]["containers"][0]["image"]
    values = {sample: app, "demo": key, sample_image: image}
    writes = {}
    updates = {mapping_path}
    for file in (sample_dir / "base").glob("*.yaml"):
        writes[root / destination / "base" / file.name] = dump(substitute(read_yaml(file), values))

    for env, server in (("stg", args.server_stg), ("prod", args.server_prod)):
        ns = f"{app}-{env}"
        sample_ns = f"{sample}-{env}"
        env_values = {**values, sample_ns: ns, f"demo-{sample_ns}": f"{key}-{ns}"}
        overlay_path = f"{destination}/overlays/{env}"
        overlay = substitute(read_yaml(sample_dir / "overlays" / env / "kustomization.yaml"), env_values)
        overlay["images"] = [{"name": image, "digest": "sha256:" + "0" * 64}]
        writes[root / overlay_path / "kustomization.yaml"] = dump(overlay)

        # 平台资产由单独的 Application 发往业务集群，不放入默认平台集群。
        asset_path = f"{destination}/platform/{env}"
        assets = []
        for filename in ("namespaces.yaml", "quotas.yaml", "networkpolicies.yaml"):
            for doc in yaml.safe_load_all((root / "platform" / env / filename).read_text()):
                meta = doc["metadata"]
                if meta.get("namespace", meta["name"]) == sample_ns:
                    assets.append(substitute(doc, env_values))
        if not {"Namespace", "ResourceQuota", "LimitRange", "NetworkPolicy"} <= {a["kind"] for a in assets}:
            raise ValueError(f"{env} 平台资产基线不完整")
        writes[root / asset_path / "assets.yaml"] = yaml.safe_dump_all(assets, sort_keys=False)
        writes[root / asset_path / "kustomization.yaml"] = dump({
            "apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization", "resources": ["assets.yaml"]})

        for group in ("projects", "applications"):
            folder = root / "argocd" / group / env
            index = folder / "kustomization.yaml"
            resources = read_yaml(index)["resources"]
            existing = {read_yaml(p)["metadata"]["name"] for p in folder.glob("*.yaml") if p != index}
            names = []
            for platform in (False, True):
                stem = f"platform-{app}" if platform else app
                project = f"platform-{ns}" if platform else f"{key}-{ns}"
                template = "platform" if platform else sample
                obj = substitute(read_yaml(folder / f"{template}.yaml"), env_values)
                name = project if group == "projects" else f"{stem}-{env}"
                filename = stem + ".yaml"
                if name in existing or filename in resources:
                    raise ValueError(f"{group}/{env}: {name} 已存在")
                existing.add(name)
                spec = obj["spec"]
                obj["metadata"]["name"] = name
                target = {"server": server, "namespace": ns}
                if group == "projects":
                    spec.update(sourceRepos=[args.gitops_url], destinations=[target])
                    spec["description"] = f"{key}/{app} {env} " + ("平台资产" if platform else "业务应用")
                    if env == "prod":
                        spec["syncWindows"] = read_yaml(folder / "platform.yaml")["spec"]["syncWindows"]
                else:
                    spec["project"] = project
                    spec["destination"] = target
                    spec["source"].update(repoURL=args.gitops_url, path=asset_path if platform else overlay_path)
                writes[folder / filename] = dump(obj)
                names.append(filename)
            # 保留现有索引注释。当前索引的最后一个字段是块形式 resources 列表。
            content = index.read_text().rstrip() + "\n" + "".join(f"  - {n}\n" for n in names)
            if yaml.safe_load(content) != {**read_yaml(index), "resources": resources + names}:
                raise ValueError(f"{index} 索引格式不匹配")
            writes[index] = content
            updates.add(index)
    mapping[args.robot] = [source, f"{key}/{app}", job]
    writes[mapping_path] = json.dumps(mapping, ensure_ascii=False, indent=2) + "\n"
    for path in writes:
        if path.resolve() != path or (path.exists() and path not in updates):
            raise ValueError(f"路径冲突: {path}")
    return writes


def install(writes):
    originals = {}
    created_dirs = []
    try:
        for path, content in writes.items():
            missing = []
            parent = path.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for folder in reversed(missing):
                folder.mkdir()
                created_dirs.append(folder)
            previous = path.read_bytes() if path.exists() else None
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                tmp_path.write_text(content)
                tmp_path.chmod(0o644)
                tmp_path.replace(path)
                originals[path] = previous
            finally:
                tmp_path.unlink(missing_ok=True)
    except BaseException:
        for path, previous in reversed(originals.items()):
            if previous is None:
                path.unlink()
            else:
                path.write_bytes(previous)
        for folder in reversed(created_dirs):
            folder.rmdir()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("project-key", "app", "gitlab-project-path", "robot", "registry-host",
                "server-stg", "server-prod", "gitops-url"):
        parser.add_argument("--" + arg, required=True)
    parser.add_argument("--language", choices=LANGUAGES, required=True)
    args = parser.parse_args()
    fd = os.open(ROOT, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        writes = generate(ROOT, args)
        install(writes)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"接入失败: {exc}\n")
    finally:
        os.close(fd)
    print(f"已生成 {args.project_key}/{args.app} 的 GitOps 变更，请审核后提交 MR")


if __name__ == "__main__":
    main()
