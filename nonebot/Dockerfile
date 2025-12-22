# 使用官方轻量级 Python 镜像 (完美支持 ARM64)
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置时区
ENV TZ=Asia/Shanghai

# 1. 安装系统级依赖
# ffmpeg: 用于语音转码 (必装)
# libnss3/curl/git: 常用工具
# 替换为国内源加速构建
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources || true
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libnss3 \
    curl \
    iputils-ping \
    git \
    && rm -rf /var/lib/apt/lists/*

# 2. 安装 Python 核心依赖
# 安装 nonebot2, onebot适配器, httpx(用于API请求)
RUN pip install --no-cache-dir nonebot2[fastapi] nonebot-adapter-onebot httpx

# 3. 复制启动脚本
COPY bot.py .

# 启动命令
CMD ["python", "bot.py"]
