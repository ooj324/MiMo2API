"""管理页面路由 — MiMo2API"""

from pathlib import Path
from fastapi import APIRouter, Depends
from starlette.responses import HTMLResponse
from .auth import verify_admin

router = APIRouter()


@router.get("/admin")
@router.get("/")
async def admin_page(username: str = Depends(verify_admin)):
    admin_html = (Path(__file__).parent.parent / "web" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(admin_html)
