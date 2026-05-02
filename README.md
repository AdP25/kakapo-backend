# Kakapo Backend

FastAPI-based LLM proxy with:
- exact cache (SQLite)
- semantic cache (FAISS + sentence-transformers embeddings)
- request/cost analytics endpoints

## Repository Layout

```text
kakapo-backend/
├── src/
│   └── backend/
│       ├── proxy.py            # Main FastAPI app
│       ├── seed_cache.py       # Seed script for cache + demo history
│       └── requirements.txt    # Runtime dependencies
├── tests/                      # Test suite (starter structure)
├── .env.example                # Environment variable template
├── .gitignore
├── pyproject.toml              # Project + tooling config
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

- `POST /v1/chat/completions` - proxy request with exact + semantic cache
- `GET /api/stats` - aggregate usage and savings
- `GET /api/semantic-cache` - inspect semantic cache entries
- `DELETE /api/semantic-cache` - clear semantic cache

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
