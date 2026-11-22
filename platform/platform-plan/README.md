# 统一 CI/CD 与 GitOps 发版方案

多供应商、多语言项目的统一交付流水线。**本仓库只放这一份方案**；流水线模板在 `platform/cicd-templates`，部署描述在 `platform/gitops-deployments`，业务仓库各自 `include` 模板。

一句话：**供应商只能提代码，能不能进环境由流水线判定；生产什么时候变，由人在窗口内点按钮决定。**

---

## 1. 三个仓库，四条链路

| 仓库 | 放什么 | 谁维护 |
|---|---|---|
| `cicd-templates` | 流水线定义（9 阶段 27 个作业） | 甲方平台 |
| 业务仓库（每供应商每项目一个） | 只声明 `include` 模板 + 三行项目标识 | 供应商 |
| `gitops-deployments` | 集群要部署成什么样（Kustomize + Argo CD） | 甲方平台 + 发布经理 |

```text
        ┌──────────────┐   ①代码     ┌──────────────┐
供应商 → │ 业务仓库      │ ─────────→ │ GitLab CI    │
        └──────────────┘            │ 9 阶段门禁    │
                                    └──────┬───────┘
                                           │ ②镜像（按 digest）
                                           ▼
                                    ┌──────────────┐
                                    │ 中央镜像仓库  │ ← 唯一发布事实源
                                    └──────┬───────┘
                                           │ ③写 overlay
                                           ▼
                                    ┌──────────────┐   ④拉取   ┌────────────┐
                                    │ gitops 仓库   │ ────────→ │ Argo CD    │
                                    └──────────────┘           │ STG / PROD │
                                                               └────────────┘
```

四条链路的边界是这套方案的核心：

1. **CI 不持有任何集群凭证**，不执行 `kubectl apply`。它只产出镜像、扫描报告、SBOM 和 GitOps 变更。
2. **镜像仓库是唯一事实源**。部署描述里写的是 digest，不是 tag，生产不重新构建。
3. **GitOps 仓库是部署事实源**。集群里被人手工改过什么，Argo CD 都会显示为 `OutOfSync`。
4. **生产变更必经人手**：部署清单 MR → 甲方审批 → 发布窗口 → 人工 Sync。

---

## 2. 十项决策

| 编号 | 决策 | 结论 |
|---|---|---|
| D01 | Runner 放哪 | 北京机房独立 CI 构建区。云端 Runner 会下载源码，与"代码不上云"冲突 |
| D02 | 多语言怎么支持 | Runner 不按语言拆，**构建镜像**按语言拆；统一 Docker executor |
| D03 | 怎么统一不同供应商 | 唯一模板仓库 + 固定版本 `include`；禁止供应商复制一套私有流水线 |
| D04 | CI 与 CD 边界 | CI 不碰集群，只产出制品与 GitOps 变更；部署归 Argo CD |
| D05 | 镜像放哪 | 中央镜像库为唯一事实源，按项目隔离命名空间与权限 |
| D06 | GitOps 仓库放哪 | 与业务代码同在北京 GitLab；Argo CD 只读拉取 |
| D07 | Argo CD 几套 | **两套**：`argocd-stg`、`argocd-prod`，按环境拆分，不按项目拆 |
| D08 | Argo CD 放哪个账号 | 优先统一运维账号；PROD 实例独立命名空间、节点池、RBAC、凭证 |
| D09 | 怎么晋级生产 | **按 digest 晋级，不按 tag 重建**。PROD 跑的就是 STG 验证过的那个镜像 |
| D10 | 怎么控生产发布 | 部署清单 MR + 甲方审批 + 固定窗口 + 人工 Sync；紧急发布也不能跳过门禁 |

---

## 3. 流水线：9 个阶段

四个示例统一引用 `platform/cicd-templates@v1.0.17`。阶段顺序见 `stages.yml`；声明 `needs` 的作业按依赖就绪情况启动。

| # | 阶段 | 作业 | 干什么 | 失败会怎样 |
|---|---|---|---|---|
| 1 | `validate` | `*-test`、`lint-go`、`lint-python` | 单元测试 + 静态检查 | 后面全不跑 |
| 2 | `quality` | `coverage-gate` | 覆盖率低于阈值失败；**找不到报告也算失败** | 同上 |
| 3 | `build` | `*-build` | 编译打包，产物作为 artifact | 同上 |
| 4 | `security` | `secret-scan`、`sast`、`sonarqube`、`dependency-scan`、`license-scan`+`license-gate`、`dockerfile-policy`、`iac-scan` | 密钥、静态分析、质量门、依赖漏洞、许可证、Dockerfile 基线、清单校验 | 不出镜像 |
| 5 | `package` | `build-image` | buildah 无守护进程构建，**只打包第 3 步产物** | 没有镜像 |
| 6 | `image-security` | `image-scan`、`sbom`、`sign-image` | 扫**最终镜像**、出物料清单、签名（待接） | 不进 STG |
| 7 | `gitops` | `stg-promotion` | 通知甲方作业按 digest 部署并等待健康 | STG 不更新 |
| 8 | `dast` | `dast-baseline` | 对 STG 发真实请求（ZAP baseline） | 手动触发 |
| 9 | `release` | `release-candidate`、`prod-promotion` | 在选定主干流水线上手动申请，校验 STG 凭证后自动建生产 MR | 发不了版 |

**为什么这 9 个阶段能成立**：第 5 步之前的全部检查，针对的是同一份代码；第 5 步只打包第 3 步的产物，不在镜像里重新编译。所以"扫描过的 = 上线跑的"这件事可以被证明，而不是靠承诺。

### 3.1 代码推送后，一步步发生什么

触发场景包括提 MR、合进 `main` 和在历史主干流水线上申请生产。按"合进 main"这条主线走一遍（最完整）：

| # | 谁 | 阶段 | 做什么 | 产出 | 卡住会怎样 |
|---|---|---|---|---|---|
| 1 | 供应商 | — | push 分支，提 MR | — | — |
| 2 | 系统 | `validate` | 单元测试 + lint | junit 报告、覆盖率报告 | MR 不能合并 |
| 3 | 系统 | `quality` | 读覆盖率报告比阈值 | 通过/不通过 | 同上 |
| 4 | 系统 | `build` | 编译打包 | jar / wheel / 二进制 / `dist/` 作为 artifact | 同上 |
| 5 | 系统 | `security` | 密钥、SAST、质量门、依赖漏洞、许可证、Dockerfile 基线、清单校验 | 各类扫描报告 | 同上 |
| 6 | 供应商 | — | 门禁绿后自己合并 MR（无需甲方审批） | `main` 上的新提交 | — |
| 7 | 系统 | 2–5 再跑一遍 | 检查的对象换成合并后的提交 | 同上 | 不构建镜像 |
| 8 | 系统 | `package` | **拿第 4 步的 artifact 构建镜像**，推仓库 | 镜像 + digest | 没有镜像，后面全停 |
| 9 | 系统 | `image-security` | 扫最终镜像、出 SBOM、签名 | trivy 报告、`sbom.json` | 不进 STG |
| 10 | 系统 | `gitops` | 写入 STG 镜像 digest | GitOps revision | 写入失败则停止 |
| 11 | 甲方运维作业 | `gitops` | 只读核对 Argo CD 的应用、目标、revision、健康状态和镜像 | 以业务流水线编号归档部署凭证后，STG 作业才成功 | 超时或归档失败则 STG 作业失败 |
| 12 | 供应商 | STG | 完成功能测试并填写窗口清单和报告 | 每个应用可选择不同日期的已测版本 | 缺验收材料则无法晋级 |
| 13 | 供应商 | `release` | 在所选历史主干流水线手动执行 `release-candidate`，输入 `RELEASE_ID` | 窗口清单编号 | 不申请则不生成生产 MR |
| 14 | 系统 | `release` | `prod-promotion` 自动核对清单、报告和该流水线的健康凭证 | 按原 digest 创建应用的生产 MR | 证据不符则拒绝 |
| 15 | 甲方 | 窗口内 | 审核 MR，按清单的顺序同步批准的 revision | 记录生产发布结果 | 异常时按清单回滚 |

业务 MR 执行适用的单测、构建及门禁。受保护主干在镜像门禁后部署 STG。生产申请始终引用当次流水线的凭证，与 STG 后续部署互不影响。业务 Git 标签不触发发布。

### demo 里哪几个阶段是占位

四个示例展示完整作业图。实际占位的六项为 SonarQube、DAST、镜像签名、依赖漏洞扫描、镜像漏洞扫描和 SBOM。后三项生成演示报告。单测、覆盖率、构建、密钥扫描、SAST、许可证判定、Dockerfile 检查和 GitOps 晋级使用公共模板。STG 成功仍需真实的 Argo CD 健康凭证。正式接入时配置对应服务并实现签名和验签。

### 为什么每个项目只跑 16 个左右作业

模板里有 27 个，但：语言模板只 include 一个；`lint-go` 只在有 `go.mod` 时跑、`lint-python` 只在有 `*.py` 时跑、`iac-scan` 只在有 `k8s/` 之类目录时跑。所以不是漏了。

---

## 4. 一次发版：10 步

| # | 步骤 | 谁做 | 关键动作 |
|---|---|---|---|
| 1 | 提交合并请求 | 供应商开发 | 分支 → MR，禁止直推 `main` |
| 2 | 门禁自动执行 | 系统 | 9 个阶段跑完，任一失败不能合并 |
| 3 | 合并（进 STG） | **供应商自己** | 门禁全绿后供应商直接合并，甲乙都不需要点；合并即触发构建与 STG 晋级 |
| 4 | 构建并自动晋级 STG | 系统 | 推镜像、写 STG overlay、Argo CD 自动同步 |
| 5 | STG 验收 | 供应商 + 发布经理 | 功能验证；需要时手动触发 `dast-baseline` |
| 6 | 归档发布材料 | 发布经理 | `releases/<releaseId>/` 放部署清单 + 每个应用一份测试报告（Schema 校验） |
| 7 | 选择版本 | 供应商 | 在已测版本的历史主干流水线中填写窗口清单编号 |
| 8 | 申请生产 | 供应商 | 执行可选的手动 `release-candidate` |
| 9 | 校验并开 MR | 甲方作业 | 匹配部署凭证、清单、测试报告和 digest 后创建生产 MR |
| 10 | 审批合并 + 窗口内 Sync | 甲方 + 安全评审 | 合并 MR → 在发布窗口内对 prod 点 Sync |

发布后 15 分钟内确认：Pod 全部 Ready、`/healthz` 正常、Argo CD 显示 `Synced`、没有新增告警。

### 发布到生产的前提：进过 STG + 供应商签过字

甲方只看两件事，都写死在流程里：

| 前提 | 谁保证 | 怎么验证 |
|---|---|---|
| 这个镜像**曾经部署到 STG** | 机器 | 甲方作业读取 `evidence/stg/<项目>/<应用>/<流水线编号>.json`，核对业务提交、镜像和 Argo CD 观察记录 |
| **测试通过** | 供应商 | 部署清单里 `stgTest.tested: true` + `confirmedBy`。Schema 强制必填，写 `false` 或省略都会校验失败 |

**刻意不做的事**：不要求"STG 此刻正在跑这个镜像"。STG 是共享测试环境，
下一个提交覆盖它是常态；甲方要的是"这个镜像测过"，不是"它一直挂在 STG 上"。
也不要求平台复核测试结论——测试是供应商的职责，平台只记录谁签的字。

### 窗口的含义

`syncWindows` 在 prod 的 AppProject 上，`manualSync: false` 的意思是"**窗口外人工也点不动**"。
它不是"窗口内允许人工同步"的开关——窗口内本来就能人工同步，这个字段管的是能不能越窗。

紧急发布不是跳过窗口，是**另开一个临时窗口**并把范围、期限、批准人写进记录。

---

## 5. 回滚

回滚**不是** `git revert` 上一次提交。做法是把 prod overlay 里的 digest 改回上一个稳定值：

1. 从 `git log apps/<key>/<app>/overlays/prod` 找到上一个稳定 digest；
2. 改 overlay 的 `digest` 字段，提 MR，说明原因；
3. 甲方审批 → 窗口内 Sync。

不需要重新构建、不需要重新扫描（镜像没变）。通常 10 分钟内完成。

**数据库变更不能这样回滚。** 所以数据库变更必须向前兼容（先加字段不删字段，双写过渡），把它当成"发版不可逆的部分"单独评审。这条写进部署清单的"数据库变更"字段，评审时逐条看。

---

## 6. 接入一个新项目：3 步

1. 把对应语言的示例项目**整套文件**复制到项目根目录（源码目录结构可以换成你自己的，`Dockerfile` 里的产物路径要对应改）。
2. 改 `.gitlab-ci.yml` 三行：`PROJECT_KEY`（供应商代号）、`APP_NAME`、`K8S_NAMESPACE`。
3. 在 GitOps 仓库生成部署骨架：`python3 tools/add_app.py ...`。它会一次性生成 base + 两套 overlay + AppProject + Application——这五样必须同时存在且互相对应，漏一个的表现是"Argo CD 里看不到这个应用"。

---

## 7. 权限与职责分离

| 角色 | GitLab 角色 | 能做什么 | 不能做什么 |
|---|---|---|---|
| 平台管理员 | Owner | 改模板、改 GitOps、发模板标签 | — |
| 发布经理 | Maintainer（GitOps 仓库） | 审批部署清单、合并生产 MR、窗口内 Sync | 改流水线模板 |
| 安全评审 | Reporter | 看扫描报告、看审计 | 改代码、改配置 |
| 供应商开发 | **Developer** | 提 MR、**合并自己的 MR（=自己发 STG）**、看自己项目的流水线 | 直推 `main`、建 `v*` 标签、改 CI 模板、合模板/GitOps 仓库 |
| 供应商负责人 | Developer + 组内 Maintainer | 管理组内成员 | 同上 |

关键约束与一个刻意的取舍：

- **供应商最高只能是 Developer**。GitLab CE 无法设"任何人不得直推 main"，所以靠
  "protected branch 只允许 Maintainer **推** + 供应商不是 Maintainer"来等价实现。
- **`main` 的合并权放开到 Developer**（`main` 保护规则里 push=Maintainer、merge=Developers）。
  也就是说：供应商不能绕过 MR 直推，但**可以自己把自己那个项目的 MR 合进去**，
  合完就自动构建 + 自动同步 STG。STG 是测试环境，甲方不在这里把关。
- 生产完全不跟着放开：模板仓库、GitOps 仓库的 `main` 仍然是 push/merge 都只给 Maintainer。

---

## 8. 上线前提

| # | 准备什么 | 具体要求 |
|---|---|---|
| 1 | 模板仓库打标签 | `examples` 里的 `ref` 必须指向真实存在的**受保护标签**，否则流水线 config error |
| 2 | 组级 CI 变量 | `REGISTRY_HOST`、`REGISTRY_TLS_VERIFY`、`REGISTRY_USER`、`REGISTRY_PASSWORD`、`OPS_PROJECT_ID`、项目专用 `OPS_TRIGGER_TOKEN`、只读 `OPS_STATUS_TOKEN`。令牌 masked + protected；写令牌只放甲方 GitOps 项目。接入步骤见该仓 README |
| 3 | Runner 隔离 | 普通测试和扫描用非特权 `docker-general`，通知用非特权 `docker-notify`。构建固定使用独立主机的 `docker-build`。甲方 GitOps 使用项目专属非特权 `docker-ops`，独立主机、独立并发容量。构建池限制授权项目和受保护引用，关闭无标签调度。 |
| 4 | Argo CD 两套 | 每套都要配：GitOps 仓库凭证、目标集群注册、根 Application（指向 `argocd/bootstrap/<env>`） |
| 5 | 镜像仓库权限 | 构建、扫描、SBOM 四处都用同一组凭据 |
| 6 | 三个开关确认没被关 | `main` 保护（push=Maintainer / merge=Developer）、`v*` 标签保护、"流水线成功才允许合并" |
| 7 | **模板仓库对供应商组只读可见** | 给供应商所在组授 Reporter。不给的话，他们的 MR 流水线**一创建就失败、0 个作业**——因为 `include` 拉不到模板。这个报错在 GitLab 界面上只说"pipeline failed"，很难联想 |

### 本地 GitLab 配置记录（2026-11-22）

`platform/gitops-deployments` 已配置项目访问令牌 `ops-promotion-writer`，到期日为 **2027-02-20**。令牌仅有 `write_repository` scope。该项目保护分支 `main` 的最低直推角色为 Maintainer，因此机器人使用此角色。

项目 CI/CD 变量名为 `GITOPS_TOKEN`，环境范围为 `promotion`，已启用 Protected、Masked 和 Hidden。新写令牌仅供甲方晋级作业使用。旧业务组令牌仍供旧模板使用，待项目切换后另行轮换回收。平台负责人应在上述到期日前轮换新令牌。

本次通过 GitLab API 核对了令牌状态、权限和变量属性，未触发部署或执行分支写入测试。

### 一个容易踩的坑：镜像名有两处，必须一致

CI 里 `IMAGE_NAME` 是 `$CI_PROJECT_PATH_SLUG`，甲方 GitOps 晋级作业核对构建产物后执行类似操作：

```bash
kustomize edit set image "<REGISTRY_HOST>/<slug>=<REGISTRY_HOST>/<slug>@<digest>"
```

左边这个 `<REGISTRY_HOST>/<slug>` 必须和 overlay 里 `images[].name` **逐字符相同**，否则
kustomize 匹配不上，会**新增**一条 image 记录，而 Deployment 引用的还是旧名字——
表现是流水线绿、GitOps 提交也有，但 STG 镜像无法正确更新。

所以改镜像仓库地址时，`defaults.yml` 的 `REGISTRY_HOST` 和 `apps/*/*/overlays/*/kustomization.yaml`
里的镜像名要**一起改**。交付包里这两处都是 `harbor.invalid`，一眼能看出没配过。

第 6 条是最容易出事的：这三项配错时流水线照样"绿"，只是绿灯不作数。改完故意让一个扫描失败一次，确认流水线真的会红、且 STG 不更新。

---

## 9. 已知缺口

按"能不能绕过"排序：

| 编号 | 缺口 | 影响 | 优先级 |
|---|---|---|---|
| G13 | 旧模板在业务项目使用 GitOps 写令牌，切换后需撤销上级组和项目遗留授权 | 遗留令牌仍可写生产配置 | **P0** |
| G1 | Argo CD 实例尚未部署到真实集群 | 部署链路最后一段只在清单层面验证过 | **P0** |
| G2 | 供应商未按子组隔离 | 供应商之间可见彼此代码 | **P0** |
| G3 | 镜像签名未启用（`sign-image` 是手动占位） | "上生产的镜像就是 CI 构建的那个"只能靠仓库权限保证 | P1 |
| G14 | 生产 `targetRevision` 仍是 `main` | 靠"无自动同步 + 窗口 + 人工 Sync"兜底 | P2 |

G13 通过甲方项目独占写入口、按触发身份限定来源项目和部署目录、轮换旧凭据处理。G14 仍需发布负责人核对实际同步的 Git revision。

---

## 10. 待与同事确认

这些没定之前，相关部分只能按假设做：

1. 等保定级与测评边界（决定审计日志留存、账号要求）。
2. "业务代码不上云"的准确边界：GitOps 仓库内容算不算、Argo CD 的云端缓存算不算。
3. Argo CD 放统一运维账号还是 CCS Local 的 plf 账号。
4. 是否一账号一集群；STG 与 PROD 是否在不同百度云账号。
5. 镜像仓库：用统一运维账号的中央库，还是各业务账号各建一个。
6. Nexus 何时就位（决定依赖源、Trivy DB、semgrep 规则集能否内网化）。
7. SonarQube 是否已有实例、由谁维护。
8. GitLab CE 版本与是否可升级（影响 API 能力）。

---

## 11. 文件职责对照

| 你要改的东西 | 改这里 |
|---|---|
| 阶段顺序 | `cicd-templates: stages.yml` |
| 全局变量、超时、重试、Runner 标签 | `cicd-templates: defaults.yml` |
| 什么时候触发流水线 | `cicd-templates: workflow.yml` |
| 某语言的构建方式 | `cicd-templates: languages/*.yml` |
| 安全门禁的判定规则 | `cicd-templates: security/*.yml` |
| 镜像构建与扫描 | `cicd-templates: container/*.yml` |
| STG 晋级 / 生产发布 | `cicd-templates: gitops/*.yml` |
| 某应用部署成什么样 | `gitops-deployments: apps/<key>/<app>/base/` |
| 某环境与该应用的差异 | `gitops-deployments: apps/<key>/<app>/overlays/<env>/` |
| 命名空间、配额、网络策略 | `gitops-deployments: platform/<env>/` |
| Argo CD 权限边界、同步窗口 | `gitops-deployments: argocd/projects/<env>/` |
| Argo CD 跟踪路径、同步策略 | `gitops-deployments: argocd/applications/<env>/` |
| 发布证据的格式 | `gitops-deployments: releases/` + `policies/*.schema.json` |

---

## 12. 几个刻意的取舍

- **镜像里不编译**：`docker build .` 不能单独用，本地要先出制品。换来的是"镜像内容可追溯到被扫描的那一份"+"内网构建期不连依赖源"。
- **生产不自动同步**：`applications/prod/*.yaml` 里没有 `syncPolicy.automated`。注意 `automated: {}`（空映射）在 YAML 里像"没配"，但 Argo CD 会当成开启——`validate-policy` 会拦这种写法。
- **`sign-image` 是占位**：签名要接 KMS/Vault，属于另一个工程。
- **`lint-java` / `lint-node` 是注释掉的作业位**：规则依赖项目自己的 checkstyle/eslint 配置，模板不替项目定风格。
- **`lint-python` 的 ruff 没锁版本**：要么改成 `ruff==0.8.4`，要么换内网镜像源——内网默认没有 PyPI。
- **`iac-scan` 用 kubeconform**：只校验清单合法性，不校验"这个镜像该不该上生产"，后者是 Argo CD 与发布流程的事。
