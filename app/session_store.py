"""会话管理 — 基于内存与 Blake2s 消息级哈希的快速匹配

采用 zai2api 类似的高级会话复用逻辑：
1. 纯内存存储，不再写入文件，避免 I/O 阻塞。
2. blake2s 消息级指纹，按单条消息哈希。
3. 模糊匹配机制，兼容各类修改部分历史上下文的客户端。
4. 两阶段提交：先找可用会话，上游 API 调用成功后再 commit 确认更新指纹。
"""

import time
import uuid
import hashlib
import threading
import json
from typing import List, Dict, Any, Tuple, Optional

# --- 全局状态 ---
_store: Dict[str, List[Dict[str, Any]]] = {}
_lock = threading.RLock()

# --- 配置 ---
TOKEN_THRESHOLD = 150000
SESSION_TTL = 3 * 86400  # 3 days
MAX_SESSIONS_PER_ACCOUNT = 20
MAX_CACHED_FINGERPRINTS = 10


# --- 哈希指纹算法 ---

def _fast_hash(data: str, length: int = 16) -> str:
    """快速哈希：blake2s"""
    return hashlib.blake2s(data.encode("utf-8"), digest_size=8).hexdigest()[:length]

def _message_fingerprint(message) -> str:
    """生成单条消息的指纹（role + content）。"""
    role = getattr(message, "role", "")
    content = getattr(message, "content", "")
    # 对列表内容（多模态）做简化处理：转为字符串
    if isinstance(content, list):
        try:
            content = json.dumps(content, sort_keys=True)
        except Exception:
            content = str(content)
    return _fast_hash(f"{role}:{content}")

def _collect_fingerprints(messages: list) -> List[str]:
    """收集消息列表末尾 N 条非 system 消息的指纹"""
    non_sys = [m for m in messages if getattr(m, 'role', '') != 'system']
    fps = [_message_fingerprint(m) for m in non_sys]
    return fps[-MAX_CACHED_FINGERPRINTS:]

def _match_continuous_session(new_fps: List[str], cached_fps: List[str]) -> int:
    """模糊匹配会话延续性。
    
    返回 matched_count (在新消息中匹配掉的非系统消息数)。
    若未命中则返回 0。
    """
    n = len(cached_fps)
    if n == 0:
        return 0
    if len(new_fps) < n:
        return 0

    overlap = new_fps[:n]
    
    # 模糊匹配策略：
    # 3 条及以上：检查最后 3 条重叠，允许 1 条不匹配
    if n >= 3:
        matches = sum(1 for i in range(1, 4) if overlap[-i] == cached_fps[-i])
        if matches >= 2:
            return n
    elif n > 0:
        # 小于 3 条，要求全匹配
        if overlap == cached_fps:
            return n

    return 0


# --- 内存存储操作 ---

def _cleanup_expired_sync() -> None:
    """同步清理过期会话（必须在获得锁的情况下调用）"""
    now = time.time()
    expired_keys = []
    for key, sessions in _store.items():
        valid_sessions = [s for s in sessions if now - s.get('last_used', 0) < SESSION_TTL]
        if len(valid_sessions) != len(sessions):
            _store[key] = valid_sessions
        if not valid_sessions:
            expired_keys.append(key)
    for k in expired_keys:
        del _store[k]


def get_or_create_session(
    account_id: str,
    messages: list,
    model: str = "mimo-v2-pro",
) -> Tuple[str, bool, int]:
    """获取或创建会话。
    
    Args:
        account_id: 账号标识
        messages: 当前请求的完整消息列表
        model: 模型名

    Returns:
        (conversation_id, is_new, matched_count)
        - conversation_id: MiMo 会话 ID（复用或新建）
        - is_new: True=新建会话, False=复用了现有会话
        - matched_count: 在新消息中复用了多少条非系统消息。新建为 0。
    """
    key = f"account_{account_id}"
    non_sys = [m for m in messages if getattr(m, 'role', '') != 'system']
    new_fps = [_message_fingerprint(m) for m in non_sys]
    
    now = time.time()

    with _lock:
        _cleanup_expired_sync()
        sessions = _store.get(key, [])

        if not new_fps:
            conv_id, is_new = _create_new(key, model, sessions)
            return conv_id, is_new, 0

        # 从最新的会话开始倒序匹配，命中率更高
        for s in reversed(sessions):
            if s.get('model') != model:
                continue
            
            cached_fps = s.get('fingerprints', [])
            if not cached_fps:
                continue

            match_count = _match_continuous_session(new_fps, cached_fps)
            if match_count > 0:
                # 命中连续会话
                if s.get('prompt_tokens', 0) > TOKEN_THRESHOLD:
                    # Token 超限 → 必须清屏，跳出匹配去新建
                    continue
                
                s['last_used'] = now
                return s['conversation_id'], False, match_count

        # 没有匹配的会话 → 创建新会话
        conv_id, is_new = _create_new(key, model, sessions)
        return conv_id, is_new, 0


def _create_new(key: str, model: str, sessions: List[Dict[str, Any]]) -> Tuple[str, bool]:
    """创建新会话（必须在获得锁的情况下调用）"""
    now = time.time()
    conv_id = uuid.uuid4().hex[:32]

    sessions.append({
        'conversation_id': conv_id,
        'fingerprints': [],  # 二阶段提交：首次为空，直到 commit_session_turn
        'prompt_tokens': 0,
        'model': model,
        'created': now,
        'last_used': now,
    })

    if len(sessions) > MAX_SESSIONS_PER_ACCOUNT:
        sessions = sessions[-MAX_SESSIONS_PER_ACCOUNT:]

    _store[key] = sessions
    return conv_id, True


def commit_session_turn(account_id: str, conversation_id: str, messages: list, prompt_tokens: int) -> None:
    """二阶段提交：在上游响应成功后，保存本次最新指纹。"""
    key = f"account_{account_id}"
    fps = _collect_fingerprints(messages)
    
    with _lock:
        sessions = _store.get(key, [])
        for s in sessions:
            if s['conversation_id'] == conversation_id:
                if fps:
                    s['fingerprints'] = fps
                if prompt_tokens:
                    s['prompt_tokens'] = max(s.get('prompt_tokens', 0), prompt_tokens)
                s['last_used'] = time.time()
                break


def find_existing_session_account(messages: list, model: str) -> Optional[str]:
    """遍历所有账号，查找是否存在延续此消息记录的未过期且未超限会话。"""
    non_sys = [m for m in messages if getattr(m, 'role', '') != 'system']
    if not non_sys:
        return None
        
    new_fps = [_message_fingerprint(m) for m in non_sys]

    with _lock:
        _cleanup_expired_sync()
        for key, sessions in _store.items():
            if not key.startswith("account_"):
                continue
            account_id = key[8:]
            # 倒序遍历提升命中率
            for s in reversed(sessions):
                if s.get('model') != model:
                    continue
                if s.get('prompt_tokens', 0) > TOKEN_THRESHOLD:
                    continue
                
                cached_fps = s.get('fingerprints', [])
                if _match_continuous_session(new_fps, cached_fps) > 0:
                    return account_id
                    
    return None


def get_expired_sessions(account_id: str = None, ttl: int = SESSION_TTL) -> list:
    """获取过期的会话列表（配合页面管理端查看）。"""
    now = time.time()
    expired = []

    with _lock:
        keys = [f"account_{account_id}"] if account_id else list(_store.keys())
        for key in keys:
            if not key.startswith("account_"):
                continue
            account_label = key[8:]
            for s in _store.get(key, []):
                age = now - s.get("last_used", s.get("created", now))
                if age > ttl:
                    expired.append((
                        account_label,
                        s["conversation_id"],
                        s.get("model", ""),
                        round(age / 86400, 1),
                    ))

    return expired


def remove_session(account_id: str, conversation_id: str) -> None:
    """从存储中移除指定会话。"""
    key = f"account_{account_id}"
    with _lock:
        sessions = _store.get(key, [])
        _store[key] = [s for s in sessions if s.get("conversation_id") != conversation_id]
        if not _store[key]:
            del _store[key]


def get_account_session_count(account_id: str) -> int:
    """获取指定账号的未过期且未超限的会话数量。"""
    key = f"account_{account_id}"
    count = 0
    with _lock:
        _cleanup_expired_sync()
        sessions = _store.get(key, [])
        for s in sessions:
            if s.get('prompt_tokens', 0) <= TOKEN_THRESHOLD:
                count += 1
    return count
