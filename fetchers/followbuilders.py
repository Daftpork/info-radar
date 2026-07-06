"""消费 follow-builders 中心 feed —— 只为拿 X 推文（唯一自建要花钱的部分，白嫖）。

feed 是 zarazhangrui 仓库里 commit 的 JSON（每天更新）。纯 GET，无需 key。
数据结构（见调查）：
  feed-x.json      -> {x: [{name, handle, bio, tweets:[{text,url,createdAt,likes,retweets,replies}]}]}
  feed-podcasts.json -> {podcasts: [{name,title,url,publishedAt,transcript}]}
"""

from __future__ import annotations

import logging

import httpx

from core.models import Item, PODCAST, TWEET

logger = logging.getLogger(__name__)

RAW = "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main"
FEED_X = f"{RAW}/feed-x.json"
FEED_PODCASTS = f"{RAW}/feed-podcasts.json"


async def _get_json(client: httpx.AsyncClient, url: str) -> dict | None:
    try:
        r = await client.get(url, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("拉取 %s 失败: %s", url, e)
        return None


async def fetch_x() -> list[Item]:
    """25 个 builder 的近期推文 → Item(kind=tweet)。"""
    async with httpx.AsyncClient() as client:
        data = await _get_json(client, FEED_X)
    if not data:
        return []
    items: list[Item] = []
    for b in data.get("x", []):
        name = b.get("name") or b.get("handle", "")
        bio = b.get("bio", "")
        handle = b.get("handle", "")
        for t in b.get("tweets", []):
            text = (t.get("text") or "").strip()
            if not text:
                continue
            title = text.split("\n", 1)[0][:80]
            items.append(Item(
                title=title,
                url=t.get("url", ""),
                source=f"x/{handle}",
                kind=TWEET,
                author=name,
                author_bio=bio,
                body=text,
                published=t.get("createdAt", ""),
                metrics={k: t[k] for k in ("likes", "retweets", "replies") if t.get(k)},
            ))
    logger.info("follow-builders X: %d 条推文", len(items))
    return items


async def fetch_podcasts() -> list[Item]:
    """follow-builders 已转录的播客（免费兜底，通常每次最多 1 集）。"""
    async with httpx.AsyncClient() as client:
        data = await _get_json(client, FEED_PODCASTS)
    if not data:
        return []
    items: list[Item] = []
    for p in data.get("podcasts", []):
        transcript = (p.get("transcript") or "").strip()
        if not transcript:
            continue
        items.append(Item(
            title=p.get("title", ""),
            url=p.get("url", ""),
            source=f"podcast/{p.get('name','')}",
            kind=PODCAST,
            author=p.get("name", ""),
            body=transcript,
            published=p.get("publishedAt", ""),
        ))
    logger.info("follow-builders 播客: %d 集", len(items))
    return items
