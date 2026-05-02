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

SEMANTIC_THRESHOLD = float(os.getenv("SEMANTIC_THRESHOLD", "0.90"))
SEMANTIC_TTL_SECONDS = int(os.getenv("SEMANTIC_TTL_SECONDS", str(60 * 60 * 24)))
SEMANTIC_MAX_ENTRIES = int(os.getenv("SEMANTIC_MAX_ENTRIES", "10000"))

GEMINI_PRICE = {"in": 0.0, "out": 0.0}
GPT4O_PRICE = {"in": 2.50, "out": 10.00}

BACKEND_DIR = Path(__file__).resolve().parents[2]
DB_PATH = str(BACKEND_DIR / "proxy.db")
