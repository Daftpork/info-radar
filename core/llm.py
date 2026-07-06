"""LLM 客户端 — 复刻 Lumio 的 yuyu(yylx) → liaobots → anthropic 文本 fallback。

设计要点（对应 Lumio/src/lib/ai/provider.ts）：
- 三个 provider 顺序降级；每个独立超时；抛错/超时即试下一个；全失败抛错或返回 fallback_text。
- yuyu 对非流式请求也返回 content-type: text/event-stream（body 却是完整 JSON），
  OpenAI SDK 会误当流解析 → choices 变 undefined。所以 yuyu/liaobots 都走裸 httpx，
  用 resp.text + json.loads()，彻底忽略 content-type。
- OpenAI 兼容网关字段：max_completion_tokens（不是 max_tokens）、temperature=0.7、不传 stream。
- 模型名是网关自定义常量：gpt-5.5 / gpt-5.4-mini。
纯文本，无 vision。
"""

from __future__ import annotations

import json
import logging
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# --- 模型档位（网关命名，可用 env 覆盖）---
DEFAULT_MODEL = os.getenv("RADAR_MODEL") or "gpt-5.4-mini"
HEAVY_MODEL = os.getenv("RADAR_HEAVY_MODEL") or "gpt-5.5"

# --- provider 端点 ---
YUYU_BASE_URL = os.getenv("YUYU_BASE_URL") or "https://app.yylx.io/v1"
LIAOBOTS_BASE_URL = os.getenv("LIAOBOTS_BASE_URL") or "https://ai.liaobots.work/v1"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-5-20250929"

# --- 每 provider 独立超时（秒）---
_YUYU_TIMEOUT = float(os.getenv("YUYU_TIMEOUT_MS", "40000")) / 1000
_LIAOBOTS_TIMEOUT = float(os.getenv("LIAOBOTS_TIMEOUT_MS", "40000")) / 1000
_ANTHROPIC_TIMEOUT = float(os.getenv("ANTHROPIC_TIMEOUT_MS", "30000")) / 1000

DEFAULT_ORDER = ["yuyu", "liaobots", "anthropic"]


class LLMError(Exception):
    """所有 provider 都失败时抛出。"""


# ---------------------------------------------------------------------------
# Token 用量统计（进程级累加；tracker 跑完写进 state/token_usage.json）
# ---------------------------------------------------------------------------
_usage: dict = {}


def _record(model: str, prompt: int, completion: int) -> None:
    m = _usage.setdefault(model, {"calls": 0, "prompt": 0, "completion": 0})
    m["calls"] += 1
    m["prompt"] += int(prompt or 0)
    m["completion"] += int(completion or 0)


def usage_summary() -> dict:
    tp = sum(m["prompt"] for m in _usage.values())
    tc = sum(m["completion"] for m in _usage.values())
    return {
        "calls": sum(m["calls"] for m in _usage.values()),
        "prompt": tp, "completion": tc, "total": tp + tc,
        "by_model": {k: dict(v) for k, v in _usage.items()},
    }


def reset_usage() -> None:
    _usage.clear()


# ---------------------------------------------------------------------------
# OpenAI 兼容 provider（yuyu / liaobots）— 裸 httpx，绕 content-type bug
# ---------------------------------------------------------------------------
def _openai_compatible_call(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    system: str | None,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> str:
    body: dict = {
        "model": model,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "max_completion_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = httpx.post(f"{base_url}/chat/completions", headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    # 关键：忽略 content-type，直接 json.loads（yuyu 会谎报 text/event-stream）
    data = json.loads(resp.text)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMError(f"bad response shape: {resp.text[:300]}")
    content = choices[0].get("message", {}).get("content") or ""
    usage = data.get("usage") or {}
    _record(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
    return _strip_reasoning(content)


# ---------------------------------------------------------------------------
# Anthropic 兜底（可选，需 ANTHROPIC_API_KEY）
# ---------------------------------------------------------------------------
def _anthropic_call(
    messages: list[dict],
    system: str | None,
    max_tokens: int,
    timeout: float,
) -> str:
    import anthropic  # 延迟导入，无 key 时不影响主路径

    client = anthropic.Anthropic(timeout=timeout)  # 自动读 ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL
    kwargs: dict = {"model": ANTHROPIC_MODEL, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    u = getattr(resp, "usage", None)
    if u:
        _record(ANTHROPIC_MODEL, getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0))
    return "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    )


# ---------------------------------------------------------------------------
# reasoning 块清理（部分模型会输出 <think>…</think>）
# ---------------------------------------------------------------------------
_REASONING_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_reasoning(text: str) -> str:
    return _REASONING_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# 对外主入口
# ---------------------------------------------------------------------------
def chat(
    prompt: str | None = None,
    *,
    system: str | None = None,
    messages: list[dict] | None = None,
    model: str | None = None,
    max_tokens: int = 1500,
    temperature: float = 0.7,
    providers: list[str] | None = None,
    fallback_text: str | None = None,
    timeout_s: float | None = None,
) -> str:
    """按 yuyu → liaobots → anthropic 顺序调用，第一个成功即返回。

    prompt 或 messages 二选一（messages 用 OpenAI 格式 [{"role","content"}]）。
    timeout_s：覆盖每个 provider 的默认超时（长文生成传大值，如 180）。
    全失败：若给了 fallback_text 则返回它，否则抛 LLMError。
    """
    if messages is None:
        if prompt is None:
            raise ValueError("chat() 需要 prompt 或 messages")
        messages = [{"role": "user", "content": prompt}]
    model = model or DEFAULT_MODEL
    order = providers or DEFAULT_ORDER
    defaults = {"yuyu": _YUYU_TIMEOUT, "liaobots": _LIAOBOTS_TIMEOUT, "anthropic": _ANTHROPIC_TIMEOUT}
    errors: list[str] = []

    for p in order:
        tmo = timeout_s or defaults.get(p, 40)
        try:
            if p == "yuyu":
                key = os.getenv("YUYU_API_KEY", "").strip()
                if not key:
                    raise LLMError("YUYU_API_KEY 未设置")
                return _openai_compatible_call(
                    YUYU_BASE_URL, key, model, messages, system, max_tokens, temperature, tmo
                )
            if p == "liaobots":
                key = os.getenv("LIAOBOTS_API_KEY", "").strip()
                if not key:
                    raise LLMError("LIAOBOTS_API_KEY 未设置")
                return _openai_compatible_call(
                    LIAOBOTS_BASE_URL, key, model, messages, system, max_tokens, temperature, tmo
                )
            if p == "anthropic":
                if not os.getenv("ANTHROPIC_API_KEY", "").strip():
                    raise LLMError("ANTHROPIC_API_KEY 未设置")
                return _anthropic_call(messages, system, max_tokens, tmo)
            raise LLMError(f"未知 provider: {p}")
        except Exception as e:  # noqa: BLE001 — 故意吞掉转下一个 provider
            logger.warning("[llm] provider %s 失败: %s", p, e)
            errors.append(f"{p}: {e}")

    if fallback_text is not None:
        logger.error("[llm] 全部 provider 失败，返回 fallback_text")
        return fallback_text
    raise LLMError("所有 provider 都失败: " + " | ".join(errors))


# ---------------------------------------------------------------------------
# JSON 输出辅助（scorer / 分组提炼用）
# ---------------------------------------------------------------------------
def chat_json(prompt: str | None = None, **kwargs):
    """要求模型输出 JSON，返回解析后的对象。自动剥离 ```json 围栏。"""
    raw = chat(prompt, **kwargs)
    return extract_json(raw)


def extract_json(text: str):
    """从模型输出里抠出第一个完整 JSON 对象/数组。"""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?", "", t).strip()
        if t.endswith("```"):
            t = t[:-3].strip()
    # 直接尝试
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # 回退：找第一个 { 或 [ 到匹配的收尾
    start = min((i for i in (t.find("{"), t.find("[")) if i != -1), default=-1)
    if start == -1:
        raise LLMError(f"输出里找不到 JSON: {text[:200]}")
    opener = t[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    for i in range(start, len(t)):
        if t[i] == opener:
            depth += 1
        elif t[i] == closer:
            depth -= 1
            if depth == 0:
                return json.loads(t[start : i + 1])
    raise LLMError(f"JSON 不完整: {text[:200]}")
