# 工单镜像的 pod 运行环境冒烟：以镜像默认用户（uid 1001，和 pod 规格里一样）核 CLI、浏览器、三个壳和 venv。
# 用法：docker run --rm -i --shm-size=1g -e WANT_CLAUDE=<版本> <工单镜像> bash -s < smoke/pod.sh
# boot 的几种情形在 smoke/pod_boot.py 里另跑。任何一步失败都以非 0 退出。
set -euo pipefail

test "$(id -u)" = 1001 || { echo "运行用户应为 uid 1001，实际是 $(id -u)"; exit 1; }
test "$HOME" = /home/christina || { echo "HOME 应为 /home/christina，实际是 $HOME"; exit 1; }
if command -v sudo >/dev/null; then echo "镜像里不应有 sudo"; exit 1; fi
W=$(mktemp -d)

# Claude Code CLI：PATH 上那份和 venv 里 SDK 随包那份（会话真正起的是它）都要是钉的版本。
want=${WANT_CLAUDE:?WANT_CLAUDE 没给}
got=$(claude --version)
bundled=$(/opt/christina/venv/lib/python3.12/site-packages/claude_agent_sdk/_bundled/claude --version)
echo "want $want / PATH: $got / SDK bundled: $bundled"
[ "${got%% *}" = "$want" ] && [ "${bundled%% *}" = "$want" ]

# venv：依赖清单副本在、只读；几样会话离不开的包 import 得了。
test -r /opt/christina/venv/requirements-staging.lock
test ! -w /opt/christina/venv/requirements-staging.lock
/opt/christina/venv/bin/python -c "import aiohttp, claude_agent_sdk, lark_oapi, playwright, yaml; print('venv ok')"

# agent-browser + chromium-1243，--no-sandbox（tools/browse 的起法），以 uid 1001 打开一页、点一下。
printf '<html><body><button onclick="this.textContent=%s">pod-smoke</button></body></html>' "'clicked'" > "$W/page.html"
set -- --executable-path "$BROWSE_CHROME" --args --no-sandbox
timeout 120 agent-browser "$@" open "file://$W/page.html" >/dev/null
timeout 60 agent-browser "$@" snapshot > "$W/snap.txt"
grep -q pod-smoke "$W/snap.txt" || { echo "agent-browser 没读到页面"; cat "$W/snap.txt"; exit 1; }
ref=$(grep -o "ref=e[0-9]*" "$W/snap.txt" | head -1 | cut -d= -f2)
timeout 60 agent-browser "$@" click "@$ref" >/dev/null
timeout 60 agent-browser "$@" snapshot | grep -q clicked || { echo "agent-browser 点击没生效"; exit 1; }
timeout 60 agent-browser "$@" close >/dev/null || true
echo "agent-browser ok ($(agent-browser --version), $("$BROWSE_CHROME" --version))"

# venv 里 playwright 1.58 自己的 chromium（headless shell，revision 1208）。
/opt/christina/venv/bin/python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    page = b.new_page()
    page.set_content("<p id=x>pw-ok</p>")
    assert page.inner_text("#x") == "pw-ok"
    b.close()
print("venv playwright chromium ok")
PY

# kubectl / aws / docker：一句话，退出 1，说清楚没有凭据、怎么办。
for name in kubectl aws docker; do
  if "$name" version > /dev/null 2> "$W/err"; then echo "$name 不该成功"; exit 1; fi
  grep -q "交回前台" "$W/err" || { echo "$name 的提示不对："; cat "$W/err"; exit 1; }
  test "$(wc -l < "$W/err")" -le 1 || { echo "$name 的提示不止一句"; exit 1; }
done

# ws：代码还没解包时说「还没就绪」，退出非 0（解包以后转给代码的那一路在 smoke/pod_boot.py 里核）。
if ws ls > /dev/null 2> "$W/err"; then echo "代码不在时 ws 不该成功"; exit 1; fi
grep -q "代码还没就绪" "$W/err" || { echo "ws 的提示不对："; cat "$W/err"; exit 1; }

# 启动链要用的：tini、boot 脚本、给 uid 1001 的几处目录。
tini --version
test -x /usr/local/bin/christina-pod-boot
for d in /opt/christina/remote-claude-code /opt/christina/.claude /etc/christina /var/lib/christina/line /run/christina \
         /opt/christina/workspace; do
  test -w "$d" || { echo "$d 对 uid 1001 不可写"; exit 1; }
done
test "$(readlink /opt/christina/current)" = remote-claude-code
test ! -w /opt/christina || { echo "/opt/christina 本身不该归 uid 1001"; exit 1; }

rm -rf "$W"
echo "pod smoke ok"
