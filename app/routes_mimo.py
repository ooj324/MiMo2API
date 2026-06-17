"""Mimo 会话管理路由 — MiMo2API"""

import time
import uuid
import json
import httpx
import re as _re
import hashlib as _hashlib
from typing import Optional
from pathlib import Path
from datetime import datetime as _dt
from urllib.parse import urlparse as _urlparse, parse_qs as _parse_qs, urlencode as _urlencode, urlunparse as _urlunparse
from http.cookies import SimpleCookie as _SimpleCookie

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel as _BaseModel

from .auth import verify_admin
from .config import config_manager, MimoAccount, XiaomiAccount
from .mimo_client import MimoClient, MimoApiError

router = APIRouter()


# ─── 字段化登录 / SSO 兑换支持 ───────────────────────────────

class LoginPasswordRequest(_BaseModel):
    username: str
    password: str


class Login2faVerifyRequest(_BaseModel):
    session_id: str


class LoginPassportRequest(_BaseModel):
    passToken: str
    userId: str
    deviceId: Optional[str] = None


_login_sessions = {}


def _clean_expired_login_sessions():
    now = time.time()
    expired = [k for k, v in _login_sessions.items() if now - v["time"] > 600]
    for k in expired:
        _login_sessions.pop(k, None)


async def exchange_passport_to_mimo(pass_token: str, user_id: str, device_id: str = None) -> dict:
    if not device_id:
        device_id = f"wb_{uuid.uuid4().hex}"

    passport_cookies = {
        "passToken": pass_token,
        "userId": user_id,
        "deviceId": device_id
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }

    async with httpx.AsyncClient(follow_redirects=False) as client:
        chat_url = "https://aistudio.xiaomimimo.com/open-apis/bot/chat"
        resp = await client.post(chat_url, json={})
        try:
            login_url = resp.json().get("loginUrl")
        except Exception:
            raise Exception("无法从 MiMo 401 响应中获取登录 URL")

        if not login_url:
            raise Exception("MiMo 401 响应未包含 loginUrl")

        parsed_url = _urlparse(login_url)
        query_params = _parse_qs(parsed_url.query)
        query_params["_json"] = ["true"]
        new_query = _urlencode(query_params, doseq=True)
        json_login_url = _urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment
        ))

        resp_ticket = await client.get(json_login_url, cookies=passport_cookies, headers=headers)
        ticket_text = resp_ticket.text
        if ticket_text.startswith("&&&START&&&"):
            ticket_text = ticket_text[11:]
        try:
            ticket_data = json.loads(ticket_text)
        except Exception:
            raise Exception(f"解析票据失败: {ticket_text[:200]}")

        code = ticket_data.get("code")
        if code != 0:
            raise Exception(f"小米 Passport 返回登录失败: {ticket_data.get('description', '未知错误')}")

        location = ticket_data.get("location")
        if not location:
            raise Exception("小米 Passport 未返回回调 location")

        resp_sts = await client.get(location, headers=headers)
        if resp_sts.status_code not in (200, 302, 307):
            raise Exception(f"STS 兑换失败: HTTP {resp_sts.status_code}")

        mimo_cookies = {}
        for cookie in client.cookies.jar:
            if "xiaomimimo.com" in cookie.domain:
                mimo_cookies[cookie.name] = cookie.value

        service_token = mimo_cookies.get("serviceToken")
        user_id_mimo = mimo_cookies.get("userId")
        xiaomichatbot_ph = mimo_cookies.get("xiaomichatbot_ph")

        if not service_token or not user_id_mimo:
            raise Exception("STS 兑换未返回 serviceToken 或 userId")

        if service_token.startswith('"') and service_token.endswith('"'):
            service_token = service_token[1:-1]
        if xiaomichatbot_ph and xiaomichatbot_ph.startswith('"') and xiaomichatbot_ph.endswith('"'):
            xiaomichatbot_ph = xiaomichatbot_ph[1:-1]

        return {
            "serviceToken": service_token,
            "userId": user_id_mimo,
            "xiaomichatbot_ph": xiaomichatbot_ph or "",
            "deviceId": device_id
        }


def _save_mimo_session_direct(user_id: str, service_token: str, xiaomichatbot_ph: str,
                               email: str, source_account: str, now_str: str):
    """直接保存 MiMo 会话到 mimo_sessions.json（不做连通性测试）"""
    existing = False
    for i, acc in enumerate(config_manager.config.mimo_accounts):
        if acc.user_id == user_id:
            config_manager.config.mimo_accounts[i] = MimoAccount(
                service_token=service_token,
                user_id=user_id,
                email=email,
                xiaomichatbot_ph=xiaomichatbot_ph,
                login_time=now_str,
                is_valid=True,
                source_account=source_account,
            )
            existing = True
            break

    if not existing:
        config_manager.config.mimo_accounts.append(MimoAccount(
            service_token=service_token,
            user_id=user_id,
            email=email,
            xiaomichatbot_ph=xiaomichatbot_ph,
            login_time=now_str,
            is_valid=True,
            source_account=source_account,
        ))

    config_manager.save_mimo_sessions()


def _save_xiaomi_account_if_new(user_id: str, pass_token: str, email: str = "", device_id: str = ""):
    """如果小米账号不存在则保存"""
    for acc in config_manager.config.xiaomi_accounts:
        if acc.user_id == user_id:
            return  # 已存在
    now = _dt.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    config_manager.config.xiaomi_accounts.append(XiaomiAccount(
        user_id=user_id,
        pass_token=pass_token,
        email=email,
        device_id=device_id,
        created_at=now,
    ))
    config_manager.save_xiaomi_accounts()


async def _save_mimo_account(user_id: str, service_token: str, xiaomichatbot_ph: str, email: str, pass_token: str, all_cookies: list, now_str: str):
    """兼容旧接口：验证并保存 MiMo 会话 + 自动保存小米账号"""
    account = MimoAccount(
        service_token=service_token,
        user_id=user_id,
        xiaomichatbot_ph=xiaomichatbot_ph
    )

    client = MimoClient(account)
    await client.call_api("hi", False)

    _save_mimo_session_direct(
        user_id=user_id,
        service_token=service_token,
        xiaomichatbot_ph=xiaomichatbot_ph,
        email=email,
        source_account=user_id,
        now_str=now_str,
    )

    # 同时保存小米 Passport 账号
    if pass_token:
        _save_xiaomi_account_if_new(user_id, pass_token, email)


@router.get("/api/accounts")
async def list_accounts(username: str = Depends(verify_admin)):
    """列出所有 MiMo 会话"""
    from .session_store import get_account_session_count
    accounts = []
    for acc in config_manager.config.mimo_accounts:
        token = acc.service_token
        masked = token[:16] + "..." + token[-6:] if len(token) > 22 else "***"
        accounts.append({
            "user_id": acc.user_id,
            "email": getattr(acc, "email", ""),
            "token_masked": masked,
            "is_valid": acc.is_valid,
            "login_time": acc.login_time,
            "last_test": acc.last_test,
            "source_account": getattr(acc, "source_account", ""),
            "active_sessions": get_account_session_count(acc.user_id)
        })
    return {"accounts": accounts}


@router.post("/api/account/import-cookie")
async def import_cookie(request: Request, username: str = Depends(verify_admin)):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "invalid json")

    st = (data.get("serviceToken") or "").strip()
    uid = (data.get("userId") or "").strip()
    ph = (data.get("xiaomichatbot_ph") or "").strip()

    if not st or not uid:
        # Check if passToken is present for auto-exchange
        pass_token = (data.get("passToken") or "").strip()
        if pass_token and uid:
            try:
                device_id = (data.get("deviceId") or "").strip()
                mimo_data = await exchange_passport_to_mimo(pass_token, uid, device_id)
                st = mimo_data["serviceToken"]
                uid = mimo_data["userId"]
                ph = mimo_data["xiaomichatbot_ph"]
                now = _dt.now().strftime("%m-%d %H:%M")
                _save_mimo_session_direct(
                    user_id=uid,
                    service_token=st,
                    xiaomichatbot_ph=ph,
                    email=f"passport_{uid}",
                    source_account=uid,
                    now_str=now,
                )
                # 同时保存小米账号
                _save_xiaomi_account_if_new(uid, pass_token, f"passport_{uid}", device_id)
                return {"ok": True, "user_id": uid, "response": "SSO兑换成功"}
            except Exception as e:
                return {"ok": False, "error": f"SSO 自动兑换失败: {str(e)}"}
        return {"ok": False, "error": "缺少必要字段 (serviceToken, userId, xiaomichatbot_ph) 或 (passToken, userId)"}

    if not ph:
        return {"ok": False, "error": "缺少必要字段 (xiaomichatbot_ph)"}

    return await _validate_and_save(st, uid, ph)


@router.post("/api/account/login-password")
async def login_password(request: LoginPasswordRequest, username: str = Depends(verify_admin)):
    user = request.username.strip()
    password = request.password.strip()

    _clean_expired_login_sessions()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    async with httpx.AsyncClient(follow_redirects=False) as client:
        chat_url = "https://aistudio.xiaomimimo.com/open-apis/bot/chat"
        resp = await client.post(chat_url, json={})
        try:
            login_url = resp.json().get("loginUrl")
        except Exception:
            raise HTTPException(400, "无法从 MiMo 响应中获取登录 URL")

        if not login_url:
            raise HTTPException(400, "MiMo 401 响应未包含 loginUrl")

        parsed_login_url = _urlparse(login_url)
        query_params = _parse_qs(parsed_login_url.query)

        md5_pwd = _hashlib.md5(password.encode('utf-8')).hexdigest().upper()

        payload = {
            "user": user,
            "hash": md5_pwd,
            "sid": "xiaomichatbot",
            "callback": query_params.get("callback", [""])[0],
            "_sign": query_params.get("_sign", [""])[0],
            "qs": query_params.get("qs", [""])[0],
            "_json": "true"
        }

        login_auth_url = "https://account.xiaomi.com/pass/serviceLoginAuth2"
        device_id = f"wb_{uuid.uuid4().hex}"
        cookies = {"deviceId": device_id}

        resp_auth = await client.post(login_auth_url, data=payload, cookies=cookies, headers=headers)
        text = resp_auth.text
        if text.startswith("&&&START&&&"):
            text = text[11:]

        try:
            data = json.loads(text)
        except Exception:
            raise HTTPException(500, f"解析 Xiaomi Auth 响应失败: {text[:200]}")

        code = data.get("code")
        if code != 0:
            raise HTTPException(400, f"登录失败: {data.get('description', '未知错误')}")

        notification_url = data.get("notificationUrl")
        if notification_url:
            session_id = uuid.uuid4().hex
            auth_cookies = {}
            for cookie_str in resp_auth.headers.get_list("set-cookie"):
                cookie = _SimpleCookie()
                cookie.load(cookie_str)
                for key, morsel in cookie.items():
                    auth_cookies[key] = morsel.value

            auth_cookies["deviceId"] = device_id

            _login_sessions[session_id] = {
                "user": user,
                "password": password,
                "cookies": auth_cookies,
                "login_url": login_url,
                "time": time.time()
            }
            return {
                "ok": False,
                "code": "need_2fa",
                "notification_url": notification_url,
                "session_id": session_id
            }

        location = data.get("location")
        if not location:
            raise HTTPException(400, "登录成功但未返回 location")

        resp_sts = await client.get(location, headers=headers)
        mimo_cookies = {}
        for cookie in client.cookies.jar:
            if "xiaomimimo.com" in cookie.domain:
                mimo_cookies[cookie.name] = cookie.value

        service_token = mimo_cookies.get("serviceToken")
        user_id_mimo = mimo_cookies.get("userId")
        xiaomichatbot_ph = mimo_cookies.get("xiaomichatbot_ph")

        if not service_token or not user_id_mimo:
            raise HTTPException(400, "SSO 兑换失败，未返回 serviceToken")

        if service_token.startswith('"') and service_token.endswith('"'):
            service_token = service_token[1:-1]
        if xiaomichatbot_ph and xiaomichatbot_ph.startswith('"') and xiaomichatbot_ph.endswith('"'):
            xiaomichatbot_ph = xiaomichatbot_ph[1:-1]

        pass_token_val = mimo_cookies.get("passToken") or ""
        if pass_token_val.startswith('"') and pass_token_val.endswith('"'):
            pass_token_val = pass_token_val[1:-1]

        now = _dt.now().strftime("%m-%d %H:%M")

        try:
            all_new_cookies = []
            for k, v in mimo_cookies.items():
                all_new_cookies.append({"name": k, "value": v, "domain": ".xiaomimimo.com" if k in ("serviceToken", "userId", "xiaomichatbot_ph") else ".xiaomi.com"})
            all_new_cookies.append({"name": "deviceId", "value": device_id, "domain": ".account.xiaomi.com"})

            await _save_mimo_account(user_id_mimo, service_token, xiaomichatbot_ph, user, pass_token_val, all_new_cookies, now)
        except Exception as e:
            raise HTTPException(400, f"验证保存失败: {str(e)}")

        return {"ok": True, "user_id": user_id_mimo, "email": user}


@router.post("/api/account/login-2fa-verify")
async def login_2fa_verify(request: Login2faVerifyRequest, username: str = Depends(verify_admin)):
    session_id = request.session_id
    if session_id not in _login_sessions:
        raise HTTPException(400, "会话已过期或不存在，请重新输入账号密码登录。")

    sess = _login_sessions[session_id]
    user = sess["user"]
    password = sess["password"]
    auth_cookies = sess["cookies"]
    login_url = sess["login_url"]

    _clean_expired_login_sessions()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    async with httpx.AsyncClient(follow_redirects=False) as client:
        parsed_login_url = _urlparse(login_url)
        query_params = _parse_qs(parsed_login_url.query)

        md5_pwd = _hashlib.md5(password.encode('utf-8')).hexdigest().upper()

        payload = {
            "user": user,
            "hash": md5_pwd,
            "sid": "xiaomichatbot",
            "callback": query_params.get("callback", [""])[0],
            "_sign": query_params.get("_sign", [""])[0],
            "qs": query_params.get("qs", [""])[0],
            "_json": "true"
        }

        login_auth_url = "https://account.xiaomi.com/pass/serviceLoginAuth2"

        resp_auth = await client.post(login_auth_url, data=payload, cookies=auth_cookies, headers=headers)
        text = resp_auth.text
        if text.startswith("&&&START&&&"):
            text = text[11:]

        try:
            data = json.loads(text)
        except Exception:
            raise HTTPException(500, f"解析 Xiaomi Auth 响应失败: {text[:200]}")

        code = data.get("code")
        if code != 0:
            notification_url = data.get("notificationUrl")
            if notification_url:
                return {
                    "ok": False,
                    "code": "need_2fa",
                    "notification_url": notification_url,
                    "session_id": session_id,
                    "message": "尚未完成验证，请在浏览器中完成验证码输入后重试。"
                }
            raise HTTPException(400, f"登录失败: {data.get('description', '未知错误')}")

        location = data.get("location")
        if not location:
            raise HTTPException(400, "登录成功但未返回 location")

        resp_sts = await client.get(location, headers=headers)
        mimo_cookies = {}
        for cookie in client.cookies.jar:
            if "xiaomimimo.com" in cookie.domain:
                mimo_cookies[cookie.name] = cookie.value

        service_token = mimo_cookies.get("serviceToken")
        user_id_mimo = mimo_cookies.get("userId")
        xiaomichatbot_ph = mimo_cookies.get("xiaomichatbot_ph")

        if not service_token or not user_id_mimo:
            raise HTTPException(400, "SSO 兑换失败，未返回 serviceToken")

        if service_token.startswith('"') and service_token.endswith('"'):
            service_token = service_token[1:-1]
        if xiaomichatbot_ph and xiaomichatbot_ph.startswith('"') and xiaomichatbot_ph.endswith('"'):
            xiaomichatbot_ph = xiaomichatbot_ph[1:-1]

        pass_token_val = mimo_cookies.get("passToken") or ""
        if pass_token_val.startswith('"') and pass_token_val.endswith('"'):
            pass_token_val = pass_token_val[1:-1]

        all_new_cookies = []
        for k, v in mimo_cookies.items():
            all_new_cookies.append({"name": k, "value": v, "domain": ".xiaomimimo.com" if k in ("serviceToken", "userId", "xiaomichatbot_ph") else ".xiaomi.com"})

        device_id = auth_cookies.get("deviceId", "")
        if device_id:
            all_new_cookies.append({"name": "deviceId", "value": device_id, "domain": ".account.xiaomi.com"})

        now = _dt.now().strftime("%m-%d %H:%M")

        try:
            await _save_mimo_account(user_id_mimo, service_token, xiaomichatbot_ph, user, pass_token_val, all_new_cookies, now)
        except Exception as e:
            raise HTTPException(400, f"验证保存失败: {str(e)}")

        _login_sessions.pop(session_id, None)
        return {"ok": True, "user_id": user_id_mimo, "email": user}


@router.post("/api/account/login-passport")
async def login_passport(request: LoginPassportRequest, username: str = Depends(verify_admin)):
    pass_token = request.passToken.strip()
    user_id = request.userId.strip()
    device_id = (request.deviceId or "").strip()

    if not pass_token or not user_id:
        raise HTTPException(400, "缺少必填字段: passToken, userId")

    try:
        mimo_data = await exchange_passport_to_mimo(pass_token, user_id, device_id)
        now = _dt.now().strftime("%m-%d %H:%M")

        _save_mimo_session_direct(
            user_id=mimo_data["userId"],
            service_token=mimo_data["serviceToken"],
            xiaomichatbot_ph=mimo_data.get("xiaomichatbot_ph", ""),
            email=f"passport_{user_id}",
            source_account=user_id,
            now_str=now,
        )

        # 同时保存小米账号
        _save_xiaomi_account_if_new(user_id, pass_token, f"passport_{user_id}", mimo_data.get("deviceId", ""))

        return {"ok": True, "user_id": mimo_data["userId"]}
    except Exception as e:
        raise HTTPException(400, f"验证/兑换失败: {str(e)}")


@router.post("/api/account/import-curl")
async def import_curl(request: Request, username: str = Depends(verify_admin)):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "invalid json")

    curl = (data.get("curl") or "").strip()
    if not curl:
        return {"ok": False, "error": "请提供 cURL 命令"}

    cookie_match = _re.search(r"(?:-b|--cookie)\s+'([^']+)'", curl)
    if not cookie_match:
        cookie_match = _re.search(r"-H\s+'Cookie:\s*([^']+)'", curl)
    if not cookie_match:
        return {"ok": False, "error": "未从 cURL 中找到 Cookie"}

    cookies = cookie_match.group(1)
    st_m = _re.search(r'serviceToken="?([^";\s]+)', cookies)
    uid_m = _re.search(r'userId=(\d+)', cookies)
    ph_m = _re.search(r'xiaomichatbot_ph="?([^";\s]+)', cookies)

    if not st_m or not uid_m or not ph_m:
        return {"ok": False, "error": "未从 Cookie 中提取到 serviceToken/userId/xiaomichatbot_ph"}

    return await _validate_and_save(st_m.group(1), uid_m.group(1), ph_m.group(1))


async def _validate_and_save(service_token: str, user_id: str, xiaomichatbot_ph: str):
    account = MimoAccount(service_token=service_token, user_id=user_id, xiaomichatbot_ph=xiaomichatbot_ph)
    client = MimoClient(account)

    try:
        content, _, _ = await client.call_api("hi", False)
        now = _dt.now().strftime("%m-%d %H:%M")

        _save_mimo_session_direct(
            user_id=user_id,
            service_token=service_token,
            xiaomichatbot_ph=xiaomichatbot_ph,
            email="",
            source_account="",
            now_str=now,
        )
        return {"ok": True, "user_id": user_id, "response": content[:100]}

    except MimoApiError as e:
        return {"ok": False, "error": f"验证失败 (HTTP {e.status_code}): {e.response_body[:100]}"}
    except Exception as e:
        return {"ok": False, "error": f"验证失败: {str(e)[:100]}"}


@router.delete("/api/accounts/{idx}")
async def delete_account(idx: int, username: str = Depends(verify_admin)):
    accounts = config_manager.config.mimo_accounts
    if idx < 0 or idx >= len(accounts):
        raise HTTPException(404, "account not found")
    removed = accounts.pop(idx)
    config_manager.save_mimo_sessions()
    return {"ok": True, "removed_user_id": removed.user_id}


@router.post("/api/account/sync-json")
async def sync_accounts_json_endpoint(username: str = Depends(verify_admin)):
    try:
        count = config_manager.load_mimo_sessions()
        return {"ok": True, "added": count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/account/import-json")
async def import_accounts_json_endpoint(request: Request, username: str = Depends(verify_admin)):
    """导入 MiMo 会话 JSON 数组"""
    try:
        data = await request.json()
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array")

        count = 0
        existing_uids = {acc.user_id for acc in config_manager.config.mimo_accounts}

        for item in data:
            if not isinstance(item, dict):
                continue
            uid = ""
            st = ""
            ph = ""

            if "serviceToken" in item or "service_token" in item:
                st = item.get("serviceToken") or item.get("service_token") or ""
            if "userId" in item or "user_id" in item:
                uid = str(item.get("userId") or item.get("user_id") or "")
            if "xiaomichatbot_ph" in item:
                ph = item["xiaomichatbot_ph"]

            # 兼容旧 cookies 格式
            cookies = item.get("cookies", [])
            for c in cookies:
                if isinstance(c, dict):
                    if c.get("name") == "serviceToken": st = c.get("value", "")
                    elif c.get("name") == "userId": uid = str(c.get("value", ""))
                    elif c.get("name") == "xiaomichatbot_ph": ph = c.get("value", "")

            if st and uid and uid not in existing_uids:
                new_acc = MimoAccount(
                    service_token=st,
                    user_id=uid,
                    email=item.get("email", ""),
                    xiaomichatbot_ph=ph,
                    login_time=item.get("created_at", ""),
                    is_valid=True,
                    source_account=item.get("source_account", ""),
                )
                config_manager.config.mimo_accounts.append(new_acc)
                existing_uids.add(uid)
                count += 1

        if count > 0:
            config_manager.save_mimo_sessions()

        return {"ok": True, "added": count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/api/account/export-json")
async def export_accounts_json_endpoint(username: str = Depends(verify_admin)):
    """导出 MiMo 会话"""
    sessions_file = Path("mimo_sessions.json")
    if not sessions_file.exists():
        raise HTTPException(status_code=404, detail="mimo_sessions.json not found")
    return FileResponse(path=sessions_file, filename="mimo_sessions.json", media_type="application/json")


@router.post("/api/accounts/{idx}/test")
async def test_account(idx: int, username: str = Depends(verify_admin)):
    accounts = config_manager.config.mimo_accounts
    if idx < 0 or idx >= len(accounts):
        raise HTTPException(404, "account not found")

    acc = accounts[idx]
    client = MimoClient(acc)

    try:
        content, _, _ = await client.call_api("hi", False)
        acc.is_valid = True
        acc.last_test = _dt.now().strftime("%m-%d %H:%M")
        config_manager.save_mimo_sessions()
        return {"ok": True, "response": content[:200]}
    except MimoApiError as e:
        acc.is_valid = False
        acc.last_test = _dt.now().strftime("%m-%d %H:%M")
        config_manager.save_mimo_sessions()
        return {"ok": False, "error": f"HTTP {e.status_code}: {e.response_body[:100]}"}
    except Exception as e:
        acc.is_valid = False
        config_manager.save_mimo_sessions()
        return {"ok": False, "error": str(e)[:200]}
