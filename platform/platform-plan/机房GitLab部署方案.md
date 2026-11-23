# 机房 GitLab CI/CD 部署手册

**起点**：机房 GitLab CE 已有供应商业务仓库。甲方负责新增平台仓库、Runner、镜像仓库权限及 Argo CD 接入。先选 CCS Local 的一个低风险服务跑通 STG，再演练一次按窗口晋级和回滚，最后逐项目推广。原业务仓保留原路径与提交历史。

**结论**：业务 CI、GitOps 写入和生产人工同步的分工可沿用。当前仓库是可验证的基线，复制整个 demo 到机房会带入演示扫描、演示目标集群和镜像占位值。下文按首次部署的实际顺序处理这些差异。

| 部署顺序 | 完成标志 |
|---|---|
| 1. 确定试点与网络 | 一张表能对应业务仓、两套云账号和集群、镜像地址、责任人 |
| 2. 建平台仓库 | 机房 GitLab 能解析受保护模板标签，供应商只能读模板 |
| 3. 注册 Runner、准备依赖 | 四种 Runner 标签都有正确的执行位置，内网可拉镜像、依赖及规则库 |
| 4. 配机器身份和变量 | 单项目触发、状态查询、运维写入、集群拉镜像各用自己的身份 |
| 5. 准备 Argo CD，生成正式清单 | 两个环境分别只渲染预期的应用和平台资产，目标集群正确 |
| 6. 接入一个业务仓 | 真实业务 MR 有流水线，源码检查完成后才能合并 |
| 7. 验收 STG、生产和回滚 | 有健康凭证、审批记录和实际部署版本，再开放下一项目 |

## 1　甲方先填试点表

| 需要落定 | CCS Local 试点填写内容 |
|---|---|
| GitLab | 内网 HTTPS 域名、CE 版本、默认分支、内部 CA、管理员。北京迁上海时优先沿用稳定域名 |
| 业务与制品 | 供应商、业务项目完整路径、应用唯一名、语言、现有构建命令、本项目的百度云账号、CCR 实例、登录域名及实际仓库路径 |
| STG / PROD | 各自百度云账号、CCE API 地址、命名空间、集群管理人；记录已有服务、镜像 digest 和现有部署工具 |
| 控制面 | 两套 Argo CD 的位置、命名空间、访问地址、管理人。已有运维账号实例可作为其中一套评估 |
| 发布 | 供应商测试负责人、甲方发布经理、正常窗口/冻结期、紧急窗口批准人、回滚目标 |

**本文采用的实施选择**：Runner 放在机房，源代码在机房检出。镜像按业务项目推送到接入表登记的百度云账号和 CCR 仓库。CCS Local 可以使用账号 A 的 CCR，另一个项目可以使用账号 B 的 CCR；两者共用流水线模板，各自配置域名、路径和凭据。同一应用的 STG 和 PROD 拉取**该项目仓库的同一 digest**。当前晋级脚本没有跨库复制步骤。如果采用云端镜像库，先确认允许代码制品上云的边界，尤其是镜像内的 Python 源文件和前端静态文件。Nexus 可后装，首期可以用已有内网代理或批准的镜像和依赖源。

**甲方先安排三项交付**：GitLab 管理员提供 CE 版本、内部域名和建组权限；机房运维提供三台 VM 或等效隔离资源、依赖源和网络连通；云平台负责人提供两套 CCE 的目标地址、镜像库与 Argo CD 的授权联系人。可以先建仓和 Runner，等 STG 试点验收后再安排生产窗口。

**版本检查**：运维仓使用顶层 `spec:inputs`，业务仓通过 trigger API 传 `inputs[action]`、`inputs[source_pipeline]`。在机房 GitLab 的 Help 查看实际版本。建议用仍受维护且具备正式 inputs 支持的版本；该 API 的 inputs 在 18.1 正式发布。旧版本先验证这两个输入及禁用任意流水线变量的设置，缺功能就先升级或评审适配，勿直接把运维写令牌下发到业务仓。[GitLab trigger API](https://docs.gitlab.com/api/pipeline_triggers/)

## 2　创建三个机房项目，导入对应仓库

由 GitLab 管理员建私有组 `platform`。下面每一行都是一个独立 Git 项目。首次建空仓不勾选初始化 README。

| 机房项目 | 导入的本地目录及基线 | 权限和用途 |
|---|---|---|
| `platform/cicd-templates` | `platform/cicd-templates`，`v1.0.19` → `ae09fb58` | 甲方维护，供应商通过 Reporter 或等效只读权限读取 include |
| `platform/gitops-deployments` | `platform/gitops-deployments`，`0772db71` | 甲方维护部署声明、发布材料和证据；供应商无写权限 |
| `platform/platform-plan` | `platform/platform-plan`，已有方案基线 `a95359ba` | 流程和本部署手册；将本手册的文档变更随交付提交 |
| 已有业务项目 | 保留供应商当前仓库 | 仅在试点分支引入 CI 入口、Dockerfile 及必要构建配置 |

有网络连通时，给**平台仓库的干净发布副本**增加一个指向机房空项目的 remote。以下为模板仓示例，先替换域名并核对目标项目；另外两仓按同法只推各自审核过的 `main`。通过隔离网时可转运含相同分支、标签的 Git bundle。在机房重新创建权限、令牌和 Runner 注册，实验环境的配置不随 Git 历史迁移。

```bash
git remote add idc https://gitlab.example.internal/platform/cicd-templates.git
git rev-parse 'v1.0.19^{commit}'
git push idc main:main refs/tags/v1.0.19:refs/tags/v1.0.19
git ls-remote idc refs/heads/main refs/tags/v1.0.19 'refs/tags/v1.0.19^{}'
```

**GitLab 管理员设置**：

- 模板和方案仓保护 `main`，日常走甲方 MR。模板保护 `v*`，仅甲方发布负责人可创建。机房模板若修改了镜像、门禁或作业规则，发布**新标签**并同步各业务 include，保留原 `v1.0.19` 指向。
- GitOps 默认分支使用 `main`（通知作业写死 `ref=main`）。保护分支，甲方发布人员合并生产 MR；为 STG 机器人保留实际能直推 `main` 的权限。CE 按角色授权时记录同角色可直推的范围，生产 overlay 按已约定的甲方 MR 流程变更。设置项目的 **Minimum role to use pipeline variables = No one allowed**。
- 业务默认分支设为受保护。供应商 Developer 可合并业务 MR，禁止供应商直推；开启 **Pipelines must succeed**。修改业务 `.gitlab-ci.yml` 按现有甲方审批约定执行。用一个真实供应商测试身份验证可读模板、可提业务 MR、无权修改 GitOps。严格接入检查是甲方验收工具，当前业务流水线不会自动强制执行它。

## 3　部署 Runner，打通镜像和依赖

建议首期准备 **3 台机房 Linux VM、4 个逻辑 Runner**。CPU、内存和磁盘按试点的最大 Maven 构建、镜像层、扫描缓存和并发实测。每台安装受支持的 Docker Engine、与机房 GitLab 兼容的 GitLab Runner 和内部 CA。

| 虚拟机 | Runner 标签 | 授权项目与配置 |
|---|---|---|
| 1 普通作业机 | `docker-general`、`docker-notify` 各注册一个 | general 非特权，跑普通业务 MR、测试、扫描和三个平台仓的检查，须能接未保护分支的 MR；notify 非特权，仅授权业务受保护主干，负责触发并等待运维流水线 |
| 2 镜像构建机 | `docker-build` | 当前 Buildah 模板按独立特权池设计。仅授权已接入业务项目的受保护引用，隔离宿主、缓存与网络；供应商的 Dockerfile 在此执行 |
| 3 运维作业机 | `docker-ops` | GitOps 项目专属，非特权，限受保护引用；仅此类作业需要 GitOps 写凭据与 STG Argo CD API |

在所需项目或受控组的 **Settings → CI/CD → Runners** 创建 Runner，配置上表标签、项目范围、保护属性，关闭无标签任务。主机运行 `sudo gitlab-runner register`，交互输入机房 URL、刚创建的 Runner authentication token、executor `docker` 和可用的内网默认镜像。分配后核对 `/etc/gitlab-runner/config.toml` 的 `privileged`、`limit` 和全局 `concurrent`，运行 `sudo gitlab-runner verify`，再以真实标签排一次作业。业务作业容器不挂宿主 Docker socket、运维目录或 kubeconfig。[Runner 注册流程](https://docs.gitlab.com/ci/runners/new_creation_workflow/)

**特别注意并发**：notify 在轮询时一直占槽，GitOps 下游先在 general 执行校验，之后才会进入 ops。若 VM 1 共用一个 manager，试点可先设全局并发 2、notify 的 `limit=1`，至少给 general 留 1 槽；也可用独立 manager。只隔离 ops 仍可能让下游校验排死。GitOps 写作业目前用全局 `resource_group: gitops-writer` 串行执行，批量推广前测量排队时间。

| 从哪里连 | 需要访问 | 现场验证 |
|---|---|---|
| Runner 主机和实际作业容器 | GitLab HTTPS/API、Git、CI 工具镜像、基础镜像和包源 | 主机能拉 helper/job 镜像；容器内也信任 CA，能 clone 和取 artifact |
| general / build | Maven、PyPI、npm、Go proxy、Alpine apk、Semgrep 规则、Trivy 漏洞库、SonarQube 和业务镜像仓库 | 用固定 digest 拉取工具；镜像构建可 push，扫描可按 digest pull；GitOps 作业能安装 Kustomize 5.3、PyYAML、jsonschema |
| ops | 机房 GitLab 和 STG Argo CD HTTPS | 能查询受权业务 job/产物、写 GitOps，并读取指定 STG Application |
| Argo CD | 机房 GitOps HTTPS、对应百度云账号的 CCE API | repo 只读连通，注册集群显示可访问；从管理 CCE 明确路由、DNS、ACL、CA |
| 两套 CCE 的节点 | 业务镜像 registry | 以集群只读拉取身份验证私有镜像；生成器未配置 imagePullSecret，按现场节点身份或目标 namespace 的 ServiceAccount 配置 |
| 执行 DAST 的 general 容器 | 试点 STG 的业务 URL | 需要 DAST 时才开放相应入口，验证 `/healthz` |

**从零准备外部服务**：

1. 镜像库管理员在该项目登记的百度云账号和 CCR 实例内创建或确认私有仓库，登记实际路径、可写的 CI 身份和只拉取的 STG/PROD 身份。给发布和回滚用的 digest 设置保留策略。试点时验证从机房推、STG 拉、PROD 拉的权限，保留 digest 比对记录。
2. 安全团队部署或提供机房可达的 SonarQube，建立试点项目、质量门和项目级分析身份。Gitleaks、Semgrep、Trivy 由作业镜像执行，无需分别部署常驻扫描服务器；准备好规则包、漏洞库和更新负责人。真实 Sonar、SAST、SCA、license、镜像扫描、SBOM 的报告分别验收。
3. 网络团队为 runner 主机、作业容器、Argo CD 和 CCE 节点分别验证上表连通性。只给管理机开通线路，作业容器仍可能因 DNS、证书链或代理失败。规划北京迁上海时，在切换 DNS 前从管理 CCE 试拉 GitOps 仓，并从新机房试调 STG Argo API。

当前工具镜像直接引用多个外部 registry 并固定 digest；`REGISTRY_HOST` 只改变业务镜像目的地。无公网时须为 Docker、Buildah、Runner helper 和扫描工具分别提供内网来源，预置 apk/pip 等依赖。可用经批准的保留 digest 的镜像代理，修改模板镜像名则发新标签。默认镜像路径是 `<REGISTRY_HOST>/<CI_PROJECT_PATH_SLUG>`。若 CCR 分配了命名空间或自定义仓库名，把业务项目变量 `IMAGE_NAME` 设为相对路径，例如 `ccs-local/booking-api`。登录域名与路径分别填写。

## 4　配置凭据和变量

统一从 GitLab **Settings → CI/CD → Variables** 配置。新环境重新签发所有秘密，启用 Masked、Protected，支持时启用 Hidden；URL、ID、布尔值等普通配置无需伪装成秘密。记录签发人、到期、轮换和回收位置。以下名称与脚本逐字一致。

| 配在哪里 | 名称 | 如何取得、允许做什么 |
|---|---|---|
| 每个业务项目 | `OPS_PROJECT_ID`、`OPS_TRIGGER_TOKEN` | ID 为机房 GitOps 项目数字 ID。在 GitOps 项目按业务仓设一个甲方机器人，用这个身份创建 **pipeline trigger token**，其权限要能触发受保护的 main。登记机器人的实际 GitLab 登录名；不同项目不共用触发身份 |
| 每个业务项目 | `OPS_STATUS_TOKEN` | GitOps 范围的只读 API 身份，例如 Reporter + `read_api`，只用于轮询下游流水线。注意其可读范围是项目级 |
| 每个业务项目 | `REGISTRY_HOST`、`IMAGE_NAME`（自定义路径时）、`REGISTRY_TLS_VERIFY=true`、`REGISTRY_USER`、`REGISTRY_PASSWORD` | 填该项目 CCR 域名、仓库路径和专用凭据。CI 只对本项目仓库推送和读取，STG/PROD CCE 各自配置对该仓库的只读拉取权限 |
| 业务项目 | `SONAR_HOST_URL`、`SONAR_TOKEN`；按需 `SAST_RULESET`、`TRIVY_DB_REPOSITORY`、`DAST_TARGET_URL` | Sonar 使用单项目分析身份。后几个变量按内网规则库、漏洞库和 STG 地址填写 |
| 只在 GitOps 项目，环境范围 `promotion` | `GITOPS_TOKEN` | 专用机器人，对本仓 `write_repository`；按分支规则能写 STG 主干、凭证及生产候选分支，通过 Git push options 创建 MR |
| 同上 | `PROMOTION_READ_TOKEN` | 甲方专用 `read_api` 身份；对已登记的业务仓有读取流水线、job、artifact 的权限，同时可读本 GitOps 仓 MR。单一业务项目的 project token 通常不覆盖这些项目 |
| 同上 | `STG_ARGOCD_URL`、`STG_ARGOCD_READ_TOKEN` | HTTPS 地址与 STG Application 只读身份，允许 get 已接入的 STG 应用。CI 不需要 PROD Sync 权限 |

**第一次试跑常见的两个卡点**：

- 普通供应商功能分支 MR 通常拿不到 protected 的 `SONAR_TOKEN`，而公共模板的 Sonar 作业在 MR 上必跑，缺令牌即失败。选定机房做法再接入：若允许业务 MR 访问单项目分析身份，应按供应商代码可读取该身份的边界授权；若只允许受保护主干用令牌，先在甲方模板调整 Sonar 触发策略、更新方案并发布新标签，保留 MR 其他必需门禁。使用的 Sonar 版本/版别还须支持选定的分析方式。[GitLab MR 与受保护变量](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/)
- 业务主干作业可能读取同环境范围的业务变量，Masked 只控制日志展示。机房验证供应商身份不能读取运维项目的 `GITOPS_TOKEN`，也不能通过组变量继承它。业务触发令牌只允许申请，运维侧再以触发身份和运行中的作业独立核对。用供应商角色实测在历史 `release-candidate` 手动作业填写 `RELEASE_ID` 的权限；GitOps 项目禁用任意流水线变量的设置不能机械复制到业务项目。

## 5　建立 Argo CD 控制面，再激活试点

**控制面安装和接入**由甲方集群管理员执行。优先复用已评估的运维 CCE。方案以 STG、PROD 两套独立实例为基线；各实例使用独立凭据、RBAC 和对应集群注册。可分别部署在不同管理集群；如果共用一个管理集群，先为两实例设置不同命名空间、控制器管理范围及实例资源跟踪标识，将生成清单中的 `metadata.namespace: argocd` 和 root 的目标命名空间改为相应实例。不要同时把同一应用交给两套控制器。

1. 通过企业批准的版本安装 Argo CD（Helm 或发行清单），保存安装版本、values、恢复方法，配置内网 HTTPS 和管理员/发布人员登录。已有实例先核实其管理范围。为两个实例添加机房 GitOps 仓库只读凭据和 CA。分别登记目标 STG/PROD API server，记录 Argo CD 返回的实际 server 字符串。限制集群凭据和 AppProject 到所需资源；业务项目管理 Deployment/Service/ConfigMap，命名空间和配额由平台 Application 管理。只给甲方发布角色目标 PROD Application 的 Sync 权限。[Argo CD 安装及集群登记](https://argo-cd.readthedocs.io/en/stable/getting_started/)
2. **在连接 root 前**克隆机房 GitOps 仓，建接入分支。原样的两个 `argocd/bootstrap/<env>` 各渲染 **5 个 Application**，含四个 demo 和一个默认平台应用。保留生成器使用的 demo 文件及平台样板，先生成真实应用，再编辑各环境 `argocd/applications/<env>/kustomization.yaml` 的启用列表，只列试点的业务和平台 Application；在 `argocd/projects/<env>/kustomization.yaml` 保留对应项目，保留自检使用的 `platform.yaml` 项目基线并审核其权限。清理 `promotion-sources.json` 中示例机器人的授权。后续每个供应商走同样的接入 MR。
3. 在 GitOps 仓根目录运行以下生成命令（把示例 CCR 域名和两个 CCE API 地址替换为接入表中的值）。生成器需要 Python 3、PyYAML；测试还需 jsonschema 和 kustomize 或带 kustomize 的 kubectl。

```bash
python3 tools/add_app.py --project-key ccs-local --app booking-api --language java \
  --gitlab-project-path vendors/ccs/booking-api --robot promote-booking \
  --registry-host ccr-project-a.example.internal \
  --server-stg https://api.stg.example.internal --server-prod https://api.prod.example.internal \
  --gitops-url https://gitlab.example.internal/platform/gitops-deployments.git
```

4. 如果在业务项目变量中配置了自定义 `IMAGE_NAME`，生成后将 base 中容器的 `image`、两套 overlay 的 `images[].name` 和已有的 `newName` 对齐为该项目的完整 CCR 镜像名，保留环境的 digest 字段。分别用 `kubectl kustomize` 渲染，核对 Deployment 引用的域名和路径。按第 2 步收敛启用列表。生成器自检目前固定用测试业务名 `order-api`、机器人 `order-bot` 和仓库路径 `vendors/acme/orders`。真实试点若恰好重名，先让自检使用独立测试数据，否则 GitOps MR 会因测试夹具冲突而失败。以此例，每环境 applications 只列 `booking-api.yaml`、`platform-booking-api.yaml`。检查生成的端口、探针、UID、配置/密钥挂载、Service、ingress、依赖和 NetworkPolicy 是否符合真实服务；样板的网络策略限制入站和出站，数据库、消息队列、入口网关须按实需放行。已有服务先与当前部署做资源名、selector、namespace、owner 和 prune 差异检查，明确接管或并行切流，再让原部署工具交接写权限。生成器要求应用名在此 GitOps 仓唯一。
5. 合并前对 STG 和 PROD 分别渲染。root 渲染的是 Application 与 AppProject 声明，还要单独渲染每个 Application 指向的目录。确认 repoURL、server、namespace、实际镜像路径、生产同步策略和窗口。初始全零 digest 是**未发版占位**；Argo CD 不会自动拒绝同步它。已有服务先写入可核实的现网基线 digest；全新 STG 先建平台资产，首个真实 digest 写入后再放行业务 Application 的首次同步。若本轮错过 10 分钟观察时间，在版本仍是主干头时重试 STG 作业。生产占位不得点 Sync。

```bash
for env in stg prod; do
  kubectl kustomize "argocd/bootstrap/$env" > "/tmp/booking-root-$env.yaml"
  kubectl kustomize "apps/ccs-local/booking-api/platform/$env" > "/tmp/booking-platform-$env.yaml"
  kubectl kustomize "apps/ccs-local/booking-api/overlays/$env" > "/tmp/booking-workload-$env.yaml"
done
python3 -B tools/validate_repo.py --root .
python3 -B tools/test_add_app.py
python3 -B tools/test_promote.py
```

6. 合并经过审核的接入 MR 后，甲方在各实例各建一个 **root Application**。仓库提供的是两个 Kustomization 入口，root Application 本身需要创建。在 Argo CD 的 **New App** 填受限的甲方引导 Project、机房 GitOps repoURL、revision `main`、path `argocd/bootstrap/stg` 或 `argocd/bootstrap/prod`；目的地填**该 Argo CD 的管理集群及自身命名空间**，允许创建 Application/AppProject。root 首次用 Manual，核对 diff 后同步。子应用目的地才是业务 CCE。先确认各目标集群的平台资产就绪；生产平台资产也受窗口约束。STG 子应用有自动同步，root 的首次 Sync 前必须落实第 5 步的首次镜像安排。

**首次同步的具体做法**：全新 STG 可把 root 的首轮启用列表只放 `platform-booking-api.yaml`，业务 Application 文件仍保留在仓中供晋级脚本核对。平台资产健康后，合并业务代码，观察运维作业提交真实 digest，再用接入 MR 把业务 Application 加回列表并同步 root。首次查询时若 Application 尚未创建，Argo API 会返回 404，当前脚本会立即失败；若 GitOps main 已前进，脚本也可能等不到精确 revision。出现这两种情况，待 root 和应用稳定后重试仍是业务主干头的 STG 作业；核到实际健康版本后才会归档。PROD root 可管理子 Application 声明，但业务 Sync 仍由发布窗口控制。

**现场窗口**：示例使用上海时区周二 22:00 开始、持续 4 小时，每月 28 日起冻结 96 小时。先在平台和应用 AppProject 核定企业实际窗口，再上线。生成器会把当时的平台窗口写入新项目，后续改窗口须同步检查已有项目。

## 6　改一个已有业务仓的 CI 入口

由甲方和供应商在现有业务仓提接入 MR。先保存已有 CI 和部署方式，列清仍要执行的原有测试、打包及合规检查。机房平台仓已就位后再接入业务仓。

1. 从对应语言的 demo `.gitlab-ci.yml` 复制完整 `include` 和项目变量。`project` 使用机房模板全路径，`ref` 指向已审核的受保护标签；保留该语言及公共质量、安全、镜像、晋级模板。填写 `PROJECT_KEY`、`APP_NAME`、`K8S_NAMESPACE`，和第 5 步保持一致。实际授权和部署目的地以甲方映射及 GitOps 声明为准。
2. **删除六段 demo 作业覆盖**：`sonarqube`、`dast-baseline`、`sign-image`、`dependency-scan`、`image-scan`、`sbom`。机房按公共模板执行。DAST 在 STG 后可选手动；公共 `sign-image` 本身仍是手动提示，若投产要求签名，须单独实现签名与验签。
3. 根 `.gitlab-ci.yml` 显式保留与公共模板一致的 MR / 主干 workflow 规则。可以从同一标签的 `workflow.yml` 原样取出 `workflow:` 块。这样删除 demo 的本地 job rules 后，GitLab 仍能从业务入口识别 MR 流水线；升级模板时同步核对这段规则。CI Lint 后实际创建普通分支 MR 验证。[GitLab MR 触发规则](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/)
4. 检查语言工具链与制品契约。Dockerfile 从本次 CI 产物打包；企业项目有多模块、自定义构建目录或多个镜像时先适配平台模板，保持现有调用和测试语义，按新标签接入。

| 业务类型 | include 的语言文件 | 机房试点应能拿到 |
|---|---|---|
| Java / Maven | `languages/java-maven.yml` | JUnit、`target/site/jacoco/jacoco.xml`、`target/*.jar`；核对 JDK 和 Sonar Java 所需编译字节码是否可用 |
| Python | `languages/python.yml` | `requirements-dev.txt`、pytest 的 `coverage.xml`、`dist/` 中的 wheel |
| Go | `languages/go.yml` | `go.mod`、`coverage.out`、`bin/`；测试/构建与 lint 的 Go 镜像版本不同，按服务的 go.mod 验证内网工具链 |
| JS / Node | `languages/node.yml` | npm 锁文件、`npm test` 输出的 `coverage/lcov.info`、`npm run build` 输出的 `dist/`；使用其他包管理器需适配 |

在甲方工作站运行 `python3 /路径/cicd-templates/tools/check_standard.py --strict /路径/业务仓`。四个原始 demo 在演示口径下为 4/4、严格口径为 0/4；清理后的试点应通过严格检查。它只检查接入格式，另在机房 GitLab 用 CI Lint 查看合并配置、实际 runner 标签、rules、needs。若 Sonar 等服务尚未准备好，可以在隔离验证项目演示步骤；正式业务项目启用前按约定接通必需门禁。

## 7　首个应用的验收和回退

| 顺序 | 操作 | 甲方放行依据 |
|---|---|---|
| 业务 MR | 供应商用普通分支提 MR；试一次测试失败，再修复 | 出现 MR 流水线；适用的测试、覆盖率、构建、源码门禁失败会拦合并；MR 不推业务镜像 |
| 合并主干 | 合并后运行真实 `build-image`、镜像扫描与 SBOM | `image.env` 中有完整 `IMAGE_REF=仓库/镜像@sha256:…`；扫描和 SBOM 使用同一引用 |
| STG | 业务 `stg-promotion` 等待甲方 GitOps `promote`；供应商做功能验证 | 源头是已登记项目、受保护主干且版本仍是当前头。Argo CD 的 app、集群、revision、digest 匹配，状态为 Synced 和 Healthy；Git 中有 `evidence/stg/<项目>/<应用>/<业务流水线ID>.json` |
| 历史版本 | 让 B 部署到 STG，再选择已验证的 A 申请 | 甲方先将供应商的清单和逐应用测试报告归档到 GitOps main 的 `releases/REL-YYYYMMDD-NNN/`；供应商回 A 的主干流水线手动运行 `release-candidate` 填 `RELEASE_ID`。随后 `prod-promotion` 自动开 A 的生产 MR，生产仍运行旧版 |
| 生产窗口 | 甲方审核部署清单和逐应用 MR，窗口内人工 Sync | 核对依赖、停机、测试结论、前后 digest、变更单与回滚计划。按批准的 revision 同步；A 服务是 B 的依赖时先确认 A 健康及接口可用，再合并/同步 B。记录实际 digest、revision、操作人 |
| 失败与回退 | 在非生产演练材料缺失、未登记身份、窗口外同步、恢复上一版本 | 缺 STG 凭证或测试报告不通过不能开生产 MR，普通发布身份不能越窗。回滚经甲方 MR 把 overlay 改回已验证 digest，再按窗口 Sync；数据库与中间件有独立回退步骤。紧急发布经批准开限时窗口，结束后撤销并留痕 |

**首次上线的例外**：部署清单 schema 强制要求 `previousImage`。已有业务填可验证的现网 digest；全新生产服务没有前版时，先由甲方补充“首次安装”材料及撤回路径、同步修改 schema/校验，再放行首次生产。不要把全零 digest 或本次镜像当作上一个稳定版本。镜像保留期应覆盖历史版本批准周期与回滚期；GitOps 晋级不会为旧流水线重建镜像。

**切换失败时**：在接管前保留原 CI、目标集群现状和可恢复制品。先暂停新部署入口和相应自动同步，核对当前版本及资源所有权，再经审核恢复旧入口或按 digest 回滚。STG 自动 prune 的应用不要直接删除根应用或级联删除子应用来回退。投产前由机房团队确认 GitLab 备份恢复（含 secrets 和 artifact 存储）、GitOps Git 历史、镜像保留、Argo CD 注册与密钥恢复、操作审计和账号轮换责任人。

## 故障先查哪里

| 现象 | 首查 |
|---|---|
| MR 无流水线 / pending | 模板标签是否存在且供应商可读；业务入口 MR rules；Runner 标签、保护范围和可用槽位 |
| 运维流水线 400/403 或一直等待 | trigger inputs 版本、受保护 main 的触发身份、真实 GitLab 用户名映射、通知与下游校验并发 |
| 镜像已推送但 STG 没凭证 | 源项目流水线是否已过期；`image.env` 下载是否被重定向到对象存储（脚本拒绝重定向，采用 GitLab 代理下载或适配可信下载）；私有 CA、Argo 只读权限、集群拉镜像身份 |
| STG 运行正常但作业超时 | 脚本只等 10 分钟，检查精确 revision、Application spec、目的地和镜像摘要；共享 main 有其他提交时核对 Argo 实际观察到的版本，不能手工补健康凭证 |
| PROD Sync 无法进行或镜像不符 | 核对窗口、冻结期、RBAC、材料和实际 GitOps revision；“生产 MR 已合并”只改变期望状态 |

**本次核查证据**：公共模板自检 27 个作业，四份业务入口均固定同一标签。晋级单测 7 项、接入测试 2 组（四种语言）和 GitOps 策略校验通过。在临时副本中，删除六个 demo 覆盖并保留 MR workflow 后，四份业务入口均通过严格静态检查；生成试点并收敛 root 后，每个环境只渲染出预期的两个 Application，两个目标及其源目录渲染均通过。机房的权限、网络、真实扫描和 CCE 发布结果由以上现场验收确认。
