# syntax=docker/dockerfile:1
# Hugging Face Spaces (Docker SDK) is the default host. Port 7860 is the
# image default; docker-entrypoint.sh honours PORT when a backup host sets it.

FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RASTA_ENV=production \
    RASTA_ALLOWED_HOSTS=localhost,127.0.0.1,*.hf.space \
    CORS_ALLOW_ORIGINS= \
    RASTA_TRUST_PROXY_HEADERS=true \
    RASTA_STATIC_DIR=/app/frontend/dist \
    PORT=7860
WORKDIR /app
COPY gnani_client /opt/src/gnani_client
COPY backend/pyproject.toml /opt/src/backend/pyproject.toml
COPY backend/rasta /opt/src/backend/rasta
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir /opt/src/gnani_client /opt/src/backend \
    && rm -rf /opt/src /root/.cache/pip
COPY --from=frontend /src/frontend/dist /app/frontend/dist
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod 755 /app/docker-entrypoint.sh \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin rasta \
    && mkdir -p /app/data \
    && chown -R rasta:rasta /app
USER rasta
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; p=os.environ.get('PORT','7860'); urllib.request.urlopen(f'http://127.0.0.1:{p}/api/ready', timeout=4)"
ENTRYPOINT ["/app/docker-entrypoint.sh"]
