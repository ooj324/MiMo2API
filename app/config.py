"""配置管理模块"""

import json
import threading
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional


@dataclass
class XiaomiAccount:
    """小米 Passport 原始账号"""
    user_id: str
    pass_token: str
    email: str = ""
    device_id: str = ""
    password: str = ""
    created_at: str = ""
    cookies: List[dict] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "email": self.email,
            "pass_token_masked": self.pass_token[:16] + "..." + self.pass_token[-6:] if len(self.pass_token) > 22 else "***",
            "device_id": self.device_id,
            "created_at": self.created_at,
            "has_password": bool(self.password),
        }


@dataclass
class MimoAccount:
    """MiMo 会话（实际用于 API 调用）"""
    service_token: str
    user_id: str
    email: str = ""
    xiaomichatbot_ph: str = ""
    login_time: str = ""
    last_test: str = ""
    is_valid: bool = False
    source_account: str = ""

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "email": self.email,
            "token_masked": self.service_token[:16] + "..." + self.service_token[-6:] if len(self.service_token) > 22 else "***",
            "xiaomichatbot_ph": "***" if self.xiaomichatbot_ph else "",
            "login_time": self.login_time,
            "last_test": self.last_test,
            "is_valid": self.is_valid,
            "source_account": self.source_account,
        }


@dataclass
class Config:
    """应用配置"""
    api_keys: str = "sk-default"
    admin_password: str = "admin"
    mimo_accounts: List[MimoAccount] = None
    xiaomi_accounts: List[XiaomiAccount] = None
    models: List[str] = None
    tools_passthrough: bool = False
    session_limit_per_account: int = 10
    session_reuse: bool = True
    debug_mode: bool = False
    resin_url: str = ""
    resin_platform_name: str = "Default"

    def __post_init__(self):
        if self.mimo_accounts is None:
            self.mimo_accounts = []
        if self.xiaomi_accounts is None:
            self.xiaomi_accounts = []
        if self.models is None:
            self.models = []

    def to_dict(self):
        d = {
            "api_keys": self.api_keys,
            "admin_password": self.admin_password,
            "mimo_accounts": [acc.to_dict() for acc in self.mimo_accounts],
            "tools_passthrough": self.tools_passthrough,
            "session_limit_per_account": self.session_limit_per_account,
            "session_reuse": self.session_reuse,
            "debug_mode": self.debug_mode,
            "resin_url": self.resin_url,
            "resin_platform_name": self.resin_platform_name,
        }
        if self.models:
            d["models"] = self.models
        return d

    def to_save_dict(self):
        d = {
            "api_keys": self.api_keys,
            "admin_password": self.admin_password,
            "tools_passthrough": self.tools_passthrough,
            "session_limit_per_account": self.session_limit_per_account,
            "session_reuse": self.session_reuse,
            "debug_mode": self.debug_mode,
            "resin_url": self.resin_url,
            "resin_platform_name": self.resin_platform_name,
        }
        if self.models:
            d["models"] = self.models
        return d


class ConfigManager:
    def __init__(self, config_file: str = "config.json"):
        self.config_file = Path(config_file)
        self.config = Config()
        self.lock = threading.RLock()
        self.account_idx = 0
        self.load()

    def load(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config = Config(
                        api_keys=data.get('api_keys', 'sk-default'),
                        admin_password=data.get('admin_password', 'admin'),
                        models=data.get('models', []),
                        tools_passthrough=data.get('tools_passthrough', False),
                        session_limit_per_account=data.get('session_limit_per_account', 10),
                        session_reuse=data.get('session_reuse', True),
                        debug_mode=data.get('debug_mode', False),
                        resin_url=data.get('resin_url', ''),
                        resin_platform_name=data.get('resin_platform_name', 'Default')
                    )
            else:
                self.config = Config()
                self.save_config_only()
        except Exception as e:
            print(f"加载配置失败: {e}")
            self.config = Config()
            self.save_config_only()

        self.load_xiaomi_accounts()
        self.load_mimo_sessions()

    def save_config_only(self):
        with self.lock:
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config.to_save_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"保存配置失败: {e}")

    def save(self):
        self.save_config_only()
        self.save_xiaomi_accounts()
        self.save_mimo_sessions()

    def validate_api_key(self, key: str) -> bool:
        with self.lock:
            keys = [k.strip() for k in self.config.api_keys.split(',')]
            return key in keys

    # ─── 小米账号 (accounts.json) ────────────────────────────

    def load_xiaomi_accounts(self) -> int:
        f = Path("accounts.json")
        if not f.exists():
            self.config.xiaomi_accounts = []
            return 0
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as e:
            print(f"读取 accounts.json 失败: {e}")
            self.config.xiaomi_accounts = []
            return 0

        accounts = []
        for item in data:
            if not isinstance(item, dict):
                continue
            email = item.get("email", "")
            password = item.get("password", "")
            token = item.get("token", "")
            cookies = item.get("cookies", [])
            created_at = item.get("created_at", "")

            # Extract user_id, pass_token, device_id from cookies if not top-level
            uid = item.get("user_id", "")
            pt = token or item.get("pass_token", "")
            did = item.get("device_id", "")

            for c in cookies:
                if not isinstance(c, dict):
                    continue
                name = c.get("name")
                val = c.get("value")
                if name == "userId" and not uid:
                    uid = val
                elif name == "passToken" and not pt:
                    pt = val
                elif name == "deviceId" and not did:
                    did = val

            if uid and pt:
                accounts.append(XiaomiAccount(
                    user_id=str(uid),
                    pass_token=pt,
                    email=email,
                    device_id=did,
                    password=password,
                    created_at=created_at,
                    cookies=cookies,
                    raw_data=item
                ))
        self.config.xiaomi_accounts = accounts
        return len(accounts)

    def save_xiaomi_accounts(self):
        with self.lock:
            out = []
            for acc in self.config.xiaomi_accounts:
                item = dict(acc.raw_data) if getattr(acc, "raw_data", None) else {}
                item["email"] = acc.email
                item["password"] = acc.password
                item["token"] = acc.pass_token
                item["created_at"] = acc.created_at

                # Merge or rebuild cookies in-place to preserve order and duplicates
                cookies = item.get("cookies", [])
                if not isinstance(cookies, list):
                    cookies = []

                has_uid = False
                has_pt = False
                has_did = False
                for c in cookies:
                    if not isinstance(c, dict):
                        continue
                    name = c.get("name")
                    if name == "userId":
                        c["value"] = acc.user_id
                        has_uid = True
                    elif name == "passToken":
                        c["value"] = acc.pass_token
                        has_pt = True
                    elif name == "deviceId":
                        c["value"] = acc.device_id
                        has_did = True

                if not has_uid and acc.user_id:
                    cookies.append({"name": "userId", "value": acc.user_id})
                if not has_pt and acc.pass_token:
                    cookies.append({
                        "name": "passToken",
                        "value": acc.pass_token,
                        "domain": ".account.xiaomi.com",
                        "path": "/",
                        "expires": 1784089697.526279,
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "None"
                    })
                if not has_did and acc.device_id:
                    cookies.append({
                        "name": "deviceId",
                        "value": acc.device_id,
                        "domain": ".account.xiaomi.com",
                        "path": "/",
                        "expires": 1815193697.526177,
                        "httpOnly": False,
                        "secure": True,
                        "sameSite": "None"
                    })

                item["cookies"] = cookies
                out.append(item)
            try:
                with open("accounts.json", 'w', encoding='utf-8') as f:
                    json.dump(out, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"写入 accounts.json 失败: {e}")

    # ─── MiMo 会话 (mimo_sessions.json) ─────────────────────

    def load_mimo_sessions(self) -> int:
        f = Path("mimo_sessions.json")
        if not f.exists():
            self.config.mimo_accounts = []
            return 0
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as e:
            print(f"读取 mimo_sessions.json 失败: {e}")
            self.config.mimo_accounts = []
            return 0

        sessions = []
        for item in data:
            if not isinstance(item, dict):
                continue
            st = item.get("service_token", "")
            uid = item.get("user_id", "")
            if st and uid:
                sessions.append(MimoAccount(
                    service_token=st, user_id=uid,
                    email=item.get("email", ""),
                    xiaomichatbot_ph=item.get("xiaomichatbot_ph", ""),
                    login_time=item.get("created_at", ""),
                    is_valid=item.get("is_valid", True),
                    source_account=item.get("source_account", ""),
                ))
        self.config.mimo_accounts = sessions
        return len(sessions)

    def save_mimo_sessions(self):
        with self.lock:
            out = []
            for acc in self.config.mimo_accounts:
                out.append({
                    "user_id": acc.user_id,
                    "service_token": acc.service_token,
                    "xiaomichatbot_ph": acc.xiaomichatbot_ph,
                    "email": acc.email,
                    "source_account": acc.source_account,
                    "created_at": acc.login_time,
                    "is_valid": acc.is_valid,
                })
            try:
                with open("mimo_sessions.json", 'w', encoding='utf-8') as f:
                    json.dump(out, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"写入 mimo_sessions.json 失败: {e}")

    # ─── 账号轮询 ────────────────────────────────────────────

    def get_next_account(self) -> Optional[MimoAccount]:
        with self.lock:
            if not self.config.mimo_accounts:
                return None

            from app.session_store import get_account_session_count

            total = len(self.config.mimo_accounts)
            limit = self.config.session_limit_per_account

            for _ in range(total):
                account = self.config.mimo_accounts[self.account_idx % total]
                self.account_idx += 1
                if not account.is_valid:
                    continue
                if get_account_session_count(account.user_id) < limit:
                    return account

            # 全满载，返回任意有效账号
            for _ in range(total):
                account = self.config.mimo_accounts[self.account_idx % total]
                self.account_idx += 1
                if account.is_valid:
                    return account

            return self.config.mimo_accounts[0]

    def update_config(self, new_config: dict):
        with self.lock:
            self.config.api_keys = new_config.get('api_keys', 'sk-default')
            self.config.admin_password = new_config.get('admin_password', 'admin')
            self.config.tools_passthrough = new_config.get('tools_passthrough', False)
            self.config.session_limit_per_account = new_config.get('session_limit_per_account', 10)
            self.config.session_reuse = new_config.get('session_reuse', True)
            self.config.resin_url = new_config.get('resin_url', '')
            self.config.resin_platform_name = new_config.get('resin_platform_name', 'Default')
            self.config.models = new_config.get('models', [])
            self.save_config_only()

    def get_config(self) -> dict:
        with self.lock:
            return self.config.to_dict()


config_manager = ConfigManager()
