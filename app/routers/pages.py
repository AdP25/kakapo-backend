"""Optional static HTML demos served from the backend directory."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from app.core.config import BACKEND_DIR

router = APIRouter(tags=["pages"])


@router.get("/dashboard")
async def dashboard():
    file_path = BACKEND_DIR / "dashboard.html"
    if file_path.exists():
        return FileResponse(str(file_path))
    return JSONResponse({"error": "dashboard.html not found"}, status_code=404)


@router.get("/demo")
async def demo():
    file_path = BACKEND_DIR / "demo.html"
    if file_path.exists():
        return FileResponse(str(file_path))
    return JSONResponse({"error": "demo.html not found"}, status_code=404)
