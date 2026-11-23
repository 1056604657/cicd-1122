# gitops-deployments

统一 GitOps 事实源仓库（Kustomize + Argo CD）。**本仓库是集群期望状态的唯一来源**，
任何人不得在集群上直接 `kubectl apply` 变更业务资源。

## 目录结构

```text
apps/<project>/<app>/base/               与环境无关的 Deployment / Service
apps/<project>/<app>/overlays/stg/       STG 差异（副本数、镜像、环境变量）
apps/<project>/<app>/overlays/prod/      PROD 差异（副本数、digest、环境变量）
platform/<env>/                          平台资产：命名空间、配额、限额、网络策略
argocd/projects/<env>/<app>.yaml         供应商应用 AppProject（最小权限）
argocd/projects/<env>/platform.yaml      平台 AppProject（管理平台资产）
argocd/applications/<env>/               Application：STG 自动同步，PROD 仅人工同步
argocd/bootstrap/<env>/                  app-of-apps 入口（每套 Argo CD 只 apply 这一层）
policies/                                部署清单与测试报告的 JSON Schema
releases/<releaseId>/                    每次生产发布的部署清单与测试报告留档（格式见 releases/README.md）
tools/add_app.py                         新应用的部署骨架生成器（overlay + Application + AppProject）
tools/validate_repo.py                   本仓库的策略校验（流水线里跑，也可本地跑）
```

## 关键约定

1. **镜像晋级不重建**：STG 由甲方作业写入构建 digest；PROD 由发布流程写入 STG 已验证镜像的 `digest`。
   禁止在生产重新构建镜像，禁止使用 `latest` 或浮动 tag。
2. **平台资产与业务资产分离**：Namespace、ResourceQuota、LimitRange、NetworkPolicy
   放在 `platform/<env>/`，由平台 AppProject 管理；供应商项目的 AppProject
   `clusterResourceWhitelist: []`，无权创建命名空间。
3. **环境隔离**：`<app>-stg` 与 `<app>-prod` 是不同命名空间、不同 AppProject；
   PROD 的 AppProject 额外带同步窗口，窗口外 Argo CD 拒绝一切同步。
4. **权限隔离**：STG 与 PROD 由两套 Argo CD 实例分别托管，凭证与 RBAC 不共用。
   供应商只拥有 STG 的只读权限；PROD 只有甲方发布人员具备 Sync 权限。
5. **变更可追溯**：每次晋级都是本仓库的一次 commit，commit message 必须包含
   `releaseId` 与源码 tag，配合不可变 tag 形成发布证据链。
6. **禁止在 GitOps 仓库存放明文密钥**：Secret 由外部密钥管理系统或 SealedSecret 管理，
   AppProject 的 `namespaceResourceWhitelist` 未放开 `Secret`。

## 业务项目怎样请求晋级

STG 作业写入镜像 digest，使用 `STG_ARGOCD_URL`（HTTPS）及 `STG_ARGOCD_READ_TOKEN` 查询对应 Application。令牌仅授权 STG 应用 get，变量限定在甲方 `promotion` 环境；私有 CA 应安装在运维作业信任库。仅在对应 GitOps revision 显示 Synced、Healthy 且应用报告该镜像时，将凭证写入 `evidence/stg/<项目>/<应用>/<业务流水线编号>.json`。等待上限 10 分钟。观察或凭证写入失败，可重试；已被跳过的版本不能补作健康证明。

生产申请读取所选业务流水线的凭证及甲方 main 已归档的窗口清单。供应商提交材料，甲方归档；每项必须填写前置服务 `dependencies`（无依赖填 `[]`）、停机影响 `downtime`（布尔值）、版本、前后镜像及测试报告。有数据库或中间件变更时分别填写 `databaseChanges`、`middlewareChanges`。申请自动携带业务流水线编号。报告与清单的版本标签、应用、项目、窗口及 digest 必须一致，功能测试由供应商签认。每个申请仅改一个应用的生产 overlay，同一窗口可关联多个应用的 MR。

### 切换到新模板前

1. 保护 GitOps 的 `main`，只允许甲方修改本项目及其 CI 配置。将本项目 **Minimum role to use pipeline variables** 设为 **No one allowed**。入口接收流水线编号 `source_pipeline` 和枚举操作 `action`，这样调用方不能以变量覆盖 GitLab 提供的触发身份、分支或凭据。需要支持 pipeline inputs 的 GitLab 版本，本地实例为 19.6.1。
2. 为每个业务项目配置独立的甲方机器人身份，用该身份创建 GitOps 项目的 **pipeline trigger token**，允许触发受保护的 main。将机器人的实际 GitLab 登录名登记在 `policies/promotion-sources.json`，对应值依次是业务项目完整路径、部署目录和语言作业前缀。示例登录名需按实际账号替换。不能多项目共用同一个触发身份。供应商只收到触发令牌，不持有机器人的登录凭证。
3. GitOps 项目配置 `GITOPS_TOKEN`（机器人仅对本仓有 write_repository，可按现有分支保护写 main/发布分支），以及 `PROMOTION_READ_TOKEN`（read_api，具有读取已登记业务项目流水线、产物和本仓 MR 的权限）。两者勾选 masked、protected，环境范围限制为 `promotion`。GitLab API 与仓库使用内部可信 TLS。示例按 GitLab 本机提供 artifact 内容设计，跨主机 artifact 重定向会拒绝。
4. 每个业务项目配置 `OPS_PROJECT_ID`（本仓数字 ID）、`OPS_TRIGGER_TOKEN`（此项目专用触发令牌）、`OPS_STATUS_TOKEN`（只读本 GitOps 项目 API，用于等待结果，例如 Reporter 角色的 read_api 项目令牌）。令牌均 masked、protected。状态令牌具有项目级读取范围，按内部部署信息的可见范围分配。业务项目无 GitOps 写凭据；清除项目和上级组继承的旧写令牌并轮换。业务默认分支及发布标签须受保护。注册带 `docker-notify` 标签的通知 Runner，甲方 GitOps 作业使用单独主机上的项目专属非特权 `docker-ops` Runner 和独立并发槽，避免等待结果时占满执行资源。
5. 先合并 GitOps 和模板 MR，再为已审核模板提交发布新的受保护版本标签。最后合并示例升级 MR。切换时暂停旧晋级作业，协调旧写令牌回收。先用一个 STG 项目验收，再推广其他项目。恢复旧模板会重新依赖业务侧写凭据，回退前需单独评估。

验收时检查业务流水线与 GitOps 流水线均成功、提交只改目标 STG overlay，以及 Argo CD 实际同步情况。失败的镜像门禁、过期主干、未登记触发身份都应阻止写入。生产候选仅产生待审 MR。旧流水线保留原作业图；仅拥有旧 STG tag 的版本缺少健康凭证，应在新流程下部署并验收后申请。切换 GitOps 接收端前处理在途申请，旧 tag 发布请求将被拒绝。

## 接入新应用

甲方先在对应的 Argo CD 实例登记 STG、PROD 集群并配置 GitOps 仓库只读凭据，按上一节为业务项目准备专用机器人、触发令牌和 CI 变量。下面的命令需要 Python 3 和 PyYAML，参数中的机器人是实际 GitLab 登录名。应用名用于 Argo CD 和命名空间，在本 GitOps 仓库中须唯一。

```bash
# 在 GitOps 工作分支生成一次接入变更
python3 tools/add_app.py --project-key acme --app order-api --language java \
  --registry-host registry.internal --gitlab-project-path vendors/acme/order-api --robot promote-order-api \
  --server-stg https://stg-cce.internal --server-prod https://prod-cce.internal \
  --gitops-url https://gitlab.internal/platform/gitops-deployments.git

# 本仓库策略校验（与流水线同一个脚本）
python3 tools/validate_repo.py --root .

# 校验某个 overlay 渲染结果
kustomize build apps/demo/java-api/overlays/prod

# 校验全部 overlay
for d in apps/*/*/overlays/*/; do kustomize build "$d" >/dev/null && echo "OK $d"; done
```

审核同一个接入 MR 中的应用部署文件、两环境的 Argo CD 入口和晋级身份映射。每个环境生成两个 Application：业务应用管理 Deployment 和 Service，平台应用管理该业务命名空间、配额、限额和网络策略。两者指向参数指定的同一目标集群。新应用的权限与同步策略沿用示例基线，生产窗口取自生产平台 AppProject。

首次接入时，甲方先确认平台应用已同步、目标命名空间已就绪，再触发首次 STG 部署。初始镜像 digest 是占位值。生产先在批准窗口同步平台资产，业务应用须等首个已测试版本的生产 MR 合并后再人工同步。CI 的 `validate-kustomize` 会在临时目录生成一个应用并从两环境入口验证。

## 占位符

`gitlab.internal`、`host.docker.internal:5500` 为本地实验环境地址，
接入真实环境时替换为实际 GitLab 域名与镜像仓库地址。
