"""无 RSS 的新闻页 HTML 抓取（目前只有 Anthropic 需要）。

Anthropic news 页是 Next.js 站，无 RSS。抓法：从索引页提取有序去重的 /news/<slug> 链接，
逐条抓文章页的 og:title / og:description / article:published_time（meta）。
只抓前 max_items 条，tracker 侧再按 SeenStore 去重。
"""

from __future__ import annotations

import logging
import re

import httpx

from core.models import BLOG, Item
from core.util import within_hours

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _meta(html: str, prop: str) -> str:
    m = re.search(
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    )
    return (m.group(1).strip() if m else "")


async def fetch_anthropic(url: str, *, company: str, lookback_hours: float,
                          max_items: int = 8) -> list[Item]:
    items: list[Item] = []
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, follow_redirects=True) as client:
        try:
            r = await client.get(url, timeout=25)
            r.raise_for_status()
            index_html = r.text
        except Exception as e:  # noqa: BLE001
            logger.warning("Anthropic 索引抓取失败: %s", e)
            return []

        # 有序去重提取 /news/<slug>
        slugs: list[str] = []
        for m in re.finditer(r'/news/([a-z0-9][a-z0-9-]+)', index_html):
            s = m.group(1)
            if s not in slugs:
                slugs.append(s)
        slugs = slugs[:max_items]

        for slug in slugs:
            article_url = f"https://www.anthropic.com/news/{slug}"
            try:
                ar = await client.get(article_url, timeout=20)
                ar.raise_for_status()
                ah = ar.text
            except Exception as e:  # noqa: BLE001
                logger.info("Anthropic 文章抓取失败 %s: %s", slug, e)
                continue
            title = _meta(ah, "og:title") or slug.replace("-", " ").title()
            desc = _meta(ah, "og:description")
            published = _meta(ah, "article:published_time")
            if published and not within_hours(published, lookback_hours):
                continue
            items.append(Item(
                title=title,
                url=article_url,
                source=f"feature/{company}",
                kind=BLOG,
                author=company,
                body=desc,
                published=published,
                extra={"company": company},
            ))
    logger.info("Anthropic HTML: %d 条", len(items))
    return items
