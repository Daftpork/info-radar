"""YouTube 频道抓取 —— 频道 RSS 探新片 + youtube-transcript-api 读字幕（=声音转文字）。

风险：GitHub Actions 数据中心 IP 拉字幕可能被 YouTube 封 → 优雅降级用标题+简介。
@handle 会先解析成 channelId（解析结果缓存在 state，避免重复请求）。
"""

from __future__ import annotations

import logging
import re

import feedparser
import httpx

from core.models import Item, VIDEO
from core.state import load_json, save_json
from core.util import within_hours

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_CHANNEL_ID_RE = re.compile(r'"channelId":"(UC[\w-]+)"')
_TRANSCRIPT_MAX = 6000


async def _resolve_channel_id(client: httpx.AsyncClient, handle: str, cache: dict) -> str | None:
    if handle in cache:
        return cache[handle]
    url = f"https://www.youtube.com/{handle}"
    try:
        r = await client.get(url, timeout=20)
        r.raise_for_status()
        m = _CHANNEL_ID_RE.search(r.text)
        if m:
            cache[handle] = m.group(1)
            return m.group(1)
    except Exception as e:  # noqa: BLE001
        logger.warning("解析频道 %s 失败: %s", handle, e)
    return None


def _get_transcript(video_id: str) -> str:
    """拉字幕；失败返回空串（调用方降级）。兼容不同版本的 youtube-transcript-api。"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:  # noqa: BLE001
        return ""
    langs = ["en", "en-US", "zh-Hans", "zh"]
    try:
        # 新版 API
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=langs)
        segments = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
    except Exception:  # noqa: BLE001
        try:
            # 旧版 classmethod
            segments = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
        except Exception as e:  # noqa: BLE001
            logger.info("字幕不可用 %s: %s", video_id, e)
            return ""
    text = " ".join(s.get("text", "") for s in segments if s.get("text"))
    return text[:_TRANSCRIPT_MAX]


async def fetch_channels(channels: list[dict], *, lookback_hours: float, max_per_channel: int = 2) -> list[Item]:
    """channels: [{name, bio?, handle}]。返回近期视频（尽量带字幕）。"""
    cache = load_json("youtube_channel_ids.json", {})
    items: list[Item] = []
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, follow_redirects=True) as client:
        for ch in channels:
            handle = ch.get("handle", "")
            cid = ch.get("channel_id") or await _resolve_channel_id(client, handle, cache)
            if not cid:
                continue
            try:
                r = await client.get(
                    f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}", timeout=20
                )
                r.raise_for_status()
                feed = feedparser.parse(r.content)
            except Exception as e:  # noqa: BLE001
                logger.warning("YouTube feed 失败 %s: %s", handle, e)
                continue

            count = 0
            for entry in feed.entries:
                if count >= max_per_channel:
                    break
                published = entry.get("published", "")
                if published and not within_hours(published, lookback_hours):
                    continue
                vid = entry.get("yt_videoid", "")
                title = entry.get("title", "")
                link = entry.get("link", "")
                desc = ""
                if entry.get("media_description"):
                    desc = entry["media_description"]
                elif entry.get("summary"):
                    desc = entry["summary"]
                transcript = _get_transcript(vid) if vid else ""
                body = transcript or (f"{title}。{desc}"[:1500])
                items.append(Item(
                    title=title,
                    url=link,
                    source=f"youtube/{ch.get('name','')}",
                    kind=VIDEO,
                    author=ch.get("name", ""),
                    author_bio=ch.get("bio", ""),
                    body=body,
                    published=published,
                    extra={"has_transcript": bool(transcript)},
                ))
                count += 1
    save_json("youtube_channel_ids.json", cache)
    logger.info("YouTube: %d 频道 → %d 视频", len(channels), len(items))
    return items
