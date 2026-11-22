# 镜像里只装 CI build 阶段产出的 静态二进制，不在镜像里重新编译。
#
# 三条理由，按重要性：
# 1) 内网构建期不该再访问依赖源。生产 Runner 在北京机房，依赖代理（Nexus）未就位，
#    镜像构建阶段再跑 `go build` 就要另开一条到 Go module 代理 的通道。
# 2) 产物来源唯一。验收时能直接回答「镜像里的 静态二进制 就是 CI 那个作业的产物」，
#    不用论证两次构建为什么等价。
# 3) RUN 里编译能绕开 lockfile（`go get` / 直接改 `go.mod`），引入未锁定版本。镜像级扫描能看到最终装了什么，
#    但那是另一个口径，不该拿它给 lockfile 审计兜底。
#
# 代价：`docker build .` 不能单独用，本地先执行 `CGO_ENABLED=0 go build -o bin/ ./...`。

FROM docker.io/library/alpine:3.22@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f

# CI 侧以 CGO_ENABLED=0 编译，产物是静态二进制，运行镜像不需要任何 libc 依赖。
# 若这里改回带 CGO 的动态链接产物，镜像能构建成功，但启动时才报找不到解释器——
# 而那时流水线已经绿了。
COPY bin/go-api /usr/local/bin/go-api

# 显式非 root：不写 USER 时默认 root，K8s 的 runAsNonRoot=true 会拒绝启动
USER 10001:10001

CMD ["go-api"]
