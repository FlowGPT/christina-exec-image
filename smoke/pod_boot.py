"""christina-pod-boot 的冒烟：起一个假的单面 API，喂几种回执，看 boot 的退出码和它做了什么。

用法（镜像里，uid 1001）：docker run --rm -i <工单镜像> python3 - < smoke/pod_boot.py
本机调试：python3 smoke/pod_boot.py --boot job/christina-pod-boot --root <空目录>（在那个根下造一个假 venv）

假的代码包里只有四样：依赖清单（镜像里那份的逐字副本）、一个打标记的 tools/plane_pod/pod_setup.py、一个打印
「ENTRY OK <版本>」后退出 0 的 src/plane_pod/entry.py、一个打印参数的 src/plane_pod/files.py（给 ws 用）。核的情形：
  - 代码包的 sha256 和头对不上 → 11，缓存里不留；
  - 依赖清单和镜像里的不一样 → 11，没有解包；
  - 令牌被拒（401）→ 10；
  - 正常：取码、缓存、解包、.venv 链到镜像 venv、跑安装步骤、exec 进 entry → 0；解包以后 ws 转给代码里的
    src.plane_pod.files（在一个自带 src/ 的目录里跑也不会被那里的 src 盖掉，相对路径按调用目录算）；
  - 命中缓存：钉了上一步那版，假服务全部回 500 → 照样 0，假服务一个请求都没收到；
  - 钉的版本生产不留了（404）→ 改取当前版本，0；
  - 跳转（302 到别的地址）→ 不跟、12，令牌没被带到跳转目标。
任何一条不对就以非 0 退出。只用标准库。
"""
import argparse
import hashlib
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--boot", default="/usr/local/bin/christina-pod-boot")
ap.add_argument("--root", default="")
args = ap.parse_args()

ROOT = Path(args.root or "/")
VENV = ROOT / "opt/christina/venv"
CODE = ROOT / "opt/christina/remote-claude-code"
CACHE = ROOT / "var/lib/christina/line/releases"
if args.root:  # 本机调试：在临时根下造一个假 venv 和那份依赖清单
    (VENV / "bin").mkdir(parents=True, exist_ok=True)
    py = VENV / "bin" / "python"
    if not py.exists():
        py.symlink_to(sys.executable)
    (VENV / "requirements-staging.lock").write_text("example==1.0\n")
LOCK = (VENV / "requirements-staging.lock").read_bytes()
TOKEN = "plt_" + "smoke" * 9
W = Path(tempfile.mkdtemp(prefix="pod-boot-smoke-"))
SETUP_MARK = W / "setup-ran"
failures = []


def release(tag: str) -> tuple[str, bytes]:
    sha = hashlib.sha1(tag.encode()).hexdigest()
    files = {
        "requirements-staging.lock": LOCK,
        "src/__init__.py": b"",
        "src/plane_pod/__init__.py": b"",
        "src/plane_pod/entry.py": b"import os\nprint('ENTRY OK', os.environ['CHRISTINA_RELEASE_SHA'], os.getcwd())\n",
        "tools/plane_pod/pod_setup.py": b"import os, pathlib\npathlib.Path(os.environ['SMOKE_SETUP_MARK']).write_text('ok')\n",
        "src/plane_pod/files.py": b"import os, sys\nprint('FILES OK', sys.argv[1:], os.getcwd())\n",
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o644
            tar.addfile(info, io.BytesIO(data))
    return sha, buf.getvalue()


class Plane(http.server.BaseHTTPRequestHandler):
    mode = "good"
    releases: dict = {}
    current = ""
    hits: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        Plane.hits.append({"path": self.path, "auth": self.headers.get("Authorization") == f"Bearer {TOKEN}"})
        mode = Plane.mode
        if mode == "down":
            return self._send(500, b"")
        if mode == "unauthorized":
            return self._send(401, b'{"error":"unauthorized"}')
        if mode == "redirect":
            return self._send(302, b"", {"Location": f"http://127.0.0.1:{SINK.server_port}/stolen"})
        if not self.path.startswith("/plane/v0/release"):
            return self._send(404, b"")
        sha = Plane.current
        if "sha=" in self.path:
            sha = self.path.split("sha=", 1)[1]
            if sha not in Plane.releases:
                return self._send(404, b'{"error":"release_not_retained"}')
        body = Plane.releases[sha]
        body_sha = hashlib.sha256(body).hexdigest()
        req_sha = hashlib.sha256(LOCK).hexdigest()
        if mode == "bad-sha256":
            body_sha = "0" * 64
        if mode == "bad-deps":
            req_sha = hashlib.sha256(b"something else\n").hexdigest()
        self._send(200, body, {"X-Release-Sha": sha, "X-Release-Sha256": body_sha, "X-Requirements-Sha256": req_sha,
                               "Content-Type": "application/gzip"})

    def _send(self, status, body, headers=None):
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Sink(http.server.BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        Sink.seen.append(self.headers.get("Authorization"))
        self.send_response(200)
        self.end_headers()


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Plane)
SINK = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Sink)
for srv in (server, SINK):
    threading.Thread(target=srv.serve_forever, daemon=True).start()
token_file = W / "token"
token_file.write_text(TOKEN)
os.chmod(token_file, 0o400)


def boot(mode: str, *, pinned: str = "") -> subprocess.CompletedProcess:
    Plane.mode, Plane.hits = mode, []
    if SETUP_MARK.exists():
        SETUP_MARK.unlink()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PLANE_", "CHRISTINA_"))}
    env.update(PLANE_URL=f"http://127.0.0.1:{server.server_port}", PLANE_TOKEN_FILE=str(token_file),
               SMOKE_SETUP_MARK=str(SETUP_MARK))
    if pinned:
        env["CHRISTINA_RELEASE_SHA"] = pinned
    if args.root:
        env["CHRISTINA_POD_BOOT_ROOT"] = str(ROOT)
    cmd = [args.boot] if not args.root else [sys.executable, args.boot]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)


def expect(label: str, ok: bool, proc=None) -> None:
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        failures.append(label)
        if proc is not None:
            print("     stdout:", proc.stdout.strip()[-500:])
            print("     stderr:", proc.stderr.strip()[-800:])


def reset_code() -> None:
    if not CODE.exists():
        return
    for child in CODE.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


v1, body1 = release("v1")
v2, body2 = release("v2")
Plane.releases = {v1: body1, v2: body2}

# 1. 代码包的 sha256 对不上
Plane.current = v1
reset_code()
p = boot("bad-sha256")
expect("sha256 不对 → 11", p.returncode == 11 and "sha256" in p.stderr, p)
expect("sha256 不对：缓存里不留", not (CACHE / f"{v1}.tar.gz").exists())
expect("sha256 不对：令牌只走 Authorization 头", all(h["auth"] for h in Plane.hits) and Plane.hits)

# 2. 依赖清单和镜像里的不一样
p = boot("bad-deps")
expect("依赖不符 → 11", p.returncode == 11 and "依赖清单" in p.stderr, p)
expect("依赖不符：没有解包", not (CODE / "src").exists())

# 3. 令牌被拒
p = boot("unauthorized")
expect("401 → 10", p.returncode == 10, p)

# 4. 正常
reset_code()
Plane.current = v2
p = boot("good")
expect("正常 → exec 进 entry，退出 0", p.returncode == 0 and f"ENTRY OK {v2} {CODE.resolve()}" in p.stdout, p)
expect("正常：跑了安装步骤", SETUP_MARK.exists())
expect("正常：.venv 链到镜像的 venv", os.readlink(CODE / ".venv") == str(VENV))
expect("正常：缓存里有包和记录", (CACHE / f"{v2}.tar.gz").exists()
       and json.loads((CACHE / f"{v2}.json").read_text())["sha"] == v2)
if not args.root:  # ws 写死了真路径，只在镜像里核
    shadow = W / "her-repo"
    (shadow / "src" / "plane_pod").mkdir(parents=True)
    (shadow / "src" / "__init__.py").write_text("")
    (shadow / "src" / "plane_pod" / "__init__.py").write_text("")
    (shadow / "src" / "plane_pod" / "files.py").write_text("print('SHADOWED')\n")
    p = subprocess.run(["ws", "get", "notes/a.md", "out.md"], cwd=shadow, capture_output=True, text=True, timeout=60)
    expect("解包以后 ws 转给代码里的 files，不被当前目录的 src 盖掉，cwd 不变",
           p.returncode == 0 and "FILES OK ['get', 'notes/a.md', 'out.md']" in p.stdout
           and str(shadow) in p.stdout and "SHADOWED" not in p.stdout, p)

# 5. 命中缓存：钉了 v2，假服务全部 500
reset_code()
p = boot("down", pinned=v2)
expect("命中缓存 → 0，不发请求", p.returncode == 0 and f"ENTRY OK {v2}" in p.stdout and not Plane.hits, p)
# 反例：缓存被改过一个字节 → 不认缓存、去取（服务挂着就取不到）
raw = (CACHE / f"{v2}.tar.gz").read_bytes()
(CACHE / f"{v2}.tar.gz").write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
p = boot("good", pinned=v2)
expect("缓存坏了 → 重新取，照样 0", p.returncode == 0 and len(Plane.hits) == 1, p)

# 6. 钉的版本不留了 → 改取当前
reset_code()
p = boot("good", pinned="f" * 40)
expect("钉的版本 404 → 改取当前，0", p.returncode == 0 and f"ENTRY OK {v2}" in p.stdout and len(Plane.hits) == 2, p)

# 7. 跳转：不跟，令牌不出门
p = boot("redirect")
expect("302 → 12，不跟跳转", p.returncode == 12 and not Sink.seen, p)

shutil.rmtree(W, ignore_errors=True)
if failures:
    print(f"pod boot smoke FAILED: {failures}")
    sys.exit(1)
print("pod boot smoke ok")
