from __future__ import annotations

import hashlib
import secrets
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import ADMIN_API_KEY
from app.db.database import get_db

_bearer = HTTPBearer()


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_key(name: str) -> str:
    raw = "kk_" + secrets.token_hex(32)
    db = get_db()
    db.execute(
        "INSERT INTO api_keys (key_hash, name, created_at) VALUES (?, ?, ?)",
        (_hash_key(raw), name, time.time()),
    )
    db.commit()
    return raw


def list_keys() -> list[dict]:
    rows = get_db().execute(
        "SELECT id, name, created_at, last_used_at, is_active FROM api_keys ORDER BY created_at DESC"
    ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "created_at": r["created_at"],
            "last_used_at": r["last_used_at"],
            "is_active": bool(r["is_active"]),
        }
        for r in rows
    ]


def revoke_key(key_id: int) -> bool:
    db = get_db()
    changed = db.execute(
        "UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,)
    ).rowcount
    db.commit()
    return changed > 0


def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> int:
    key_hash = _hash_key(credentials.credentials)
    db = get_db()
    row = db.execute(
        "SELECT id FROM api_keys WHERE key_hash = ? AND is_active = 1", (key_hash,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    db.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (time.time(), row["id"]))
    db.commit()
    return row["id"]


def verify_admin_key(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> None:
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY is not configured")
    if not secrets.compare_digest(credentials.credentials, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid admin key")
