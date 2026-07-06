"""Feature Tracker（每周五）—— 御三家（OpenAI/Anthropic/Google）产品更新。

OpenAI/Google 有 RSS；Anthropic 无 RSS 走 HTML 解析。curated 源，不逐条打分，
只 LLM 选出真更新 + 带观点提炼。
"""

from __future__ import annotations

import asyncio
import logging

import config
from core import digest, notify, scorer
from core.models import BLOG, dedupe
from core.prompts import load_prompt
from core.state import SeenStore, write_output
from core.util import today_str
from fetchers import htmlnews, rss

logger = logging.getLogger(__name__)


async def _gather() -> list:
    lookback = config.FEATURE_LOOKBACK_HOURS
    rss_sources = [
        {"name": s["company"], "rss": s["url"], "company": s["company"], "bio": ""}
        for s in config.FEATURE_SOURCES if s["type"] == "rss"
    ]
    tasks = [rss.fetch_feeds(rss_sources, kind=BLOG, lookback_hours=lookback, company_field=True)]
    for s in config.FEATURE_SOURCES:
        if s["type"] == "html":
            tasks.append(htmlnews.fetch_anthropic(s["url"], company=s["company"], lookback_hours=lookback))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Feature 某源异常: %s", r)
            continue
        items.extend(r)
    return dedupe(items)


async def run(dry_run: bool = False) -> int:
    date = today_str()
    items = await _gather()
    logger.info("Feature 抓到 %d 条", len(items))

    seen = SeenStore("feature")
    fresh = seen.filter_new(items)
    if not fresh:
        logger.info("Feature 无新内容，跳过")
        return 0

    sel = scorer.select_and_distill(
        fresh, instruction=load_prompt("feature_distill"),
        keep=config.FEATURE_KEEP, want_tag=False,
    )
    if not sel:
        seen.mark_all(items)
        seen.save(dry_run=dry_run)
        return 0

    entries = []
    for s in sel:
        it = fresh[s["index"]]
        entries.append({
            "company": (it.extra or {}).get("company") or it.author,
            "title": it.title,
            "url": it.url,
            "insight": s["insight"],
        })

    md = digest.render_feature(date, entries)
    notify.send_email(f"🚀 Feature Weekly · {date}", md, dry_run=dry_run)
    write_output(f"{date}-feature.md", md, dry_run=dry_run)

    seen.mark_all(items)
    seen.save(dry_run=dry_run)
    return 0
