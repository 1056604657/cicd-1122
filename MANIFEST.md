# 归档清单

- 生成时间：2026-11-23 14:39:27 +0800
- 来源目录：`/Users/babyyy/工作/Hyundai/cicd-workbuddy`
- 文件总数：131（含本 README/MANIFEST/SNAPSHOT 之外由 7 个仓库复制的文件）

| 归档路径 | 源分支 | HEAD | 最近提交 | 跟踪文件数 | 工作区干净 | 说明 |
|---|---|---|---|---:|---|---|
| `platform/cicd-templates` | `main` | `ae09fb58a40b` | Merge branch 'fix/optional-stg-dast' into 'main' | 27 | 是 | 流水线模板：9 阶段、Java/Python/Go/Node 构建、质量门禁、镜像构建、STG/PROD 晋级作业 |
| `platform/gitops-deployments` | `main` | `0772db715fcf` | Merge branch 'fix/register-gitops-app' into 'main' | 67 | 是 | GitOps 事实源：Kustomize base/overlay、Argo CD Application/AppProject、发布清单、晋级脚本 |
| `platform/platform-plan` | `docs/idc-gitlab-deployment` | `b10f124ab3ce` | 新增机房 GitLab CI/CD 部署手册 | 3 | 是 | 总方案文档：架构、权限、发布流程、已知缺口和待确认事项 |
| `demo-projects/java-api` | `main` | `e7b00da46f2b` | Merge branch 'fix/optional-stg-dast' into 'main' | 7 | 是 | Java/Maven 示例业务仓库 |
| `demo-projects/python-api` | `main` | `4ff135528f62` | Merge branch 'fix/optional-stg-dast' into 'main' | 9 | 是 | Python 示例业务仓库 |
| `demo-projects/go-api` | `main` | `247ecbec14d3` | Merge branch 'fix/optional-stg-dast' into 'main' | 8 | 是 | Go 示例业务仓库 |
| `demo-projects/frontend-web` | `main` | `6668db7db47b` | Merge branch 'fix/optional-stg-dast' into 'main' | 10 | 是 | 前端/Node 示例业务仓库 |

## 模板引用

- demo-projects/java-api: v1.0.19
- demo-projects/python-api: v1.0.19
- demo-projects/go-api: v1.0.19
- demo-projects/frontend-web: v1.0.19

## 安全说明

- 源仓库的 `.git/` 目录没有复制，因此本地 GitLab remote URL 中的凭据不会进入 GitHub。
- `remote_sanitized` 字段只记录脱敏后的远端地址；详见 `SNAPSHOT.json`。
- 归档中没有包含本地实验用的 `lab/`、`*.env`、容器运行时状态和临时 token 文件。
