from __future__ import annotations

import os
from pathlib import Path

OPENAI_BASE_URL = os.getenv(
    "OPENAI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-flash-latest")
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"

GEMINI_PRICE = {"in": 0.0, "out": 0.0}
GPT4O_PRICE = {"in": 2.50, "out": 10.00}

BACKEND_DIR = Path(__file__).resolve().parents[2]
DB_PATH = str(BACKEND_DIR / "proxy.db")

# JWT (auth) — override JWT_SECRET in production
JWT_SECRET = (
    os.getenv("JWT_SECRET") or "dev-only-secret-min-32-chars-not-for-prod!!"
).strip()
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # default 7 days
