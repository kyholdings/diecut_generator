# diecut_generator 独立镜像（阿里云生产部署用）
FROM python:3.11-slim

WORKDIR /app

# 依赖（含 gunicorn，容器内不用开发 server）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 生成文件输出目录（bind mount 持久化，见 docker-compose.yml）
RUN mkdir -p /app/outputs

EXPOSE 8899

# 单 worker + 2 线程（低频设计工具，内存友好，适配 1.6Gi 主机）
CMD ["gunicorn", "-w", "1", "--threads", "2", "-b", "0.0.0.0:8899", "app:app"]
