"""API路由门面 — MiMo2API

整合所有子路由模块并重导出外部依赖项。
"""

from fastapi import APIRouter

# 导入所有子路由
from .routes_models import router as models_router, _do_discover
from .routes_chat import (
    router as chat_router,
    validate_api_key,
    _strip_citations,
    _strip_tool_result_blocks,
    _strip_tool_name_prefix,
    _strip_mimo_prefix,
    _safe_flush
)
from .routes_admin import router as admin_router
from .routes_xiaomi import router as xiaomi_router
from .routes_mimo import router as mimo_router
from .routes_config import router as config_router
from .routes_responses import router as responses_router

# 声明主路由器
router = APIRouter()

# 包含所有子路由器
router.include_router(models_router)
router.include_router(chat_router)
router.include_router(admin_router)
router.include_router(xiaomi_router)
router.include_router(mimo_router)
router.include_router(config_router)
router.include_router(responses_router)

# 显式重导出供 main.py 和 anthropic_routes.py 等使用的依赖
__all__ = [
    "router",
    "_do_discover",
    "validate_api_key",
    "_strip_citations",
    "_strip_tool_result_blocks",
    "_strip_tool_name_prefix",
    "_strip_mimo_prefix",
    "_safe_flush"
]
