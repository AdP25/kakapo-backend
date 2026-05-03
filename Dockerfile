# syntax=docker/dockerfile:1
# Kakapo backend — FastAPI + uvicorn (MVP container for ECS / App Runner / EC2)
#
# sentence-transformers depends on torch; install CPU wheels first (smaller/faster than
# default PyPI torch). BuildKit cache speeds rebuilds: DOCKER_BUILDKIT=1 docker build ...
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY src/backend/requirements-docker.txt /app/requirements-docker.txt

# Install torch from PyTorch CPU index only, then other deps, then sentence-transformers.
# A single `pip install -r requirements.txt` can resolve torch from PyPI and pull
# nvidia-* wheels → OSError read-only / failed layer commit on some Docker Desktop setups.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r /app/requirements-docker.txt \
    && pip install "sentence-transformers>=2.6,<4"

COPY src/backend /app
ENV PYTHONPATH=/app

EXPOSE 8000
# App Runner and some platforms inject PORT
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
