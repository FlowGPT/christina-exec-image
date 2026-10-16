# 通用镜像的冒烟测试：常用库逐个 import，再实际跑几样。工单镜像也跑这一份，确认加装的东西没弄坏原有的。
# 用法（在 /tmp 这类可写目录里跑）：docker run --rm -i -w /tmp <镜像> python3 - < smoke/exec.py
import importlib, subprocess, sys
mods = ["numpy", "pandas", "scipy", "matplotlib", "PIL", "requests", "httpx", "openpyxl", "sklearn",
        "statsmodels", "duckdb", "pyarrow", "sqlalchemy", "psycopg2", "pymysql", "yaml", "bs4", "lxml",
        "pymupdf", "pypdf", "fontTools", "tiktoken", "langdetect", "websocket", "fastapi", "uvicorn",
        "pytest", "tqdm", "torch", "torchaudio", "torchvision", "torchcodec", "whisper", "faster_whisper",
        "demucs", "librosa", "soundfile", "silero_vad", "onnxruntime", "rembg", "spandrel", "ultralytics",
        "transformers", "yt_dlp", "cairosvg", "segno", "cv2", "av", "playwright", "ctranslate2", "numba"]
bad = []
for m in mods:
    try:
        importlib.import_module(m)
    except BaseException as e:
        bad.append(f"import {m}: {type(e).__name__}: {e}")
subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-y", "t.wav"], check=True)
checks = {
    "faster_whisper.decode_audio": lambda: __import__("faster_whisper.audio", fromlist=["x"]).decode_audio("t.wav"),
    "torchaudio.load": lambda: __import__("torchaudio").load("t.wav"),
    "librosa.load": lambda: __import__("librosa").load("t.wav"),
    "playwright chromium": lambda: subprocess.run(["python3", "-c", "from playwright.sync_api import sync_playwright as p\nwith p() as x: b=x.chromium.launch(); b.close()"], check=True),
}
for name, fn in checks.items():
    try:
        fn()
    except BaseException as e:
        bad.append(f"{name}: {type(e).__name__}: {e}")
print("\n".join(bad) or "smoke ok")
sys.exit(1 if bad else 0)
