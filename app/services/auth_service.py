from __future__ import annotations

import time
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET
from app.db.database import get_db
from app.schemas.auth import UserPublic

_bearer = HTTPBearer(auto_error=False)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, email: str) -> str:
    now = time.time()
    exp = now + JWT_EXPIRE_MINUTES * 60
    payload = {"sub": str(user_id), "email": email, "iat": now, "exp": exp}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


def register_user(email: str, password: str) -> UserPublic:
    email_n = _normalize_email(email)
    db = get_db()
    row = db.execute("SELECT id FROM users WHERE email = ?", (email_n,)).fetchone()
    if row:
        raise HTTPException(status_code=409, detail="Email already registered")

    pw_hash = hash_password(password)
    created_at = time.time()
    cur = db.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email_n, pw_hash, created_at),
    )
    db.commit()
    user_id = int(cur.lastrowid)
    return UserPublic(id=user_id, email=email_n, created_at=created_at)


def authenticate_user(email: str, password: str) -> UserPublic:
    email_n = _normalize_email(email)
    db = get_db()
    row = db.execute(
        "SELECT id, email, password_hash, created_at FROM users WHERE email = ?",
        (email_n,),
    ).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return UserPublic(id=row["id"], email=row["email"], created_at=row["created_at"])


def get_user_by_id(user_id: int) -> Optional[UserPublic]:
    row = get_db().execute(
        "SELECT id, email, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    return UserPublic(id=row["id"], email=row["email"], created_at=row["created_at"])


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> UserPublic:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
