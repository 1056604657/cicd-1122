# cicd-templates

全平台唯一的 CI/CD 模板仓库。所有业务仓库通过跨项目 `include` 引用本仓库，
**禁止在各业务仓库内复制粘贴或改写构建逻辑**。模板变更走 MR + 平台负责人审批，
`main` 为保护分支；模板改动影响全部项目，必须连带验证后打新版本标签。

## 目录

```text
defaults.yml              平台标准变量、默认 Runner 标签、超时与重试策略
workflow.yml              统一 workflow 规则：一次提交只跑一条流水线，自动取消冗余流水线
stages.yml                统一阶段：validate → quality → build → security → package
                          → image-security → gitops → dast → release
languages/*.yml           Java(Maven) / Python / Go / Node 构建与测试
quality/lint.yml          gofmt + go vet / ruff 安全子集（Java/Node 保留作业位）
quality/coverage-gate.yml 覆盖率门禁（Cobertura / Go coverprofile / lcov）
security/secret-scan.yml  gitleaks 密钥泄露扫描（离线规则，硬门禁）
security/sast.yml         semgrep 静态分析
security/sonarqube.yml    SonarQube 扫描 + qualitygate.wait 强门禁
security/sca.yml          trivy 依赖漏洞扫描
security/license-scan.yml trivy 许可证收集 + 独立判定作业（禁止清单/例外白名单）
security/iac-scan.yml     Dockerfile 安全基线（FROM/USER/编译/密钥 9 条硬规则）+ kubeconform 清单校验
security/dast.yml         OWASP ZAP baseline 动态扫描（先探测 STG 就绪）
container/build-image.yml buildah 无守护进程构建 + 推送 + 记录 digest
container/scan-image.yml  按 build-image 归档的 digest 扫描镜像
container/sign-image.yml  镜像签名（待接入密钥管理）
container/sbom.yml        Trivy 按同一 digest 对最终镜像生成 CycloneDX SBOM，随制品留存 365 天
gitops/stg-promotion.yml  通知甲方按 digest 部署 STG，并等待健康凭证归档
gitops/release-candidate.yml 历史主干流水线的手动窗口申请
gitops/prod-promotion.yml 自动通知甲方作业创建生产 MR
tools/check_standard.py    校验业务仓库有没有偏离本仓库的约定
```

## 业务仓库接入方式

`ref` 必须指向**受保护的版本标签**，不得写 `main`——否则平台侧任何一次提交都会
即时改变所有供应商的构建行为，出问题时无法定位，也无法回滚。

```yaml
include:
  - project: platform/cicd-templates
    ref: v1.0.19
    file:
      - /defaults.yml
      - /workflow.yml
      - /stages.yml
      - /languages/go.yml
      - /security/secret-scan.yml
      - /security/sast.yml
      - /security/sca.yml
      - /container/build-image.yml
      - /container/scan-image.yml
      - /container/sign-image.yml
      - /container/sbom.yml
      - /quality/lint.yml
      - /quality/coverage-gate.yml
      - /security/license-scan.yml
      - /security/iac-scan.yml
      - /security/sonarqube.yml
      - /security/dast.yml
      - /gitops/stg-promotion.yml
      - /gitops/release-candidate.yml
      - /gitops/prod-promotion.yml

variables:
  PROJECT_KEY: "demo"
  APP_NAME: "go-api"
```

业务仓库只允许覆盖：`PROJECT_KEY`、`APP_NAME`、`K8S_NAMESPACE`、`REGISTRY_HOST`、
`REGISTRY_TLS_VERIFY`，以及按需的质量阈值。
其余变量由平台统一维护。白名单的判定实现在 `tools/check_standard.py`——
它读的就是这份清单，不存在"文档写一套、脚本判另一套"。

## 自带的校验工具

```bash
python3 tools/check_standard.py <业务仓库路径> [...]      # 生产口径
python3 tools/check_standard.py --lab --all               # 实验口径（放行手动占位）
```

它检查六件事：`include` 的 project 与 ref 是否合规（ref 必须是语义化版本标签）、
模板文件清单是否完整、变量是否在白名单内、有没有改写平台作业、Dockerfile 的 `FROM`
是否按 digest 固定、有没有 `.gitignore` 且忽略了 CI 产物。

**为什么这个脚本放在模板仓库而不是别处**：它判定的依据就是本仓库的定义。
放在一起，改模板时不会忘记同步判定逻辑；分开放，两边一定会漂移。


## 工具链版本固定

所有作业镜像与基础镜像都以 **digest** 固定，不使用浮动标签。供应商无法通过改
`Dockerfile` 的 `FROM` 或作业镜像引入未经审核的工具链。

| 用途 | 镜像 | digest（sha256） |
| --- | --- | --- |
| Java 构建/测试 | `maven:3.9.6-eclipse-temurin-21` | `8d63d4c1902c…` |
| Java 运行时 | `eclipse-temurin:21-jre` | `d77e090ae1f6…` |
| Python | `python:3.12-slim` | `5e2bdb1b0d54…` |
| Go | `golang:1.23-alpine` | `383395b794df…` |
| Node | `node:22-alpine` | `1314fb30ec37…` |
| 通用脚本作业 | `alpine:3.20` | `d9e853e87e55…` |
| 镜像构建 | `quay.io/buildah/stable:v1.36.0` | `3a4f175b9839…` |
| 跨仓库复制 | `quay.io/skopeo/stable:v1.15.0` | `11759b822fef…` |
| 漏洞扫描 | `aquasec/trivy:0.58.0` | `b88012e2a0a3…` |
| 密钥扫描 | `zricethezav/gitleaks:v8.24.0` | `2bcceac45179…` |
| SAST | `returntocorp/semgrep:1.85.0` | `b4c2272e0a2e…` |
| SBOM | `anchore/syft:v1.16.0` | `7dffd5ca0d20…` |
| 前端运行时 | `nginxinc/nginx-unprivileged:1.27-alpine` | `65e3e85dbaed…` |
| 动态扫描 | `ghcr.io/zaproxy/zaproxy:stable` | `9624669db72f…` |
| 清单校验 | `ghcr.io/yannh/kubeconform:v0.6.7` | `0925177fb05b…` |
| 代码质量扫描 | `sonarsource/sonar-scanner-cli:11.1` | `5812d28892fa…` |

升级工具链 = 改模板 + 打新版本标签 + 各项目改 `ref`，三步都要留痕。

## 镜像构建契约（Dockerfile 必须遵守）

镜像里装的必须是**已经被扫描过的那份产物**。这条不是风格偏好，而是"扫描结论能不能
算在镜像上"的前提：

```text
validate/security 阶段 ──> 检查工作区源码 ──┐
                                            ├──> 必须是同一份东西
build 阶段 ─────────────> 产出 jar/dist/bin ─┘
                                            │
package 阶段 ────────────> 镜像只打包它 ────┘
```

如果 Dockerfile 在 `RUN` 里再跑一次 `mvn package` / `go build` / `npm run build`，
镜像里就是**第二次独立构建**的产物：编译器版本、依赖解析结果、构建时间戳都可能不同，
SAST/SCA 的结论对镜像不再成立，SBOM 也和镜像实际内容对不上。所以：

| 规则 | 判定方式 | 违反后果 |
| --- | --- | --- |
| `RUN` 里不得执行编译/打包命令 | `dockerfile-policy` 正则拦截 | 构建失败 |
| 必须从构建上下文 `COPY` 产物 | 至少一条不带 `--from` 的 `COPY` | 构建失败 |
| 必须显式声明非 root `USER` | 无 `USER` 等同于 root | 构建失败 |
| `build-image` 前产物目录必须存在 | 检查 `target/`、`dist/`、`bin/` | 构建失败 |

产物路径约定：Java `target/<finalName>.jar`、Python `dist/*.whl`、Go `bin/<bin>`、
Node `dist/`。Dockerfile 用**固定文件名**而不是通配符——约定被破坏时构建直接失败，
不会悄悄打进错的文件。

> 不写 `USER` 的镜像默认以 root 运行。K8s 的 `runAsNonRoot: true` 会拒绝启动这种 Pod，
> 错误要等到部署阶段才暴露，所以门禁放在构建前。
>
> 代价是 `docker build .` 不能直接用了：本地构建前先执行对应的 build 命令，
> 让产物目录里有东西。这是有意为之——镜像来源必须唯一。

## 质量门禁

源码和镜像的必需安全门禁自动执行，命中阈值会阻断晋级。STG 部署成功后可手动执行 DAST。扫描结果供发布评审查看，未执行或扫描失败均不自动阻断生产申请。
可按需调整的只有阈值和规则集来源，且调整权限归平台/安全角色。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SCA_SEVERITY` | `HIGH,CRITICAL` | 依赖漏洞阻断阈值 |
| `IMAGE_SCAN_SEVERITY` | `HIGH,CRITICAL` | 镜像漏洞阻断阈值 |
| `SAST_RULESET` | `p/default` | semgrep 规则集，内网应指向内部规则源 |
| `TRIVY_DB_REPOSITORY` | 内部 OCI 仓库 | 漏洞库来源，避免每次构建拉公网 |

> 扫描依赖外部数据源：Trivy 漏洞库（约 136MB，ghcr.io）与 semgrep 公共规则集。
> 内网环境必须先把两者同步到内部仓库，否则作业会在下载阶段超时；
> 不允许用“关闭扫描”的方式绕过该问题。

## 流水线语义

- **分支流水线（main）**：测试与 lint → 覆盖率门禁 → 编译 → 密钥/SAST/SonarQube/SCA/
  许可证/Dockerfile 基线 → 构建镜像并推送 → 镜像扫描/SBOM → 写 GitOps STG overlay
  → 等待 Argo CD 确认该版本健康并归档 → 按需 DAST。
- **MR 流水线**：执行测试、语言构建和源码级扫描，不推送镜像或写 GitOps，
  避免未审核代码进入环境。
- **历史主干流水线**：供应商在已验证的版本上手动执行 `release-candidate`，填写 `RELEASE_ID`。随后 `prod-promotion` 自动请求甲方核验窗口材料和 STG 健康凭证并开 MR。
- **生产 Sync**：不由 CI 触发，只能在发布窗口内由授权人员人工执行。

## 关键约束

1. CI 不持有任何业务集群的 kubeconfig，集群变更只经 Argo CD。
2. 业务项目配置甲方项目编号 `OPS_PROJECT_ID`、本项目专用 `OPS_TRIGGER_TOKEN` 和只读 `OPS_STATUS_TOKEN`。写入令牌 `GITOPS_TOKEN` 只配置在甲方 GitOps 项目。权限、来源映射及切换顺序见 GitOps 仓库 README。
3. 镜像 tag 为提交短 SHA，STG 与 PROD 部署同一 digest，禁止 `latest`。
4. 模板引用用受保护标签 `ref` 固定；升级模板需改 `ref`，不允许项目侧“本地补丁”。
5. 普通作业使用非特权 `docker-general`，通知使用非特权 `docker-notify`，Buildah 使用独立构建机上的 `docker-build`，甲方 GitOps 作业使用独立的 `docker-ops`，禁止项目指定其它 Runner 绕过构建约束。
6. 释放资源的作业（测试、扫描）标 `interruptible: true`；构建、晋级、发布类作业
   不可被自动取消，避免半截状态。
7. **镜像只打包 build 阶段的产物**，Dockerfile 不得编译、必须显式声明非 root `USER`，
   否则镜像里跑的东西与扫描过的代码之间没有可证明的对应关系。
