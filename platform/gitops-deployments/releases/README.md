# releases/

每次生产的发布证据放这里，一个发布一个目录：`REL-YYYYMMDD-NNN/`

必须包含：
- `deployment-list.yaml`（或 `.json`）：本次发布的部署清单，符合 `policies/deployment-list.schema.json`
- `test-report-<app>.yaml`：每个应用一份，符合 `policies/test-report.schema.json`

目录里只要有子目录，GitOps 仓库的 `validate-policy` 作业就会逐份校验：
缺部署清单、缺某个应用的测试报告、字段不符 Schema，都会阻断 MR。

清单登记窗口编号、应用版本与镜像 digest。甲方作业从所选业务流水线获取编号和源码提交，并与 STG 部署凭证核对。供应商无需在清单里填写流水线编号。

## 每个应用要写 `stgTest`：供应商对"STG 测过"的确认

```yaml
applications:
  - name: java-api
    sourceTag: v1.2.3              # 清单和报告共同使用的版本名
    dependencies: [go-api]         # go-api 先发且验证通过；无前置依赖填 []
    downtime: false                # 必填，按实际影响填 true 或 false
    databaseChanges: "发布前新增订单索引"  # 无数据库变更可省略
    middlewareChanges: "发布前创建订单消息队列"  # 无中间件变更可省略
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
