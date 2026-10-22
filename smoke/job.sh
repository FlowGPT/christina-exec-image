# 工单镜像的冒烟测试：以镜像默认用户（uid 1001 christina，和工单 pod 里一样）按 README 里的起法起 postgres 和 redis，再试预览工具。
# 用法：docker run --rm -i <工单镜像> bash -s < smoke/job.sh
# 任何一步失败都以非 0 退出。
set -euo pipefail

test "$(id -u)" = 1001 || { echo "运行用户应为 uid 1001，实际是 $(id -u)"; exit 1; }
if command -v sudo >/dev/null; then echo "镜像里不应有 sudo"; exit 1; fi

W=$(mktemp -d)

# PostgreSQL + pgvector：initdb 到可写目录，socket 也放那里，连 localhost:5432
D="$W/pg"
initdb -D "$D" -U postgres -A trust >/dev/null
pg_ctl -D "$D" -l "$D/server.log" -o "-k $D" -w start
got=$(psql -h localhost -U postgres -v ON_ERROR_STOP=1 -qtA <<'SQL'
CREATE EXTENSION vector;
CREATE TABLE items (id int PRIMARY KEY, embedding vector(3));
INSERT INTO items VALUES (1, '[1,2,3]'), (2, '[4,5,6]'), (3, '[1,1,1]');
CREATE INDEX ON items USING hnsw (embedding vector_l2_ops);
SET enable_seqscan = off;
SELECT id FROM items ORDER BY embedding <-> '[1,2,4]' LIMIT 1;
SQL
)
test "$got" = 1 || { echo "向量查询结果应为 1，实际是：$got"; exit 1; }
# 测试代码常用的连法：带密码的连接串（trust 下密码随便填）
python3 - <<'PY'
import psycopg2
with psycopg2.connect("postgresql://postgres:postgres@localhost:5432/postgres") as conn, conn.cursor() as cur:
    cur.execute("SELECT version(), (SELECT extversion FROM pg_extension WHERE extname = 'vector')")
    pg, vec = cur.fetchone()
    print(pg.split(" on ")[0], "| pgvector", vec)
PY

# redis：后台起在 127.0.0.1:6379，不落盘
R="$W/redis"
mkdir -p "$R"
redis-server --daemonize yes --dir "$R" --bind 127.0.0.1 --port 6379 --save '' --appendonly no \
    --pidfile "$R/redis.pid" --logfile "$R/redis.log"
for _ in $(seq 50); do [ "$(redis-cli ping 2>/dev/null)" = PONG ] && break; sleep 0.1; done
test "$(redis-cli ping)" = PONG || { echo "redis 没有回 PONG"; cat "$R/redis.log"; exit 1; }
redis-server --version

# 预览工具：版本，以及 caddy 能以普通用户在高端口起服务
caddy version
cloudflared --version
echo caddy-ok > "$W/index.html"
caddy file-server --listen 127.0.0.1:18080 --root "$W" >"$W/caddy.log" 2>&1 &
caddy_pid=$!
for _ in $(seq 50); do curl -fsS http://127.0.0.1:18080/index.html >/dev/null 2>&1 && break; sleep 0.1; done
test "$(curl -fsS http://127.0.0.1:18080/index.html)" = caddy-ok || { echo "caddy 没起来"; cat "$W/caddy.log"; exit 1; }

kill "$caddy_pid"
redis-cli shutdown nosave >/dev/null 2>&1 || true
pg_ctl -D "$D" -w stop >/dev/null
echo "job smoke ok"
