"""Product Hunt 抓取 —— 公开 RSS（免 token）。

PH 官方 GraphQL API 已限制新 developer token 申请（oauth/applications 返回 403），
故改用公开 RSS。缺点：RSS 不带 votes，故不显示票数（meta 显示 ⬆ New）。
"""

from __future__ import annotations

import logging
import re

import feedparser
import httpx

from core.models import Item, PRODUCT
from core.util import within_hours

logger = logging.getLogger(__name__)

FEEDS = [
    "https://www.producthunt.com/feed",
    "https://www.producthunt.com/feed?category=artificial-intelligence",
    "https://www.producthunt.com/feed?category=developer-tools",
    "https://www.producthunt.com/feed?category=design-tools",
]
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_TAG_RE = re.compile(r"<[^>]+>")


async def fetch_top(lookback_hours: float, first: int = 20) -> list[Item]:
    items: list[Item] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, follow_redirects=True) as client:
        for url in FEEDS:
            try:
                r = await client.get(url, timeout=25)
                r.raise_for_status()
                feed = feedparser.parse(r.content)
            except Exception as e:  # noqa: BLE001
                logger.warning("Product Hunt RSS 失败 (%s): %s", url, e)
                continue
            for entry in feed.entries:
                link = entry.get("link", "")
                if not link or link in seen:
                    continue
                published = entry.get("published", "")
                if published and not within_hours(published, lookback_hours):
                    continue
                seen.add(link)
                summary = _TAG_RE.sub(" ", entry.get("summary", "")).strip()
                items.append(Item(
                    title=entry.get("title", ""),
                    url=link,
                    source="producthunt",
                    kind=PRODUCT,
                    body=summary[:600],
                    published=published,
                    extra={"tagline": summary[:120]},
                ))
    logger.info("Product Hunt(RSS): %d 条", len(items))
    return items
