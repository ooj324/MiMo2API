"""模型发现与发现路由 — MiMo2API"""

import asyncio
import httpx
from typing import Optional
from fastapi import APIRouter, HTTPException, Header

from .config import config_manager
from .routes_chat import validate_api_key

router = APIRouter()

# ─── 常量 ─────────────────────────────────────────────────────

MODELS_CONFIG_URL = "https://aistudio.xiaomimimo.com/open-apis/bot/config"

# ─── 模型上下文参数 ───────────────────────────────────────────
# 官方数据：https://platform.xiaomimimo.com/static/docs/pricing.md

def _model_context(model_id: str) -> dict:
    """返回 (context_length, max_output_tokens) 或 (默认, 默认)。"""
    m = model_id.lower()
    # Pro / v2.5 系列 — 1M 上下文
    if any(prefix in m for prefix in ("v2.5-pro", "v2-pro", "v2.5")):
        return {"context_length": 1048576, "max_output_tokens": 131072}
    # Flash — 256K 上下文, 64K 输出
    if "v2-flash" in m:
        return {"context_length": 262144, "max_output_tokens": 65536}
    # Omni — 256K 上下文
    if "v2-omni" in m:
        return {"context_length": 262144, "max_output_tokens": 131072}
    # 未知模型 → 不返回上下文信息
    return None

_models_cache = None
_models_lock = asyncio.Lock()


# ─── 动态模型发现 ─────────────────────────────────────────────

async def _do_discover() -> list:
    global _models_cache
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(MODELS_CONFIG_URL, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                print(f"[模型发现] config端点返回 {r.status_code}")
                return []
            data = r.json()
            model_list = data.get("data", {}).get("modelConfigList", [])
            models = [m["model"] for m in model_list if "model" in m]
    except Exception as e:
        print(f"[模型发现] 请求失败: {e}")
        return []

    async with _models_lock:
        _models_cache = models
    print(f"[模型发现] 找到 {len(models)} 个可用模型: {models}")
    return models


async def discover_models() -> list:
    if config_manager.config.models:
        return config_manager.config.models
    return await _do_discover()


def get_models_list() -> list:
    if config_manager.config.models:
        return config_manager.config.models
    if _models_cache is not None:
        return _models_cache
    return []


async def _background_refresh():
    try:
        await _do_discover()
    except Exception as e:
        print(f"[模型发现] 后台刷新失败: {e}")


@router.get("/v1/models")
async def list_models(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})
    asyncio.create_task(_background_refresh())
    models = get_models_list()
    ctx_items = [(m, _model_context(m)) for m in models]
    return {
        "object": "list",
        "data": [
            {
                "id": m, "object": "model", "created": 1681940951, "owned_by": "xiaomi",
                "context_length": ctx["context_length"],
                "context_window": ctx["context_length"],
                "max_input_tokens": ctx["context_length"],
                "max_output_tokens": ctx["max_output_tokens"],
            }
            for m, ctx in ctx_items if ctx is not None
        ]
    }


@router.post("/v1/models/refresh")
async def refresh_models(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})
    models = await discover_models()
    ctx_items = [(m, _model_context(m)) for m in models]
    return {
        "object": "list",
        "data": [
            {
                "id": m, "object": "model", "created": 1681940951, "owned_by": "xiaomi",
                "context_length": ctx["context_length"],
                "context_window": ctx["context_length"],
                "max_input_tokens": ctx["context_length"],
                "max_output_tokens": ctx["max_output_tokens"],
            }
            for m, ctx in ctx_items if ctx is not None
        ]
    }


@router.get("/v1/models/{model_id}")
async def get_model(
    model_id: str,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})
    models = get_models_list()
    if model_id in models:
        ctx = _model_context(model_id)
        base = {
            "id": model_id, "object": "model", "created": 1681940951, "owned_by": "xiaomi",
        }
        if ctx:
            base.update({
                "context_length": ctx["context_length"],
                "context_window": ctx["context_length"],
                "max_input_tokens": ctx["context_length"],
                "max_output_tokens": ctx["max_output_tokens"],
            })
        return base
    raise HTTPException(status_code=404, detail={"error": {"message": f"Model {model_id} not found"}})
