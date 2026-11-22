# 镜像里只装 CI build 阶段产出的 jar，不在镜像里重新编译。
#
# 三条理由，按重要性：
# 1) 内网构建期不该再访问依赖源。生产 Runner 在北京机房，依赖代理（Nexus）未就位，
#    镜像构建阶段再跑 `mvn package` 就要另开一条到 Maven 仓库 的通道。
# 2) 产物来源唯一。验收时能直接回答「镜像里的 jar 就是 CI 那个作业的产物」，
#    不用论证两次构建为什么等价。
# 3) RUN 里编译能绕开 lockfile（`mvn -U`），引入未锁定版本。镜像级扫描能看到最终装了什么，
#    但那是另一个口径，不该拿它给 lockfile 审计兜底。
#
# 代价：`docker build .` 不能单独用，本地先执行 `mvn -B -DskipTests package`。

FROM docker.io/library/eclipse-temurin:21-jre@sha256:d77e090ae1f6970c047b443c6f0a6c1358b0426d44432bb5a7753408cd43de0d

WORKDIR /app

# 固定为 target/<finalName>.jar（pom.xml 已设 finalName=java-api）。
# 用固定文件名而不用通配符：约定被破坏时构建直接失败，不会悄悄打进别的文件。
COPY target/java-api.jar app.jar

# 显式声明非 root。镜像不写 USER 时默认就是 root，K8s 的 runAsNonRoot=true
# 会在启动时拒绝它，Pod 起不来——这个错要到部署时才暴露，所以门禁放在构建前。
USER 10001:10001

CMD ["java", "-jar", "app.jar"]
