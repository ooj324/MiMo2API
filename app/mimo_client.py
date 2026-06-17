"""Mimo API客户端"""

import json
import uuid
import httpx
import traceback
import random
from typing import Optional, Tuple, AsyncIterator
from .config import MimoAccount
from .resin import apply_resin_proxy


class MimoApiError(Exception):
    """MiMo API上游错误，携带HTTP状态码和响应体"""
    def __init__(self, status_code: int, response_body: str):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"MiMo API error {status_code}: {response_body[:200]}")


class MimoClient:
    """Mimo API客户端"""

    API_URL = "https://aistudio.xiaomimimo.com/open-apis/bot/chat"
    TIMEOUT = 120.0

    # MiMo API 原生 SSE 事件前缀（始终在 SSE #2 输出，独立于我们的工具定义）
    _MIMO_SSE_PREFIXES = {'webSearch', 'getTime', 'getTimeInfo', 'sessionSearch',
                          'imageSearch', 'fileSearch', 'getLocation', 'webExtract',
                          'getWeather', 'calculator'}

    def __init__(self, account: MimoAccount):
        self.account = account

    def _create_headers(self) -> dict:
        """创建伪随机请求头（按账号隔离指纹）"""
        # 使用账号唯一 ID 作为种子，保证同一账号指纹一致，不同账号指纹随机
        rng = random.Random(self.account.user_id)
        
        platforms = [
            {"ua_os": "Windows NT 10.0; Win64; x64", "sec_os": '"Windows"'},
            {"ua_os": f"Macintosh; Intel Mac OS X 10_{rng.randint(11, 15)}_{rng.randint(0, 9)}", "sec_os": '"macOS"'},
            {"ua_os": "X11; Linux x86_64", "sec_os": '"Linux"'}
        ]
        platform = rng.choice(platforms)
        
        chrome_major = rng.randint(115, 133)
        chrome_version = f"{chrome_major}.0.{rng.randint(1000, 9999)}.{rng.randint(10, 200)}"
        
        sec_ch_ua = f'"Not(A:Brand";v="99", "Google Chrome";v="{chrome_major}", "Chromium";v="{chrome_major}"'
        user_agent = f"Mozilla/5.0 ({platform['ua_os']}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"
        
        return {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://aistudio.xiaomimimo.com",
            "Referer": "https://aistudio.xiaomimimo.com/",
            "User-Agent": user_agent,
            "sec-ch-ua": sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": platform["sec_os"],
            "x-timezone": "Asia/Shanghai",
        }

    def _create_cookies(self) -> dict:
        """创建Cookies，保留 accounts.json 中原有的其他可用 Cookie"""
        cookies = {}
        # 从 raw_data 恢复附加的 Cookie（例如设备特征或追踪标示）
        if hasattr(self.account, "raw_data") and isinstance(self.account.raw_data, dict):
            raw_cookies = self.account.raw_data.get("cookies", [])
            if isinstance(raw_cookies, list):
                for c in raw_cookies:
                    if isinstance(c, dict) and "name" in c and "value" in c:
                        cookies[c["name"]] = c["value"]
                        
        # 确保核心认证字段使用最新的属性值覆盖
        cookies["serviceToken"] = self.account.service_token
        cookies["userId"] = self.account.user_id
        if self.account.xiaomichatbot_ph:
            cookies["xiaomichatbot_ph"] = self.account.xiaomichatbot_ph
            
        return cookies

    def _create_request_body(self, query: str, thinking: bool, model: str = "mimo-v2-pro", multi_medias: list = None, attachments: list = None, conversation_id: str = None) -> dict:
        """创建请求体"""
        return {
            "msgId": uuid.uuid4().hex[:32],
            "conversationId": conversation_id or uuid.uuid4().hex[:32],
            "query": query,
            "modelConfig": {
                "enableThinking": thinking,
                "temperature": 0.8,
                "topP": 0.95,
                "webSearchStatus": "disabled",
                "model": model
            },
            "multiMedias": multi_medias or [],
            "attachments": attachments or []
        }

    async def call_api(self, query: str, thinking: bool = False, model: str = "mimo-v2-pro", multi_medias: list = None, attachments: list = None, conversation_id: str = None) -> Tuple[str, str, dict]:
        """
        调用Mimo API（非流式）

        Args:
            conversation_id: 复用现有 MiMo 会话 ID（None=新建）

        Returns:
            (content, think_content, usage)
        """
        body = self._create_request_body(query, thinking, model, multi_medias, attachments, conversation_id)
        url, proxy_kwargs, headers = apply_resin_proxy(self.API_URL, self.account.user_id, self._create_headers())

        async with httpx.AsyncClient(timeout=self.TIMEOUT, **proxy_kwargs) as client:
            response = await client.post(
                url,
                params={"xiaomichatbot_ph": self.account.xiaomichatbot_ph},
                headers=headers,
                cookies=self._create_cookies(),
                json=body
            )

            if response.status_code != 200:
                raise MimoApiError(response.status_code, response.text)

            result = []
            usage = {"promptTokens": 0, "completionTokens": 0}

            # 解析SSE流
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data = line[5:].strip()
                    try:
                        sse_data = json.loads(data)
                        if isinstance(sse_data, dict):
                            if sse_data.get("type") == "text":
                                content = sse_data.get("content", "")
                                # 过滤 MiMo 原生前缀
                                if content.strip() not in self._MIMO_SSE_PREFIXES:
                                    result.append(content)
                            if "promptTokens" in sse_data:
                                usage = {
                                    "promptTokens": sse_data.get("promptTokens", 0),
                                    "completionTokens": sse_data.get("completionTokens", 0)
                                }
                        # list 类型跳过
                        elif isinstance(sse_data, list):
                            continue
                    except json.JSONDecodeError:
                        continue

            # 合并结果并解析think标签
            full_text = "".join(result).replace("\x00", "")
            content, think_content = self._parse_think_tags(full_text)

            return content, think_content, usage

    async def stream_api(self, query: str, thinking: bool = False, model: str = "mimo-v2-pro", multi_medias: list = None, attachments: list = None, conversation_id: str = None) -> AsyncIterator[dict]:
        """
        调用Mimo API（流式）

        Yields:
            SSE数据字典（仅 type=text 且有 content 的，已过滤 MiMo 原生前缀）
        """
        body = self._create_request_body(query, thinking, model, multi_medias, attachments, conversation_id)
        url, proxy_kwargs, headers = apply_resin_proxy(self.API_URL, self.account.user_id, self._create_headers())

        chunk_count = 0

        async with httpx.AsyncClient(timeout=self.TIMEOUT, **proxy_kwargs) as client:
            async with client.stream(
                "POST",
                url,
                params={"xiaomichatbot_ph": self.account.xiaomichatbot_ph},
                headers=headers,
                cookies=self._create_cookies(),
                json=body
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    raise MimoApiError(response.status_code, error_body.decode(errors="replace"))

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    chunk_count += 1
                    try:
                        sse_data = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    # 安全的类型分发
                    if isinstance(sse_data, list):
                        continue
                    if not isinstance(sse_data, dict):
                        continue

                    # DEBUG 日志（已关闭）
                    # try:
                    #     with open('/data/data/com.termux/files/home/MiMo2API/debug_api.log', 'a') as _df:
                    #         _df.write(f"[SSE #{chunk_count}] type={sse_data.get('type','?')} content={repr(sse_data.get('content',''))[:200]} keys={list(sse_data.keys())}\n")
                    # except Exception:
                    #     pass

                    # 过滤 MiMo 原生 SSE 前缀事件（如 SSE #2 的 'webSearch'）
                    if sse_data.get("type") == "text" and sse_data.get("content"):
                        content_val = sse_data["content"].strip()
                        if content_val in self._MIMO_SSE_PREFIXES:
                            continue  # 跳过 MiMo 原生的工具名 SSE 事件

                    # 只 yield text 类型和 usage 事件
                    if sse_data.get("type") == "text" and sse_data.get("content"):
                        yield sse_data
                    elif "promptTokens" in sse_data:
                        yield {"type": "usage", "promptTokens": sse_data.get("promptTokens", 0),
                               "completionTokens": sse_data.get("completionTokens", 0),
                               "totalTokens": sse_data.get("totalTokens", 0)}

    @staticmethod
    def _parse_think_tags(text: str) -> Tuple[str, str]:
        """
        解析think标签

        Returns:
            (content, think_content)
        """
        start = text.find("<think>")
        if start == -1:
            return text, ""

        end = text.find("</think>")
        if end == -1:
            return text, ""

        think_content = text[start + 7:end]
        content = text[end + 8:]
        return content, think_content

    async def delete_conversations(self, conversation_ids: list) -> bool:
        """删除 MiMo 服务端对话记录。

        Args:
            conversation_ids: 要删除的 conversation_id 列表

        Returns:
            True 表示全部删除成功
        """
        if not conversation_ids:
            return True
        url = "https://aistudio.xiaomimimo.com/open-apis/chat/conversation/delete"
        url, proxy_kwargs, headers = apply_resin_proxy(url, self.account.user_id, self._create_headers())
        try:
            async with httpx.AsyncClient(timeout=30.0, **proxy_kwargs) as client:
                resp = await client.post(
                    url,
                    params={"xiaomichatbot_ph": self.account.xiaomichatbot_ph},
                    headers=headers,
                    cookies=self._create_cookies(),
                    json=conversation_ids,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("code") == 0
                print(f"[Cleanup] MiMo delete failed: HTTP {resp.status_code}")
                return False
        except Exception as e:
            print(f"[Cleanup] MiMo delete error: {e}")
            return False

    async def get_conversations(self, page_num: int = 1, page_size: int = 20) -> dict:
        """获取 MiMo 服务端对话列表。

        Args:
            page_num: 页码
            page_size: 每页数量

        Returns:
            成功时返回 data 字典，包含 total 和 dataList 等信息，失败返回空字典 {}
        """
        url = "https://aistudio.xiaomimimo.com/open-apis/chat/conversation/list"
        url, proxy_kwargs, headers = apply_resin_proxy(url, self.account.user_id, self._create_headers())
        body = {
            "pageInfo": {
                "pageNum": page_num,
                "pageSize": page_size
            }
        }
        try:
            async with httpx.AsyncClient(timeout=30.0, **proxy_kwargs) as client:
                resp = await client.post(
                    url,
                    params={"xiaomichatbot_ph": self.account.xiaomichatbot_ph},
                    headers=headers,
                    cookies=self._create_cookies(),
                    json=body,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == 0:
                        return data.get("data", {})
                print(f"[ListConversations] MiMo list failed: HTTP {resp.status_code}")
                return {}
        except Exception as e:
            print(f"[ListConversations] MiMo list error: {e}")
            return {}

