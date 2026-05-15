# 如果官方源无法访问，可以尝试使用 docker.m.daocloud.io/library/python:3.10-slim
FROM python:3.10-slim

WORKDIR /app

# 安装必要的系统依赖
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 默认命令
CMD ["python", "-m", "app.main"]
