FROM python:3.10-slim

WORKDIR /app
ENV TZ=Asia/Shanghai

# 使用清华源加速
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources || true
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libnss3 curl iputils-ping git \
    && rm -rf /var/lib/apt/lists/*

# 安装核心依赖
# zhdate: 农历支持
# nonebot-plugin-apscheduler: 定时任务
# websocket-client: 语音支持
RUN pip install --no-cache-dir nonebot2[fastapi] nonebot-adapter-onebot httpx nonebot-plugin-apscheduler zhdate websocket-client

COPY bot.py .

CMD ["python", "bot.py"]