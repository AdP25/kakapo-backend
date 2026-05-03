# Kakapo Backend

FastAPI-based LLM proxy with:

- exact cache (SQLite)
- semantic cache (FAISS + sentence-transformers embeddings)
- request/cost analytics endpoints
- JWT auth (`/auth/register`, `/auth/login`, `/auth/me`)

## Repository layout

```text
kakapo-backend/
├── .github/workflows/deploy-aws-ecr.yml   # GitHub → Amazon ECR (optional ECS roll)
├── deployment/examples/spa-s3-cloudfront.workflow.yml  # copy to frontend repo
├── Dockerfile
├── app/                 # Application package (routes, services, db)
│   ├── main.py
│   ├── routers/
│   ├── services/
│   └── ...
├── proxy.py             # CLI entrypoint → uvicorn
├── seed_cache.py        # Optional seed script (stop server first)
├── requirements.txt     # Local / CI Python deps
├── requirements-docker.txt  # Docker: non-ML deps (torch + ST installed in image)
├── tests/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## Quick start

1. Create and activate a virtual environment (keep it **outside** git or rely on `.gitignore`).

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. Configure environment:

```bash
cp .env.example .env
```

3. Run the API **from the repository root**:

```bash
python proxy.py --host 0.0.0.0 --port 8000
```

4. Optional: seed demo cache/history (**stop the server first**):

```bash
python seed_cache.py
```

## Environment variables

See `.env.example`. Important keys include:

- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `DEFAULT_MODEL`, `MOCK_MODE`
- Semantic cache: `SEMANTIC_THRESHOLD`, `SEMANTIC_TTL_SECONDS`, `SEMANTIC_MAX_ENTRIES`
- Auth: `JWT_SECRET`, `JWT_EXPIRE_MINUTES`

## API overview

- `GET /health` — load balancer liveness (`{"status":"ok"}`)
- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `POST /v1/chat/completions`
- `GET /api/stats`
- `GET` / `DELETE /api/semantic-cache`

Open **`/docs`** for interactive Swagger UI.

## Deploy (GitHub → AWS, MVP)

**Backend (this repo):** push to `main` runs `.github/workflows/deploy-aws-ecr.yml`, which builds the `Dockerfile` and pushes `:latest` and `:$GITHUB_SHA` to ECR.

1. In AWS, create an **ECR** repository (or use your namespaced repo).
2. Configure **OIDC** for GitHub Actions and an IAM role that can push to that repository (and optionally `ecs:UpdateService` for the deploy step).
3. In the GitHub repo **Settings → Secrets and variables → Actions**:
   - Secret: `AWS_ROLE_ARN` (assume-role ARN for OIDC).
   - Variables: `AWS_REGION`, `ECR_REPOSITORY` (must match the ECR repo name, e.g. `kakapo/kakapo-backend`).
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

```bash
pip install -e ".[dev]"
ruff check .
pytest
```
