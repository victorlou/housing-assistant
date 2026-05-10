# syntax=docker/dockerfile:1
#
# Targets:
#   dev      — Python 3.11 + uv + dev tools; use with docker compose (repo bind-mount).
#   runtime  — minimal install: venv + agents/ + app/ + ingestion/ + config/ + data/sources.yaml.
#
# See docker/README.md

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH"

FROM base AS dev

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --group dev

WORKDIR /workspace
CMD ["bash"]

FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/housing-assistant

WORKDIR /opt/housing-assistant

COPY --from=base /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY agents/ ./agents/
COPY app/ ./app/
COPY ingestion/ ./ingestion/
COPY config/ ./config/
COPY data/sources.yaml ./data/sources.yaml

# Override when you add an app (Streamlit, uvicorn, etc.).
CMD ["python", "-c", "print('housing-assistant: set CMD to your entrypoint; see docker/README.md')"]
