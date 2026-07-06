"""通用文本 LLM 打分/提炼器 — 各 tracker 共用的「大脑」。

设计：LLM 负责从一批候选里「选出最值得看的 + 分组打标签 + 写带观点的中文提炼」，
本模块把候选压缩成紧凑列表喂给 LLM，解析回结构化 entries（引用 item 序号 + insight + tag）。
rubric（挑选标准）由各 tracker 以 instruction 传入。纯文本，无 vision。
"""

from __future__ import annotations

import logging

from core import llm
from core.models import Item

logger = logging.getLogger(__name__)

# 全局编辑嗓音（Vanessa 质量标准）—— 所有 tracker 共用
BASE_VOICE = """你是一名资深 AI 行业编辑，为一份高质量中文情报日报做提炼。要求：
- 每条提炼是「带观点的蒸馏」，不是中性翻译或复述。要给出判断，常用破折号「——」引出一句态度鲜明的评点（例：「工具链垄断风险浮出水面」「观点激进但逻辑自洽」「信息密度极高」）。
- 中文，简洁、信息密度高，每条 1–2 句。
- 绝不编造：只依据给定内容，不虚构事实、数据或人物身份。
- 不要复读标题，要提炼出「所以呢 / 意味着什么」。"""

DEFAULT_TAGS = [
    "AI 工程/工具", "AI 能力突破", "AI 治理", "AI 经济",
    "产品/UX", "开源/模型发布", "机器人/具身", "📌 其他",
]


def _fmt_items(items: list[Item], body_chars: int = 400) -> str:
    rows = []
    for i, it in enumerate(items):
        snippet = " ".join((it.body or "").split())[:body_chars]
        bio = f"({it.author_bio}) " if it.author_bio else ""
        metrics = " ".join(f"{k}={v}" for k, v in (it.metrics or {}).items())
        metrics = f" [指标:{metrics}]" if metrics else ""
        rows.append(
            f"[{i}] 来源={it.source} 作者={it.author or '-'} {bio}类型={it.kind}{metrics}\n"
            f"    标题: {it.title}\n"
            f"    内容: {snippet}"
        )
    return "\n".join(rows)


def select_and_distill(
    items: list[Item],
    *,
    instruction: str,
    keep: int,
    want_tag: bool = True,
    want_bio: bool = False,
    tag_pool: list[str] | None = None,
    model: str | None = None,
) -> list[dict]:
    """从 items 里选出至多 keep 条并为每条写带观点提炼。

    返回 [{index:int, insight:str, tag:str|None, author_bio:str|None}]，按重要性排序。
    caller 用 items[index] 补 url/title/author 等，与本模块解耦。
    """
    if not items:
        return []

    fields = [
        '"index": <候选序号，整数>',
        '"insight": "<带观点的中文提炼，1-2句，含破折号——判断>"',
    ]
    if want_tag:
        if tag_pool:
            tag_hint = "，从这些标签里选最贴切的一个：" + " / ".join(tag_pool)
        else:
            tag_hint = "，用一个简短中文主题标签，例如：" + " / ".join(DEFAULT_TAGS)
        fields.append(f'"tag": "<主题标签{tag_hint}>"')
    if want_bio:
        fields.append(
            '"author_bio": "<该作者广为人知的身份/角色，如「独立开发者」「Meta 首席AI科学家」；'
            '不确定就留空字符串，切勿编造>"'
        )
    schema = "{ " + ", ".join(fields) + " }"

    prompt = f"""{instruction}

从下面 {len(items)} 条候选里，挑出最值得一读的**至多 {keep} 条**，按重要性从高到低排序，为每条写提炼。
宁缺毋滥：不够好的不必凑数。只返回一个 JSON 数组，每个元素形如：
{schema}

候选列表：
{_fmt_items(items)}

只输出 JSON 数组，不要任何多余文字。"""

    max_tokens = min(4000, 400 + keep * 200)
    try:
        data = llm.chat_json(prompt, system=BASE_VOICE, model=model, max_tokens=max_tokens)
    except Exception as e:  # noqa: BLE001
        logger.error("select_and_distill LLM 失败: %s", e)
        return []

    if not isinstance(data, list):
        logger.warning("select_and_distill 返回非数组: %r", str(data)[:200])
        return []

    out = []
    for e in data:
        if not isinstance(e, dict):
            continue
        idx = e.get("index")
        if not isinstance(idx, int) or not (0 <= idx < len(items)):
            continue
        out.append({
            "index": idx,
            "insight": (e.get("insight") or "").strip(),
            "tag": (e.get("tag") or "").strip() or None,
            "author_bio": (e.get("author_bio") or "").strip() or None,
        })
    return out[:keep]


def triage(items: list[Item], *, keep: int, criteria: str, model: str | None = None) -> list[Item]:
    """轻量预筛：从大批候选里选出 keep 条（只挑不提炼），降后续成本。"""
    if len(items) <= keep:
        return items
    prompt = f"""{criteria}

从下面 {len(items)} 条里选出最值得深入看的 {keep} 条，只返回它们的序号，形如 [3,7,12]。

{_fmt_items(items, body_chars=200)}

只输出一个数字 JSON 数组。"""
    try:
        data = llm.chat_json(prompt, system=BASE_VOICE, model=model, max_tokens=500)
    except Exception as e:  # noqa: BLE001
        logger.warning("triage 失败，退回前 %d 条: %s", keep, e)
        return items[:keep]
    if not isinstance(data, list):
        return items[:keep]
    picked = [items[i] for i in data if isinstance(i, int) and 0 <= i < len(items)]
    return picked[:keep] if picked else items[:keep]
