"""纯音频播客抓取 —— RSS 探新集 → 下载音频 → ffmpeg 降采样分片 → Whisper API 转录。

Whisper API 有 25MB 上限，故：降采样成单声道 16kHz 32kbps，再按 25 分钟分片逐片转录后拼接。
任一环节缺失/失败（无 WHISPER_API_KEY、无 ffmpeg、下载失败）→ 优雅降级用 show notes。
转录是阻塞操作，走 asyncio.to_thread。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import feedparser
import httpx

from core.models import Item, PODCAST
from core.util import within_hours

logger = logging.getLogger(__name__)

WHISPER_BASE = os.getenv("WHISPER_BASE_URL", "https://api.openai.com/v1").rstrip("/")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
_UA = "Mozilla/5.0 (compatible; info-radar/0.1)"
_TAG_RE = re.compile(r"<[^>]+>")
_TRANSCRIPT_MAX = 12000
_SEGMENT_SECONDS = 1500  # 25 分钟/片，降采样后约 6MB，稳在 25MB 限下


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _enclosure_url(entry) -> str:
    for enc in entry.get("enclosures", []) or []:
        if enc.get("href") and "audio" in (enc.get("type", "") or "audio"):
            return enc["href"]
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and link.get("href"):
            return link["href"]
    return ""


def _download(url: str, dst: Path) -> bool:
    try:
        with httpx.stream("GET", url, headers={"User-Agent": _UA},
                          follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
        return dst.stat().st_size > 0
    except Exception as e:  # noqa: BLE001
        logger.warning("音频下载失败 %s: %s", url, e)
        return False


def _downsample_and_segment(src: Path, workdir: Path) -> list[Path]:
    """降采样成 mono/16k/32k 并切成 25 分钟片，返回片文件列表。"""
    pattern = str(workdir / "seg_%03d.mp3")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src),
        "-ac", "1", "-ar", "16000", "-b:a", "32k",
        "-f", "segment", "-segment_time", str(_SEGMENT_SECONDS), "-y", pattern,
    ]
    subprocess.run(cmd, check=True, timeout=1800)
    return sorted(workdir.glob("seg_*.mp3"))


def _whisper_one(path: Path, api_key: str) -> str:
    with open(path, "rb") as f:
        files = {"file": (path.name, f, "audio/mpeg")}
        data = {"model": WHISPER_MODEL, "response_format": "text"}
        r = httpx.post(
            f"{WHISPER_BASE}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files=files, data=data, timeout=300,
        )
    r.raise_for_status()
    ct = r.headers.get("content-type", "")
    return r.json().get("text", "") if "json" in ct else r.text


def _transcribe(audio_url: str) -> str:
    api_key = os.getenv("WHISPER_API_KEY", "").strip()
    if not api_key or not _has_ffmpeg():
        return ""
    with tempfile.TemporaryDirectory(prefix="ir_pod_") as tmp:
        tmpdir = Path(tmp)
        raw = tmpdir / "audio.src"
        if not _download(audio_url, raw):
            return ""
        try:
            segments = _downsample_and_segment(raw, tmpdir)
        except Exception as e:  # noqa: BLE001
            logger.warning("ffmpeg 处理失败: %s", e)
            return ""
        parts: list[str] = []
        for seg in segments:
            try:
                parts.append(_whisper_one(seg, api_key))
            except Exception as e:  # noqa: BLE001
                logger.warning("Whisper 转录失败 %s: %s", seg.name, e)
        return " ".join(p.strip() for p in parts if p).strip()[:_TRANSCRIPT_MAX]


async def fetch_podcasts(podcasts: list[dict], *, lookback_hours: float,
                         max_per_podcast: int = 1) -> list[Item]:
    """podcasts: [{name, bio?, rss}]。每档最多取 max_per_podcast 集最新。"""
    if not podcasts:
        return []
    items: list[Item] = []
    async with httpx.AsyncClient(headers={"User-Agent": _UA}, follow_redirects=True) as client:
        for pod in podcasts:
            url = pod.get("rss", "")
            try:
                r = await client.get(url, timeout=25)
                r.raise_for_status()
                feed = feedparser.parse(r.content)
            except Exception as e:  # noqa: BLE001
                logger.warning("播客 RSS 失败 %s: %s", pod.get("name"), e)
                continue

            count = 0
            for entry in feed.entries:
                if count >= max_per_podcast:
                    break
                published = entry.get("published", "")
                if published and not within_hours(published, lookback_hours):
                    continue
                show_notes = _TAG_RE.sub(" ", entry.get("summary", "")).strip()[:2000]
                audio = _enclosure_url(entry)
                transcript = ""
                if audio:
                    transcript = await asyncio.to_thread(_transcribe, audio)
                items.append(Item(
                    title=entry.get("title", ""),
                    url=entry.get("link", "") or audio,
                    source=f"podcast/{pod.get('name','')}",
                    kind=PODCAST,
                    author=pod.get("name", ""),
                    author_bio=pod.get("bio", ""),
                    body=transcript or show_notes,
                    published=published,
                    extra={"has_transcript": bool(transcript)},
                ))
                count += 1
    logger.info("播客: %d 档 → %d 集", len(podcasts), len(items))
    return items
