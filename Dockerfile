# syntax=docker/dockerfile:1
# Kakapo backend — FastAPI + uvicorn (MVP container for ECS / App Runner / EC2)
#
# Repo layout: app/ at repository root (see chore/init_setup). CPU torch first to avoid
# CUDA nvidia-* wheels in slim images. BuildKit: DOCKER_BUILDKIT=1 docker build ...
FROM python:3.11-slim-bookworm

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt /srv/requirements-docker.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r /srv/requirements-docker.txt \
    && pip install "sentence-transformers>=2.6,<4" \
    && pip install "bcrypt>=4.1,<5" "PyJWT>=2.8,<3" "email-validator>=2.1,<3"

COPY app /srv/app
COPY proxy.py seed_cache.py /srv/

ENV PYTHONPATH=/srv

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
