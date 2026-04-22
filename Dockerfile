# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-compile /wheels/* \
    # 清理 Python 包内测试目录和字节码，避免运行时镜像携带构建/测试产物。
    && find /usr/local/lib/python3.12/site-packages -depth \
        \( -type d \( -name tests -o -name test -o -name __pycache__ \) \
        -o -type f \( -name "*.pyc" -o -name "*.pyo" \) \) -exec rm -rf '{}' + \
    && rm -rf /wheels /root/.cache/pip

COPY src/ /app/src/

RUN mkdir -p /app/logs \
    && groupadd -r appuser \
    && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=3).read()" || exit 1

CMD ["python", "/app/src/main.py"]
