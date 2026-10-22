# christina-exec-image

Christina 集群作业的公开工具镜像。她把不需要来回交互、要跑几分钟以上、吃 CPU 或内存的批处理活（转写、音视频处理、数据分析、批量渲染等），交到一个干净容器里跑；这个镜像就是那个容器的运行环境。

本仓库发布两个镜像：

```
ghcr.io/flowgpt/christina-exec-image:<构建日期>-<提交号>   # 通用镜像
ghcr.io/flowgpt/christina-exec-job:<构建日期>-<提交号>     # 工单镜像 = 通用镜像 + 测试用数据库 + 预览工具，见下文
```

## 里面有什么

- Python 3.12：数据处理、科学计算、音视频（whisper、faster-whisper、demucs 等）、视觉、机器学习库，全部是 CPU 版。
- Node 22，以及 pnpm、typescript、tsx。
- Claude Code CLI，版本钉死在 Dockerfile 的 `ARG CLAUDE_CODE_VERSION`，和 Christina 生产用的 SDK 随包带的 CLI 同一版；自动更新已关。
- ffmpeg、imagemagick、poppler-utils、git、curl、jq。
- Playwright 和 Chromium（用于批量截图和渲染，不做交互）。
- 中日韩字体和 emoji 字体。

每次构建实际装到的版本，写在镜像里的 `/opt/runner/versions.txt`。

## 工单镜像

整张工单在集群的 pod 里跑时用这个镜像。pod 里没有 docker，测试要的数据库没法 `docker run`，所以预装好，在 pod 里当普通进程起。

比通用镜像多了：

- **PostgreSQL 18 和 pgvector**，取自 PostgreSQL 官方 apt 源（apt.postgresql.org，也是官方 postgres 镜像的来源）。bookworm 自带的只有 PostgreSQL 15，且没有 pgvector 包。18 是现在 `docker run postgres` 不带标签拿到的版本；为旧版写的 SQL 在 18 上照样能跑。
- **redis-server**（Debian bookworm 自带的 7.0，有安全更新）。不含 Redis 8 起官方镜像自带的 JSON、搜索等模块。
- **caddy** 和 **cloudflared**，预览用。取自各自官方 GitHub release，版本钉死，下载按钉死的校验和核对。

运行用户和通用镜像一样是 uid 1000，没有 sudo。数据库都由这个用户在任意可写目录里起，不需要 root。

### 在 pod 里起数据库

```sh
# PostgreSQL + pgvector：数据目录和 socket 都放在一个可写目录里，监听 localhost:5432
D=${TMPDIR:-/tmp}/pg
initdb -D "$D" -U postgres -A trust >/dev/null
pg_ctl -D "$D" -l "$D/server.log" -o "-k $D" -w start
psql -h localhost -U postgres -c 'CREATE EXTENSION IF NOT EXISTS vector'
# 连接串：postgresql://postgres:postgres@localhost:5432/postgres（trust 认证，密码随便填）
# 停：pg_ctl -D "$D" stop；要干净重来：停掉后 rm -rf "$D"

# redis：后台起，只听本机，不落盘
R=${TMPDIR:-/tmp}/redis; mkdir -p "$R"
redis-server --daemonize yes --dir "$R" --bind 127.0.0.1 --port 6379 --save '' --appendonly no \
    --pidfile "$R/redis.pid" --logfile "$R/redis.log"
redis-cli ping   # 刚起时可能要等零点几秒才回 PONG
# 停：redis-cli shutdown nosave
```

和 docker 的对应：

- `docker run -p 5432:5432 -e POSTGRES_PASSWORD=… postgres`、`pgvector/pgvector` 都换成上面这段，pgvector 已经装好，`CREATE EXTENSION vector` 即可。
- 要第二个实例，换一个目录和端口：`-o "-k $D2 -p 5433"`，连接串里的端口跟着改。
- 要建别的库：`createdb -h localhost -U postgres <库名>`。
- `-l` 不要省：不写日志文件时，postgres 的输出会挂在调用它的进程上，脚本或测试可能因此卡住不退出。
- `initdb`、`pg_ctl` 等在 `/usr/lib/postgresql/18/bin`，已经在 PATH 里。

### 预览工具

`caddy` 和 `cloudflared` 在 PATH 里，用法同各自官方文档。以普通用户运行，监听用 1024 以上的端口。

### 基础镜像和升级

工单镜像的 `FROM` 是某一版通用镜像，在 `job/Dockerfile` 的 `ARG BASE` 里按「标签@digest」钉死。两者的层完全相同，所以集群节点上已经有那版通用镜像时，只需要拉工单镜像多出来的那一截。通用镜像发了新版、工单镜像要跟上时，改这一行（标签和 digest 一起改）。

caddy、cloudflared 的版本和校验和也在 `job/Dockerfile` 里，升级时一起改。实际装到的版本写在 `/opt/runner/versions.txt` 末尾的 `# christina-exec-job` 一节。

## 里面没有什么

这是公开镜像，只装公开的工具和库：

- 不含任何代码、数据、配置或凭据。
- 不含任何内部域名或地址。
- 通用镜像的 Dockerfile 除了从官方 node 镜像取 node 以外，不 COPY、不 ADD 任何东西；工单镜像的 `job/Dockerfile` 不 COPY、不 ADD 任何东西，构建上下文里只有它自己。
- 仓库里只有这几样：两个 Dockerfile、构建流水线、本 README，以及 `smoke/` 下的两个冒烟脚本。冒烟脚本只在构建时跑，用来确认镜像真能用，不会进镜像；它们和其余文件一样过仓库那道密钥扫描。

## 怎么构建和发布

`.github/workflows/build.yml`：

- 合进 main 的提交：两个镜像都构建、冒烟、扫描，全过才发布。
- 手动跑（Actions 里的 workflow_dispatch，可以选分支）：`publish` 默认 `false`，只构建、冒烟、扫描，不推；选 `true` 才推。命令行：`gh workflow run build.yml --ref <分支> -f publish=false`。
- 冒烟测试，有一项失败就不推：
  - 通用镜像跑 `smoke/exec.py`：常用库逐个 import，再实际跑几样（音频解码、Chromium 启动）；再以默认用户跑 `claude --version`，必须等于 Dockerfile 里钉的版本。
  - 工单镜像先跑 `smoke/job.sh`：以 uid 1000 按上面的起法起 postgres，建 vector 扩展、建 HNSW 索引跑一句向量查询，再用带密码的连接串连一次；起 redis 并 PING；`caddy version`、`cloudflared --version`，并让 caddy 以普通用户在高端口起服务。然后再跑一遍 `smoke/exec.py`，确认加装的东西没弄坏原有的。
- 两道 trivy 密钥扫描：先扫本仓库的文件，再扫构建出的每个镜像。任何一条命中，流水线就失败，镜像不会推出去。
- 标签是「构建日期-提交号」，同一次构建两个镜像标签相同；没有 `latest`，用的人自己钉版本。
