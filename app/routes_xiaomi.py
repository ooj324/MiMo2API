"""小米 Passport 账号管理路由 — MiMo2API"""

from pathlib import Path
from datetime import datetime as _dt
import re as _re
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import FileResponse

from .auth import verify_admin
from .config import config_manager, XiaomiAccount
from .routes_mimo import exchange_passport_to_mimo, _save_mimo_session_direct

router = APIRouter()


@router.get("/api/xiaomi-accounts")
async def list_xiaomi_accounts(username: str = Depends(verify_admin)):
    """列出所有小米 Passport 账号"""
    accounts = []
    for acc in config_manager.config.xiaomi_accounts:
        accounts.append(acc.to_dict())
    return {"accounts": accounts}


@router.post("/api/xiaomi-account/add")
async def add_xiaomi_account(request: Request, username: str = Depends(verify_admin)):
    """添加小米 Passport 账号（passToken + userId）"""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "invalid json")

    pass_token = (data.get("passToken") or data.get("pass_token") or "").strip()
    user_id = (data.get("userId") or data.get("user_id") or "").strip()
    email = (data.get("email") or "").strip()
    device_id = (data.get("deviceId") or data.get("device_id") or "").strip()
    password = (data.get("password") or "").strip()

    if not pass_token or not user_id:
        return {"ok": False, "error": "缺少必填字段: passToken, userId"}

    # 检查是否已存在
    for acc in config_manager.config.xiaomi_accounts:
        if acc.user_id == user_id:
            # 更新现有账号
            acc.pass_token = pass_token
            if email:
                acc.email = email
            if device_id:
                acc.device_id = device_id
            if password:
                acc.password = password
            config_manager.save_xiaomi_accounts()
            return {"ok": True, "user_id": user_id, "message": "账号已更新"}

    now = _dt.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    new_acc = XiaomiAccount(
        user_id=user_id,
        pass_token=pass_token,
        email=email,
        password=password,
        device_id=device_id,
        created_at=now,
    )
    config_manager.config.xiaomi_accounts.append(new_acc)
    config_manager.save_xiaomi_accounts()
    return {"ok": True, "user_id": user_id, "message": "账号已添加"}


@router.delete("/api/xiaomi-accounts/{idx}")
async def delete_xiaomi_account(idx: int, username: str = Depends(verify_admin)):
    """删除小米 Passport 账号"""
    accounts = config_manager.config.xiaomi_accounts
    if idx < 0 or idx >= len(accounts):
        raise HTTPException(404, "account not found")
    removed = accounts.pop(idx)
    config_manager.save_xiaomi_accounts()
    return {"ok": True, "removed_user_id": removed.user_id}


@router.post("/api/xiaomi-accounts/{idx}/exchange")
async def exchange_xiaomi_account(idx: int, username: str = Depends(verify_admin)):
    """使用指定小米账号兑换 MiMo 权限"""
    accounts = config_manager.config.xiaomi_accounts
    if idx < 0 or idx >= len(accounts):
        raise HTTPException(404, "account not found")

    acc = accounts[idx]
    try:
        mimo_data = await exchange_passport_to_mimo(acc.pass_token, acc.user_id, acc.device_id or None)
        now = _dt.now().strftime("%m-%d %H:%M")

        # 保存 MiMo 会话
        _save_mimo_session_direct(
            user_id=mimo_data["userId"],
            service_token=mimo_data["serviceToken"],
            xiaomichatbot_ph=mimo_data.get("xiaomichatbot_ph", ""),
            email=acc.email,
            source_account=acc.user_id,
            now_str=now,
        )

        # 更新设备 ID
        if mimo_data.get("deviceId"):
            acc.device_id = mimo_data["deviceId"]
            config_manager.save_xiaomi_accounts()

        return {"ok": True, "user_id": mimo_data["userId"], "message": "兑换成功"}
    except Exception as e:
        return {"ok": False, "error": f"兑换失败: {str(e)}"}


@router.post("/api/xiaomi-accounts/exchange-all")
async def exchange_all_xiaomi_accounts(username: str = Depends(verify_admin)):
    """批量兑换所有小米账号"""
    accounts = config_manager.config.xiaomi_accounts
    if not accounts:
        return {"ok": True, "success": 0, "failed": 0, "message": "没有小米账号可兑换"}

    success = 0
    failed = 0
    errors = []

    for acc in accounts:
        try:
            mimo_data = await exchange_passport_to_mimo(acc.pass_token, acc.user_id, acc.device_id or None)
            now = _dt.now().strftime("%m-%d %H:%M")

            _save_mimo_session_direct(
                user_id=mimo_data["userId"],
                service_token=mimo_data["serviceToken"],
                xiaomichatbot_ph=mimo_data.get("xiaomichatbot_ph", ""),
                email=acc.email,
                source_account=acc.user_id,
                now_str=now,
            )

            if mimo_data.get("deviceId"):
                acc.device_id = mimo_data["deviceId"]

            success += 1
        except Exception as e:
            failed += 1
            errors.append(f"{acc.email or acc.user_id}: {str(e)[:60]}")

    config_manager.save_xiaomi_accounts()
    return {
        "ok": True,
        "success": success,
        "failed": failed,
        "errors": errors,
        "message": f"兑换完成: {success} 成功, {failed} 失败"
    }


@router.post("/api/xiaomi-account/import-json")
async def import_xiaomi_accounts_json(request: Request, username: str = Depends(verify_admin)):
    """导入小米 Passport 账号 JSON 数组"""
    try:
        data = await request.json()
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array")

        count = 0
        existing_uids = {acc.user_id for acc in config_manager.config.xiaomi_accounts}

        for item in data:
            if not isinstance(item, dict):
                continue

            user_id = str(item.get("user_id") or item.get("userId") or "")
            pass_token = item.get("pass_token") or item.get("passToken") or item.get("token") or ""

            # 兼容旧格式：从 cookies 提取
            if not pass_token:
                for c in item.get("cookies", []):
                    if isinstance(c, dict) and c.get("name") == "passToken":
                        pass_token = c.get("value", "")
            if not user_id:
                for c in item.get("cookies", []):
                    if isinstance(c, dict) and c.get("name") == "userId":
                        user_id = str(c.get("value", ""))

            if not user_id or not pass_token or user_id in existing_uids:
                continue

            now = _dt.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            config_manager.config.xiaomi_accounts.append(XiaomiAccount(
                user_id=user_id,
                pass_token=pass_token,
                email=item.get("email", ""),
                password=item.get("password", ""),
                device_id=item.get("device_id") or item.get("deviceId") or "",
                created_at=item.get("created_at", now),
                cookies=item.get("cookies", []),
                raw_data=item,
            ))
            existing_uids.add(user_id)
            count += 1

        if count > 0:
            config_manager.save_xiaomi_accounts()

        return {"ok": True, "added": count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/api/xiaomi-account/export-json")
async def export_xiaomi_accounts_json(username: str = Depends(verify_admin)):
    """导出小米 Passport 账号"""
    accounts_file = Path("accounts.json")
    if not accounts_file.exists():
        raise HTTPException(status_code=404, detail="accounts.json not found")
    return FileResponse(path=accounts_file, filename="accounts.json", media_type="application/json")
