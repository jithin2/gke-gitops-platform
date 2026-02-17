# Build stage — install dependencies (when requirements.txt has real packages)
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN mkdir -p /install && pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage — minimal image with only what the app needs
FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY main.py .

USER appuser

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8081/healthz')" || exit 1

CMD ["python", "main.py"]
