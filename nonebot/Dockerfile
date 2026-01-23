FROM python:3.10-slim

WORKDIR /app
ENV TZ=Asia/Shanghai

# 使用清华源加速
# RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources || true
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libnss3 curl iputils-ping git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "nonebot2[fastapi]" \
    "nb-cli" \
    "nonebot-adapter-onebot" \
    "httpx" \
    "nonebot-plugin-apscheduler" \
    "zhdate" \
    "websocket-client" \
    "nonebot-plugin-memes>=0.5.0" \
    "meme-generator>=0.2.2" \
    "aiosqlite"

# 👇 新增这一行：把配置文件复制进去
COPY pyproject.toml .

# 复制 bot 和插件文件
COPY bot.py .

CMD ["python", "bot.py"]
