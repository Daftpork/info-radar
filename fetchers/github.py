"""GitHub 抓取 —— 通用 AI 热门仓库 + 设计类热门仓库。

GitHub 无官方 trending API，用 Search API 近似：按「近期创建 + star 多」排序，
= 新且热的仓库。设计半区按设计 topic 搜。本地填 GITHUB_TOKEN 提额度；
GitHub Actions 里自动有 GITHUB_TOKEN。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from core.models import Item, REPO, looks_ai_related

logger = logging.getLogger(__name__)

API = "https://api.github.com/search/repositories"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "info-radar/0.1"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _since(lookback_hours: float) -> str:
    # 「新仓库」窗口比 lookback 宽些（trending 往往是近两三周冒出来的）
    days = max(14, int(lookback_hours / 24) + 1)
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


async def _search(client: httpx.AsyncClient, q: str, per_page: int = 20) -> list[dict]:
    try:
        r = await client.get(
            API,
            params={"q": q, "sort": "stars", "order": "desc", "per_page": per_page},
            timeout=25,
        )
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception as e:  # noqa: BLE001
        logger.warning("GitHub 搜索失败 (%s): %s", q[:60], e)
        return []


def _to_item(repo: dict, source: str) -> Item:
    return Item(
        title=repo.get("full_name", ""),
        url=repo.get("html_url", ""),
        source=source,
        kind=REPO,
        author=(repo.get("owner") or {}).get("login", ""),
        body=(repo.get("description") or "")[:600] +
             (f" [topics: {', '.join(repo.get('topics', [])[:6])}]" if repo.get("topics") else ""),
        published=repo.get("created_at", ""),
        metrics={"stars": repo.get("stargazers_count", 0), "forks": repo.get("forks_count", 0)},
    )


async def fetch_trending_general(lookback_hours: float, min_stars: int = 25) -> list[Item]:
    """新近创建、star 较多的仓库，过滤到 AI 相关。"""
    since = _since(lookback_hours)
    async with httpx.AsyncClient(headers=_headers()) as client:
        repos = await _search(client, f"created:>{since} stars:>{min_stars}", per_page=40)
    items = [_to_item(r, "github/trending") for r in repos]
    items = [it for it in items if looks_ai_related(f"{it.title} {it.body}")]
    logger.info("GitHub 通用: %d 条（AI 过滤后）", len(items))
    return items


async def fetch_design(topics: list[str], lookback_hours: float, min_stars: int = 40) -> list[Item]:
    """设计类近期崛起的热门仓库：每个 topic 单独查（GitHub Search 不支持 topic 间 OR）。
    用 created:>{约15个月} 排除远古巨仓（react/material-ui 等），只留近期冒头且已积累 star 的；
    sort=stars 取头部，靠 SeenStore 去重逐步换新。"""
    since = (datetime.now(timezone.utc) - timedelta(days=460)).strftime("%Y-%m-%d")
    seen: set[str] = set()
    items: list[Item] = []
    async with httpx.AsyncClient(headers=_headers()) as client:
        for t in topics:
            q = f"topic:{t} created:>{since} stars:>{min_stars}"
            for r in await _search(client, q, per_page=8):
                url = r.get("html_url", "")
                if url in seen:
                    continue
                seen.add(url)
                items.append(_to_item(r, "github/design"))
            await asyncio.sleep(0.7)  # 避免 GitHub 二级限流
    items.sort(key=lambda it: it.metrics.get("stars", 0), reverse=True)
    logger.info("GitHub 设计: %d 条", len(items))
    return items
