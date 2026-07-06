"""播客/视频转录归档 + 中文详解生成。

给 Thinker 选中的、带真实转录的播客/视频，生成一份中文详解（分点 + 金句英中对照），
连同原文全文存成 output/transcripts/<slug>.json，供静态站渲染「详解 + 原文」双语切换页。
"""

from __future__ import annotations

import logging
import re

from core import llm, state
from core.models import PODCAST, VIDEO
from core.prompts import load_prompt

logger = logging.getLogger(__name__)

_CJK = re.compile(r"[一-鿿]")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _looks_chinese(text: str) -> bool:
    sample = text[:500]
    cjk = len(_CJK.findall(sample))
    return cjk > 30  # 中文转录会有大量汉字


def _slug(date: str, item) -> str:
    base = item.source.replace("/", "-") + "-" + (item.title or "")
    s = _SLUG_STRIP.sub("-", base.lower()).strip("-")[:60]
    return f"{date}-{s}" if s else f"{date}-{item.id}"


def polish(text: str) -> str:
    """给语音转录稿加标点 + 分段（严格不改字），让「全文」能读。分块处理保证忠实。"""
    text = (text or "").strip()
    if len(text) < 120:
        return text
    step = 4000
    chunks = [text[i:i + step] for i in range(0, min(len(text), 20000), step)]
    out = []
    for ch in chunks:
        try:
            polished = llm.chat(
                "下面是一段语音转文字稿，缺标点、没分段，很难读。你只做两件事："
                "①补上正确的标点符号 ②按语义分段（段与段之间空一行）。"
                "严格保留原文每一个字，不改写、不删减、不总结、不翻译。直接输出处理后的文字：\n\n" + ch,
                model=llm.DEFAULT_MODEL, max_tokens=3400, timeout_s=120,
            )
            out.append(polished.strip())
        except Exception as e:  # noqa: BLE001
            logger.warning("转录润色失败(保留原样): %s", e)
            out.append(ch)
    return "\n\n".join(out)


def archive(item, date: str, *, dry_run: bool = False) -> dict | None:
    """为一个带转录的播客/视频 item 生成中文详解 + 存档，返回记录（含 slug）。"""
    if item.kind not in (PODCAST, VIDEO):
        return None
    if not (item.extra or {}).get("has_transcript"):
        return None
    transcript = (item.body or "").strip()
    if len(transcript) < 300:
        return None

    is_zh = _looks_chinese(transcript)
    try:
        detail_zh = llm.chat(
            f"播客/视频标题：《{item.title}》，来源：{item.author or item.source}。\n\n转录全文：\n{transcript[:12000]}",
            system=load_prompt("transcript_detail"),
            model=llm.DEFAULT_MODEL,
            max_tokens=2200,
            timeout_s=120,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("转录详解生成失败 %s: %s", item.title, e)
        return None

    slug = _slug(date, item)
    record = {
        "date": date,
        "slug": slug,
        "title": item.title,
        "source": item.source,
        "author": item.author,
        "author_bio": item.author_bio,
        "url": item.url,
        "orig_lang": "zh" if is_zh else "en",
        "detail_zh": detail_zh,
        "transcript": polish(transcript),
    }
    state.save_transcript(slug, record, dry_run=dry_run)
    logger.info("转录归档: %s (%s)", slug, "中文" if is_zh else "英文")
    return record
