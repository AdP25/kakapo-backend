# Kakapo Backend

FastAPI-based LLM proxy with:
- exact cache (SQLite)
- semantic cache (FAISS + sentence-transformers embeddings)
- request/cost analytics endpoints

## Repository Layout

```text
kakapo-backend/
├── .github/workflows/deploy-aws-ecr.yml   # GitHub → Amazon ECR (optional ECS roll)
├── deployment/examples/spa-s3-cloudfront.workflow.yml  # copy to frontend repo
├── Dockerfile
├── src/
│   └── backend/
│       ├── proxy.py            # CLI entry (uvicorn)
│       ├── seed_cache.py       # Seed script for cache + demo history
│       ├── requirements.txt    # Local / CI Python deps
│       └── requirements-docker.txt  # Docker: non-ML deps (torch + ST installed in image)
├── tests/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r src/backend/requirements.txt
```

3. Configure environment:

```bash
cp .env.example .env
```

4. Run the API:

```bash
python src/backend/proxy.py --host 0.0.0.0 --port 8000
```

5. Optional: seed demo cache/history (with server stopped):

```bash
python src/backend/seed_cache.py
```

## Environment Variables

See `.env.example` for the full list. The most important keys:
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `DEFAULT_MODEL`
- `MOCK_MODE`
- `SEMANTIC_THRESHOLD`
- `SEMANTIC_TTL_SECONDS`
- `SEMANTIC_MAX_ENTRIES`

## API Endpoints

- `GET /health` - load balancer liveness (JSON `{"status":"ok"}`)
- `POST /v1/chat/completions` - proxy request with exact + semantic cache
- `GET /api/stats` - aggregate usage and savings
- `GET /api/semantic-cache` - inspect semantic cache entries
- `DELETE /api/semantic-cache` - clear semantic cache

## Deploy (GitHub → AWS, MVP)

**Backend (this repo):** push to `main` runs `.github/workflows/deploy-aws-ecr.yml`, which builds the `Dockerfile` and pushes `:latest` and `:$GITHUB_SHA` to ECR.

1. In AWS, create an **ECR** repository (e.g. `kakapo-backend`).
2. Configure **OIDC** for GitHub Actions and an IAM role that can push to that repository (and optionally `ecs:UpdateService` for the deploy step).
3. In the GitHub repo **Settings → Secrets and variables → Actions**:
   - Secret: `AWS_ROLE_ARN` (assume-role ARN for OIDC).
   - Variables: `AWS_REGION`, `ECR_REPOSITORY` (override defaults in the workflow if you like).
   - Optional: `ENABLE_ECS_DEPLOY` = `true`, plus `ECS_CLUSTER` and `ECS_SERVICE`, to force a new ECS deployment after each push.
4. Run the API on **ECS Fargate**, **App Runner**, or **EC2** from that image. Inject env at runtime (see `.env.example`); do not bake secrets into the image.

**Frontend (other repo):** copy `deployment/examples/spa-s3-cloudfront.workflow.yml` to `.github/workflows/deploy-aws-spa.yml`, adjust install/build paths, and set variables `S3_BUCKET`, `CLOUDFRONT_DISTRIBUTION_ID` plus the same OIDC pattern (`AWS_ROLE_ARN`).

```bash
DOCKER_BUILDKIT=1 docker build -t kakapo-backend:local .
docker run --rm -p 8000:8000 --env-file .env kakapo-backend:local
```

First image build can take a long time (PyTorch + sentence-transformers). Later rebuilds are faster thanks to the pip cache mount.

If the build fails with **read-only file system** or errors under `nvidia/cudnn`, Docker is probably pulling **CUDA** PyTorch wheels. The `Dockerfile` installs **CPU-only** torch first, then `requirements-docker.txt`, then `sentence-transformers` to avoid that. Prune and retry: `docker builder prune -f`, then `DOCKER_BUILDKIT=1 docker build --no-cache -t kakapo-backend:local .`

## Development

Install dev tools:

```bash
pip install -e ".[dev]"
```

Run checks:

```bash
ruff check .
pytest
```
