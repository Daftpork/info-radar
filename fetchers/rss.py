"""通用 RSS 抓取 —— Thinker 深度长文 + Feature 御三家（有 RSS 的）共用。

用 httpx 拉原始 feed（可控 UA / 超时），再 feedparser 解析，按回看窗口过滤。
"""

from __future__ import annotations

import calendar
import logging
import re
from datetime import datetime, timezone

import feedparser
import httpx

from core.models import Item, looks_ai_related
from core.util import within_hours

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG_RE.sub(" ", s or "").replace("&nbsp;", " ").strip()


def _entry_time_iso(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc).isoformat()
    return entry.get("published") or entry.get("updated") or ""


def _entry_body(entry) -> str:
    if entry.get("content"):
        raw = entry["content"][0].get("value", "")
    else:
        raw = entry.get("summary", "") or entry.get("description", "")
    return _strip_html(raw)[:4000]


async def fetch_feeds(
    sources: list[dict],
    *,
    kind: str,
    lookback_hours: float,
    ai_filter: bool = False,
    company_field: bool = False,
) -> list[Item]:
    """sources: [{name, bio?, rss, company?}]. 返回近 lookback 小时内的条目。"""
    items: list[Item] = []
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, follow_redirects=True) as client:
        for src in sources:
            url = src.get("rss") or src.get("url")
            if not url:
                continue
            try:
                r = await client.get(url, timeout=25)
                r.raise_for_status()
                feed = feedparser.parse(r.content)
            except Exception as e:  # noqa: BLE001
                logger.warning("RSS 拉取失败 %s (%s): %s", src.get("name"), url, e)
                continue

            for entry in feed.entries:
                published = _entry_time_iso(entry)
                if published and not within_hours(published, lookback_hours):
                    continue
                title = _strip_html(entry.get("title", ""))
                link = entry.get("link", "")
                if not link:
                    continue
                body = _entry_body(entry)
                if ai_filter and not looks_ai_related(f"{title} {body}"):
                    continue
                extra = {}
                if company_field and src.get("company"):
                    extra["company"] = src["company"]
                items.append(Item(
                    title=title,
                    url=link,
                    source=f"{kind}/{src.get('name', '')}",
                    kind=kind,
                    author=src.get("name", ""),
                    author_bio=src.get("bio", ""),
                    body=body,
                    published=published,
                    extra=extra,
                ))
    logger.info("RSS(%s): %d 源 → %d 条", kind, len(sources), len(items))
    return items
