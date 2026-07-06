"""Product Hunt 抓取 —— 官方 GraphQL API（免费申请 developer token）。

无 PRODUCTHUNT_TOKEN 时返回空（优雅降级）。
API: https://api.producthunt.com/v2/api/graphql
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from core.models import Item, PRODUCT

logger = logging.getLogger(__name__)

API = "https://api.producthunt.com/v2/api/graphql"

_QUERY = """
query($after: DateTime!, $n: Int!) {
  posts(order: VOTES, postedAfter: $after, first: $n) {
    edges { node {
      name tagline url votesCount createdAt
      topics(first: 3) { edges { node { name } } }
    } }
  }
}
"""


async def fetch_top(lookback_hours: float, first: int = 20) -> list[Item]:
    token = os.getenv("PRODUCTHUNT_TOKEN", "").strip()
    if not token:
        logger.info("PRODUCTHUNT_TOKEN 未设置，跳过 Product Hunt")
        return []
    after = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                API,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"query": _QUERY, "variables": {"after": after, "n": first}},
                timeout=25,
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("Product Hunt 拉取失败: %s", e)
        return []

    items: list[Item] = []
    for edge in (data.get("data", {}).get("posts", {}) or {}).get("edges", []):
        node = edge.get("node", {})
        topics = [t["node"]["name"] for t in (node.get("topics", {}) or {}).get("edges", [])]
        items.append(Item(
            title=node.get("name", ""),
            url=node.get("url", ""),
            source="producthunt",
            kind=PRODUCT,
            body=node.get("tagline", ""),
            published=node.get("createdAt", ""),
            metrics={"votes": node.get("votesCount", 0)},
            extra={"tagline": node.get("tagline", ""), "topics": topics},
        ))
    logger.info("Product Hunt: %d 条", len(items))
    return items
