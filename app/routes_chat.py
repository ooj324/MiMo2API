"""聊天与SSE清理路由 — MiMo2API"""

import time
import uuid
import json
import asyncio
import re
import httpx
from typing import Optional, Tuple
from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse

from .models import (
    OpenAIRequest, OpenAIResponse, OpenAIChoice, OpenAIMessage,
    OpenAIDelta, OpenAIUsage
)
from .config import config_manager
from .mimo_client import MimoClient, MimoApiError
from .utils import build_query_from_messages, extract_medias_from_messages, upload_media_to_mimo, upload_text_file_to_mimo
from .tool_call import extract_tool_call, get_tool_names, clean_tool_text
from .tool_sieve import StreamSieve
from .usage_store import add_usage as _add_usage
from .session_store import (
    get_or_create_session as _get_or_create_session,
    commit_session_turn as _commit_session_turn,
    find_existing_session_account as _find_existing_session_account,
)

router = APIRouter()

# ─── 常量 ─────────────────────────────────────────────────────

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"


# ─── API Key 验证 ─────────────────────────────────────────────

def validate_api_key(authorization: Optional[str]) -> bool:
    if not authorization:
        return False
    key = authorization.replace("Bearer ", "").strip()
    return config_manager.validate_api_key(key)


# ─── 文本清洗辅助函数 ────────────────────────────────────────

def _strip_tool_result_blocks(text: str) -> str:
    """移除模型幻觉输出的 TOOL_RESULT 标签。

    模型看到上下文中 [TOOL_RESULT] 和 <tool_result> 格式后学会复述。
    移除所有已知格式。
    """
    if not text:
        return text
    cleaned = re.sub(r'\[TOOL_RESULT\]\s*', '', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'\[/TOOL_RESULT\]\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\[tool_result\s+id=\S+\]\s*', '', cleaned, flags=re.IGNORECASE)
    # XML 格式: <tool_result>...</tool_result>（模型学会的另一种格式）
    cleaned = re.sub(r'</?tool_result>\s*', '', cleaned, flags=re.IGNORECASE)
    return cleaned


def _strip_citations(text: str) -> str:
    """移除 MiMo 模型输出的引用标记，如 (citation:1)(citation:14)。"""
    if not text:
        return text
    return re.sub(r'\(citation:\d+\)\s*', '', text)


def _camel_case(name: str) -> str:
    """snake_case -> camelCase: web_search -> webSearch"""
    parts = name.split('_')
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])


def _strip_tool_name_prefix(text: str, tool_names: list) -> str:
    """去掉模型作为独立 SSE 事件输出的工具名（如 'webSearch'）。

    处理 snake_case 和 camelCase 变体，大小写不敏感。
    """
    if not text or not tool_names:
        return text
    variants = []
    for n in tool_names:
        variants.append(re.escape(n))
        if '_' in n:
            variants.append(re.escape(_camel_case(n)))
    escaped = '|'.join(variants)
    cleaned = re.sub(rf'^\s*({escaped})\s*\n?', '', text, flags=re.IGNORECASE)
    return cleaned


def _strip_mimo_prefix(text: str) -> str:
    """通用 MiMo 原生前缀清理（含 IGNORECASE）。

    在 mimo_client 层已过滤 SSE 事件，此处做兜底。
    """
    if not text:
        return text
    prefixes = ['webSearch', 'getTimeInfo', 'getTime', 'sessionSearch',
                'imageSearch', 'fileSearch', 'getLocation', 'webExtract',
                'getWeather', 'calculator']
    escaped = '|'.join(re.escape(p) for p in prefixes)
    cleaned = re.sub(rf'^\s*({escaped})\s*\n?', '', text, flags=re.IGNORECASE)
    return cleaned


def _clean_response_text(text: str, tool_names: list = None) -> str:
    """综合文本清理管道：TOOL_RESULT + 引用 + 工具前缀 + MiMo前缀 + 工具文本残留。"""
    text = _strip_tool_result_blocks(text)
    text = _strip_citations(text)
    if tool_names:
        text = _strip_tool_name_prefix(text, tool_names)
    text = _strip_mimo_prefix(text)
    text = clean_tool_text(text)
    return text


# ─── Think 标签处理 ──────────────────────────────────────────

def _safe_flush(text: str) -> Tuple[str, str]:
    """分割文本为 (安全发送, 保留在缓冲区)。

    仅保留可能是 <think> 或 </think> 部分标签的最长后缀。
    其余全部立即刷新，避免 silence gap 导致客户端进入缓冲模式。
    """
    last_lt = text.rfind('<')
    if last_lt == -1:
        return text, ""
    suffix = text[last_lt:]
    if THINK_OPEN.startswith(suffix) or THINK_CLOSE.startswith(suffix):
        return text[:last_lt], suffix
    return text, ""


def _split_think(text: str) -> Tuple[str, str]:
    """从文本中分离 think 块和正文。

    Returns: (main_content, think_content)
    """
    start = text.find(THINK_OPEN)
    if start == -1:
        return text, ""

    end = text.find(THINK_CLOSE, start)
    if end == -1:
        return text[:start].strip(), text[start + len(THINK_OPEN):]

    think_content = text[start + len(THINK_OPEN):end]
    main = text[:start] + text[end + len(THINK_CLOSE):]
    return main.strip(), think_content


# ─── 响应构建 ─────────────────────────────────────────────────

def _build_response(
    msg_id: str, model: str,
    content: str = None, tool_calls: list = None,
    finish_reason: str = "stop", usage: dict = None
) -> OpenAIResponse:
    """统一构建 OpenAI 非流式响应。"""
    message = OpenAIMessage(role="assistant", content=content, tool_calls=tool_calls)
    usage_obj = None
    if usage:
        usage_obj = OpenAIUsage(
            prompt_tokens=usage.get("promptTokens", 0),
            completion_tokens=usage.get("completionTokens", 0),
            total_tokens=usage.get("promptTokens", 0) + usage.get("completionTokens", 0)
        )
    return OpenAIResponse(
        id=msg_id, object="chat.completion",
        created=int(time.time()), model=model,
        choices=[OpenAIChoice(index=0, message=message, finish_reason=finish_reason)],
        usage=usage_obj or OpenAIUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    )


def _build_chunk(
    msg_id: str, model: str,
    content: str = None, reasoning: str = None,
    tool_calls: list = None, finish_reason: str = None,
    role: str = None, created: int = None
) -> str:
    """统一构建 SSE chunk 字符串。

    exclude_none=True 去除 null 字段，避免客户端因 message:null
    等非标准字段误判为非流式模式。
    reasoning 同时输出 reasoning 和 reasoning_content（RikkaHub 兼容）。
    """
    delta = OpenAIDelta(
        role=role, content=content,
        reasoning=reasoning, tool_calls=tool_calls
    )
    chunk = OpenAIResponse(
        id=msg_id, object="chat.completion.chunk",
        created=created if created is not None else int(time.time()),
        model=model,
        choices=[OpenAIChoice(index=0, delta=delta, finish_reason=finish_reason)]
    )
    data = chunk.dict(exclude_none=True)
    if reasoning:
        for choice in data.get('choices', []):
            d = choice.get('delta', {})
            if 'reasoning' in d:
                d['reasoning_content'] = reasoning
    return f"data: {json.dumps(data)}\n\n"

def _build_usage_chunk(msg_id: str, model: str, usage: dict, created: int = None) -> str:
    """构建包含用量的结束 chunk。"""
    usage_obj = OpenAIUsage(
        prompt_tokens=usage.get("promptTokens", 0),
        completion_tokens=usage.get("completionTokens", 0),
        total_tokens=usage.get("promptTokens", 0) + usage.get("completionTokens", 0)
    )
    chunk = OpenAIResponse(
        id=msg_id, object="chat.completion.chunk",
        created=created if created is not None else int(time.time()),
        model=model,
        choices=[],
        usage=usage_obj
    )
    return f"data: {json.dumps(chunk.dict(exclude_none=True))}\n\n"


# ─── 聊天接口 ─────────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(
    request: OpenAIRequest,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    """OpenAI兼容的聊天接口。"""

    session_reuse = config_manager.config.session_reuse
    account = None

    if session_reuse:
        existing_account_id = _find_existing_session_account(request.messages, request.model)
        if existing_account_id:
            for acc in config_manager.config.mimo_accounts:
                if acc.user_id == existing_account_id and acc.is_valid:
                    account = acc
                    break

    if not account:
        account = config_manager.get_next_account()

    if not account:
        raise HTTPException(status_code=503, detail={"error": {"message": "no mimo account"}})

    # 转换 tools 为字典列表
    tools_dict = [t.dict() if hasattr(t, 'dict') else t for t in request.tools] if request.tools else None

    # 提取媒体和文本文件
    query_text, base64_medias, text_files, processed_msgs = extract_medias_from_messages(request.messages)
    effective_model = request.model

    multi_medias = []
    if base64_medias:
        for media in base64_medias:
            media_obj = await upload_media_to_mimo(
                media["base64"], media["mimeType"], account, effective_model
            )
            if media_obj:
                multi_medias.append(media_obj)

    # 上传文本文件到 MiMo（同样走 multiMedias，mediaType="file"）
    if text_files:
        for tf in text_files:
            media_obj = await upload_text_file_to_mimo(
                tf["base64"], tf["filename"], tf["mimeType"], account, effective_model
            )
            if media_obj:
                multi_medias.append(media_obj)

    # 构建查询与会话管理
    passthrough_mode = request.passthrough or config_manager.config.tools_passthrough
    tools_no_parsing = request.tools_no_parsing or config_manager.config.tools_no_parsing
    thinking = bool(request.reasoning_effort)
    client = MimoClient(account)
    
    if session_reuse:
        # 会话管理：通过消息指纹续接 MiMo conversationId
        conv_id, conv_is_new, matched_count = _get_or_create_session(
            account.user_id, request.messages, request.model
        )
        
        # 剥离出所有的非 system 消息
        non_sys_messages = [m for m in request.messages if m.role != 'system']
        sys_messages = [m for m in request.messages if m.role == 'system']

        # 仅保留新增的消息 (Delta)
        new_messages = non_sys_messages[matched_count:]
        
        if not new_messages:
            delta_request_messages = request.messages
            query = build_query_from_messages(delta_request_messages, tools=tools_dict, passthrough=passthrough_mode)
        else:
            if matched_count == 0:
                delta_request_messages = sys_messages + new_messages
                query = build_query_from_messages(delta_request_messages, tools=tools_dict, passthrough=passthrough_mode)
            else:
                # 增量复用模式：由于 MiMo 服务端已经缓存了首次发包的系统指令，
                # 这里不要在增量包中重复发送系统指令和工具定义，否则会破坏模型的上下文感知。
                delta_request_messages = new_messages
                query = build_query_from_messages(delta_request_messages, tools=None, passthrough=passthrough_mode)
    else:
        # 不复用会话：直接传 None 作为 conv_id，全量消息拼接
        conv_id = None
        query = build_query_from_messages(request.messages, tools=tools_dict, passthrough=passthrough_mode)

    # 流式响应
    if request.stream:
        include_usage = config_manager.config.stream_include_usage
        if request.stream_options and request.stream_options.include_usage is not None:
            include_usage = request.stream_options.include_usage

        return StreamingResponse(
            _stream_response(client, query, thinking, effective_model, None if tools_no_parsing else tools_dict, multi_medias, passthrough=passthrough_mode,
                             conv_id=conv_id, account_id=account.user_id, messages=request.messages, include_usage=include_usage),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            }
        )

    # 非流式响应
    try:
        content, think_content, usage = await client.call_api(
            query, thinking, effective_model, multi_medias, conversation_id=conv_id)

        # 保存用量
        if usage:
            _add_usage(request.model, usage.get("promptTokens", 0), usage.get("completionTokens", 0))
            if conv_id:
                _commit_session_turn(account.user_id, conv_id, request.messages, usage.get("promptTokens", 0))

        # 清理模型输出杂质
        content = _strip_tool_result_blocks(content)
        content = _strip_citations(content)
        content = clean_tool_text(content)

        msg_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

        # 提取工具调用
        tool_names = []
        tool_calls = None
        if tools_dict and not tools_no_parsing:
            tool_names = get_tool_names(tools_dict)
            result = extract_tool_call(content, tool_names)
            if result:
                if result[0]:
                    tool_calls = result[0]  # List[Dict]
                if result[1] is not None:
                    content = result[1]  # 使用清理后的文本（含 MMML 残留清理）

        # 清洗工具名前缀
        content = _strip_tool_name_prefix(content, tool_names)

        if tool_calls:
            return _build_response(
                msg_id, request.model,
                content=None, tool_calls=tool_calls,
                finish_reason="tool_calls", usage=usage
            )
        else:
            full_content = content
            if think_content:
                full_content = f"{THINK_OPEN}{think_content}{THINK_CLOSE}\n{content}"
            return _build_response(
                msg_id, request.model,
                content=full_content, finish_reason="stop", usage=usage
            )

    except MimoApiError as e:
        raise HTTPException(status_code=e.status_code, detail={"error": {"message": f"MiMo API: {e.response_body[:200]}"}})
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail={"error": {"message": str(e)}})


async def _stream_response(
    client: MimoClient, query: str, thinking: bool, model: str,
    tools: list = None, multi_medias: list = None,
    passthrough: bool = False,
    conv_id: str = None, account_id: str = None,
    messages: list = None, include_usage: bool = False,
):
    """流式响应生成器。"""
    msg_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created_t = int(time.time())

    # 初始 role delta
    yield _build_chunk(msg_id, model, created=created_t, role="assistant")

    has_tools = tools is not None

    try:
        if has_tools:
            # ═══════════════════════════════════════════════════
            # 有工具定义：reasoning 流式，正文通过筛分流式
            # sieve 实时分离 TOOL_CALL 文本与普通正文
            # ═══════════════════════════════════════════════════
            tool_names = get_tool_names(tools)
            sieve = StreamSieve(
                mode='tool_call',
                parse_fn=lambda text: extract_tool_call(text, tool_names),
            )
            collected_tool_calls = []
            content_buffer_chunks = []  # 收集 content（工具调用时丢弃）
            in_think = False
            buffer = ""
            last_usage = None

            async for sse_data in client.stream_api(query, thinking, model, multi_medias):
                # 用量事件
                if sse_data.get("type") == "usage":
                    last_usage = sse_data
                    continue
                chunk = sse_data.get("content", "")
                if not chunk:
                    continue

                buffer += chunk.replace("\x00", "")

                # 处理 think 标签
                while True:
                    if not in_think:
                        idx = buffer.find(THINK_OPEN)
                        if idx != -1:
                            safe, keep = _safe_flush(buffer[:idx])
                            if safe:
                                # Feed through sieve — stream text, collect tool calls
                                for ev in sieve.feed(safe):
                                    if ev.type == 'text':
                                        clean = _clean_response_text(ev.data, tool_names)
                                        if clean:
                                            content_buffer_chunks.append(clean)
                                            yield _build_chunk(msg_id, model, created=created_t, content=clean)
                                    elif ev.type == 'tool_calls':
                                        collected_tool_calls.extend(ev.data)
                            in_think = True
                            buffer = buffer[idx + len(THINK_OPEN):]
                            continue

                        safe, keep = _safe_flush(buffer)
                        if safe:
                            for ev in sieve.feed(safe):
                                if ev.type == 'text':
                                    clean = _clean_response_text(ev.data, tool_names)
                                    if clean:
                                        content_buffer_chunks.append(clean)
                                        yield _build_chunk(msg_id, model, created=created_t, content=clean)
                                elif ev.type == 'tool_calls':
                                    collected_tool_calls.extend(ev.data)
                        buffer = keep
                        break
                    else:
                        idx = buffer.find(THINK_CLOSE)
                        if idx != -1:
                            safe, keep = _safe_flush(buffer[:idx])
                            if safe:
                                yield _build_chunk(msg_id, model, created=created_t, reasoning=safe)
                            in_think = False
                            buffer = buffer[idx + len(THINK_CLOSE):]
                            continue

                        safe, keep = _safe_flush(buffer)
                        if safe:
                            yield _build_chunk(msg_id, model, created=created_t, reasoning=safe)
                        buffer = keep
                        break

            # 正文留在 buffer 中的追加到 sieve
            if buffer and not in_think:
                for ev in sieve.feed(buffer):
                    if ev.type == 'text':
                        clean = _clean_response_text(ev.data, tool_names)
                        if clean:
                            content_buffer_chunks.append(clean)
                            yield _build_chunk(msg_id, model, created=created_t, content=clean)
                    elif ev.type == 'tool_calls':
                        collected_tool_calls.extend(ev.data)

            # 刷新 sieve，回收最终残留 text/tool_calls
            for ev in sieve.flush():
                if ev.type == 'text':
                    clean = _clean_response_text(ev.data, tool_names)
                    if clean:
                        content_buffer_chunks.append(clean)
                        yield _build_chunk(msg_id, model, created=created_t, content=clean)
                elif ev.type == 'tool_calls':
                    collected_tool_calls.extend(ev.data)

            if collected_tool_calls:
                # 有工具调用 → 不发 content，只发 tool_calls
                for i, tc in enumerate(collected_tool_calls):
                    # 兼容严格的 OpenAI 客户端：分两次发送 name 和 arguments
                    chunk1_tc = {
                        "index": i,
                        "id": tc.get("id"),
                        "type": "function",
                        "function": {
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": ""
                        }
                    }
                    yield _build_chunk(msg_id, model, created=created_t, tool_calls=[chunk1_tc])
                    
                    chunk2_tc = {
                        "index": i,
                        "function": {
                            "arguments": tc.get("function", {}).get("arguments", "")
                        }
                    }
                    yield _build_chunk(msg_id, model, created=created_t, tool_calls=[chunk2_tc])

                yield _build_chunk(msg_id, model, created=created_t, finish_reason="tool_calls")
                if include_usage and last_usage:
                    yield _build_usage_chunk(msg_id, model, last_usage, created_t)
                yield "data: [DONE]\n\n"
                if last_usage:
                    _add_usage(model, last_usage.get("promptTokens", 0), last_usage.get("completionTokens", 0))
                if conv_id and messages:
                    _commit_session_turn(account_id, conv_id, messages, last_usage.get("promptTokens", 0) if last_usage else 0)
                return

            # 无工具调用：content 已在流中发出，只需发 stop
            yield _build_chunk(msg_id, model, created=created_t, finish_reason="stop")
            if include_usage and last_usage:
                yield _build_usage_chunk(msg_id, model, last_usage, created_t)
            yield "data: [DONE]\n\n"
            if last_usage:
                _add_usage(model, last_usage.get("promptTokens", 0), last_usage.get("completionTokens", 0))
            if conv_id and messages:
                _commit_session_turn(account_id, conv_id, messages, last_usage.get("promptTokens", 0) if last_usage else 0)

        else:
            # ═══════════════════════════════════════════════════
            # 无工具定义：实时流式输出
            # ═══════════════════════════════════════════════════
            buffer = ""
            in_think = False
            last_usage = None

            async for sse_data in client.stream_api(query, thinking, model, multi_medias):
                if sse_data.get("type") == "usage":
                    last_usage = sse_data
                    continue
                chunk = sse_data.get("content", "")
                if not chunk:
                    continue

                buffer += chunk.replace("\x00", "")

                while True:
                    if not in_think:
                        idx = buffer.find(THINK_OPEN)
                        if idx != -1:
                            safe, keep = _safe_flush(buffer[:idx])
                            if safe:
                                clean = _clean_response_text(safe)
                                if clean:
                                    yield _build_chunk(msg_id, model, created=created_t, content=clean)
                            in_think = True
                            buffer = buffer[idx + len(THINK_OPEN):]
                            continue

                        safe, keep = _safe_flush(buffer)
                        if safe:
                            clean = _clean_response_text(safe)
                            if clean:
                                yield _build_chunk(msg_id, model, created=created_t, content=clean)
                        buffer = keep
                        break
                    else:
                        idx = buffer.find(THINK_CLOSE)
                        if idx != -1:
                            safe, keep = _safe_flush(buffer[:idx])
                            if safe:
                                yield _build_chunk(msg_id, model, created=created_t, reasoning=safe)
                            in_think = False
                            buffer = buffer[idx + len(THINK_CLOSE):]
                            continue

                        safe, keep = _safe_flush(buffer)
                        if safe:
                            yield _build_chunk(msg_id, model, created=created_t, reasoning=safe)
                        buffer = keep
                        break

            # 发送剩余内容
            if buffer:
                clean = _clean_response_text(buffer)
                if clean:
                    if in_think:
                        yield _build_chunk(msg_id, model, created=created_t, reasoning=clean)
                    else:
                        yield _build_chunk(msg_id, model, created=created_t, content=clean)

            yield _build_chunk(msg_id, model, created=created_t, finish_reason="stop")
            if include_usage and last_usage:
                yield _build_usage_chunk(msg_id, model, last_usage, created_t)
            yield "data: [DONE]\n\n"
            if last_usage:
                _add_usage(model, last_usage.get("promptTokens", 0), last_usage.get("completionTokens", 0))
            if conv_id and messages:
                _commit_session_turn(account_id, conv_id, messages, last_usage.get("promptTokens", 0) if last_usage else 0)

    except httpx.ReadTimeout:
        # 连接读取超时 — 发送优雅结束
        yield _build_chunk(msg_id, model, created=created_t, finish_reason="length")
        yield "data: [DONE]\n\n"
    except MimoApiError as e:
        error_data = {"error": {"message": f"MiMo API {e.status_code}: {e.response_body[:200]}",
                                "type": "upstream_error", "code": e.status_code}}
        yield f"data: {json.dumps(error_data)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': {'message': str(e)}})}\n\n"
        yield "data: [DONE]\n\n"
