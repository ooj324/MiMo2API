"""Responses API 兼容路由 — MiMo2API"""

import time
import uuid
import json
import re
import httpx
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse

from .models import OpenAIResponse, OpenAIChoice, OpenAIMessage, OpenAIUsage, OpenAIDelta
from .config import config_manager
from .mimo_client import MimoClient, MimoApiError
from .utils import extract_medias_from_messages, upload_media_to_mimo, upload_text_file_to_mimo, build_query_from_messages
from .tool_call import extract_tool_call, get_tool_names, clean_tool_text
from .tool_sieve import StreamSieve
from .usage_store import add_usage as _add_usage
from .session_store import find_existing_session_account as _find_existing_session_account
from .response_store import (
    save_response_record as _save_response_record,
    get_response_record as _get_response_record,
    delete_response_record as _delete_response_record,
    update_response_record as _update_response_record,
)
from .routes_chat import (
    validate_api_key, _strip_tool_result_blocks, _strip_citations,
    _strip_tool_name_prefix, _safe_flush, _clean_response_text,
    THINK_OPEN, THINK_CLOSE
)

router = APIRouter()

# ─── 常量 ────────────────────────────────────────────────────

_RESPONSE_TERMINAL_STATUSES = {"completed", "failed", "incomplete", "cancelled"}

# ─── 辅助函数 ─────────────────────────────────────────────────

def _gen_response_id() -> str:
    """生成响应ID：resp_ + uuid4 hex[:32]"""
    return f"resp_{uuid.uuid4().hex[:32]}"


def _response_text_config(body: dict) -> dict:
    """从 body 中提取 text.format 配置。"""
    text = body.get("text")
    if isinstance(text, dict):
        cfg = dict(text)
        fmt = cfg.get("format")
        if isinstance(fmt, dict):
            cfg["format"] = dict(fmt)
        elif isinstance(fmt, str):
            cfg["format"] = {"type": fmt}
        else:
            cfg["format"] = {"type": "text"}
        return cfg
    return {"format": {"type": "text"}}


def _json_schema_from_text_config(text_config: dict | None) -> dict | None:
    """从 text_config 中提取 JSON Schema 字典。"""
    fmt = text_config.get("format") if isinstance(text_config, dict) else None
    if not isinstance(fmt, dict) or fmt.get("type") != "json_schema":
        return None
    schema = fmt.get("schema")
    if isinstance(schema, dict):
        return schema
    json_schema = fmt.get("json_schema")
    if isinstance(json_schema, dict):
        nested = json_schema.get("schema")
        return nested if isinstance(nested, dict) else json_schema
    return None


def _response_text_item(text: str, item_id: str | None = None) -> dict:
    """构建 OpenAI Responses output_text item。"""
    return {
        "id": item_id or f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [{
            "type": "output_text",
            "text": text or "",
            "annotations": [],
        }],
    }


def _response_reasoning_item(summary_text: str, item_id: str | None = None) -> dict:
    """构建 reasoning summary item。"""
    return {
        "id": item_id or f"rs_{uuid.uuid4().hex[:24]}",
        "type": "reasoning",
        "summary": [{
            "type": "summary_text",
            "text": summary_text or "",
        }],
    }


def _response_function_call_item(tool_call: dict, call_id: str | None = None) -> dict:
    """从 tool_call 构建 function_call item。"""
    fn = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
    return {
        "id": f"fc_{uuid.uuid4().hex[:24]}",
        "type": "function_call",
        "call_id": call_id or tool_call.get("id") or f"call_{uuid.uuid4().hex[:24]}",
        "name": fn.get("name", ""),
        "arguments": fn.get("arguments", "{}"),
        "status": "completed",
    }


def _make_response_object(
    response_id: str, model: str, status: str,
    items: list, usage: dict | None,
    incomplete_details: dict | None = None,
) -> dict:
    """构建完整的 Response 对象字典。"""
    text_cfg = {"format": {"type": "text"}}
    output_text = ""
    for item in items or []:
        if item.get("type") == "message":
            for part in item.get("content", []) or []:
                if part.get("type") == "output_text":
                    output_text = part.get("text", "") or ""
    usage_obj = None
    if usage:
        usage_obj = {
            "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": int(usage.get("completion_tokens", 0) or 0),
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
        }
    return {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": status,
        "error": None,
        "incomplete_details": incomplete_details,
        "instructions": None,
        "max_output_tokens": None,
        "model": model,
        "output": items or [],
        "parallel_tool_calls": True,
        "previous_response_id": None,
        "reasoning": {},
        "store": True,
        "temperature": None,
        "text": text_cfg,
        "tool_choice": "auto",
        "tools": [],
        "top_p": None,
        "truncation": "disabled",
        "usage": usage_obj,
        "user": None,
        "metadata": {},
        "output_text": output_text,
    }


def _convert_response_input_to_messages(input_data) -> list[dict]:
    """将 Responses API input 格式转换为 OpenAI Chat 消息列表。"""
    messages: list[dict] = []
    if input_data is None:
        return messages
    items = input_data if isinstance(input_data, list) else [input_data]
    for item in items:
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        role = item.get("role")

        if role in ("system", "user", "assistant", "tool"):
            content = item.get("content", "")
            if isinstance(content, list):
                parts = []
                assistant_tool_calls = []
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    ptype = part.get("type")
                    if ptype in ("input_text", "output_text", "text"):
                        parts.append({"type": "text", "text": part.get("text", "")})
                    elif ptype == "input_image":
                        image_url = part.get("image_url") or part.get("url") or ""
                        if image_url:
                            parts.append({"type": "image_url", "image_url": {"url": image_url}})
                    elif ptype == "input_file":
                        parts.append({
                            "type": "file",
                            "file": {
                                "filename": part.get("filename") or "file.txt",
                                "file_data": part.get("file_data") or part.get("data") or "",
                            }
                        })
                    elif ptype == "function_call" and role == "assistant":
                        assistant_tool_calls.append({
                            "id": part.get("call_id") or part.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                            "type": "function",
                            "function": {
                                "name": part.get("name", ""),
                                "arguments": part.get("arguments", "{}") if isinstance(part.get("arguments", "{}"), str)
                                else json.dumps(part.get("arguments", {}), ensure_ascii=False),
                            }
                        })
                msg = {"role": role, "content": parts if parts else ""}
                if assistant_tool_calls:
                    msg["tool_calls"] = assistant_tool_calls
                    if not parts:
                        msg["content"] = None
                messages.append(msg)
            else:
                msg = {"role": role, "content": content}
                if role == "assistant" and item_type == "function_call":
                    msg["tool_calls"] = [{
                        "id": item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": item.get("name", ""),
                            "arguments": item.get("arguments", "{}") if isinstance(item.get("arguments", "{}"), str)
                            else json.dumps(item.get("arguments", {}), ensure_ascii=False),
                        }
                    }]
                    if content in ("", None):
                        msg["content"] = None
                messages.append(msg)
            continue

        if item_type == "message":
            content = item.get("content", [])
            role = item.get("role", "user")
            parts = []
            assistant_tool_calls = []
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    ptype = part.get("type")
                    if ptype in ("input_text", "output_text", "text"):
                        parts.append({"type": "text", "text": part.get("text", "")})
                    elif ptype == "input_image":
                        image_url = part.get("image_url") or part.get("url") or ""
                        if image_url:
                            parts.append({"type": "image_url", "image_url": {"url": image_url}})
                    elif ptype == "input_file":
                        parts.append({
                            "type": "file",
                            "file": {
                                "filename": part.get("filename") or "file.txt",
                                "file_data": part.get("file_data") or part.get("data") or "",
                            }
                        })
                    elif ptype == "function_call" and role == "assistant":
                        assistant_tool_calls.append({
                            "id": part.get("call_id") or part.get("id") or f"call_{uuid.uuid4().hex[:24]}",
                            "type": "function",
                            "function": {
                                "name": part.get("name", ""),
                                "arguments": part.get("arguments", "{}") if isinstance(part.get("arguments", "{}"), str)
                                else json.dumps(part.get("arguments", {}), ensure_ascii=False),
                            }
                        })
            msg = {"role": role, "content": parts if parts else ""}
            if assistant_tool_calls:
                msg["tool_calls"] = assistant_tool_calls
                if not parts:
                    msg["content"] = None
            messages.append(msg)
            continue

        if item_type == "function_call_output":
            output = item.get("output", "")
            if isinstance(output, dict):
                output = json.dumps(output, ensure_ascii=False)
            elif output is None:
                output = ""
            tool_message = {"role": "tool", "content": str(output)}
            if item.get("call_id"):
                tool_message["tool_call_id"] = item.get("call_id")
            messages.append(tool_message)
            continue

        if item_type in ("input_text", "text"):
            messages.append({"role": "user", "content": item.get("text", "")})

    return messages


def _normalize_structured_output_text(output_text: str, text_config: dict | None) -> str:
    """对 structured output (json_object/json_schema) 规范化输出文本。"""
    if not output_text or not isinstance(text_config, dict):
        return output_text
    fmt = text_config.get("format")
    if not isinstance(fmt, dict):
        return output_text
    fmt_type = fmt.get("type")
    if fmt_type not in ("json_object", "json_schema"):
        return output_text

    # 尝试从文本中提取 JSON
    candidate = output_text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    start_candidates = [i for i in (candidate.find("{"), candidate.find("[")) if i != -1]
    if start_candidates:
        start = min(start_candidates)
        end_candidates = [candidate.rfind("}"), candidate.rfind("]")]
        end = max(end_candidates)
        if end > start:
            candidate = candidate[start:end + 1]
    try:
        parsed = json.loads(candidate)
        return json.dumps(parsed, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError, TypeError):
        return output_text


# ─── Token 计数辅助 ──────────────────────────────────────────

def _count_response_input_tokens(
    input_value,
    instructions: str | None = None,
    tools: list[dict] | None = None,
) -> int:
    """估算 input tokens：字符数 / 4 的简单启发式方法。"""
    total_chars = 0
    if isinstance(input_value, list):
        serialized = json.dumps(input_value, ensure_ascii=False)
        total_chars += len(serialized)
    elif isinstance(input_value, str):
        total_chars += len(input_value)
    if instructions:
        total_chars += len(instructions)
    if tools:
        total_chars += len(json.dumps(tools, ensure_ascii=False))
    return max(1, total_chars // 4)


def _count_tokens(text: str) -> int:
    """简单 token 估算：字符数 / 4。"""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _build_response_usage(usage: dict | None) -> dict:
    """将 MiMo usage 转换为 Responses API usage 格式。"""
    usage = usage or {}
    input_tokens = int(usage.get("promptTokens", 0) or usage.get("prompt_tokens", 0) or 0)
    output_tokens = int(usage.get("completionTokens", 0) or usage.get("completion_tokens", 0) or 0)
    total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": total_tokens,
    }


def _extract_output_text(output: list[dict]) -> str:
    """从 output items 列表中提取文本内容。"""
    texts: list[str] = []
    for item in output or []:
        if item.get("type") == "message":
            for content in item.get("content", []) or []:
                if content.get("type") == "output_text":
                    texts.append(content.get("text", "") or "")
    return "".join(texts)


def _response_output_from_message(msg: dict) -> list[dict]:
    """从 OpenAI chat message 构建 Responses output items。"""
    output: list[dict] = []
    reasoning = msg.get("reasoning_content", "")
    if reasoning:
        output.append(_response_reasoning_item(reasoning))
    content = msg.get("content", "")
    if isinstance(content, str) and content:
        output.append(_response_text_item(content))
    tool_calls = msg.get("tool_calls") or []
    for tc in tool_calls:
        output.append(_response_function_call_item(tc))
    if not output:
        output.append(_response_text_item(""))
    return output


def _response_status_from_finish_reason(finish_reason: str) -> str:
    if finish_reason in ("stop", "tool_calls"):
        return "completed"
    if finish_reason in ("length", "content_filter"):
        return "incomplete"
    return "completed"


def _sse_json(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# ─── 核心函数：非流式 ────────────────────────────────────────

async def _do_response_chat(body: dict, account) -> tuple:
    """非流式 Responses API 聊天。

    Returns:
        (model_used, usage_dict, items_list)
    """
    model = body.get("model", "default")
    input_data = body.get("input", [])
    instructions = body.get("instructions")
    tools = body.get("tools")
    text_config = _response_text_config(body)

    # 转换 input 为消息列表
    messages = _convert_response_input_to_messages(input_data)

    # 处理 instructions：作为 system 消息前置
    if isinstance(instructions, str) and instructions.strip():
        messages.insert(0, {"role": "system", "content": instructions.strip()})

    # structured output 处理
    structured_format = text_config.get("format", {}).get("type")
    if structured_format in ("json_object", "json_schema"):
        has_system = any(m.get("role") == "system" for m in messages)
        if structured_format == "json_schema":
            schema = _json_schema_from_text_config(text_config)
            instruction_text = "Please respond with valid JSON matching this schema."
        else:
            schema = None
            instruction_text = "Please respond with valid JSON object."
        sys_instruction = {"role": "system", "content": instruction_text}
        if has_system:
            # 追加到最后一条 system 消息之后
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "system":
                    messages.insert(i + 1, sys_instruction)
                    break
        else:
            messages.insert(0, sys_instruction)

    # 转换 dict 消息为 OpenAIMessage 对象
    openai_messages = []
    for m in messages:
        openai_messages.append(OpenAIMessage(
            role=m.get("role", "user"),
            content=m.get("content"),
            tool_calls=m.get("tool_calls"),
            tool_call_id=m.get("tool_call_id"),
        ))

    # 提取媒体
    query_text, base64_medias, text_files, processed_msgs = extract_medias_from_messages(openai_messages)
    effective_model = model

    multi_medias = []
    if base64_medias:
        for media in base64_medias:
            media_obj = await upload_media_to_mimo(
                media["base64"], media["mimeType"], account, effective_model
            )
            if media_obj:
                multi_medias.append(media_obj)
    if text_files:
        for tf in text_files:
            media_obj = await upload_text_file_to_mimo(
                tf["base64"], tf["filename"], tf["mimeType"], account, effective_model
            )
            if media_obj:
                multi_medias.append(media_obj)

    # 构建 tools dict
    tools_dict = [dict(t) if hasattr(t, 'dict') else t for t in tools] if tools else None

    # 构建查询
    query = build_query_from_messages(openai_messages, tools=tools_dict)

    thinking = False

    # 调用 MimoClient
    client = MimoClient(account)
    try:
        content, think_content, usage = await client.call_api(
            query, thinking, effective_model, multi_medias
        )
    except MimoApiError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error": {"message": f"MiMo API: {e.response_body[:200]}"}}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail={"error": {"message": str(e)}})

    # 清理输出
    content = _strip_tool_result_blocks(content)
    content = _strip_citations(content)
    content = clean_tool_text(content)

    # 额外处理：模型可能输出多个 think 块，_parse_think_tags 只剥除了第一个
    remaining_thinks = []
    cleaned_content = re.sub(
        r'<think>(.*?)</think>',
        lambda m: remaining_thinks.append(m.group(1).strip()) or '',
        content,
        flags=re.DOTALL
    )
    # 过滤空 think 块（模型可能输出 <think></think>）
    remaining_thinks = [t for t in remaining_thinks if t]
    if remaining_thinks:
        content = cleaned_content.strip()
        extra_think = '\n'.join(remaining_thinks)
        think_content = (think_content + '\n' + extra_think).strip() if think_content else extra_think

    # 构建 items
    items = []
    has_thinking = False
    if think_content:
        items.append(_response_reasoning_item(think_content))
        has_thinking = True

    # 工具调用提取
    tool_names = []
    tool_calls = None
    if tools_dict:
        tool_names = get_tool_names(tools_dict)
        result = extract_tool_call(content, tool_names)
        if result:
            if result[0]:
                tool_calls = result[0]
            if result[1] is not None:
                content = result[1]  # 使用清理后的文本（含 MMML 残留清理）

    content = _strip_tool_name_prefix(content, tool_names)

    if tool_calls:
        for tc in tool_calls:
            items.append(_response_function_call_item(tc))
    elif content:
        normalized = _normalize_structured_output_text(content, text_config)
        items.append(_response_text_item(normalized))

    if not items:
        items.append(_response_text_item(""))

    return effective_model, usage, items


# ─── 核心函数：流式 ──────────────────────────────────────────

async def _stream_response_events(body: dict, account):
    """流式 Responses API 事件生成器。

    Yields:
        event dicts (response.created, response.output_text.delta, etc.)
    """
    model = body.get("model", "default")
    input_data = body.get("input", [])
    instructions = body.get("instructions")
    tools = body.get("tools")
    text_config = _response_text_config(body)

    # 转换 input 为消息列表（同非流式）
    messages = _convert_response_input_to_messages(input_data)
    if isinstance(instructions, str) and instructions.strip():
        messages.insert(0, {"role": "system", "content": instructions.strip()})

    structured_format = text_config.get("format", {}).get("type")
    if structured_format in ("json_object", "json_schema"):
        has_system = any(m.get("role") == "system" for m in messages)
        if structured_format == "json_schema":
            instruction_text = "Please respond with valid JSON matching this schema."
        else:
            instruction_text = "Please respond with valid JSON object."
        sys_instruction = {"role": "system", "content": instruction_text}
        if has_system:
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "system":
                    messages.insert(i + 1, sys_instruction)
                    break
        else:
            messages.insert(0, sys_instruction)

    openai_messages = []
    for m in messages:
        openai_messages.append(OpenAIMessage(
            role=m.get("role", "user"),
            content=m.get("content"),
            tool_calls=m.get("tool_calls"),
            tool_call_id=m.get("tool_call_id"),
        ))

    query_text, base64_medias, text_files, processed_msgs = extract_medias_from_messages(openai_messages)
    effective_model = model

    multi_medias = []
    if base64_medias:
        for media in base64_medias:
            media_obj = await upload_media_to_mimo(
                media["base64"], media["mimeType"], account, effective_model
            )
            if media_obj:
                multi_medias.append(media_obj)
    if text_files:
        for tf in text_files:
            media_obj = await upload_text_file_to_mimo(
                tf["base64"], tf["filename"], tf["mimeType"], account, effective_model
            )
            if media_obj:
                multi_medias.append(media_obj)

    tools_dict = [dict(t) if hasattr(t, 'dict') else t for t in tools] if tools else None
    query = build_query_from_messages(openai_messages, tools=tools_dict)
    thinking = False

    response_id = body.get("_response_id") or _gen_response_id()
    created_t = int(time.time())

    # 初始事件
    init_payload = {
        "id": response_id,
        "object": "response",
        "created_at": created_t,
        "status": "in_progress",
        "model": effective_model,
        "output": [],
        "usage": None,
    }
    yield {"type": "response.created", "response": dict(init_payload)}
    yield {"type": "response.in_progress", "response": dict(init_payload)}

    reasoning_parts: list[str] = []
    text_parts: list[str] = []
    reasoning_item_id = f"rs_{uuid.uuid4().hex[:24]}"
    message_item_id = f"msg_{uuid.uuid4().hex[:24]}"
    output_started: set[str] = set()
    output_indices: dict[str, int] = {}
    content_started = False
    tool_calls_map: dict[int, dict] = {}

    def _start_output_item(item: dict) -> tuple[int, dict | None]:
        item_id = item.get("id") or f"out_{len(output_indices)}"
        if item_id not in output_indices:
            output_indices[item_id] = len(output_indices)
        output_index = output_indices[item_id]
        if item_id not in output_started:
            output_started.add(item_id)
            return_event = {
                "type": "response.output_item.added",
                "output_index": output_index,
                "item": item,
            }
            return output_index, return_event
        return output_index, None

    client = MimoClient(account)
    has_tools = tools_dict is not None

    try:
        if has_tools:
            # 有工具定义：使用 StreamSieve
            tool_names = get_tool_names(tools_dict)
            sieve = StreamSieve(
                mode='tool_call',
                parse_fn=lambda text: extract_tool_call(text, tool_names),
            )
            in_think = False
            buffer = ""

            async for sse_data in client.stream_api(query, thinking, effective_model, multi_medias):
                if sse_data.get("type") == "usage":
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
                                for ev in sieve.feed(safe):
                                    if ev.type == 'text':
                                        clean = _clean_response_text(ev.data, tool_names)
                                        if clean:
                                            text_parts.append(clean)
                                            if not content_started:
                                                content_started = True
                                                item = _response_text_item("", message_item_id)
                                                oi, start_evt = _start_output_item(item)
                                                if start_evt:
                                                    yield start_evt
                                                yield {
                                                    "type": "response.content_part.added",
                                                    "item_id": message_item_id,
                                                    "output_index": oi,
                                                    "content_index": 0,
                                                    "part": item["content"][0],
                                                }
                                            yield {
                                                "type": "response.output_text.delta",
                                                "item_id": message_item_id,
                                                "output_index": output_indices.get(message_item_id, 0),
                                                "content_index": 0,
                                                "delta": clean,
                                            }
                                    elif ev.type == 'tool_calls':
                                        for tc in ev.data:
                                            idx = len(tool_calls_map)
                                            fc_item = _response_function_call_item(tc)
                                            fc_id = fc_item["id"]
                                            tool_calls_map[idx] = {
                                                "id": fc_id,
                                                "call_id": fc_item.get("call_id", fc_id),
                                                "name": tc.get("function", {}).get("name", ""),
                                                "arguments": tc.get("function", {}).get("arguments", "{}"),
                                                "status": "completed",
                                            }
                                            # output_item.added 不预填 arguments
                                            added_item = {k: v for k, v in fc_item.items() if k != "arguments"}
                                            oi, start_evt = _start_output_item(added_item)
                                            if start_evt:
                                                yield start_evt
                                            # 始终通过 delta 传递参数
                                            args_str = fc_item.get("arguments", "{}")
                                            yield {
                                                "type": "response.function_call_arguments.delta",
                                                "item_id": fc_id,
                                                "output_index": oi,
                                                "delta": args_str,
                                            }
                            in_think = True
                            buffer = buffer[idx + len(THINK_OPEN):]
                            continue

                        safe, keep = _safe_flush(buffer)
                        if safe:
                            for ev in sieve.feed(safe):
                                if ev.type == 'text':
                                    clean = _clean_response_text(ev.data, tool_names)
                                    if clean:
                                        text_parts.append(clean)
                                        if not content_started:
                                            content_started = True
                                            item = _response_text_item("", message_item_id)
                                            oi, start_evt = _start_output_item(item)
                                            if start_evt:
                                                yield start_evt
                                            yield {
                                                "type": "response.content_part.added",
                                                "item_id": message_item_id,
                                                "output_index": oi,
                                                "content_index": 0,
                                                "part": item["content"][0],
                                            }
                                        yield {
                                            "type": "response.output_text.delta",
                                            "item_id": message_item_id,
                                            "output_index": output_indices.get(message_item_id, 0),
                                            "content_index": 0,
                                            "delta": clean,
                                        }
                                elif ev.type == 'tool_calls':
                                    for tc in ev.data:
                                        idx = len(tool_calls_map)
                                        fc_item = _response_function_call_item(tc)
                                        fc_id = fc_item["id"]
                                        tool_calls_map[idx] = {
                                            "id": fc_id,
                                            "call_id": fc_item.get("call_id", fc_id),
                                            "name": tc.get("function", {}).get("name", ""),
                                            "arguments": tc.get("function", {}).get("arguments", "{}"),
                                            "status": "completed",
                                        }
                                        # output_item.added 不预填 arguments
                                        added_item = {k: v for k, v in fc_item.items() if k != "arguments"}
                                        oi, start_evt = _start_output_item(added_item)
                                        if start_evt:
                                            yield start_evt
                                        # 始终通过 delta 传递参数
                                        args_str = fc_item.get("arguments", "{}")
                                        yield {
                                            "type": "response.function_call_arguments.delta",
                                            "item_id": fc_id,
                                            "output_index": oi,
                                            "delta": args_str,
                                        }
                        buffer = keep
                        break
                    else:
                        idx = buffer.find(THINK_CLOSE)
                        if idx != -1:
                            safe, keep = _safe_flush(buffer[:idx])
                            if safe:
                                reasoning_parts.append(safe)
                                item = _response_reasoning_item("", reasoning_item_id)
                                oi, start_evt = _start_output_item(item)
                                if start_evt:
                                    yield start_evt
                                yield {
                                    "type": "response.reasoning_text.delta",
                                    "item_id": reasoning_item_id,
                                    "output_index": output_indices.get(reasoning_item_id, 0),
                                    "content_index": 0,
                                    "delta": safe,
                                }
                            in_think = False
                            buffer = buffer[idx + len(THINK_CLOSE):]
                            continue

                        safe, keep = _safe_flush(buffer)
                        if safe:
                            reasoning_parts.append(safe)
                            if len(reasoning_parts) == 1:
                                item = _response_reasoning_item("", reasoning_item_id)
                                oi, start_evt = _start_output_item(item)
                                if start_evt:
                                    yield start_evt
                            yield {
                                "type": "response.reasoning_text.delta",
                                "item_id": reasoning_item_id,
                                "output_index": output_indices.get(reasoning_item_id, 0),
                                "content_index": 0,
                                "delta": safe,
                            }
                        buffer = keep
                        break

            # Flush buffer
            if buffer and not in_think:
                for ev in sieve.feed(buffer):
                    if ev.type == 'text':
                        clean = _clean_response_text(ev.data, tool_names)
                        if clean:
                            text_parts.append(clean)
                            if not content_started:
                                content_started = True
                                item = _response_text_item("", message_item_id)
                                oi, start_evt = _start_output_item(item)
                                if start_evt:
                                    yield start_evt
                                yield {
                                    "type": "response.content_part.added",
                                    "item_id": message_item_id,
                                    "output_index": oi,
                                    "content_index": 0,
                                    "part": item["content"][0],
                                }
                            yield {
                                "type": "response.output_text.delta",
                                "item_id": message_item_id,
                                "output_index": output_indices.get(message_item_id, 0),
                                "content_index": 0,
                                "delta": clean,
                            }

            for ev in sieve.flush():
                if ev.type == 'text':
                    clean = _clean_response_text(ev.data, tool_names)
                    if clean:
                        text_parts.append(clean)
                        if not content_started:
                            content_started = True
                            item = _response_text_item("", message_item_id)
                            oi, start_evt = _start_output_item(item)
                            if start_evt:
                                yield start_evt
                            yield {
                                "type": "response.content_part.added",
                                "item_id": message_item_id,
                                "output_index": oi,
                                "content_index": 0,
                                "part": item["content"][0],
                            }
                        yield {
                            "type": "response.output_text.delta",
                            "item_id": message_item_id,
                            "output_index": output_indices.get(message_item_id, 0),
                            "content_index": 0,
                            "delta": clean,
                        }
                elif ev.type == 'tool_calls':
                    for tc in ev.data:
                        idx = len(tool_calls_map)
                        fc_item = _response_function_call_item(tc)
                        fc_id = fc_item["id"]
                        tool_calls_map[idx] = {
                            "id": fc_id,
                            "call_id": fc_item.get("call_id", fc_id),
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": tc.get("function", {}).get("arguments", "{}"),
                            "status": "completed",
                        }
                        # output_item.added 不预填 arguments
                        added_item = {k: v for k, v in fc_item.items() if k != "arguments"}
                        oi, start_evt = _start_output_item(added_item)
                        if start_evt:
                            yield start_evt
                        # 始终通过 delta 传递参数
                        args_str = fc_item.get("arguments", "{}")
                        yield {
                            "type": "response.function_call_arguments.delta",
                            "item_id": fc_id,
                            "output_index": oi,
                            "delta": args_str,
                        }

        else:
            # 无工具：简单流式
            in_think = False
            buffer = ""

            async for sse_data in client.stream_api(query, thinking, effective_model, multi_medias):
                if sse_data.get("type") == "usage":
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
                                    text_parts.append(clean)
                                    if not content_started:
                                        content_started = True
                                        item = _response_text_item("", message_item_id)
                                        oi, start_evt = _start_output_item(item)
                                        if start_evt:
                                            yield start_evt
                                        yield {
                                            "type": "response.content_part.added",
                                            "item_id": message_item_id,
                                            "output_index": oi,
                                            "content_index": 0,
                                            "part": item["content"][0],
                                        }
                                    yield {
                                        "type": "response.output_text.delta",
                                        "item_id": message_item_id,
                                        "output_index": output_indices.get(message_item_id, 0),
                                        "content_index": 0,
                                        "delta": clean,
                                    }
                            in_think = True
                            buffer = buffer[idx + len(THINK_OPEN):]
                            continue

                        safe, keep = _safe_flush(buffer)
                        if safe:
                            clean = _clean_response_text(safe)
                            if clean:
                                text_parts.append(clean)
                                if not content_started:
                                    content_started = True
                                    item = _response_text_item("", message_item_id)
                                    oi, start_evt = _start_output_item(item)
                                    if start_evt:
                                        yield start_evt
                                    yield {
                                        "type": "response.content_part.added",
                                        "item_id": message_item_id,
                                        "output_index": oi,
                                        "content_index": 0,
                                        "part": item["content"][0],
                                    }
                                yield {
                                    "type": "response.output_text.delta",
                                    "item_id": message_item_id,
                                    "output_index": output_indices.get(message_item_id, 0),
                                    "content_index": 0,
                                    "delta": clean,
                                }
                        buffer = keep
                        break
                    else:
                        idx = buffer.find(THINK_CLOSE)
                        if idx != -1:
                            safe, keep = _safe_flush(buffer[:idx])
                            if safe:
                                reasoning_parts.append(safe)
                                item = _response_reasoning_item("", reasoning_item_id)
                                oi, start_evt = _start_output_item(item)
                                if start_evt:
                                    yield start_evt
                                yield {
                                    "type": "response.reasoning_text.delta",
                                    "item_id": reasoning_item_id,
                                    "output_index": output_indices.get(reasoning_item_id, 0),
                                    "content_index": 0,
                                    "delta": safe,
                                }
                            in_think = False
                            buffer = buffer[idx + len(THINK_CLOSE):]
                            continue

                        safe, keep = _safe_flush(buffer)
                        if safe:
                            reasoning_parts.append(safe)
                            if len(reasoning_parts) == 1:
                                item = _response_reasoning_item("", reasoning_item_id)
                                oi, start_evt = _start_output_item(item)
                                if start_evt:
                                    yield start_evt
                            yield {
                                "type": "response.reasoning_text.delta",
                                "item_id": reasoning_item_id,
                                "output_index": output_indices.get(reasoning_item_id, 0),
                                "content_index": 0,
                                "delta": safe,
                            }
                        buffer = keep
                        break

            # 发送剩余缓冲区内容
            if buffer:
                clean = _clean_response_text(buffer)
                if clean:
                    if in_think:
                        reasoning_parts.append(clean)
                        yield {
                            "type": "response.reasoning_text.delta",
                            "item_id": reasoning_item_id,
                            "output_index": output_indices.get(reasoning_item_id, 0),
                            "content_index": 0,
                            "delta": clean,
                        }
                    else:
                        text_parts.append(clean)
                        if not content_started:
                            content_started = True
                            item = _response_text_item("", message_item_id)
                            oi, start_evt = _start_output_item(item)
                            if start_evt:
                                yield start_evt
                            yield {
                                "type": "response.content_part.added",
                                "item_id": message_item_id,
                                "output_index": oi,
                                "content_index": 0,
                                "part": item["content"][0],
                            }
                        yield {
                            "type": "response.output_text.delta",
                            "item_id": message_item_id,
                            "output_index": output_indices.get(message_item_id, 0),
                            "content_index": 0,
                            "delta": clean,
                        }

        # ─── 完成事件 ─────────────────────────────────────
        # 构建 output items
        output_by_id: dict[str, dict] = {}
        if reasoning_parts:
            output_by_id[reasoning_item_id] = _response_reasoning_item("".join(reasoning_parts), reasoning_item_id)
        full_text = _normalize_structured_output_text("".join(text_parts), text_config) if text_parts else ""
        if full_text:
            output_by_id[message_item_id] = _response_text_item(full_text, message_item_id)
        for idx in sorted(tool_calls_map.keys()):
            tc = tool_calls_map[idx]
            output_by_id[tc["id"]] = {
                "id": tc["id"],
                "type": "function_call",
                "call_id": tc.get("call_id", tc["id"]),
                "name": tc["name"],
                "arguments": tc["arguments"],
                "status": "completed",
            }

        if not output_by_id:
            output_by_id[message_item_id] = _response_text_item("", message_item_id)
            if message_item_id not in output_indices:
                item = _response_text_item("", message_item_id)
                oi, start_evt = _start_output_item(item)
                if start_evt:
                    yield start_evt

        output = [
            item for _, item in sorted(
                output_by_id.items(),
                key=lambda pair: output_indices.get(pair[0], len(output_indices))
            )
        ]

        # 发出 done 事件
        if reasoning_parts:
            yield {
                "type": "response.reasoning_text.done",
                "item_id": reasoning_item_id,
                "output_index": output_indices.get(reasoning_item_id, 0),
                "content_index": 0,
                "text": "".join(reasoning_parts),
            }
        if full_text:
            yield {
                "type": "response.output_text.done",
                "item_id": message_item_id,
                "output_index": output_indices.get(message_item_id, 0),
                "content_index": 0,
                "text": full_text,
            }
            yield {
                "type": "response.content_part.done",
                "item_id": message_item_id,
                "output_index": output_indices.get(message_item_id, 0),
                "content_index": 0,
                "part": _response_text_item(full_text, message_item_id)["content"][0],
            }
        for idx in sorted(tool_calls_map.keys()):
            tc = tool_calls_map[idx]
            yield {
                "type": "response.function_call_arguments.done",
                "item_id": tc["id"],
                "output_index": output_indices.get(tc["id"], 0),
                "arguments": tc["arguments"],
            }
        for idx, item in enumerate(output):
            if item.get("type") == "reasoning":
                # 由 reasoning_text.done 结束，不发 output_item.done
                # 避免 RikkaHub 重复创建空白思维链卡片
                continue
            yield {
                "type": "response.output_item.done",
                "output_index": idx,
                "item": item,
            }

        # 用量估算
        total_reasoning = "".join(reasoning_parts)
        total_text = "".join(text_parts)
        approx_completion = _count_tokens(total_reasoning + total_text)
        approx_prompt = _count_tokens(query)
        completion_record = {
            "input_tokens": approx_prompt,
            "output_tokens": approx_completion,
            "total_tokens": approx_prompt + approx_completion,
        }

        completed_payload = dict(init_payload)
        completed_payload["status"] = "completed"
        completed_payload["completed_at"] = int(time.time())
        completed_payload["output"] = output
        completed_payload["usage"] = _build_response_usage(completion_record)
        if has_tools and tool_calls_map:
            completed_payload["status"] = "completed"
        yield {"type": "response.completed", "response": completed_payload}

    except MimoApiError as e:
        failed_payload = dict(init_payload)
        failed_payload["status"] = "failed"
        failed_payload["error"] = {"message": f"MiMo API {e.status_code}: {e.response_body[:200]}", "type": "server_error"}
        yield {"type": "response.failed", "response": failed_payload}
    except httpx.ReadTimeout:
        failed_payload = dict(init_payload)
        failed_payload["status"] = "incomplete"
        failed_payload["incomplete_details"] = {"reason": "max_output_tokens"}
        yield {"type": "response.incomplete", "response": failed_payload}
    except Exception as e:
        failed_payload = dict(init_payload)
        failed_payload["status"] = "failed"
        failed_payload["error"] = {"message": str(e)[:500], "type": "server_error"}
        yield {"type": "response.failed", "response": failed_payload}


async def _sse_stream_response(body: dict, account):
    """将 _stream_response_events 包装为 SSE 格式。"""
    async for event in _stream_response_events(body, account):
        yield _sse_json(event)


# ─── 路由：8 个 Responses API 端点 ──────────────────────────

@router.post("/v1/responses")
async def create_response(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    """创建 Response（非流式/流式）。"""
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    body = await request.json()
    stream = body.get("stream", False)
    body["_response_id"] = _gen_response_id()

    input_data = body.get("input", [])
    instructions = body.get("instructions")
    messages = _convert_response_input_to_messages(input_data)
    if isinstance(instructions, str) and instructions.strip():
        messages.insert(0, {"role": "system", "content": instructions.strip()})

    model = body.get("model", "default")

    account = None
    existing_account_id = _find_existing_session_account(messages, model)
    if existing_account_id:
        for acc in config_manager.config.mimo_accounts:
            if acc.user_id == existing_account_id and acc.is_valid:
                account = acc
                break

    if not account:
        account = config_manager.get_next_account()

    if not account:
        raise HTTPException(status_code=503, detail={"error": {"message": "no mimo account"}})

    if stream:
        return StreamingResponse(
            _sse_stream_response(body, account),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            }
        )

    # 非流式
    try:
        model_used, usage, items = await _do_response_chat(body, account)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": {"message": str(e)}})

    response_id = body["_response_id"]
    response_obj = _make_response_object(
        response_id=response_id,
        model=model_used,
        status="completed",
        items=items,
        usage=usage,
    )

    # 保存记录
    record = dict(response_obj)
    record["_messages"] = _convert_response_input_to_messages(body.get("input", []))
    record["_input"] = body.get("input", [])
    record["_body"] = body
    try:
        _save_response_record(record)
    except Exception:
        pass

    # 记录用量
    if usage:
        _add_usage(model_used, usage.get("promptTokens", 0) or usage.get("prompt_tokens", 0),
                   usage.get("completionTokens", 0) or usage.get("completion_tokens", 0))

    return response_obj


@router.post("/v1/responses/input_tokens")
async def count_input_tokens(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    """估算 input tokens。"""
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    body = await request.json()
    input_value = body.get("input")
    instructions = body.get("instructions") if isinstance(body.get("instructions"), str) else None
    tools = body.get("tools") if isinstance(body.get("tools"), list) else None
    count = _count_response_input_tokens(input_value, instructions, tools)
    return {"object": "response.input_tokens", "input_tokens": count}


def _compact_response_record(source: dict, body: dict) -> dict:
    """创建 compacted response 记录。"""
    response_id = _gen_response_id()
    source_text = _extract_output_text(source.get("output", []))
    compact_text = body.get("summary") if isinstance(body.get("summary"), str) else source_text
    compact_item = _response_text_item(compact_text or "", response_id)
    compact_messages = [{"role": "assistant", "content": compact_text or ""}]
    compact_body = {
        "_response_id": response_id,
        "input": [compact_item],
        "model": body.get("model") or source.get("model", "default"),
        "previous_response_id": source.get("id"),
        "metadata": dict(source.get("metadata") or {}),
        "store": True,
    }
    compact_body["metadata"].update({
        "compacted": True,
        "source_response_id": source.get("id"),
    })
    record = _make_response_object(
        response_id=response_id,
        model=compact_body["model"],
        status="completed",
        items=[_response_text_item(compact_text or "")],
        usage={
            "prompt_tokens": _count_tokens(json.dumps(source.get("_input", []), ensure_ascii=False)),
            "completion_tokens": _count_tokens(compact_text or ""),
            "total_tokens": _count_tokens(json.dumps(source.get("_input", []), ensure_ascii=False)) + _count_tokens(compact_text or ""),
        },
    )
    record["_messages"] = compact_messages
    record["_input"] = compact_body["input"]
    record["_body"] = compact_body
    record["store"] = True
    return record


@router.post("/v1/responses/compact")
async def compact_response(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    """压缩 response。"""
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    body = await request.json()
    response_id = body.get("response_id") or body.get("previous_response_id")
    if not response_id:
        raise HTTPException(status_code=400, detail={"error": {"message": "response_id is required", "type": "invalid_request_error"}})
    source = _get_response_record(response_id)
    if not source:
        raise HTTPException(status_code=404, detail={"error": {"message": f"response {response_id} not found", "type": "invalid_request_error"}})
    record = _compact_response_record(source, body)
    _save_response_record(record)
    return record


@router.post("/v1/responses/{response_id}/compact")
async def compact_response_by_id(
    response_id: str,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    """按 ID 压缩 response。"""
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    body = await request.json()
    source = _get_response_record(response_id)
    if not source:
        raise HTTPException(status_code=404, detail={"error": {"message": f"response {response_id} not found", "type": "invalid_request_error"}})
    record = _compact_response_record(source, body)
    _save_response_record(record)
    return record


@router.post("/v1/responses/{response_id}/cancel")
async def cancel_response(
    response_id: str,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    """取消 response。"""
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    record = _get_response_record(response_id)
    if not record:
        raise HTTPException(status_code=404, detail={"error": {"message": f"response {response_id} not found", "type": "invalid_request_error"}})
    if record.get("status") == "cancelled":
        return record
    if record.get("status") in _RESPONSE_TERMINAL_STATUSES:
        return record

    now = int(time.time())
    record["status"] = "cancelled"
    record["completed_at"] = now
    record["error"] = None
    record["incomplete_details"] = None
    _update_response_record(response_id, record)
    return record


@router.get("/v1/responses/{response_id}")
async def get_response(
    response_id: str,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    """获取 response 记录。"""
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    record = _get_response_record(response_id)
    if not record:
        raise HTTPException(status_code=404, detail={"error": {"message": f"response {response_id} not found", "type": "invalid_request_error"}})
    return record


@router.get("/v1/responses/{response_id}/input_items")
async def get_response_input_items(
    response_id: str,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    """获取 response 的 input items。"""
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    record = _get_response_record(response_id)
    if not record:
        raise HTTPException(status_code=404, detail={"error": {"message": f"response {response_id} not found", "type": "invalid_request_error"}})

    stored_items = record.get("_input") or record.get("input") or []
    if not isinstance(stored_items, list):
        stored_items = [stored_items] if stored_items else []

    # 统一转换为 dict 格式（input 可能是纯字符串）
    normalized = []
    for item in stored_items:
        if isinstance(item, str):
            normalized.append({"id": f"inp_{uuid.uuid4().hex[:24]}", "type": "input_text", "text": item})
        elif isinstance(item, dict):
            normalized.append(item)
    stored_items = normalized

    limit_raw = request.query_params.get("limit")
    try:
        limit = max(1, min(int(limit_raw), 100)) if limit_raw is not None else 20
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": {"message": "invalid limit", "type": "invalid_request_error"}})

    after = request.query_params.get("after")
    before = request.query_params.get("before")
    order = (request.query_params.get("order") or "desc").lower()
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail={"error": {"message": "invalid order", "type": "invalid_request_error"}})

    # 简单分页
    ordered = list(stored_items)
    if order == "desc":
        ordered = list(reversed(ordered))
    if after:
        idx = next((i for i, item in enumerate(ordered) if item.get("id") == after), -1)
        ordered = ordered[idx + 1:] if idx != -1 else []
    if before:
        idx = next((i for i, item in enumerate(ordered) if item.get("id") == before), -1)
        ordered = ordered[:idx] if idx != -1 else []

    has_more = len(ordered) > limit
    page_items = ordered[:limit]

    return {
        "object": "list",
        "data": page_items,
        "first_id": page_items[0].get("id") if page_items else None,
        "last_id": page_items[-1].get("id") if page_items else None,
        "has_more": has_more,
    }


@router.delete("/v1/responses/{response_id}")
async def delete_response(
    response_id: str,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
):
    """删除 response 记录。"""
    api_key = authorization or (f"Bearer {x_api_key}" if x_api_key else None)
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401, detail={"error": {"message": "invalid api key"}})

    if not _delete_response_record(response_id):
        raise HTTPException(status_code=404, detail={"error": {"message": f"response {response_id} not found", "type": "invalid_request_error"}})
    return {"id": response_id, "object": "response", "deleted": True}
