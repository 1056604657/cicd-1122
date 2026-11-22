"""只读查询 STG Argo CD，记录指定版本已同步并健康的时间。"""
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request


def healthy_application(app, declared, revision, image):
    spec = app["spec"]
    if (spec["source"] != declared["spec"]["source"] or
            spec["destination"] != declared["spec"]["destination"] or
            spec["project"] != declared["spec"]["project"] or
            app["metadata"]["name"] != declared["metadata"]["name"]):
        raise ValueError("Argo CD Application 来源或部署目标与声明不符")
    status = app.get("status") or {}
    sync = status.get("sync") or {}
    return (sync.get("revision") == revision and sync.get("status") == "Synced"
            and (status.get("health") or {}).get("status") == "Healthy"
            and image in (status.get("summary") or {}).get("images", []))


def wait_for_stg(opener, declared, revision, image):
    url = os.environ["STG_ARGOCD_URL"].rstrip("/")
    if not url.startswith("https://"):
        raise ValueError("STG_ARGOCD_URL 需要受信任的 HTTPS 地址")
    name = declared["metadata"]["name"]
    request = Request(url + "/api/v1/applications/" + quote(name, safe=""),
                      headers={"Authorization": "Bearer " + os.environ["STG_ARGOCD_READ_TOKEN"]})
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        with opener.open(request, timeout=20) as response:
            current = json.load(response)
        if healthy_application(current, declared, revision, image):
            return {"application": name, "destination": declared["spec"]["destination"],
                    "gitopsRevision": revision, "observedAt": datetime.now(timezone.utc).isoformat()}
        time.sleep(5)
    raise TimeoutError(f"{name} 未在 10 分钟内确认 revision {revision} 已同步且健康")
