FROM python:3.10-slim

WORKDIR /app
ENV TZ=Asia/Shanghai

# 使用清华源加速
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources || true
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libnss3 curl iputils-ping git \
    && rm -rf /var/lib/apt/lists/*

# 安装核心依赖
RUN pip install --no-cache-dir nonebot2[fastapi] \
    nonebot-adapter-onebot \
    httpx \
    nonebot-plugin-apscheduler \
    zhdate \
    websocket-client \
    nonebot-plugin-memes

# 复制 bot 和插件文件
COPY bot.py .
COPY nonebot/plugins ./nonebot/plugins
COPY nonebot_data ./nonebot_data

CMD ["python", "bot.py"]
