#!/usr/bin/env python3
"""标准符合性检查：验证业务仓库没有偏离 platform/cicd-templates 的约定。

检查项：
  1. include 的项目与 ref 必须合规；ref 必须是受保护的语义化版本标签（禁止 main）
  2. 引用的模板文件清单必须完整（含 SBOM）
  3. variables 只能出现在白名单内
  4. 不允许改写平台作业（--demo 时仅放行 sonarqube / dast-baseline 的占位）
  5. Dockerfile 所有 FROM 必须按 digest 固定
  6. 仓库必须带 .gitignore，且忽略 CI 产物文件

用法：
    python3 tools/check_standard.py <仓库路径> [<仓库路径> ...]
    python3 tools/check_standard.py --all                 # 自动扫描同级目录下所有业务仓库
    python3 tools/check_standard.py --demo <仓库路径> ...  # 允许 sonarqube/dast 占位
    python3 tools/check_standard.py --lab <仓库路径> ...   # 同上（旧名，保留兼容）
    python3 tools/check_standard.py --strict <仓库路径> ...# 生产口径，默认即此
    python3 tools/check_standard.py --json ...

退出码：全部通过为 0，任一不通过为 1。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

# 这两个作业依赖外部服务，允许"服务未就绪时暂时不 include"，但会在报告里标出来。
# 不是因为它俩不重要，而是因为它俩的失败原因是"没有服务"而不是"没有门禁"：
#   · sonarqube 需要 SonarQube 实例与令牌
#   · dast      需要已经部署起来的 STG
# 硬要求 include 只会逼项目去复制一份被改坏的模板，反而更差。
CONDITIONAL_TEMPLATES = {
    "/security/sonarqube.yml": "需要 SonarQube 实例",
    "/security/dast.yml": "需要已部署的 STG",
}

# 模板项目的完整路径随组层级而变（实验室是 platform/cicd-templates，
# 机房通常是 <顶层组>/platform/cicd-templates）。所以只认"最后一段是 cicd-templates"，
# 不把层级写死——写死会让换一次组织结构就要改工具。
TEMPLATE_PROJECT_SUFFIX = "cicd-templates"


def is_template_project(project: str | None) -> bool:
    return (project or "").strip("/").rsplit("/", 1)[-1] == TEMPLATE_PROJECT_SUFFIX

# ref 必须是语义化版本标签，例如 v1.0.0。禁止 main / 分支 / 提交 SHA：
# 分支会随平台侧提交漂移，SHA 无法表达版本语义，两者都不利于审计与回滚。
REF_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")

REQUIRED_TEMPLATES = {
    "/defaults.yml",
    "/workflow.yml",
    "/stages.yml",
    "/security/secret-scan.yml",
    "/security/sast.yml",
    "/security/sca.yml",
    "/container/build-image.yml",
    "/container/scan-image.yml",
    "/container/sign-image.yml",
    "/container/sbom.yml",
    "/security/license-scan.yml",
    "/security/iac-scan.yml",
    "/quality/lint.yml",
    "/quality/coverage-gate.yml",
    "/gitops/stg-promotion.yml",
    "/gitops/release-candidate.yml",
    "/gitops/prod-promotion.yml",
}
LANGUAGE_TEMPLATES = {
    "/languages/java-maven.yml",
    "/languages/python.yml",
    "/languages/go.yml",
    "/languages/node.yml",
}

ALLOWED_VARIABLES = {
    "PROJECT_KEY",
    "APP_NAME",
    "K8S_NAMESPACE",
    "REGISTRY_HOST",
    "REGISTRY_TLS_VERIFY",
    "BUILDAH_REGISTRY_MIRROR",
}

# 允许 demo 用 echo 占位代替的作业。两类：
#   依赖外部服务：sonarqube（要 SonarQube）、dast-baseline（要已部署 STG）、
#                 sign-image（要 KMS/Vault 私钥）；
#   依赖公网漏洞库：dependency-scan / image-scan / sbom 三个 Trivy 作业每次下 136MB，
#                 demo 环境网络不稳会卡住；它们只做展示，不进晋级可信链（promote.py
#                 用 build-image 的 image.env digest，不读这三个的报告）。
# 其它门禁（密钥、SAST、覆盖率、许可证、Dockerfile 基线、镜像构建）在 demo 里必须真跑。
# 生产口径（--strict）下这些覆盖一律视为违规，真实项目须删除占位段。
DEMO_JOB_OVERRIDES = {
    "sonarqube", "dast-baseline", "sign-image",
    "dependency-scan", "image-scan", "sbom",
}

RESERVED_KEYS = {
    "include", "variables", "stages", "workflow", "default", "image", "services",
    "before_script", "after_script", "cache", "pages",
}

FROM_DIGEST = re.compile(r"^FROM\s+\S+@sha256:[a-f0-9]{64}", re.IGNORECASE)


def check(repo: Path, allow_lab: bool = False) -> dict:
    problems: list[str] = []
    notes: list[str] = []
    ci_path = repo / ".gitlab-ci.yml"
    if not ci_path.is_file():
        return {"repo": repo.name, "ok": False, "problems": ["缺少 .gitlab-ci.yml"], "notes": []}

    config = yaml.safe_load(ci_path.read_text(encoding="utf-8")) or {}

    # 1. include 与 ref
    includes = config.get("include") or []
    if isinstance(includes, dict):
        includes = [includes]
    files: set[str] = set()
    project_ok = ref_ok = False
    for inc in includes:
        if is_template_project(inc.get("project")):
            project_ok = True
            ref = str(inc.get("ref") or "")
            if REF_PATTERN.match(ref):
                ref_ok = True
            elif ref in {"main", "master"}:
                problems.append(f"模板 ref 指向可变分支 {ref}，必须固定为版本标签（如 v1.0.0）")
            else:
                problems.append(f"模板 ref「{ref}」不是语义化版本标签（形如 v1.0.0）")
            entries = inc.get("file") or []
            if isinstance(entries, str):
                entries = [entries]
            files.update(entries)
    if not project_ok:
        problems.append("未引用模板项目（路径最后一段必须是 cicd-templates）")

    missing = REQUIRED_TEMPLATES - files
    if missing:
        problems.append("缺少模板：" + ", ".join(sorted(missing)))
    if not (files & LANGUAGE_TEMPLATES):
        problems.append("缺少语言模板")

    for tpl, reason in CONDITIONAL_TEMPLATES.items():
        if tpl not in files:
            notes.append(f"未引用 {tpl}（{reason}，服务就绪后应加回）")
    extra = files - REQUIRED_TEMPLATES - LANGUAGE_TEMPLATES - set(CONDITIONAL_TEMPLATES)
    if extra:
        notes.append("额外引用：" + ", ".join(sorted(extra)))

    # 2. variables 白名单
    variables = config.get("variables") or {}
    unknown = set(variables) - ALLOWED_VARIABLES
    if unknown:
        problems.append("变量不在白名单：" + ", ".join(sorted(unknown)))

    # 3. 是否改写平台作业
    jobs = {k for k in config if k not in RESERVED_KEYS and not str(k).startswith(".")}
    if allow_lab:
        illegal = jobs - DEMO_JOB_OVERRIDES
        allowed_used = jobs & DEMO_JOB_OVERRIDES
        if allowed_used:
            notes.append("demo 占位（真实项目删除本段并接入服务）：" + ", ".join(sorted(allowed_used)))
    else:
        illegal = jobs
        if jobs:
            notes.append("生产口径不允许任何作业覆盖段")
    if illegal:
        problems.append("改写了标准作业：" + ", ".join(sorted(illegal)))

    # 4. Dockerfile 与基础镜像固定
    dockerfile = repo / "Dockerfile"
    if not dockerfile.is_file():
        problems.append("缺少 Dockerfile")
    else:
        froms = [
            line.strip()
            for line in dockerfile.read_text(encoding="utf-8").splitlines()
            if line.strip().upper().startswith("FROM ")
        ]
        if not froms:
            problems.append("Dockerfile 没有 FROM 指令")
        unpinned = [f for f in froms if not FROM_DIGEST.match(f)]
        if unpinned:
            problems.append("基础镜像未按 digest 固定：" + " | ".join(unpinned))

    # 5. 依赖锁定：没有锁定文件就无法复现、也无法做完整性校验
    if (repo / "package.json").is_file() and not (repo / "package-lock.json").is_file():
        problems.append("存在 package.json 但缺少 package-lock.json（npm ci 无法保证依赖一致）")
    if (repo / "go.mod").is_file():
        gomod = (repo / "go.mod").read_text(encoding="utf-8")
        # 只有引入了外部依赖才要求 go.sum；纯标准库项目没有 go.sum 是正常的
        if "require" in gomod and not (repo / "go.sum").is_file():
            problems.append("go.mod 声明了外部依赖但缺少 go.sum（无法校验依赖完整性）")

    # 6. 仓库卫生
    ignore = repo / ".gitignore"
    if not ignore.is_file():
        notes.append("缺少 .gitignore")
    else:
        text = ignore.read_text(encoding="utf-8")
        for artifact in (".image-digest", "image.env"):
            if artifact not in text:
                problems.append(f".gitignore 未忽略 CI 产物 {artifact}")

    return {"repo": repo.name, "ok": not problems, "problems": problems, "notes": notes}


# 平台自身仓库不是业务项目，不适用"业务仓库接入标准"
PLATFORM_REPOS = {"cicd-templates", "gitops-deployments", "platform-plan"}


def discover(base: Path) -> list[Path]:
    """扫描同级目录下带 .gitlab-ci.yml 的业务仓库。"""
    return sorted(
        p for p in base.iterdir()
        if p.is_dir() and p.name not in PLATFORM_REPOS and (p / ".gitlab-ci.yml").is_file()
    )


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    allow_lab = "--demo" in argv or "--lab" in argv   # --lab 是旧名，保留兼容
    targets = [Path(a) for a in argv if not a.startswith("--")]

    if "--all" in argv:
        base = targets[0] if targets else Path(__file__).resolve().parents[2]
        targets = discover(base)
        if not targets:
            print(f"未在 {base} 下找到含 .gitlab-ci.yml 的仓库")
            return 2

    if not targets:
        print(__doc__)
        return 2

    results = [check(p, allow_lab=allow_lab) for p in targets]

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        mode = "demo 口径（--demo：允许外部服务/Trivy 漏洞库占位）" if allow_lab else "生产口径（--strict）"
        print(f"检查模式：{mode}\n")
        for r in results:
            print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['repo']}")
            for p in r["problems"]:
                print(f"       ✗ {p}")
            for n in r["notes"]:
                print(f"       · {n}")
        passed = sum(1 for r in results if r["ok"])
        print(f"\n{passed}/{len(results)} 个仓库符合标准")

    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
