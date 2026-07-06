"""Exa 语义搜索 —— 行业深潜的跨平台深挖。需 EXA_API_KEY，无 key 则返回空。

API: https://api.exa.ai/search
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

API = "https://api.exa.ai/search"


async def search(query: str, *, num: int = 6, days: int = 14) -> list[dict]:
    key = os.getenv("EXA_API_KEY", "").strip()
    if not key:
        return []
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "query": query,
        "numResults": num,
        "startPublishedDate": start,
        "contents": {"text": {"maxCharacters": 1200}},
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                API,
                headers={"x-api-key": key, "Content-Type": "application/json"},
                json=payload, timeout=30,
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("Exa 搜索失败 (%s): %s", query[:50], e)
        return []
    out = []
    for res in data.get("results", []):
        out.append({
            "title": res.get("title", ""),
            "url": res.get("url", ""),
            "text": (res.get("text", "") or "")[:1200],
            "published": res.get("publishedDate", ""),
        })
    return out
