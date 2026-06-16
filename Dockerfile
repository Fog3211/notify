FROM python:3.12-slim

# 时区：日志与「北京时间」展示需要 tzdata
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖，利用层缓存
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# 去重库持久化目录（compose 里挂卷）
VOLUME ["/app/data"]

# 默认：常驻定时模式。也可在 compose/cron 里覆盖为 `python -m app run`
CMD ["python", "-m", "app", "schedule"]
