# christina-exec-image：Christina 集群作业用的公开工具镜像（用途见 README.md）。
#
# 只装公开的工具和库：除了官方 node 镜像里的 node，不 COPY、不 ADD 任何东西，
# 不含代码、数据、配置或凭据。不装 docker、云厂商 CLI、GPU 版本的任何东西。
FROM node:22-bookworm-slim AS node

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PATH=/work/.home/.local/bin:$PATH

# 系统工具：音视频、PDF、图片处理，以及出图要用的中日韩字体和 emoji 字体
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg imagemagick poppler-utils git curl ca-certificates jq bc xz-utils unzip \
        build-essential pkg-config libsndfile1 libgl1 libglib2.0-0 \
        fonts-noto-cjk fonts-noto-color-emoji fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Node 22 取自官方镜像
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g pnpm typescript tsx \
    && npm cache clean --force

# torch 三件套用 CPU 版
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchaudio torchvision

# 数据与通用、音视频与视觉、浏览器自动化。不钉版本：镜像本身就是钉，
# 每次构建的实际版本写进镜像里的 /opt/runner/versions.txt。
# rembg 要 opencv-python-headless、ultralytics 要 opencv-python，两个都提供 cv2：装完只留 headless。
RUN pip install \
        numpy pandas scipy matplotlib pillow requests httpx openpyxl scikit-learn statsmodels \
        duckdb pyarrow sqlalchemy psycopg2-binary pymysql pyyaml beautifulsoup4 lxml pymupdf pypdf \
        fonttools tiktoken langdetect websocket-client fastapi uvicorn pytest uv tqdm \
        openai-whisper faster-whisper demucs librosa soundfile silero-vad onnxruntime rembg spandrel \
        ultralytics transformers yt-dlp cairosvg segno \
        playwright \
    && pip uninstall -y opencv-python opencv-python-headless \
    && pip install --no-deps opencv-python-headless

RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/runner \
    && { python3 --version; node --version; ffmpeg -version | head -1; pip freeze; } > /opt/runner/versions.txt \
    && useradd -m -u 1000 runner

USER 1000
WORKDIR /work/run
