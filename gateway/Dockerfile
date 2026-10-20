# Optional container deployment (native uv deployment is the primary path).
# Multi-arch: builds identically on ARM64 (Jetson) and AMD64 (AI Max).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /srv/aura
COPY pyproject.toml ./
COPY app ./app
RUN uv venv /srv/aura/.venv \
    && uv pip install --python /srv/aura/.venv -r pyproject.toml \
    && useradd -r -m aura -d /srv/aura \
    && chown -R aura:aura /srv/aura

EXPOSE 8765
USER aura
ENV GATEWAY_DATA_DIR=/srv/aura/data
VOLUME ["/srv/aura/data"]
ENTRYPOINT ["/srv/aura/.venv/bin/python", "-m", "app.main"]
