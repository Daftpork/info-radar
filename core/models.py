"""统一数据模型 — 所有 fetcher 产出 Item，所有 tracker 消费 Item。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

# item.kind 取值
TWEET = "tweet"
BLOG = "blog"
PODCAST = "podcast"
VIDEO = "video"
REPO = "repo"
PRODUCT = "product"
PAPER = "paper"


@dataclass
class Item:
    """一条抓到的信息。字段尽量通用，来源专属数据放 metrics / extra。"""

    title: str
    url: str
    source: str          # 如 "x/karpathy" | "github/trending" | "ph" | "arxiv" | "blog/simonwillison"
    kind: str            # TWEET / BLOG / PODCAST / VIDEO / REPO / PRODUCT / PAPER
    author: str = ""     # 人名 / 组织名
    author_bio: str = "" # 身份（Thinker 用，如 "独立开发者"）
    body: str = ""       # 全文 / 转录 / 简介
    published: str = ""  # ISO 时间戳
    metrics: dict = field(default_factory=dict)  # {"stars":N,"upvotes":N,"likes":N,...}
    extra: dict = field(default_factory=dict)    # 来源专属

    @property
    def id(self) -> str:
        return hashlib.sha256(self.url.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})


# ---------------------------------------------------------------------------
# AI 相关性初筛（给 HN / arXiv 这类高噪音源用；curated 源不需要）
# ---------------------------------------------------------------------------
_AI_KEYWORDS = frozenset({
    "ai", "artificial intelligence", "machine learning", "ml", "llm", "llms",
    "agent", "agents", "agentic", "gpt", "claude", "gemini", "llama", "qwen",
    "deepseek", "mistral", "model", "models", "transformer", "diffusion",
    "rag", "embedding", "embeddings", "fine-tune", "finetune", "fine-tuning",
    "inference", "prompt", "prompting", "multimodal", "vision-language", "vlm",
    "reinforcement learning", "rlhf", "neural", "openai", "anthropic",
    "hugging face", "huggingface", "vector", "chatbot", "copilot", "reasoning",
})
_WORD_RE = re.compile(r"[a-z][a-z\-]+")


def looks_ai_related(text: str) -> bool:
    """粗判是否与 AI 相关。用词集合 + 若干短语。"""
    low = (text or "").lower()
    for phrase in ("artificial intelligence", "machine learning", "hugging face",
                   "reinforcement learning", "vision-language"):
        if phrase in low:
            return True
    words = set(_WORD_RE.findall(low))
    return bool(words & _AI_KEYWORDS)


def dedupe(items: list[Item]) -> list[Item]:
    """按 url 哈希去重，保留首次出现顺序。"""
    seen: set[str] = set()
    out: list[Item] = []
    for it in items:
        if it.id in seen:
            continue
        seen.add(it.id)
        out.append(it)
    return out
