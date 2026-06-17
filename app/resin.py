import urllib.parse
import httpx
from .config import config_manager

def apply_resin_proxy(url: str, account_id: str, headers: dict = None, use_forward: bool = False):
    """
    为网络请求应用 Resin 代理池配置（正向/反向代理）。
    
    Args:
        url: 原始目标 URL
        account_id: 稳定/临时账号标识
        headers: 原始请求头 (可选)
        use_forward: 是否使用正向代理，默认 False (使用反向代理)
        
    Returns:
        (new_url, proxy_kwargs, new_headers)
        - new_url: 重写后的反向代理 URL，或原始 URL
        - proxy_kwargs: 用于 httpx.AsyncClient 的 kwargs，如 {"proxy": "..."}
        - new_headers: 补充了 Resin Auth 头的新 Headers 字典
    """
    if account_id and not str(account_id).startswith("mm2a:"):
        account_id = f"mm2a:{account_id}"

    config = config_manager.config
    if not config.resin_url:
        return url, {}, headers or {}

    parsed_resin = urllib.parse.urlparse(config.resin_url)
    platform = config.resin_platform_name or "Default"
    new_headers = dict(headers) if headers else {}

    if use_forward:
        # 正向代理
        token = parsed_resin.path.strip("/")
        auth_user = urllib.parse.quote(f"{platform}.{account_id}")
        auth_token = urllib.parse.quote(token)
        proxy_url = f"{parsed_resin.scheme}://{auth_user}:{auth_token}@{parsed_resin.netloc}"
        proxy_kwargs = {"proxy": proxy_url}
        return url, proxy_kwargs, new_headers
    else:
        # 反向代理
        parsed_target = urllib.parse.urlparse(url)
        target_scheme = parsed_target.scheme
        
        is_ws = target_scheme in ("ws", "wss")
        protocol = "http" if target_scheme == "ws" else ("https" if target_scheme == "wss" else target_scheme)
        
        new_url = f"{config.resin_url.rstrip('/')}/{platform}/{protocol}/{parsed_target.netloc}{parsed_target.path}"
        if parsed_target.query:
            new_url += f"?{parsed_target.query}"
            
        if is_ws:
            parsed_new = urllib.parse.urlparse(new_url)
            new_scheme = "ws" if parsed_new.scheme == "http" else "wss"
            new_url = urllib.parse.urlunparse(parsed_new._replace(scheme=new_scheme))
            
        new_headers["X-Resin-Account"] = account_id
        return new_url, {}, new_headers


async def inherit_lease(temp_account: str, stable_account: str):
    """
    当账号临时标识 (如登录前的 email/phone) 获取到持久稳定标识 (user_id) 后，
    向 Resin 发送租约继承请求。
    """
    if temp_account and not str(temp_account).startswith("mm2a:"):
        temp_account = f"mm2a:{temp_account}"
    if stable_account and not str(stable_account).startswith("mm2a:"):
        stable_account = f"mm2a:{stable_account}"

    config = config_manager.config
    if not config.resin_url:
        return
        
    platform = config.resin_platform_name or "Default"
    url = f"{config.resin_url.rstrip('/')}/api/v1/{platform}/actions/inherit-lease"
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={
                "parent_account": temp_account,
                "new_account": stable_account
            })
    except Exception as e:
        print(f"[Resin] Failed to inherit lease from {temp_account} to {stable_account}: {e}")
