# releases/

每次生产的发布证据放这里，一个发布一个目录：`REL-YYYYMMDD-NNN/`

必须包含：
- `deployment-list.yaml`（或 `.json`）：本次发布的部署清单，符合 `policies/deployment-list.schema.json`
- `test-report-<app>.yaml`：每个应用一份，符合 `policies/test-report.schema.json`

目录里只要有子目录，GitOps 仓库的 `validate-policy` 作业就会逐份校验：
缺部署清单、缺某个应用的测试报告、字段不符 Schema，都会阻断 MR。

`deployment-list` 里必须写的三样：`releaseId`、`commit`、`image digest`。
这三样是"发布的东西 = 测过的东西 = 批过的东西"的连接点，缺一样审计就断链。

## 每个应用要写 `stgTest`：供应商对"STG 测过"的确认

```yaml
applications:
  - name: java-api
    sourcePipeline: "12345"         # 已在 STG 健康部署的业务流水线编号
    sourceTag: v1.2.3              # 清单和报告共同使用的版本名
    dependencies: []
    downtime: false
    image: harbor/demo-projects-java-api@sha256:...
    previousImage: harbor/demo-projects-java-api@sha256:...
    stgTest:                       # ← 必填
      tested: true                 # 必须写 true，写 false 或省略都会被 Schema 拦下
      confirmedBy: acme-pm         # 供应商侧确认人
      at: "2026-11-22"
      note: 回归用例 32 条全过，重点验了订单导出    # 可空
    testReport: test-report-java-api.yaml
```

供应商负责功能测试签认。甲方校验该报告的窗口、应用、版本、digest 和测试统计，再与所选流水线的 STG 健康凭证交叉核对。窗口清单及报告应在点击生产申请前归档到 GitOps 主干。
