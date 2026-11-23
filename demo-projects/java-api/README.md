# java-api

Java 21 + Maven 示例服务，用于验证平台统一 CI/CD 与 GitOps 流程。**它不是业务代码模板**，
而是“一个项目接入标准流水线后应该长什么样”的参照物。

- 对外接口：`GET /healthz`（探针）、`GET /greet?name=`（示例业务接口）
- 容器端口：8080

## 本地运行

```bash
mvn -B test
mvn -B package
docker build -t java-api:dev . && docker run -p 8080:8080 java-api:dev
```

## 流水线

本项目通过 `.gitlab-ci.yml` 引用 `platform/cicd-templates@v1.0.19` 的对应语言模板。

1. 供应商提交 MR，执行语言测试、覆盖率、构建和适用门禁。
2. 合并主干后，Buildah 在 `docker-build` 构建并推送镜像。甲方 GitOps 作业按 digest 部署 STG，确认 Argo CD 报告指定版本已同步且健康，再归档凭证。
3. 生产窗口前，在选定的历史主干流水线上手动执行 `release-candidate`，填写清单编号 `RELEASE_ID`。`prod-promotion` 自动请求甲方核验材料并创建生产 MR。甲方审核后在窗口内同步。

示例中六个作业使用占位实现：SonarQube、DAST、签名、依赖漏洞扫描、镜像漏洞扫描和 SBOM。普通测试和扫描使用 `docker-general`，业务通知使用 `docker-notify`，甲方晋级使用 `docker-ops`。四种语言共享这些调度规则，构建镜像按语言选择。
