# 使用官方Python镜像作为构建环境
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖和中文字体
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    fonts-wqy-microhei \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件
COPY requirements.txt .

# 升级pip并安装依赖
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 复制应用程序代码
COPY src/ /app/src/

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 创建日志目录
RUN mkdir -p /app/logs

# 设置运行用户
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

# 暴露Gradio服务的端口
EXPOSE 7860

# 设置健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:7860/ || exit 1

# 启动应用
CMD ["python", "/app/src/main.py"]
