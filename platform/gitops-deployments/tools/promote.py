"""受保护的 GitOps 作业。请求方仅提交自己的流水线编号。"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml

from release_material import checked_materials
from stg_receipt import wait_for_stg


class NoRedirect(HTTPRedirectHandler):
    # 只向配置的 GitLab API 发送只读凭证。
    def redirect_request(self, *args):
        return None


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def git(*args, check=True):
    return subprocess.run(["git", *args], check=check, text=True, stdout=subprocess.PIPE)


def verified_source(api, pipeline_id, action, language, image):
    pipe = api(f"/pipelines/{pipeline_id}")
    sha = pipe["sha"]
    require(re.fullmatch("[0-9a-f]{40}", sha), "非法源码提交")
    default = api("")["default_branch"]
    require(not pipe["tag"] and pipe["ref"] == default and pipe["source"] in ("push", "web"),
            "需要默认分支流水线")
    branch = api("/repository/branches/" + quote(default, safe=""))
    require(branch["protected"], "默认分支未保护")
    if action == "stg":
        require(branch["commit"]["id"] == sha, "拒绝过期的 STG 请求")

    jobs = {}
    page = 1
    while True:
        rows = api(f"/pipelines/{pipeline_id}/jobs?per_page=100&page={page}")
        jobs.update({j["name"]: j for j in rows})
        if len(rows) < 100:
            break
        page += 1
    require(jobs.get(action + "-promotion", {}).get("status") == "running", "来源晋级作业未运行")
    if action == "prod":
        for name in ("stg-promotion", "release-candidate"):
            require(jobs.get(name, {}).get("status") == "success", name + " 未成功")
        job_id = jobs["release-candidate"]["id"]
        release_id = api(f"/jobs/{job_id}/artifacts/release-id.txt", raw=True).strip()
        require(re.fullmatch(r"REL-[0-9]{8}-[0-9]{3}", release_id), "申请的清单编号无效")
        return sha, release_id

    gates = {language + "-test", language + "-build", "coverage-gate", "secret-scan", "sast",
             "dependency-scan", "license-scan", "license-gate", "dockerfile-policy", "sbom",
             "build-image", "image-scan"}
    require(all(jobs.get(k, {}).get("status") == "success" for k in gates), "来源门禁未通过")
    artifact = api(f"/jobs/{jobs['build-image']['id']}/artifacts/image.env", raw=True)
    prefix = "IMAGE_REF=" + image + "@"
    require(artifact.startswith(prefix), "镜像与项目配置不匹配")
    digest = artifact[len(prefix):].strip()
    require(re.fullmatch("sha256:[0-9a-f]{64}", digest), "镜像 digest 非法")
    return sha, image + "@" + digest


def production_image(root, release_id, project, app, pipeline_id, sha, record):
    key, name = app.split("/")
    owner, entries = checked_materials(root, release_id)
    require(owner == key and name in entries, "窗口清单未包含本项目和应用")
    entry = entries[name]
    if "sourcePipeline" in entry:  # 兼容已经填写流水线编号的清单
        require(entry["sourcePipeline"] == pipeline_id, "清单与所选业务流水线不符")
    require((record["project"], record["app"], record["pipeline"], record["commit"], record["image"])
            == (project, app, pipeline_id, sha, entry["image"]), "清单与 STG 健康部署凭证不符")
    require(re.fullmatch("[0-9a-f]{40}", record.get("gitopsRevision", "")) and
            record.get("application") and record.get("destination") and record.get("observedAt"),
            "缺少 STG 的同步目标、版本或健康观察时间")
    return entry["image"]


def commit_file(path, subject, project, pipeline_id):
    git("add", "--", str(path))
    git("-c", "user.name=gitops-promotion", "-c", "user.email=ci-bot@noreply.local",
        "commit", "-m", subject, "-m", f"Source: {project} pipeline {pipeline_id}")


def write_receipt(path, record, branch, push):
    for _ in range(3):
        git("fetch", "origin", "refs/heads/" + branch)
        git("checkout", "--detach", "-f", "FETCH_HEAD")
        if path.exists():
            saved = json.loads(path.read_text())
            require(all(saved[k] == record[k] for k in ("project", "app", "pipeline", "commit", "image")),
                    "已有不同的 STG 凭证")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + "\n")
        commit_file(path, f"record(stg): {record['app']} #{record['pipeline']}", record["project"], record["pipeline"])
        if push(branch).returncode == 0:
            return
    raise ValueError("STG 已确认健康，但凭证归档失败，请重试")


def main():
    pipeline_id, action = sys.argv[1:]
    require(action in ("stg", "prod"), "无效晋级操作")
    require(re.fullmatch("[1-9][0-9]{0,17}", pipeline_id), "缺少业务流水线编号")
    sources = json.loads(Path("policies/promotion-sources.json").read_text())
    owner = os.environ["GITLAB_USER_LOGIN"]
    require(owner in sources, "未登记此触发身份")
    project, app, language = sources[owner]
    api_url = os.environ["CI_API_V4_URL"] + "/projects/" + quote(project, safe="")
    opener = build_opener(NoRedirect())

    def api(path, raw=False):
        request = Request(api_url + path, headers={"PRIVATE-TOKEN": os.environ["PROMOTION_READ_TOKEN"]})
        with opener.open(request, timeout=30) as response:
            data = response.read().decode()
            return data if raw else json.loads(data)

    base = Path("apps") / app / "overlays"
    branch = os.environ["CI_DEFAULT_BRANCH"]
    push_url = os.environ["CI_PROJECT_URL"] + ".git"
    helper = '!f() { echo username=oauth2; echo "password=$GITOPS_TOKEN"; }; f'

    def push(target, *options):
        return git("-c", "credential.helper=", "-c", "credential.helper=" + helper, "push",
                   *options, push_url, "HEAD:refs/heads/" + target, check=False)

    prod = action == "prod"
    receipt = Path("evidence/stg") / app / (pipeline_id + ".json")
    for _ in range(3):
        git("fetch", "origin", "refs/heads/" + branch)
        git("checkout", "--detach", "-f", "FETCH_HEAD")
        overlay = base / action
        file = overlay / "kustomization.yaml"
        image, = yaml.safe_load(file.read_text())["images"]
        name = image["name"]
        sha, result = verified_source(api, pipeline_id, action, language, image.get("newName", name))
        target = branch
        options = []
        if prod:
            release_id = result
            require(receipt.is_file(), "该历史流水线缺少 STG 健康凭证")
            ref = production_image(Path("."), release_id, project, app, pipeline_id, sha,
                                   json.loads(receipt.read_text()))
            target = f"release/{release_id}/{app}/{pipeline_id}"
            options = ["-o", "merge_request.create", "-o", "merge_request.target=" + branch,
                       "-o", "merge_request.remove_source_branch"]
        else:
            ref = result
            if receipt.exists():
                saved = json.loads(receipt.read_text())
                require((saved["commit"], saved["image"]) == (sha, ref), "该流水线已归档不同的镜像")
                return
        subprocess.run(["kustomize", "edit", "set", "image", name + "=" + ref], cwd=overlay, check=True)
        rendered = subprocess.check_output(["kustomize", "build", str(overlay)], text=True)
        workloads = [d for d in yaml.safe_load_all(rendered) if d["kind"] == "Deployment"
                     and d["metadata"]["name"] == app.split("/")[-1]]
        require(len(workloads) == 1 and any(c["image"] == ref for c in
                workloads[0]["spec"]["template"]["spec"]["containers"]), "部署清单未渲染出目标镜像")
        subject = f"release(prod): {release_id} {app} #{pipeline_id}" if prod else f"chore(stg): {app} #{pipeline_id}"
        changed = git("diff", "--quiet", "--", str(file), check=False).returncode != 0
        if changed:
            commit_file(file, subject, project, pipeline_id)
            pushed = push(target, *options)
            if not prod and pushed.returncode != 0:
                continue
        elif prod:
            print("生产已声明清单中的镜像，无需重复晋级")
            return
        if prod:
            git("fetch", "origin", "refs/heads/" + target)
            same = git("diff", "--quiet", "FETCH_HEAD", "HEAD", "--", str(file), check=False)
            require(same.returncode == 0, "已有发布分支与本次候选不同")
            head = git("rev-parse", "FETCH_HEAD").stdout.strip()
            mrs = gitops_open_mrs(target, branch, opener)
            require(any(mr["sha"] == head and str(mr["source_project_id"]) == os.environ["CI_PROJECT_ID"]
                        for mr in mrs), "发布分支存在，缺少对应的开放 MR")
            return
        revision = git("rev-parse", "HEAD").stdout.strip()
        app_name = app.split("/")[-1]
        declared = yaml.safe_load((Path("argocd/applications/stg") / (app_name + ".yaml")).read_text())
        require(declared["spec"]["source"]["path"] == str(overlay), "Application 与 STG overlay 不匹配")
        observed = wait_for_stg(opener, declared, revision, ref)
        write_receipt(receipt, dict(project=project, app=app, pipeline=pipeline_id, commit=sha,
                                    image=ref, **observed), branch, push)
        return
    raise ValueError("并发更新或推送失败，请重试")


def gitops_open_mrs(source, target, opener):
    from urllib.parse import urlencode
    query = urlencode({"state": "opened", "source_branch": source, "target_branch": target})
    url = os.environ["CI_API_V4_URL"] + "/projects/" + os.environ["CI_PROJECT_ID"]
    req = Request(url + "/merge_requests?" + query,
                  headers={"PRIVATE-TOKEN": os.environ["PROMOTION_READ_TOKEN"]})
    with opener.open(req, timeout=30) as response:
        return json.load(response)


if __name__ == "__main__":
    main()
