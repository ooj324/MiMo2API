"""配置管理模块"""

import json
import threading
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict


@dataclass
class MimoAccount:
    """Mimo账号配置"""
    service_token: str
    user_id: str
    email: str = ""
    xiaomichatbot_ph: str = ""
    login_time: str = ""
    last_test: str = ""
    is_valid: bool = False
    raw_data: dict = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d.pop("raw_data", None)
        d["token_masked"] = self.service_token[:16] + "..." + self.service_token[-6:] if len(self.service_token) > 22 else "***"
        return d


@dataclass
class Config:
    """应用配置"""
    api_keys: str = "sk-default"
    admin_password: str = "admin"
    mimo_accounts: List[MimoAccount] = None
    models: List[str] = None  # 自定义模型列表，None 表示自动探测
    tools_passthrough: bool = False  # 全局工具透传模式
    session_limit_per_account: int = 10  # 单个账号最大并发会话数

    def __post_init__(self):
        if self.mimo_accounts is None:
            self.mimo_accounts = []
        if self.models is None:
            self.models = []

    def to_dict(self):
        d = {
            "api_keys": self.api_keys,
            "admin_password": self.admin_password,
            "mimo_accounts": [acc.to_dict() for acc in self.mimo_accounts],
            "tools_passthrough": self.tools_passthrough,
            "session_limit_per_account": self.session_limit_per_account,
        }
        if self.models:
            d["models"] = self.models
        return d

    def to_save_dict(self):
        """用于保存到 config.json 的格式（不含账号信息）"""
        d = {
            "api_keys": self.api_keys,
            "admin_password": self.admin_password,
            "tools_passthrough": self.tools_passthrough,
            "session_limit_per_account": self.session_limit_per_account,
        }
        if self.models:
            d["models"] = self.models
        return d


class ConfigManager:
    """配置管理器 - 线程安全"""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = Path(config_file)
        self.config = Config()
        self.lock = threading.RLock()
        self.account_idx = 0
        self.load()

    def load(self):
        """加载配置和账号"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config = Config(
                        api_keys=data.get('api_keys', 'sk-default'),
                        admin_password=data.get('admin_password', 'admin'),
                        mimo_accounts=[],  # 由 load_accounts_from_json 填充
                        models=data.get('models', []),
                        tools_passthrough=data.get('tools_passthrough', False),
                        session_limit_per_account=data.get('session_limit_per_account', 10)
                    )
            else:
                self.config = Config()
                self.save_config_only()
        except Exception as e:
            print(f"加载配置失败: {e}")
            self.config = Config()
            self.save_config_only()
            
        self.load_accounts_from_json()

    def save_config_only(self):
        """仅保存 config.json"""
        with self.lock:
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config.to_save_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"保存配置失败: {e}")

    def save(self):
        """保存配置和账号"""
        self.save_config_only()
        self.save_accounts_to_json()

    def validate_api_key(self, key: str) -> bool:
        """验证API Key"""
        with self.lock:
            keys = [k.strip() for k in self.config.api_keys.split(',')]
            return key in keys

    def load_accounts_from_json(self) -> int:
        """从 accounts.json 读取账号数据"""
        accounts_file = Path("accounts.json")
        if not accounts_file.exists():
            self.config.mimo_accounts = []
            return 0
            
        try:
            with open(accounts_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"读取 accounts.json 失败: {e}")
            self.config.mimo_accounts = []
            return 0
            
        accounts = []
        for item in data:
            if not isinstance(item, dict): continue
            email = item.get("email", "")
            cookies = item.get("cookies", [])
            st = uid = ph = ""
            for c in cookies:
                if not isinstance(c, dict): continue
                cname = c.get("name", "")
                cval = c.get("value", "")
                if cname == "serviceToken": st = cval
                elif cname == "userId": uid = cval
                elif cname == "xiaomichatbot_ph": ph = cval
            
            if st and uid:
                new_acc = MimoAccount(
                    service_token=st,
                    user_id=uid,
                    email=email,
                    xiaomichatbot_ph=ph,
                    login_time=item.get("created_at", ""),
                    is_valid=True,
                    raw_data=item
                )
                accounts.append(new_acc)
                
        self.config.mimo_accounts = accounts
        return len(accounts)

    def sync_accounts_json(self, auto_save: bool = True) -> int:
        """保持向后兼容：同步 accounts.json"""
        return self.load_accounts_from_json()

    def save_accounts_to_json(self):
        """将内存中的账号列表写入 accounts.json"""
        accounts_file = Path("accounts.json")
        output_data = []
        with self.lock:
            for acc in self.config.mimo_accounts:
                item = dict(acc.raw_data) if getattr(acc, "raw_data", None) else {}
                if acc.email:
                    item["email"] = acc.email
                if acc.login_time:
                    item["created_at"] = acc.login_time
                
                old_cookies = item.get("cookies", [])
                new_cookies = []
                seen_names = {"serviceToken", "userId", "xiaomichatbot_ph"}
                new_cookies.append({"name": "serviceToken", "value": acc.service_token})
                new_cookies.append({"name": "userId", "value": acc.user_id})
                if acc.xiaomichatbot_ph:
                    new_cookies.append({"name": "xiaomichatbot_ph", "value": acc.xiaomichatbot_ph})
                    
                for c in old_cookies:
                    if isinstance(c, dict) and c.get("name") not in seen_names:
                        new_cookies.append(c)
                item["cookies"] = new_cookies
                output_data.append(item)
                
        try:
            with open(accounts_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"写入 accounts.json 失败: {e}")

    def get_next_account(self) -> Optional[MimoAccount]:
        """获取下一个未超载的账号（轮询 + 会话限制）"""
        with self.lock:
            if not self.config.mimo_accounts:
                return None
                
            from app.session_store import get_account_session_count
            
            total_accounts = len(self.config.mimo_accounts)
            attempts = 0
            limit = self.config.session_limit_per_account
            
            while attempts < total_accounts:
                account = self.config.mimo_accounts[self.account_idx % total_accounts]
                self.account_idx += 1
                attempts += 1
                
                # 跳过无效账号
                if not account.is_valid:
                    continue
                    
                # 检查会话上限
                active_sessions = get_account_session_count(account.user_id)
                if active_sessions < limit:
                    return account
                    
            # 如果所有有效账号都满载了，就退避到原始轮询（或者选一个最近的），这里简单返回轮询结果
            # 为了防止死循环，直接返回轮询的下一个有效账号，不在乎是否满载（保证服务可用性优先）
            for _ in range(total_accounts):
                account = self.config.mimo_accounts[self.account_idx % total_accounts]
                self.account_idx += 1
                if account.is_valid:
                    return account
                    
            # 连一个有效账号都没有
            return self.config.mimo_accounts[self.account_idx % total_accounts]

    def update_config(self, new_config: dict):
        """更新配置"""
        with self.lock:
            existing_accounts = {acc.user_id: acc for acc in self.config.mimo_accounts}
            accounts = []
            for acc in new_config.get('mimo_accounts', []):
                uid = acc.get("user_id")
                new_acc = MimoAccount(**{k: v for k, v in acc.items() if k in MimoAccount.__dataclass_fields__})
                if uid in existing_accounts:
                    new_acc.raw_data = existing_accounts[uid].raw_data
                accounts.append(new_acc)
                
            self.config = Config(
                api_keys=new_config.get('api_keys', 'sk-default'),
                admin_password=new_config.get('admin_password', 'admin'),
                mimo_accounts=accounts,
                models=new_config.get('models', []),
                tools_passthrough=new_config.get('tools_passthrough', False),
                session_limit_per_account=new_config.get('session_limit_per_account', 10)
            )
            self.save()

    def get_config(self) -> dict:
        """获取配置"""
        with self.lock:
            return self.config.to_dict()


# 全局配置管理器实例
config_manager = ConfigManager()
