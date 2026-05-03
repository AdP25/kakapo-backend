# Kakapo Backend

FastAPI-based LLM proxy with:

- exact cache (SQLite)
- semantic cache (FAISS + sentence-transformers embeddings)
- request/cost analytics endpoints
- JWT auth (`/auth/register`, `/auth/login`, `/auth/me`)

## Repository layout

```text
kakapo-backend/
├── app/                 # Application package (routes, services, db)
│   ├── main.py
│   ├── routers/
│   ├── services/
│   └── ...
├── proxy.py             # CLI entrypoint → uvicorn
├── seed_cache.py        # Optional seed script (stop server first)
├── requirements.txt
├── tests/
├── .env.example
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

- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `POST /v1/chat/completions`
- `GET /api/stats`
- `GET` / `DELETE /api/semantic-cache`

Open **`/docs`** for interactive Swagger UI.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```
