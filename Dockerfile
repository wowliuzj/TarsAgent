FROM python:3.10-slim

WORKDIR /app

# 安装必要的系统依赖 (如 git, curl 等，Agent 可能会用到)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 默认命令 (可以被 docker-compose run 覆盖)
CMD ["python", "app/main.py"]
