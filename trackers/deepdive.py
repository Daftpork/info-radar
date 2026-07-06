"""行业深潜（每周）—— 从累积的 trend_history 里挑最热赛道，Exa 深挖，LLM 写第一人称长文。

依赖 Trend 跑过几次攒下的 trend_history；不足时临时抓一份快照兜底。
用重模型（gpt-5.5）写，质量优先。
"""

from __future__ import annotations

import asyncio
import logging

import config
from core import digest, llm, notify
from core.prompts import load_prompt
from core.state import load_json, load_trend_history, save_json, write_output
from core.util import today_str
from fetchers import arxiv, exa, github, huggingface

logger = logging.getLogger(__name__)


async def _material() -> list[dict]:
    items: list[dict] = []
    for day in load_trend_history()[-7:]:
        items.extend(day.get("items", []))
    if len(items) < 8:
        logger.info("trend_history 不足，临时抓快照兜底")
        gh, papers, hf = await asyncio.gather(
            github.fetch_trending_general(72),
            arxiv.fetch_papers(config.TREND_ARXIV_CATEGORIES, 72),
            huggingface.fetch_trending(20),
            return_exceptions=True,
        )
        for r in (gh, papers, hf):
            if not isinstance(r, Exception):
                items.extend({"title": it.title, "url": it.url, "source": it.source,
                              "metrics": it.metrics} for it in r)
    return items


def _fmt_material(items: list[dict]) -> str:
    rows = []
    for it in items[:40]:
        m = " ".join(f"{k}={v}" for k, v in (it.get("metrics") or {}).items())
        rows.append(f"- {it.get('title','')} [{it.get('source','')}] {m} {it.get('url','')}")
    return "\n".join(rows)


async def _pick_topic(material: str, past: list[str]) -> dict:
    prompt = f"""下面是过去一周信息雷达收集到的 AI 热门项目/论文（含来源）。
请选出**最值得做一篇「行业深潜」深度分析的一个赛道/主题**（如：AI Agent 安全、机器人/具身智能、本地推理、AI 编程工具、AI 科研 等）。
避免最近做过的主题：{('、'.join(past) if past else '无')}。

返回 JSON：{{"topic": "赛道名", "angle": "为什么这周值得深挖的一句话", "queries": ["3-5 个用于深入检索的英文查询"]}}

材料：
{material}

只输出 JSON。"""
    try:
        data = llm.chat_json(prompt, max_tokens=500)
        if isinstance(data, dict) and data.get("topic"):
            return data
    except Exception as e:  # noqa: BLE001
        logger.warning("选题失败: %s", e)
    return {}


async def run(dry_run: bool = False) -> int:
    if not config.DEEPDIVE_ENABLED:
        return 0
    date = today_str()
    material_items = await _material()
    if not material_items:
        logger.info("无材料，深潜跳过")
        return 0
    material = _fmt_material(material_items)

    past = load_json("deepdive_topics.json", [])[-6:]
    picked = await _pick_topic(material, past)
    if not picked:
        logger.info("未选出主题，跳过")
        return 0
    topic = picked["topic"]
    logger.info("本周深潜主题: %s", topic)

    # Exa 深挖（有 key 才跑）
    exa_sources: list[dict] = []
    for q in (picked.get("queries") or [])[:config.DEEPDIVE_EXA_QUERIES_PER_TOPIC]:
        exa_sources.extend(await exa.search(q, num=5))
    exa_block = "\n".join(
        f"- {s['title']} ({s['url']}): {s['text'][:400]}" for s in exa_sources[:20]
    ) or "（无额外检索资料，仅用上方热门材料）"

    writing = f"""赛道/主题：{topic}
本周为何值得深挖：{picked.get('angle','')}

【本周热门材料（真实、可引用）】
{material}

【深入检索到的资料】
{exa_block}"""

    body = llm.chat(
        writing,
        system=load_prompt("deepdive"),
        model=llm.HEAVY_MODEL,
        max_tokens=4500,
        timeout_s=180,
    )
    md = digest.render_deepdive(date, topic, body)

    notify.send_email(f"🔍 深读 · {date} — {topic}", md, dry_run=dry_run)
    write_output(f"{date}-deepdive.md", md, dry_run=dry_run)

    if not dry_run:
        topics = load_json("deepdive_topics.json", [])
        topics.append(topic)
        save_json("deepdive_topics.json", topics[-20:])
    return 0
