# 镜像里只装 CI build 阶段产出的静态文件，不在镜像里重新打包。
#
# 三条理由，按重要性：
# 1) 内网构建期不该再访问依赖源。镜像构建阶段再跑 `npm run build` 就要另开一条到 npm registry 的通道。
# 2) 产物来源唯一。验收时能直接回答「镜像里的 dist 就是 CI 那个作业的产物」。
# 3) RUN 里编译能绕开 lockfile（`npm install` / 改 package-lock.json）引入未锁定版本。
#
# 为什么用 busybox 而不是 nginx：纯静态站点只需要一个能发文件的 httpd。
# nginx-unprivileged 基于 alpine 全量镜像，Trivy 实测带 3 个 CRITICAL + 65 个 HIGH 可修复漏洞，
# 对一个只发静态文件的容器来说攻击面过大；busybox 实测 0 个。
# 如果站点需要 SPA 路由重写、gzip、反代，再换回 nginx 并为漏洞建立例外单。
#
# 代价：`docker build .` 不能单独用，本地先执行 `npm ci && npm run build`。
FROM docker.io/library/busybox:1.37@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec

# 静态文件放在 /www，busybox httpd 用它作为文档根
COPY dist/ /www

# 显式非 root：不写 USER 时默认 root，K8s 的 runAsNonRoot=true 会拒绝启动
USER 10001:10001

EXPOSE 8080

# -f 前台运行（容器要前台进程），-p 8080（非特权端口），-h 指定文档根
CMD ["httpd", "-f", "-p", "8080", "-h", "/www"]
