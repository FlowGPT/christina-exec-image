# christina-exec-job：工单 pod 用的镜像 = 通用镜像 + 测试常用的数据库 + 预览工具（用途见 README.md）。
#
# 和通用镜像一样只装公开的东西：不 COPY、不 ADD，不含代码、数据、配置或凭据。
# 构建上下文是 job/ 这个目录，里面只有这个文件。

# 基础镜像按「标签@digest」钉死：同一份层，集群节点上已有通用镜像时只需拉增量。
# 升级通用镜像时，标签和 digest 一起改。
ARG BASE=ghcr.io/flowgpt/christina-exec-image:20261015-3e356fa@sha256:b4650b7601fd7a06af9fb05ad6d0ea2d77a0cf5f96ad49524f10d292744cbd66
FROM ${BASE}

LABEL org.opencontainers.image.source=https://github.com/FlowGPT/christina-exec-image

USER root

# PostgreSQL 18 + pgvector，取自 PostgreSQL 官方 apt 源（apt.postgresql.org，PGDG）；redis 取自 bookworm。
# - 不用 bookworm 自带的 PostgreSQL：bookworm 只有 15，而且 bookworm 和 bookworm-backports 都没有 pgvector 包。
#   PGDG 也是官方 postgres 镜像（docker run postgres）用的源。
# - 选 18：现在 `docker run postgres` 不带标签拿到的就是 18（19 还在 RC）；新版能跑为旧版写的 SQL，反过来不行。
# - PGDG 签名密钥按完整指纹核对（与官方 postgres 镜像 Dockerfile 里钉的指纹相同），文件里只能有这一把，对不上就失败。
# - 不建默认集群（库由运行用户自己 initdb），不装 JIT（postgresql-18-jit 会拖进 LLVM，测试用不上）。
# - 小版本不钉：和通用镜像一样，镜像本身就是钉，实际版本写进 /opt/runner/versions.txt。
# - postgresql 依赖的 ssl-cert 安装时会生成一张自签证书和私钥（snakeoil），还在 /etc/ssl/certs 里给它建了信任链接。
#   公开镜像不留私钥，也不该信任它：三样都删。用不到它：initdb 建的库默认不开 ssl。
ARG PG_MAJOR=18
ARG PGDG_FINGERPRINT=B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends gpg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /tmp/pgdg.asc; \
    gpg --batch --show-keys --with-colons /tmp/pgdg.asc > /tmp/pgdg.colons; \
    test "$(grep -c '^pub:' /tmp/pgdg.colons)" = 1; \
    test "$(awk -F: '$1 == "fpr" { print $10; exit }' /tmp/pgdg.colons)" = "$PGDG_FINGERPRINT"; \
    gpg --batch --dearmor < /tmp/pgdg.asc > /usr/share/keyrings/pgdg.gpg; \
    rm /tmp/pgdg.asc /tmp/pgdg.colons; \
    echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-common; \
    sed -ri 's/#(create_main_cluster) .*$/\1 = false/' /etc/postgresql-common/createcluster.conf; \
    apt-get install -y --no-install-recommends \
        "postgresql-$PG_MAJOR" "postgresql-$PG_MAJOR-pgvector" redis-server; \
    find /etc/ssl/certs -lname ssl-cert-snakeoil.pem -delete; \
    rm /etc/ssl/certs/ssl-cert-snakeoil.pem /etc/ssl/private/ssl-cert-snakeoil.key; \
    rm -rf /var/lib/apt/lists/*

# initdb、pg_ctl 不在 Debian 的默认 PATH 里，加到最后（和官方 postgres 镜像一样）。
ENV PATH=$PATH:/usr/lib/postgresql/$PG_MAJOR/bin

# 预览用的 caddy 和 cloudflared：官方 GitHub release，版本和校验和都钉死，对不上就失败。
# 校验和是下载后自算、再与该 release 自己公布的值（caddy 的 checksums.txt、cloudflared 的 release 说明）对过的。
# 通用镜像只有 amd64，这里也只装 amd64。
ARG CADDY_VERSION=2.11.7
ARG CADDY_SHA512=a7a433a1b133efc3c8d10eb0b99d52a24b5ef5c322dc77f5282182b1c0402139ab83f3a99f0c52409df77d20123fb0b523edad8a66d8f5e49136197bf61ef0e7
ARG CLOUDFLARED_VERSION=2026.10.0
ARG CLOUDFLARED_SHA256=d33ff2d14475178d2012c2c56beba87389ac5ded27649519f198a7d3134a99db
RUN set -eux; \
    test "$(dpkg --print-architecture)" = amd64; \
    cd /tmp; \
    curl -fsSLo caddy.tar.gz "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz"; \
    echo "${CADDY_SHA512}  caddy.tar.gz" | sha512sum -c -; \
    tar -xzf caddy.tar.gz --no-same-owner -C /usr/local/bin caddy; \
    curl -fsSLo cloudflared "https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-linux-amd64"; \
    echo "${CLOUDFLARED_SHA256}  cloudflared" | sha256sum -c -; \
    install -m 0755 cloudflared /usr/local/bin/cloudflared; \
    chmod 0755 /usr/local/bin/caddy; \
    rm caddy.tar.gz cloudflared

RUN { echo; echo "# christina-exec-job"; \
      postgres --version; \
      echo "pgvector $(dpkg-query -W -f '${Version}' "postgresql-$PG_MAJOR-pgvector")"; \
      redis-server --version; \
      echo "caddy $(caddy version)"; \
      cloudflared --version; \
    } >> /opt/runner/versions.txt

USER 1000
WORKDIR /home/runner
