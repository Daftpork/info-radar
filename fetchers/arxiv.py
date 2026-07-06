"""arXiv 热门论文 —— 主用 Hugging Face 每日精选论文（自带热度/upvotes，比裸抓 arXiv 更「热」），
失败回退 arXiv 官方 API 按提交时间取近期。免 key。
"""

from __future__ import annotations

import calendar
import logging
from datetime import datetime, timezone

import feedparser
import httpx

from core.models import Item, PAPER
from core.util import within_hours

logger = logging.getLogger(__name__)

HF_DAILY = "https://huggingface.co/api/daily_papers"
ARXIV_API = "https://export.arxiv.org/api/query"


async def _hf_daily(client: httpx.AsyncClient, limit: int) -> list[Item]:
    try:
        r = await client.get(HF_DAILY, params={"limit": limit}, timeout=25)
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("HF daily_papers 失败: %s", e)
        return []
    items: list[Item] = []
    for row in data:
        paper = row.get("paper", row)
        pid = paper.get("id", "")
        title = paper.get("title", "").strip()
        if not (pid and title):
            continue
        items.append(Item(
            title=title,
            url=f"https://arxiv.org/abs/{pid}",
            source="arxiv/hf-daily",
            kind=PAPER,
            author=", ".join(a.get("name", "") for a in (paper.get("authors") or [])[:3]),
            body=(paper.get("summary") or "")[:1200],
            published=row.get("publishedAt", "") or paper.get("publishedAt", ""),
            metrics={"upvotes": paper.get("upvotes", 0)} if paper.get("upvotes") else {},
        ))
    logger.info("arXiv(HF 每日): %d 篇", len(items))
    return items


async def _arxiv_recent(client: httpx.AsyncClient, categories: list[str], lookback_hours: float) -> list[Item]:
    q = "+OR+".join(f"cat:{c}" for c in categories)
    try:
        r = await client.get(
            f"{ARXIV_API}?search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results=40",
            timeout=25,
        )
        r.raise_for_status()
        feed = feedparser.parse(r.content)
    except Exception as e:  # noqa: BLE001
        logger.warning("arXiv API 失败: %s", e)
        return []
    items: list[Item] = []
    for entry in feed.entries:
        st = entry.get("published_parsed")
        published = datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc).isoformat() if st else ""
        if published and not within_hours(published, lookback_hours):
            continue
        items.append(Item(
            title=entry.get("title", "").strip().replace("\n", " "),
            url=entry.get("link", ""),
            source="arxiv/recent",
            kind=PAPER,
            author=", ".join(a.get("name", "") for a in entry.get("authors", [])[:3]),
            body=entry.get("summary", "").strip()[:1200],
            published=published,
        ))
    logger.info("arXiv(API 近期): %d 篇", len(items))
    return items


async def fetch_papers(categories: list[str], lookback_hours: float, limit: int = 30) -> list[Item]:
    async with httpx.AsyncClient(headers={"User-Agent": "info-radar/0.1"}, follow_redirects=True) as client:
        items = await _hf_daily(client, limit)
        if not items:
            items = await _arxiv_recent(client, categories, lookback_hours)
    return items
