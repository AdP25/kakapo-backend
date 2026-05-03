from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserPublic
from app.services.auth_service import authenticate_user, create_access_token, get_current_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=201)
def register(body: RegisterRequest):
    """Create a new account; password is stored as a bcrypt hash."""
    return register_user(body.email, body.password)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    """Return a JWT for subsequent `Authorization: Bearer <token>` requests."""
    user = authenticate_user(body.email, body.password)
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserPublic)
def me(user: UserPublic = Depends(get_current_user)):
    """Current user profile (requires Bearer token from /auth/login)."""
    return user
