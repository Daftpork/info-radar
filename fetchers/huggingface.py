"""Hugging Face 抓取 —— trending 模型 / spaces。免 key。

API: https://huggingface.co/api/models?sort=trending  （也支持 sort=likes）
     https://huggingface.co/api/spaces?sort=trending
"""

from __future__ import annotations

import logging

import httpx

from core.models import Item, REPO

logger = logging.getLogger(__name__)

BASE = "https://huggingface.co/api"


async def _fetch(client: httpx.AsyncClient, kind_path: str, limit: int) -> list[dict]:
    try:
        r = await client.get(
            f"{BASE}/{kind_path}",
            params={"sort": "trendingScore", "direction": "-1", "limit": limit},
            timeout=25,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("HF %s 拉取失败: %s", kind_path, e)
        return []


async def fetch_trending(limit: int = 25) -> list[Item]:
    items: list[Item] = []
    async with httpx.AsyncClient(headers={"User-Agent": "info-radar/0.1"}) as client:
        models = await _fetch(client, "models", limit)
        spaces = await _fetch(client, "spaces", limit // 2)

    for m in models:
        mid = m.get("id") or m.get("modelId", "")
        if not mid:
            continue
        tags = [t for t in (m.get("tags") or []) if isinstance(t, str)][:8]
        pipeline = m.get("pipeline_tag", "")
        body = f"pipeline: {pipeline}; tags: {', '.join(tags)}"
        items.append(Item(
            title=mid,
            url=f"https://huggingface.co/{mid}",
            source="huggingface/model",
            kind=REPO,
            author=mid.split("/")[0] if "/" in mid else "",
            body=body,
            published=m.get("createdAt", ""),
            metrics={k: m[k] for k in ("likes", "downloads", "trendingScore") if m.get(k)},
        ))

    for s in spaces:
        sid = s.get("id", "")
        if not sid:
            continue
        body = (s.get("cardData", {}) or {}).get("short_description", "") or \
               f"tags: {', '.join((s.get('tags') or [])[:6])}"
        items.append(Item(
            title=sid,
            url=f"https://huggingface.co/spaces/{sid}",
            source="huggingface/space",
            kind=REPO,
            author=sid.split("/")[0] if "/" in sid else "",
            body=body,
            published=s.get("createdAt", ""),
            metrics={k: s[k] for k in ("likes",) if s.get(k)},
        ))
    logger.info("HuggingFace: %d 条（models+spaces）", len(items))
    return items
