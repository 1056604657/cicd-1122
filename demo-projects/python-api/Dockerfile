# 镜像里只装 CI build 阶段产出的 wheel，不在镜像里重新编译。
#
# 三条理由，按重要性：
# 1) 内网构建期不该再访问依赖源。生产 Runner 在北京机房，依赖代理（Nexus）未就位，
#    镜像构建阶段再跑 `python -m build` 就要另开一条到 PyPI 的通道。
# 2) 产物来源唯一。验收时能直接回答「镜像里的 wheel 就是 CI 那个作业的产物」，
#    不用论证两次构建为什么等价。
# 3) RUN 里编译能绕开 lockfile（`pip install --upgrade`），引入未锁定版本。镜像级扫描能看到最终装了什么，
#    但那是另一个口径，不该拿它给 lockfile 审计兜底。
#
# 代价：`docker build .` 不能单独用，本地先执行 `python -m build`。

FROM docker.io/library/python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# 用 /tmp 暂存，装完即删，wheel 不留在最终镜像层里
COPY dist/ /tmp/dist/

RUN pip install --no-cache-dir /tmp/dist/*.whl && rm -rf /tmp/dist

# 显式非 root：不写 USER 时默认 root，K8s 的 runAsNonRoot=true 会拒绝启动
USER 10001:10001

WORKDIR /app

CMD ["python", "-m", "python_api.app"]
