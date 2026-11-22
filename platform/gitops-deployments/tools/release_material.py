"""校验 GitOps 已归档的窗口清单及每个应用的供应商测试报告。"""
import json
import re

import jsonschema
import yaml


def checked_materials(root, release_id):
    if not re.fullmatch(r"REL-[0-9]{8}-[0-9]{3}", release_id):
        raise ValueError("发布清单编号无效")
    folder = root / "releases" / release_id

    def read(path, schema):
        if path.resolve().parent != folder.resolve() or path.is_symlink():
            raise ValueError("发布材料须位于对应清单目录")
        data = yaml.safe_load(path.read_text())
        definition = root / "policies" / (schema + ".schema.json")
        jsonschema.validate(data, json.loads(definition.read_text()))
        return data

    lists = [folder / ("deployment-list" + ext) for ext in (".yaml", ".yml", ".json")]
    found = [p for p in lists if p.is_file()]
    if len(found) != 1:
        raise ValueError("每个窗口须有且只有一份部署清单")
    listing = read(found[0], "deployment-list")
    meta = listing["metadata"]
    if meta["releaseId"] != release_id:
        raise ValueError("窗口编号与目录不符")
    entries = {}
    for item in listing["spec"]["applications"]:
        name = item["name"]
        report_name = item["testReport"]
        if name in entries or not re.fullmatch(r'test-report-[\w.-]+\.(yaml|yml|json)', report_name):
            raise ValueError("应用重复或测试报告文件名无效")
        report = read(folder / report_name, "test-report")
        expected = dict(releaseId=release_id, project=meta["project"], app=name,
                        sourceTag=item["sourceTag"], digest=item["image"].rsplit("@", 1)[1])
        if report["metadata"] != expected:
            raise ValueError(f"{name} 测试报告与窗口、应用、版本或 digest 不符")
        t = report["spec"]["tests"]
        if t["failed"] or not t["passed"] or t["total"] != t["passed"] + t["skipped"]:
            raise ValueError(f"{name} 测试结论不通过或统计不一致")
        entries[name] = item
    return meta["project"], entries
