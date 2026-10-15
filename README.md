# christina-exec-image

Christina 集群作业的公开工具镜像。她把不需要来回交互、要跑几分钟以上、吃 CPU 或内存的批处理活（转写、音视频处理、数据分析、批量渲染等），交到一个干净容器里跑；这个镜像就是那个容器的运行环境。

```
ghcr.io/flowgpt/christina-exec-image:<构建日期>-<提交号>
```

## 里面有什么

- Python 3.12：数据处理、科学计算、音视频（whisper、faster-whisper、demucs 等）、视觉、机器学习库，全部是 CPU 版。
- Node 22，以及 pnpm、typescript、tsx。
- ffmpeg、imagemagick、poppler-utils、git、curl、jq。
- Playwright 和 Chromium（用于批量截图和渲染，不做交互）。
- 中日韩字体和 emoji 字体。

每次构建实际装到的版本，写在镜像里的 `/opt/runner/versions.txt`。

## 里面没有什么

这是公开镜像，只装公开的工具和库：

- 不含任何代码、数据、配置或凭据。
- 不含任何内部域名或地址。
- Dockerfile 除了从官方 node 镜像取 node 以外，不 COPY、不 ADD 任何东西。

## 怎么构建和发布

`.github/workflows/build.yml`：

- 只有合进 main 的提交会构建、发布。
- 构建完先做冒烟测试：常用库逐个 import，再实际跑几样（音频解码、Chromium 启动），有一项失败就不推。
- 构建前后各做一道 trivy 密钥扫描：先扫本仓库的文件，再扫构建出的整个镜像。任何一条命中，流水线就失败，镜像不会推出去。
- 标签是「构建日期-提交号」，没有 `latest`，用的人自己钉版本。
