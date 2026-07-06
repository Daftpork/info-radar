"""Thinker Tracker（每天）—— 四种源合并，只有 X 靠 follow-builders。

X 推文(follow-builders) + 深度长文(自建博客 RSS) + 视频(自建 YouTube) + 纯音频播客(Whisper)
→ 去重 → LLM 分组打标签 + 带观点提炼（curated 源，不逐条打分）→ 渲染 → 邮件。
"""

from __future__ import annotations

import asyncio
import logging

import config
from core import digest, llm, notify, scorer
from core.models import BLOG, PODCAST, VIDEO, dedupe
from core.prompts import load_prompt
from core.state import SeenStore, write_output
from core.util import today_str
from fetchers import followbuilders, podcast, rss, youtube

logger = logging.getLogger(__name__)


async def _gather() -> list:
    lookback = config.THINKER_LOOKBACK_HOURS
    tasks = [
        followbuilders.fetch_x(),
        rss.fetch_feeds(config.THINKER_BLOGS, kind=BLOG, lookback_hours=lookback),
        youtube.fetch_channels(config.THINKER_YOUTUBE, lookback_hours=lookback),
        podcast.fetch_podcasts(config.THINKER_PODCASTS, lookback_hours=lookback),
    ]
    if config.THINKER_USE_FOLLOWBUILDERS_PODCASTS:
        tasks.append(followbuilders.fetch_podcasts())

    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("某个源抓取异常: %s", r)
            continue
        items.extend(r)
    return dedupe(items)


async def run(dry_run: bool = False) -> int:
    date = today_str()
    items = await _gather()
    logger.info("Thinker 抓到 %d 条（去重后）", len(items))

    seen = SeenStore("thinker")
    fresh = seen.filter_new(items)
    logger.info("其中未推送过的 %d 条", len(fresh))
    if not fresh:
        logger.info("没有新内容，跳过")
        return 0

    sel = scorer.select_and_distill(
        fresh,
        instruction=load_prompt("thinker_distill"),
        keep=config.THINKER_KEEP,
        want_tag=True,
        want_bio=True,
        model=llm.HEAVY_MODEL,
        timeout_s=120,
    )
    if not sel:
        logger.info("LLM 未选出内容，跳过")
        seen.mark_all(items)
        seen.save(dry_run=dry_run)
        return 0

    entries = []
    for s in sel:
        it = fresh[s["index"]]
        # 个人（推文/博客）用 LLM 推断的精炼身份（更贴切）；
        # 播客/视频的 author 是节目本身，用配置里的节目描述，别让 LLM 塞嘉宾角色。
        if it.kind in (PODCAST, VIDEO):
            bio = it.author_bio
        else:
            bio = s.get("author_bio") or it.author_bio
        entries.append({
            "tag": s.get("tag") or "📌 其他",
            "author": it.author,
            "author_bio": bio,
            "source_type": it.kind,
            "title": it.title,
            "url": it.url,
            "insight": s["insight"],
        })

    tracked = len({e["author"] for e in entries if e["author"]})
    md = digest.render_thinker(date, tracked_people=tracked, entries=entries)

    notify.send_email(f"🧠 观点 · {date}", md, dry_run=dry_run)
    write_output(f"{date}-thinker.md", md, dry_run=dry_run)

    # 已抓到的全部标记为已见（未入选的也标，避免以后反复冒出来）
    seen.mark_all(items)
    seen.save(dry_run=dry_run)
    return 0
