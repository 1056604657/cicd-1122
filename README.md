# GitLab CI/CD + GitOps 离线归档

本仓库是把本地 GitLab 中的 7 个仓库做成一个**只读查看用归档快照**，便于在没有本地 GitLab 网络时查看代码。

- 生成时间：2026-11-23 14:39:27 +0800
- 来源目录：`/Users/babyyy/工作/Hyundai/cicd-workbuddy`
- 当前各仓库分支：`docs/idc-gitlab-deployment`、`main`
- 模板引用：demo-projects/java-api: v1.0.19, demo-projects/python-api: v1.0.19, demo-projects/go-api: v1.0.19, demo-projects/frontend-web: v1.0.19
- 归档方式：仅复制每个仓库中 Git 跟踪的文件；**不包含 `.git` 目录，也不包含本地 GitLab root 凭据**。

## 目录结构

```text
platform/
├── cicd-templates/       流水线模板仓库快照
├── gitops-deployments/   Kustomize + Argo CD GitOps 仓库快照
└── platform-plan/        CI/CD + GitOps 方案文档快照

demo-projects/
├── java-api/             Java/Maven 示例业务仓库快照
├── python-api/           Python 示例业务仓库快照
├── go-api/               Go 示例业务仓库快照
└── frontend-web/         前端/Node 示例业务仓库快照
```

## 使用方式

1. 直接在 GitHub 网页查看目录和文件。
2. 需要离线完整副本时，下载本仓库 ZIP。
3. 需要核对当时源仓库版本时，查看根目录 `MANIFEST.md` 和 `SNAPSHOT.json`。

## 注意

- 这是快照，不是可继续推送的 7 个 GitLab 仓库本身；这里没有各仓库 Git 历史。
- 不要把本归档当作生产部署源。真实源仍是北京机房 GitLab 中的 7 个仓库。
- 本地工作副本的 `.git/config` 可能含内嵌凭据，**已刻意排除**，不要手工补进本仓库。
- 业务仓库 `.gitlab-ci.yml` 末尾保留了 demo 占位段，真实接入前应按注释删除。
