"""配置与工具路由 — MiMo2API"""

from fastapi import APIRouter, HTTPException, Request, Depends

from .auth import verify_admin
from .config import config_manager, MimoAccount
from .models import ParseCurlRequest, TestAccountRequest
from .utils import parse_curl
from .mimo_client import MimoClient
from .usage_store import get_usage as _get_usage, clear_usage as _clear_usage
from .session_store import get_expired_sessions as _get_expired_sessions, remove_session as _remove_session
from .routes_models import get_models_list

router = APIRouter()


@router.get("/api/config")
async def get_config(username: str = Depends(verify_admin)):
    return config_manager.get_config()


@router.post("/api/config")
async def update_config(request: Request, username: str = Depends(verify_admin)):
    try:
        new_config = await request.json()
        config_manager.update_config(new_config)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": "invalid"})


@router.post("/api/parse-curl")
async def parse_curl_command(request: ParseCurlRequest, username: str = Depends(verify_admin)):
    account = parse_curl(request.curl)
    if not account:
        raise HTTPException(status_code=400, detail={"error": "parse failed"})
    return account.to_dict()


@router.post("/api/test-account")
async def test_account_endpoint(request: TestAccountRequest, username: str = Depends(verify_admin)):
    try:
        account = MimoAccount(
            service_token=request.service_token,
            user_id=request.user_id,
            xiaomichatbot_ph=request.xiaomichatbot_ph
        )
        client = MimoClient(account)
        content, _, _ = await client.call_api("hi", False)
        return {"success": True, "response": content}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── 用量统计 API ─────────────────────────────────────────────

@router.get("/api/usage")
async def usage_stats(username: str = Depends(verify_admin)):
    """返回用量统计：按模型分组 + 全部汇总。"""
    return _get_usage()


@router.delete("/api/usage")
async def clear_usage(username: str = Depends(verify_admin)):
    """清空全部用量统计数据。"""
    _clear_usage()
    return {"ok": True}


@router.post("/api/cleanup")
async def manual_cleanup(username: str = Depends(verify_admin)):
    """手动触发会话清理（从远端获取全部会话并清空）。"""
    try:
        from .session_store import _store, _lock
        deleted = 0
        total_found = 0

        for a in config_manager.config.mimo_accounts:
            client = MimoClient(a)
            # 每次拉取最多 50 条最近的会话进行清理
            resp_data = await client.get_conversations(page_num=1, page_size=50)
            data_list = resp_data.get("dataList", [])
            
            if not data_list:
                continue

            conv_ids = [item.get("conversationId") for item in data_list if item.get("conversationId")]
            total_found += len(conv_ids)

            if conv_ids:
                if await client.delete_conversations(conv_ids):
                    deleted += len(conv_ids)
                    print(f"[Cleanup] Deleted {len(conv_ids)} remote sessions for account {a.user_id}")
                    # 同步清空本地内存中该账号的所有缓存会话
                    key = f"account_{a.user_id}"
                    with _lock:
                        if key in _store:
                            del _store[key]
                else:
                    print(f"[Cleanup] Failed to delete remote sessions for account {a.user_id}")

        if total_found == 0:
            return {"ok": True, "msg": "远端没有可以清理的会话", "deleted": 0}

        return {"ok": True, "msg": f"清理完成: 成功删除 {deleted}/{total_found} 个远端会话", "deleted": deleted}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


# ─── 模型列表（免鉴权，供管理页面使用） ───────────────────────

@router.get("/api/models")
async def admin_models():
    """返回可用模型列表（无鉴权，仅供管理页面动态加载）。"""
    return {"models": get_models_list()}
