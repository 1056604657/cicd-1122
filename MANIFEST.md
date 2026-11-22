# 归档清单

- 生成时间：2026-11-22 22:43:09 +0800
- 来源目录：`/Users/babyyy/工作/Hyundai/cicd-workbuddy`
- 文件总数：129（含本 README/MANIFEST/SNAPSHOT 之外由 7 个仓库复制的文件）

| 归档路径 | 源分支 | HEAD | 最近提交 | 跟踪文件数 | 工作区干净 | 说明 |
|---|---|---|---|---:|---|---|
| `platform/cicd-templates` | `release/verified-stg-history` | `25b1ba715448` | 隔离作业并支持历史主干版本申请生产 | 27 | 是 | 流水线模板：9 阶段、Java/Python/Go/Node 构建、质量门禁、镜像构建、STG/PROD 晋级作业 |
| `platform/gitops-deployments` | `release/verified-stg-history` | `da9affb9058d` | 核验 STG 健康凭证并从历史流水线申请生产 | 66 | 是 | GitOps 事实源：Kustomize base/overlay、Argo CD Application/AppProject、发布清单、晋级脚本 |
| `platform/platform-plan` | `release/verified-stg-history` | `19ddf0e173ab` | 对齐版本、Runner 和窗口发布流程 | 2 | 是 | 总方案文档：架构、权限、发布流程、已知缺口和待确认事项 |
| `demo-projects/java-api` | `release/verified-stg-history` | `aae0462efa61` | 接入 v1.0.17 并同步示例发布说明 | 7 | 是 | Java/Maven 示例业务仓库 |
| `demo-projects/python-api` | `release/verified-stg-history` | `24fb625a724b` | 接入 v1.0.17 并同步示例发布说明 | 9 | 是 | Python 示例业务仓库 |
| `demo-projects/go-api` | `release/verified-stg-history` | `5db741066b5a` | 接入 v1.0.17 并同步示例发布说明 | 8 | 是 | Go 示例业务仓库 |
| `demo-projects/frontend-web` | `release/verified-stg-history` | `9450df87b2a7` | 接入 v1.0.17 并同步示例发布说明 | 10 | 是 | 前端/Node 示例业务仓库 |

## 模板引用

- demo-projects/java-api: v1.0.17
- demo-projects/python-api: v1.0.17
- demo-projects/go-api: v1.0.17
- demo-projects/frontend-web: v1.0.17

## 安全说明

- 源仓库的 `.git/` 目录没有复制，因此本地 GitLab remote URL 中的凭据不会进入 GitHub。
- `remote_sanitized` 字段只记录脱敏后的远端地址；详见 `SNAPSHOT.json`。
- 归档中没有包含本地实验用的 `lab/`、`*.env`、容器运行时状态和临时 token 文件。
