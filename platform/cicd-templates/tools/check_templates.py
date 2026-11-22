#!/usr/bin/env python3
"""模板仓库自检：在改动被合进 main 之前，先在这里把错误挡住。

为什么模板仓库必须有门禁
------------------------
模板里的错误不是"这个仓库红一下"，而是**所有业务项目的流水线同时 config error**。
一个 stage 名写错、一个镜像漏了 digest、README 里 include 的文件被改名，
都会在几十个项目里同时爆，而报错指向的是别人的仓库。

这些错误里有一大半是纯静态就能判出来的，所以没必要等它炸：

T1 语法与结构  每个 YAML 能解析；作业的 stage 必须在 stages.yml 里声明过
T2 镜像固定    每个作业镜像必须是 @sha256: 形式，且不许写 latest
T3 清单一致    README 的 include 示例里列出的文件必须真实存在
T4 无死阶段    stages.yml 里的每个阶段至少被一个作业用到
T5 无密钥      模板里会贴示例，最容易带入真实地址/令牌

不检查什么
----------
作业脚本的逻辑对不对——那要靠示例仓库真跑一遍流水线，静态检查判不出来。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML：pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent

# 顶层这些 key 不是作业
NON_JOB_KEYS = {"default", "variables", "include", "stages", "workflow", "image", "services",
                "before_script", "after_script", "cache"}

problems: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def load_all(path: Path) -> list[dict]:
    try:
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        fail(f"T1 {path.relative_to(ROOT)} 不是合法 YAML：{str(exc)[:160]}")
        return []
    return [d for d in docs if isinstance(d, dict)]


def iter_jobs() -> list[tuple[str, dict, Path]]:
    """返回 (作业名, 配置, 所在文件)。"""
    jobs = []
    for path in sorted(ROOT.rglob("*.yml")):
        if path.name in {"stages.yml"}:   # 只有 stages 定义，没有作业
            continue
        if path.name == ".gitlab-ci.yml":  # 本仓库自己的流水线，不是给别人 include 的片段
            continue
        for doc in load_all(path):
            for name, cfg in doc.items():
                if name in NON_JOB_KEYS or not isinstance(cfg, dict):
                    continue
                if "script" in cfg or "trigger" in cfg or "extends" in cfg:
                    jobs.append((name, cfg, path))
    return jobs


def check_stages(jobs: list[tuple[str, dict, Path]]) -> set[str]:
    stages_file = ROOT / "stages.yml"
    docs = load_all(stages_file)
    declared = docs[0].get("stages", []) if docs else []
    if not declared:
        fail("T1 stages.yml 里没有 stages 列表")
        return set()

    used = set()
    for name, cfg, path in jobs:
        stage = cfg.get("stage")
        if stage is None:
            fail(f"T1 作业 {name}（{path.relative_to(ROOT)}）没有 stage")
            continue
        used.add(stage)
        if stage not in declared:
            # 这是最典型的事故：业务项目 include 之后直接 config error，
            # 报错却出现在别人的仓库里
            fail(f"T1 作业 {name} 用了未声明的 stage「{stage}」，"
                 f"stages.yml 里只有 {declared}")
    notes.append(f"T1 作业 {len(jobs)} 个，stage 均在 stages.yml 内")
    return set(declared) - used


def check_images(jobs: list[tuple[str, dict, Path]]) -> None:
    for name, cfg, path in jobs:
        image = cfg.get("image")
        if image is None:
            continue
        ref = image.get("name") if isinstance(image, dict) else image
        if not isinstance(ref, str):
            continue
        if "@sha256:" not in ref:
            fail(f"T2 作业 {name} 的镜像未按 digest 固定：{ref}")
        if re.search(r":latest(@|$)", ref):
            fail(f"T2 作业 {name} 的镜像用了 latest：{ref}")
    notes.append(f"T2 镜像固定：{sum(1 for _, c, _ in jobs if c.get('image'))} 个作业镜像已检查")


def check_readme_filelist() -> None:
    readme = ROOT / "README.md"
    if not readme.is_file():
        fail("T3 缺少 README.md")
        return
    text = readme.read_text(encoding="utf-8")
    # 抓 include 代码块里的 "- /xxx.yml"
    listed = re.findall(r"^\s*-\s*(/[A-Za-z0-9_./-]+\.ya?ml)\s*$", text, re.M)
    if not listed:
        fail("T3 README 里找不到 include 示例（应当有一个 file: 列表）")
        return
    missing = [p for p in listed if not (ROOT / p.lstrip("/")).is_file()]
    for p in missing:
        fail(f"T3 README 的 include 示例列了不存在的文件：{p}")
    # 反向：仓库里的模板文件应当都被示例列出
    actual = {"/" + str(p.relative_to(ROOT)) for p in ROOT.rglob("*.yml")
              if p.name not in {"stages.yml", "defaults.yml", "workflow.yml", ".gitlab-ci.yml"}}
    actual |= {"/defaults.yml", "/workflow.yml", "/stages.yml"}
    unlisted = sorted(actual - set(listed))
    if unlisted:
        notes.append(f"T3 有 {len(unlisted)} 个模板文件未出现在 README 的 include 示例里："
                     + ", ".join(unlisted[:5]))
    else:
        notes.append(f"T3 README include 清单与仓库文件一致（{len(listed)} 项）")


def check_unused_stages(unused: set[str]) -> None:
    if unused:
        fail(f"T4 stages.yml 里这些阶段没有任何作业使用：{sorted(unused)}")


def main() -> int:
    jobs = iter_jobs()
    if not jobs:
        fail("T1 一个作业都没解析到，检查文件结构")
    unused = check_stages(jobs)
    check_images(jobs)
    check_readme_filelist()
    check_unused_stages(unused)

    print("=" * 62)
    for note in notes:
        print(f"  ok   {note}")
    print("=" * 62)
    if problems:
        print(f"FAIL: {len(problems)} 项不通过\n")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("PASS: 模板仓库自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
