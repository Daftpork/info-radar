"""Trend Tracker（每周一三五）—— 两半区，合成一封邮件。

通用半区：GitHub 通用 + Product Hunt + Hugging Face + arXiv → 逐源 LLM 选+提炼。
设计半区：GitHub 设计 topic → 设计 rubric 选+提炼。
另把入选项写入 trend_history，供行业深潜算增长趋势。
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict

import config
from core import digest, llm, notify, scorer
from core.models import PAPER
from core.prompts import load_prompt
from core.state import SeenStore, append_trend_history, write_output
from core.util import today_str
from fetchers import arxiv, github, huggingface, producthunt

logger = logging.getLogger(__name__)


def _label_meta(it) -> tuple[str, str]:
    m = it.metrics or {}
    if it.source.startswith("github"):
        stars = m.get("stars", 0)
        return it.title, (f"★ {stars:,}" if stars else "")
    if it.source.startswith("huggingface"):
        likes = m.get("likes")
        return it.title, (f"❤ {likes}" if likes else "")
    if it.source == "producthunt":
        tagline = (it.extra or {}).get("tagline", "")
        votes = m.get("votes")
        label = f"{it.title} — {tagline}" if tagline else it.title
        return label, (f"⬆ {votes}" if votes else "⬆ New")
    if it.kind == PAPER:
        up = m.get("upvotes")
        return it.title, (f"👍 {up}" if up else "")
    return it.title, ""


def _entries(items: list, selected: list[dict]) -> list[dict]:
    out = []
    for s in selected:
        it = items[s["index"]]
        label, meta = _label_meta(it)
        out.append({"label": label, "meta": meta, "url": it.url, "insight": s["insight"]})
    return out


def _summary_line(sections: "OrderedDict[str, list[dict]]", total: int) -> str:
    labels = [e["label"] for items in sections.values() for e in items][:20]
    if not labels:
        return f"今日精选共 {total} 条。"
    try:
        line = llm.chat(
            "下面是今天精选的 AI 领域热门项目/论文标题，请用一句中文概括今日看点，"
            "并给出 2-4 个关键词。格式：`今日从 GitHub、Product Hunt、Hugging Face、arXiv 精选共 "
            f"{total} 条。今日关键词：X、Y、Z`。只输出这一句：\n\n" + "\n".join(labels),
            max_tokens=200,
        ).strip().splitlines()[0]
        return line or f"今日精选共 {total} 条。"
    except Exception:  # noqa: BLE001
        return f"今日从 GitHub、Product Hunt、Hugging Face、arXiv 精选共 {total} 条。"


async def run(dry_run: bool = False) -> int:
    date = today_str()
    lookback = config.TREND_LOOKBACK_HOURS

    gh, ph, hf, papers, design = await asyncio.gather(
        github.fetch_trending_general(lookback),
        producthunt.fetch_top(lookback),
        huggingface.fetch_trending(),
        arxiv.fetch_papers(config.TREND_ARXIV_CATEGORIES, lookback),
        github.fetch_design(config.TREND_DESIGN_TOPICS, lookback),
        return_exceptions=True,
    )
    gh, ph, hf, papers, design = [
        ([] if isinstance(x, Exception) else x) for x in (gh, ph, hf, papers, design)
    ]

    seen = SeenStore("trend")
    trend_instr = load_prompt("trend_score")
    design_instr = load_prompt("design_score")

    general = OrderedDict([
        ("On GitHub", (gh, 4)),
        ("On Product Hunt", (ph, 5)),
        ("On Hugging Face", (hf, 4)),
        ("On arXiv", (papers, 4)),
    ])

    sections: "OrderedDict[str, list[dict]]" = OrderedDict()
    selected_items: list = []
    all_fetched: list = []

    for name, (items, keep) in general.items():
        all_fetched.extend(items)
        fresh = seen.filter_new(items)
        if not fresh:
            sections[name] = []
            continue
        sel = scorer.select_and_distill(fresh, instruction=trend_instr, keep=keep, want_tag=False)
        sections[name] = _entries(fresh, sel)
        selected_items.extend(fresh[s["index"]] for s in sel)

    # 设计半区：排除已在通用半区出现过的仓库
    exclude = {it.id for it in gh + ph + hf + papers}
    all_fetched.extend(design)
    dfresh = [it for it in seen.filter_new(design) if it.id not in exclude]
    dsel = scorer.select_and_distill(
        dfresh, instruction=design_instr, keep=config.TREND_KEEP_DESIGN, want_tag=False
    ) if dfresh else []
    sections["🎨 GitHub 设计精选"] = _entries(dfresh, dsel)
    selected_items.extend(dfresh[s["index"]] for s in dsel)

    total = sum(len(v) for v in sections.values())
    if total == 0:
        logger.info("Trend 无新内容，跳过")
        seen.mark_all(all_fetched)
        seen.save(dry_run=dry_run)
        return 0

    summary = _summary_line(sections, total)
    md = digest.render_trend(date, summary, sections)

    notify.send_email(f"📡 Trend Tracker · {date}", md, dry_run=dry_run)
    write_output(f"{date}-trend.md", md, dry_run=dry_run)
    append_trend_history(date, selected_items, dry_run=dry_run)

    seen.mark_all(all_fetched)
    seen.save(dry_run=dry_run)
    return 0
