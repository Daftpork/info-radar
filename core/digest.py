"""日报渲染器 — 采用 Vanessa 风格模板。

分工：LLM（core/scorer）负责「选 + 分组打标签 + 写带观点的中文提炼」，产出结构化 entries；
本模块只做确定性的 markdown 拼装，不调用 LLM。
"""

from __future__ import annotations

import os
from collections import OrderedDict

# 站点基址（部署后设为 secret）；设了才在 digest 里放「全文+详解」链接
SITE_BASE = (os.getenv("RADAR_SITE_BASE") or "").rstrip("/")

# 来源类型的中文label
SOURCE_TYPE_LABEL = {
    "tweet": "X", "blog": "博客", "podcast": "播客", "video": "YouTube",
    "repo": "GitHub", "product": "Product Hunt", "paper": "arXiv",
}


# ---------------------------------------------------------------------------
# Thinker
# ---------------------------------------------------------------------------
def render_thinker(date: str, tracked_people: int, entries: list[dict]) -> str:
    """entries: [{tag, author, author_bio, source_type, title, url, insight}]"""
    lines = [
        f"🧠 观点 · {date}",
        f"追踪 {tracked_people} 人 · {len(entries)} 条动态",
        "",
    ]
    # 按 tag 分组，保留首次出现顺序
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for e in entries:
        groups.setdefault(e.get("tag") or "📌 其他", []).append(e)

    for tag, items in groups.items():
        lines.append(f"🏷️ {tag}")
        for e in items:
            src = SOURCE_TYPE_LABEL.get(e.get("source_type", ""), e.get("source_type", ""))
            bio = f"（{e['author_bio']}）" if e.get("author_bio") else ""
            head = f"{e.get('author','')}{bio}"
            if src:
                head += f" · {src}"
            lines.append(head)
            if e.get("title"):
                lines.append(f"**{e['title']}**")
            if e.get("url"):
                lines.append(f"{e['url']}")
            lines.append("")
            lines.append(e.get("insight", ""))
            if e.get("detail_slug") and SITE_BASE:
                lines.append(f"📄 [全文+详解]({SITE_BASE}/t/{e['detail_slug']}.html)")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Trend（两半区合一）
# ---------------------------------------------------------------------------
def render_trend(date: str, summary: str, sections: "OrderedDict[str, list[dict]]") -> str:
    """sections: {区块名: [{label, meta, url, insight}]}
    label 如 'owner/repo'；meta 如 '★ 1,703' 或 '⬆ New'。空区块跳过。"""
    total = sum(len(v) for v in sections.values())
    lines = [
        f"📡 趋势 · {date}",
        summary or f"今日精选共 {total} 条。",
        "",
    ]
    for name, items in sections.items():
        if not items:
            continue
        lines.append(f"## {name}")
        for it in items:
            meta = f" {it['meta']}" if it.get("meta") else ""
            lines.append(f"📌 {it.get('label','')}{meta}")
            if it.get("url"):
                lines.append(it["url"])
            lines.append(it.get("insight", ""))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Feature（御三家产品更新）
# ---------------------------------------------------------------------------
def render_feature(date: str, entries: list[dict]) -> str:
    """entries: [{company, title, url, insight}]，按 company 分组。"""
    lines = [
        f"🚀 御三家动态 · {date}",
        f"本周御三家产品更新共 {len(entries)} 条。",
        "",
    ]
    groups: "OrderedDict[str, list[dict]]" = OrderedDict()
    for e in entries:
        groups.setdefault(e.get("company") or "其他", []).append(e)
    for company, items in groups.items():
        lines.append(f"## {company}")
        for e in items:
            lines.append(f"**{e.get('title','')}**")
            if e.get("url"):
                lines.append(e["url"])
            lines.append(e.get("insight", ""))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# 行业深潜（正文由 LLM 直接产出长文 markdown，这里只包个头）
# ---------------------------------------------------------------------------
def render_deepdive(date: str, topic: str, body_markdown: str) -> str:
    return f"🔍 深读 · {date} — {topic}\n\n{body_markdown.strip()}\n"
