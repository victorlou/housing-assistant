# Docker

Two ways to use Docker in this repo:

1. **Dev container (`target: dev`)** — full clone bind-mounted at `/workspace`; the image supplies Python 3.11, `uv`, and dev tools (`ruff`, `pytest`) from the repo-root `pyproject.toml`. Use this while Terraform, Databricks CLI, and bundles stay on the host unless you install them into the image later.
2. **Runtime image (`target: runtime`)** — only the Python virtualenv plus `agents/`, `app/`, `ingestion/`, `config/`, and `data/sources.yaml`. No `terraform/`, `docs/`, `pipelines/`, or `notebooks/`. Override `CMD` when you add a web or worker entrypoint.

## Prerequisites

- Docker Engine and Docker Compose v2 (`docker compose`).

## Local development (recommended)

From the repository root:

```bash
docker compose build dev
docker compose run --rm dev
```

You get a shell with `python`, `uv`, `ruff`, and `pytest` on `PATH`. The repo is mounted at `/workspace`; edit on the host and run commands inside the container.

Examples:

```bash
docker compose run --rm dev ruff check .
docker compose run --rm dev ruff format --check .
docker compose run --rm dev pytest agents app
```

## Build the minimal runtime image

```bash
docker build -f docker/Dockerfile --target runtime -t housing-assistant:runtime .
```

Run with a custom entrypoint (placeholder until the app exists):

```bash
docker run --rm housing-assistant:runtime python -c "import sys; print(sys.executable)"
```

When you add Streamlit or FastAPI, set `CMD` in `docker/Dockerfile` (runtime stage) or pass at `docker run` time, for example:

```bash
docker run --rm -p 8501:8501 housing-assistant:runtime streamlit run app/streamlit_app.py --server.address=0.0.0.0
```

## Windows notes

Run `docker compose` from the repo root in PowerShell. Bind mounts use the current directory; avoid Git Bash path rewriting for volume paths if you hit mount errors.

## CI

GitHub Actions builds the `runtime` target on pushes and pull requests when `docker/**`, `docker-compose.yml`, `pyproject.toml`, or `uv.lock` change.
