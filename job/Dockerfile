# christina-exec-job：工单 pod 用的镜像 = 通用镜像 + 测试常用的数据库 + 预览工具 + 工单 pod 的运行环境（用途见 README.md）。
#
# 和通用镜像一样只装公开的东西：不含 Christina 的代码、数据、配置或凭据，也不写任何内部地址。代码在 pod 起来以后由
# christina-pod-boot 带线令牌从单面 API 取（地址由 pod 规格的 PLANE_URL 给）。
# 构建上下文是 job/ 这个目录。COPY 进来的只有四样，都在这个目录里、都过仓库的密钥扫描：
#   - requirements-staging.lock：Christina 仓同名文件的逐字副本，只有 PyPI 上第三方包的精确版本（装 venv 用）；
#   - christina-pod-boot：pod 的启动脚本；
#   - bin/no-credentials：kubectl / aws / docker 的一句话壳；
#   - bin/ws：工作区文件按需取 / 回传的壳（转给解包后的代码，代码不在就说还没就绪）。

# 基础镜像按「标签@digest」钉死：同一份层，集群节点上已有通用镜像时只需拉增量。
# 升级通用镜像时，标签和 digest 一起改。20261022-83d44fb 起通用镜像里有 Claude Code CLI 2.1.299（#2）。
ARG BASE=ghcr.io/flowgpt/christina-exec-image:20261022-83d44fb@sha256:b0c9f32fbe7f8eaefd20a37dd7495ecd6b307050d96ae4c30864cd6cc77c6328
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

# ── 工单 pod 的运行环境（整单上集群第一批）──────────────────────────────────────────────
# pod 规格在 Christina 仓 tools/cluster_job_pod.py：uid 1001、HOME /home/christina，代码解包到
# /opt/christina/remote-claude-code，线卷挂在 /var/lib/christina/line，令牌在 /run/christina/plane/token。

# tini 当 PID 1：她的 Bash、MCP、浏览器起的孙进程会挂到 PID 1 上，没人收就成僵尸；python 当 PID 1 还会无视 SIGTERM。
# procps（ps / pgrep / pkill）：她和子代理查进程要用。其余是浏览器的系统库，清单照 Christina 仓 Dockerfile.arena
# （playwright 1.58 的 debian12 chromium 依赖清单），通用镜像的 playwright install --with-deps 已经装了大半，这里补齐；
# fonts-liberation 是生产宿主装的那一份（截图里的西文字体和生产一致）。
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends tini procps \
        libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 \
        libglib2.0-0 libnspr4 libnss3 libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 \
        libxfixes3 libxkbcommon0 libxrandr2 fonts-liberation; \
    rm -rf /var/lib/apt/lists/*

# 运行身份：uid / gid 1001 的 christina，HOME /home/christina——和生产同一个 uid、同一条路径（她记得的路径、会话记录里
# 的路径都不用变）。没有 sudo。
RUN groupadd --gid 1001 christina \
    && useradd --uid 1001 --gid 1001 --home-dir /home/christina --create-home --shell /bin/bash christina

# Christina 的 venv：只用依赖清单的副本装（pip-compile 出的全量精确版本，--no-deps 保证不多装一个，装完 pip check）。
# 清单副本留在 venv 里：boot 拿它的 sha256 和这版代码要的（release 头 X-Requirements-Sha256）比，不一样以 11 退出。
# Christina 仓的 deploy/k8s/job_image.json 记着同一个 sha256，那边清单一变 CI 就红，提醒来这里换副本、推新镜像。
COPY requirements-staging.lock /opt/christina/venv/requirements-staging.lock
RUN set -eux; \
    python3 -m venv /opt/christina/venv; \
    /opt/christina/venv/bin/pip install --no-cache-dir --no-deps -r /opt/christina/venv/requirements-staging.lock; \
    /opt/christina/venv/bin/pip check; \
    chmod 0444 /opt/christina/venv/requirements-staging.lock

# 浏览器：版本、来源、校验和都照 Christina 仓 Dockerfile.arena（那边每个哈希都是两个镜像源各取一次、一致才钉的，
# 并和生产宿主上正在用的那份逐字节对过）。只装 amd64（通用镜像只有 amd64）。
#   - tools/browse 用的 chromium-1243（Chrome for Testing 153.0.8010.12），/opt/christina/chrome 指向它，
#     ENV BROWSE_CHROME 显式指过去（tools/browse 默认只在 $HOME/.cache/ms-playwright 找，pod 的 HOME 是内存盘）；
#   - venv 里 playwright 1.58 自己的 chromium-1208 和 headless shell（卡片封面这类 Python 截图用）。
# 都按 playwright 的目录布局放进 PLAYWRIGHT_BROWSERS_PATH（/opt/ms-playwright，通用镜像设好的）。
ARG BROWSE_CHROMIUM_REVISION=1243
ARG BROWSE_CHROMIUM_BROWSER_VERSION=153.0.8010.12
ARG BROWSE_CHROMIUM_SHA256=8aac35011c18f6e2d10696154af89a5728ac2ddd6dc6fad24ffdf243c3fcfd5a
ARG PLAYWRIGHT_CHROMIUM_REVISION=1208
ARG PLAYWRIGHT_CHROMIUM_BROWSER_VERSION=145.0.7632.6
ARG PLAYWRIGHT_CHROMIUM_SHA256=b5e3195041af345a668d110f5daf5581961fa3608626ea588c97dd0fe81c4e38
ARG PLAYWRIGHT_HEADLESS_SHELL_SHA256=2536e97d8f410df0394b3e7c4252e88ce9f239f04f3af4e247a26caf45baf49e
RUN set -eux; \
    test "$(dpkg --print-architecture)" = amd64; \
    fetch() { curl -fsSL --retry 5 --retry-delay 2 -o /tmp/pw.zip "$2"; \
              echo "$3  /tmp/pw.zip" | sha256sum -c -; \
              mkdir -p "$1"; unzip -q /tmp/pw.zip -d "$1"; rm -f /tmp/pw.zip; \
              touch "$1/INSTALLATION_COMPLETE" "$1/DEPENDENCIES_VALIDATED"; }; \
    cft=https://cdn.playwright.dev/chrome-for-testing-public; \
    fetch "$PLAYWRIGHT_BROWSERS_PATH/chromium-$BROWSE_CHROMIUM_REVISION" \
          "$cft/$BROWSE_CHROMIUM_BROWSER_VERSION/linux64/chrome-linux64.zip" "$BROWSE_CHROMIUM_SHA256"; \
    fetch "$PLAYWRIGHT_BROWSERS_PATH/chromium-$PLAYWRIGHT_CHROMIUM_REVISION" \
          "$cft/$PLAYWRIGHT_CHROMIUM_BROWSER_VERSION/linux64/chrome-linux64.zip" "$PLAYWRIGHT_CHROMIUM_SHA256"; \
    fetch "$PLAYWRIGHT_BROWSERS_PATH/chromium_headless_shell-$PLAYWRIGHT_CHROMIUM_REVISION" \
          "$cft/$PLAYWRIGHT_CHROMIUM_BROWSER_VERSION/linux64/chrome-headless-shell-linux64.zip" \
          "$PLAYWRIGHT_HEADLESS_SHELL_SHA256"; \
    chmod -R a+rX "$PLAYWRIGHT_BROWSERS_PATH"; \
    mkdir -p /opt/christina; \
    ln -s "$PLAYWRIGHT_BROWSERS_PATH/chromium-$BROWSE_CHROMIUM_REVISION/chrome-linux64/chrome" /opt/christina/chrome; \
    /opt/christina/chrome --version | grep -F "$BROWSE_CHROMIUM_BROWSER_VERSION"; \
    "$PLAYWRIGHT_BROWSERS_PATH/chromium-$PLAYWRIGHT_CHROMIUM_REVISION/chrome-linux64/chrome" --version \
        | grep -F "$PLAYWRIGHT_CHROMIUM_BROWSER_VERSION"

# agent-browser（tools/browse 的底层），与 Christina 仓 tools/install_browse.sh 同一个版本，装进和生产同一个目录。
# 先 npm pack 取 tarball、按 registry 发布的 integrity（sha512）核对，再从本地 tarball 装；别的平台的原生二进制删掉。
ARG AGENT_BROWSER_VERSION=0.38.1
ARG AGENT_BROWSER_INTEGRITY=sha512-k58FCz0yUOCANoNkMiqJe+H2y6r6sUZazqXsWF+MYq1iRC42PjtLcBoag6SSTOD/FRQppvPDvE5HDYEhclvnhw==
RUN set -eux; \
    mkdir -p /tmp/ab-pack /opt/christina/tools/agent-browser; \
    cd /tmp/ab-pack; \
    npm pack --silent "agent-browser@$AGENT_BROWSER_VERSION" >/dev/null; \
    tgz="/tmp/ab-pack/agent-browser-$AGENT_BROWSER_VERSION.tgz"; \
    python3 -c "import base64,hashlib,sys; d='sha512-'+base64.b64encode(hashlib.sha512(open(sys.argv[1],'rb').read()).digest()).decode(); sys.exit(0 if d==sys.argv[2] else 'agent-browser integrity mismatch: '+d)" "$tgz" "$AGENT_BROWSER_INTEGRITY"; \
    cd /opt/christina/tools/agent-browser; \
    echo '{"name":"christina-agent-browser","private":true}' > package.json; \
    npm install --no-audit --no-fund --silent "$tgz"; \
    npm cache clean --force; \
    rm -rf /tmp/ab-pack; \
    find node_modules/agent-browser/bin -maxdepth 1 -type f -name 'agent-browser-*' ! -name agent-browser-linux-x64 -delete; \
    chmod -R a+rX /opt/christina/tools; \
    ln -s /opt/christina/tools/agent-browser/node_modules/.bin/agent-browser /usr/local/bin/agent-browser; \
    agent-browser --version | grep -F "$AGENT_BROWSER_VERSION"

# 安装闸（同 Dockerfile.arena）：以 uid 1001、--no-sandbox 真开一次浏览器、点一下按钮才算装好。pod 里给不了 chromium
# 自带沙箱要的用户命名空间，隔离由 pod 提供；生产的 tools/browse 本来也带 --no-sandbox。RUN 结束容器即销毁。
RUN set -eux; \
    gate=/tmp/abgate; mkdir -p "$gate/home" "$gate/tmp"; \
    printf '<html><body><button onclick="this.textContent=%s">pod-gate</button></body></html>' "'clicked'" > "$gate/gate.html"; \
    chown -R 1001:1001 "$gate"; \
    setpriv --reuid=1001 --regid=1001 --clear-groups \
      env HOME="$gate/home" TMPDIR="$gate/tmp" AGENT_BROWSER_SESSION=pod-build-gate \
          XDG_CONFIG_HOME="$gate/home/.config" XDG_CACHE_HOME="$gate/home/.cache" XDG_DATA_HOME="$gate/home/.local/share" \
      sh -ec 'set -- --executable-path /opt/christina/chrome --args --no-sandbox; \
        timeout 120 agent-browser "$@" open "file:///tmp/abgate/gate.html" >/dev/null; \
        timeout 60 agent-browser "$@" snapshot > /tmp/abgate/snap.txt; \
        grep -q pod-gate /tmp/abgate/snap.txt; \
        ref=$(grep -o "ref=e[0-9]*" /tmp/abgate/snap.txt | head -1 | cut -d= -f2); \
        timeout 60 agent-browser "$@" click "@$ref" >/dev/null; \
        timeout 60 agent-browser "$@" snapshot | grep -q clicked; \
        timeout 60 agent-browser "$@" close >/dev/null || true'; \
    rm -rf "$gate"

# 启动脚本、三个一句话的壳、ws，以及 pod 里要写的几处目录（都交给 uid 1001；/opt/christina 本身仍归 root）：
#   /opt/christina/remote-claude-code  代码解包处（容器可写层，每次容器新起都是空的）；/opt/christina/current 指向它
#   /opt/christina/.claude             生产的 hooks 目录（/opt/christina/.claude/hooks）
#   /etc/christina                     这版代码的边界设置和听众注册表由 pod_setup 放进来（生产上归 root；pod 里代码本身
#                                      就是她解包的，这两份在 pod 里不是边界，边界在单面 API）
#   /opt/christina/workspace、/var/lib/christina/line、/run/christina  内存盘和线卷的挂载点
COPY christina-pod-boot /usr/local/bin/christina-pod-boot
COPY bin/no-credentials /usr/local/bin/no-credentials
COPY bin/ws /usr/local/bin/ws
RUN set -eux; \
    chmod 0755 /usr/local/bin/christina-pod-boot /usr/local/bin/no-credentials /usr/local/bin/ws; \
    for name in kubectl aws docker; do ln -s no-credentials "/usr/local/bin/$name"; done; \
    install -d -o 1001 -g 1001 -m 0755 /opt/christina/remote-claude-code /opt/christina/.claude \
        /opt/christina/workspace /etc/christina /var/lib/christina/line /run/christina; \
    ln -s remote-claude-code /opt/christina/current; \
    test -x /usr/bin/tini

ENV BROWSE_CHROME=/opt/christina/chrome \
    PATH=/home/christina/.local/bin:$PATH

RUN { echo; echo "# christina-exec-job: pod runtime"; \
      tini --version; \
      echo "agent-browser $(agent-browser --version)"; \
      /opt/christina/chrome --version; \
      echo "venv requirements-staging.lock sha256 $(sha256sum /opt/christina/venv/requirements-staging.lock | cut -c1-64)"; \
      /opt/christina/venv/bin/pip freeze; \
    } >> /opt/runner/versions.txt

USER 1001
WORKDIR /home/christina
