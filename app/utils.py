"""工具函数 — MiMo2API

凭证解析、媒体提取/上传、消息构建。
"""

import re
import hashlib
import json as _json
import httpx
from typing import Optional, List, Tuple, Dict, Any
from .config import MimoAccount
from .resin import apply_resin_proxy


def parse_curl(curl_command: str) -> Optional[MimoAccount]:
    """解析cURL命令提取Mimo账号凭证。"""
    account = {
        'service_token': '',
        'user_id': '',
        'xiaomichatbot_ph': ''
    }

    cookie_match = re.search(r"(?:-b|--cookie)\s+'([^']+)'", curl_command)
    if not cookie_match:
        cookie_match = re.search(r'(?:-b|--cookie)\s+"([^"]+)"', curl_command)
    if not cookie_match:
        cookie_match = re.search(r"-H\s+'[Cc]ookie:\s*([^']+)'", curl_command)
    if not cookie_match:
        cookie_match = re.search(r'-H\s+"[Cc]ookie:\s*([^"]+)"', curl_command)
    if not cookie_match:
        return None

    cookies = cookie_match.group(1)

    service_token_match = re.search(r'serviceToken="([^"]+)"', cookies)
    if service_token_match:
        account['service_token'] = service_token_match.group(1)

    user_id_match = re.search(r'userId=(\d+)', cookies)
    if user_id_match:
        account['user_id'] = user_id_match.group(1)

    ph_match = re.search(r'xiaomichatbot_ph="([^"]+)"', cookies)
    if ph_match:
        account['xiaomichatbot_ph'] = ph_match.group(1)

    if not account['service_token']:
        return None

    return MimoAccount(**account)


def extract_medias_from_messages(messages: list) -> Tuple[str, list, list, list]:
    """从消息列表中提取图片/视频/音频媒体和文本文件。

    Returns:
        (query_text, base64_medias, text_files, processed_messages)
        text_files: [{"base64": ..., "filename": ..., "mimeType": ...}, ...]
    """
    base64_medias = []
    text_files = []
    seen_base64 = set()
    processed_messages = []

    for msg in messages:
        text = ""
        content = msg.content or ""

        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text += item.get("text", "")
                elif item.get("type") == "image_url":
                    img_url = item.get("image_url", {})
                    url = img_url.get("url", "") if isinstance(img_url, dict) else str(img_url)
                    if url and url.startswith("data:"):
                        base64 = url.split(",", 1)[1] if "," in url else url
                        if base64 and base64 not in seen_base64:
                            mime = url.split(";")[0].split(":")[1] if ";" in url else "image/jpeg"
                            base64_medias.append({
                                "base64": base64,
                                "mimeType": mime,
                                "type": "image"
                            })
                            seen_base64.add(base64)
                elif item.get("type") == "file":
                    # 文本文件：收集 base64 用于 MiMo 上传（mediaType="file"）
                    file_obj = item.get("file", {})
                    if isinstance(file_obj, dict):
                        filename = file_obj.get("filename", "file.txt")
                        file_data = file_obj.get("file_data", "") or file_obj.get("data", "")
                        if file_data and file_data not in seen_base64:
                            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
                            text_files.append({
                                "base64": file_data,
                                "filename": filename,
                                "mimeType": "text/plain"
                            })
                            seen_base64.add(file_data)
        else:
            text = str(content) if content else ""

        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            text = _serialize_tool_calls(msg.tool_calls)

        if msg.role == "tool":
            tool_call_id = getattr(msg, 'tool_call_id', '') or ''
            clean = re.sub(r'\[TOOL_RESULT\]\s*', '', text, flags=re.IGNORECASE)
            text = f"[tool_result id={tool_call_id[:8]}] {clean}"

        processed_messages.append({"role": msg.role, "text": text})

    query_text = processed_messages[-1]["text"] if processed_messages else ""
    return query_text, base64_medias, text_files, processed_messages


def _serialize_tool_calls(tool_calls: list) -> str:
    """统一定义工具调用序列化 — 兼容 dict 和 pydantic model。"""
    tc_lines = []
    for tc in tool_calls:
        tc_id = _safe_nested_get(tc, "id", "")
        fn = _safe_nested_get(tc, "function")
        if not fn:
            continue
        fname = _safe_nested_get(fn, "name", "")
        args_str = _safe_nested_get(fn, "arguments", "{}")

        if not isinstance(args_str, str):
            try:
                args_str = _json.dumps(args_str, ensure_ascii=False)
            except Exception:
                args_str = str(args_str)

        clean_args = args_str.replace(']]>', ']]]]><![CDATA[>')

        tc_lines.append(
            f'<|MMML|tool_call id="{tc_id}" name="{fname}">\n'
            f'<![CDATA[\n{clean_args}\n]]>\n'
            f'</|MMML|tool_call>'
        )

    return "\n".join(tc_lines)


def _safe_nested_get(obj, *keys, default=None):
    """安全嵌套取值 — 兼容 dict 和 pydantic model。"""
    for key in keys:
        if obj is None:
            return default
        if isinstance(obj, dict):
            obj = obj.get(key, default)
        else:
            obj = getattr(obj, key, default)
    return obj


async def upload_text_file_to_mimo(
    base64_data: str,
    filename: str,
    mime_type: str,
    account: MimoAccount,
    model: str = "mimo-v2-pro"
) -> Optional[Dict[str, Any]]:
    """上传文本文件到小米Mimo服务器。

    三步流程：genUploadInfo -> PUT 上传 -> resource/parse
    返回 multiMedias 格式的 dict，可直接传给 MiMo chat API。
    """
    if "," in base64_data:
        base64_data = base64_data.split(",", 1)[1]

    import base64 as b64
    binary_data = b64.b64decode(base64_data)

    md5 = hashlib.md5(binary_data).hexdigest()

    cookie = f"serviceToken={account.service_token}; userId={account.user_id}; xiaomichatbot_ph={account.xiaomichatbot_ph}"
    headers = {
        "Cookie": cookie,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://aistudio.xiaomimimo.com/",
        "Origin": "https://aistudio.xiaomimimo.com"
    }

    _, proxy_kwargs, _ = apply_resin_proxy("", account.user_id)
    async with httpx.AsyncClient(timeout=60, **proxy_kwargs) as client:
        try:
            ph = account.xiaomichatbot_ph
            info_url = f"https://aistudio.xiaomimimo.com/open-apis/resource/genUploadInfo?xiaomichatbot_ph={ph}"
            req_url, _, req_h = apply_resin_proxy(info_url, account.user_id, headers)
            info_res = await client.post(
                req_url,
                json={"fileName": filename, "fileContentMd5": md5},
                headers=req_h
            )
            info_data = info_res.json()
            if info_data.get("code") != 0 or not info_data.get("data"):
                print(f"[uploadTextFile] genUploadInfo failed: {info_data}")
                return None

            upload_url = info_data["data"]["uploadUrl"]
            resource_url = info_data["data"]["resourceUrl"]
            object_name = info_data["data"]["objectName"]

            put_headers = {"Content-Type": "application/octet-stream", "content-md5": md5}
            put_req_url, _, put_req_h = apply_resin_proxy(upload_url, account.user_id, put_headers)
            put_res = await client.put(put_req_url, content=binary_data, headers=put_req_h)
            if put_res.status_code != 200:
                print(f"[uploadTextFile] PUT failed: {put_res.status_code}")
                return None

            from urllib.parse import quote

            parse_url = (
                f"https://aistudio.xiaomimimo.com/open-apis/resource/parse"
                f"?fileUrl={quote(resource_url, safe='')}"
                f"&objectName={quote(object_name, safe='')}"
                f"&model={model}"
                f"&xiaomichatbot_ph={ph}"
            )
            parse_headers = {
                "Cookie": cookie,
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://aistudio.xiaomimimo.com/",
                "Origin": "https://aistudio.xiaomimimo.com"
            }
            parse_req_url, _, parse_req_h = apply_resin_proxy(parse_url, account.user_id, parse_headers)

            parse_res = None
            for attempt in range(5):
                try:
                    resp = await client.post(parse_req_url, json={}, headers=parse_req_h)
                    data = resp.json()
                    if data.get("code") == 0 and data.get("data", {}).get("id"):
                        parse_res = data
                        import asyncio
                        await asyncio.sleep(3)
                        break
                except Exception:
                    pass
                import asyncio
                await asyncio.sleep(2)

            if not parse_res:
                print("[uploadTextFile] Parse failed after retries")
                return None

            resource_id = parse_res["data"]["id"]
            return {
                "mediaType": "file",
                "fileUrl": resource_url,
                "compressedVideoUrl": "",
                "audioTrackUrl": "",
                "name": filename,
                "size": len(binary_data),
                "status": "completed",
                "objectName": object_name,
                "tokenUsage": parse_res["data"].get("tokenUsage", 0),
                "url": resource_id
            }

        except Exception as e:
            print(f"[uploadTextFile] Error: {e}")
            return None


async def upload_media_to_mimo(
    base64_data: str,
    mime_type: str,
    account: MimoAccount,
    model: str = "mimo-v2-omni"
) -> Optional[Dict[str, Any]]:
    """上传媒体文件到小米Mimo服务器。

    三步流程：genUploadInfo -> PUT 上传 -> resource/parse
    """
    if "," in base64_data:
        base64_data = base64_data.split(",", 1)[1]

    import base64 as b64
    binary_data = b64.b64decode(base64_data)

    md5 = hashlib.md5(binary_data).hexdigest()
    import uuid
    ext = mime_type.split("/")[-1] if "/" in mime_type else "jpg"
    if ext == "jpeg":
        ext = "jpg"
    file_name = f"{uuid.uuid4().hex}.{ext}"

    cookie = f"serviceToken={account.service_token}; userId={account.user_id}; xiaomichatbot_ph={account.xiaomichatbot_ph}"
    headers = {
        "Cookie": cookie,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://aistudio.xiaomimimo.com/",
        "Origin": "https://aistudio.xiaomimimo.com"
    }

    _, proxy_kwargs, _ = apply_resin_proxy("", account.user_id)
    async with httpx.AsyncClient(timeout=30, **proxy_kwargs) as client:
        try:
            ph = account.xiaomichatbot_ph
            info_url = f"https://aistudio.xiaomimimo.com/open-apis/resource/genUploadInfo?xiaomichatbot_ph={ph}"
            req_url, _, req_h = apply_resin_proxy(info_url, account.user_id, headers)
            info_res = await client.post(
                req_url,
                json={"fileName": file_name, "fileContentMd5": md5},
                headers=req_h
            )
            info_data = info_res.json()
            if info_data.get("code") != 0 or not info_data.get("data"):
                print(f"[uploadMedia] genUploadInfo failed: {info_data}")
                return None

            upload_url = info_data["data"]["uploadUrl"]
            resource_url = info_data["data"]["resourceUrl"]
            object_name = info_data["data"]["objectName"]

            put_headers = {"Content-Type": "application/octet-stream", "content-md5": md5}
            put_req_url, _, put_req_h = apply_resin_proxy(upload_url, account.user_id, put_headers)
            put_res = await client.put(put_req_url, content=binary_data, headers=put_req_h)
            if put_res.status_code != 200:
                print(f"[uploadMedia] PUT failed: {put_res.status_code}")
                return None

            from urllib.parse import quote

            parse_url = (
                f"https://aistudio.xiaomimimo.com/open-apis/resource/parse"
                f"?fileUrl={quote(resource_url, safe='')}"
                f"&objectName={quote(object_name, safe='')}"
                f"&model={model}"
                f"&xiaomichatbot_ph={ph}"
            )
            parse_headers = {
                "Cookie": cookie,
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": "https://aistudio.xiaomimimo.com/",
                "Origin": "https://aistudio.xiaomimimo.com"
            }
            parse_req_url, _, parse_req_h = apply_resin_proxy(parse_url, account.user_id, parse_headers)

            parse_res = None
            for attempt in range(5):
                try:
                    resp = await client.post(parse_req_url, json={}, headers=parse_req_h)
                    data = resp.json()
                    if data.get("code") == 0 and data.get("data", {}).get("id"):
                        parse_res = data
                        import asyncio
                        await asyncio.sleep(3)
                        break
                except Exception:
                    pass
                import asyncio
                await asyncio.sleep(2)

            if not parse_res:
                print("[uploadMedia] Parse failed after retries")
                return None

            resource_id = parse_res["data"]["id"]
            is_video = mime_type.startswith("video/")
            is_audio = mime_type.startswith("audio/")
            media_type = "video" if is_video else ("audio" if is_audio else "image")

            return {
                "mediaType": media_type,
                "fileUrl": resource_url,
                "compressedVideoUrl": "",
                "audioTrackUrl": resource_url if is_audio else "",
                "name": file_name,
                "size": len(binary_data),
                "status": "completed",
                "objectName": object_name,
                "tokenUsage": parse_res["data"].get("tokenUsage", 106),
                "url": resource_id
            }

        except Exception as e:
            print(f"[uploadMedia] Error: {e}")
            return None


def build_query_from_messages(
    messages: list,
    tools: list = None,
    passthrough: bool = False,
) -> str:
    """从消息列表构建查询字符串。

    采用强隔离的 MMML XML 标签结构防止 Prompt Injection。
    """
    from .tool_call import build_tool_prompt

    query_parts = []
    system_text = ""

    for msg in messages:
        role = msg.role
        content = msg.content or ""

        if role == "system":
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                content = " ".join(text_parts)
            system_text += str(content).strip() + "\n"
            continue

        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = " ".join(text_parts)

        # 把 assistant 工具调用对象转换为文本（MMML 标签形式）
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            tool_str = _serialize_tool_calls(msg.tool_calls)
            # 兼容：如果 assistant 已有文本内容，则拼接，否则直接使用工具调用字符串
            content = f"{content}\n{tool_str}" if content else tool_str
            content = content.strip()

        if role == "tool":
            tool_call_id = getattr(msg, 'tool_call_id', '') or ''
            clean = re.sub(r'\[TOOL_RESULT\]\s*', '', content, flags=re.IGNORECASE)
            clean = clean.strip()
            # 转义 CDATA 避免嵌套导致 XML 解析破坏
            clean_cdata = clean.replace(']]>', ']]]]><![CDATA[>')
            content = f'<|MMML|tool_response id="{tool_call_id}">\n<![CDATA[\n{clean_cdata}\n]]>\n</|MMML|tool_response>'
            query_parts.append(content)
        elif role == "user":
            query_parts.append(f"<|MMML|user>\n{content}\n</|MMML|user>")
        elif role == "assistant":
            query_parts.append(f"<|MMML|assistant>\n{content}\n</|MMML|assistant>")
        else:
            query_parts.append(f"<|MMML|{role}>\n{content}\n</|MMML|{role}>")

    system_text = system_text.strip()

    # 工具提示词嵌入 system 消息
    if tools:
        tool_prompt = build_tool_prompt(tools, passthrough=passthrough)
        if tool_prompt:
            tool_block = f"<|MMML|tools_definition>\n{tool_prompt}\n</|MMML|tools_definition>"
            if system_text:
                system_text = system_text + "\n\n" + tool_block
            else:
                system_text = tool_block

    # system 消息插入最前面
    if system_text:
        query_parts.insert(0, f"<|MMML|system_instructions>\n{system_text}\n</|MMML|system_instructions>")

    return "\n\n".join(query_parts)
