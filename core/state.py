"""JSON 状态持久化 — 去重 / 趋势历史 / 冷却。

所有状态存 state/*.json，由 GitHub Actions 每次运行结尾 commit 回仓，实现跨运行持久化
（去重、趋势增长计算、冷却都靠它）。JSON 比 SQLite 更适合 git diff/合并。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.util import days_ago, now_iso

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def write_output(filename: str, content: str, dry_run: bool = False) -> None:
    """把生成的 digest 归档到 output/（CI commit 回仓）。"""
    if dry_run:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / filename).write_text(content, "utf-8")


def _path(name: str) -> Path:
    return STATE_DIR / name


def load_json(name: str, default):
    p = _path(name)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("读取 state/%s 失败: %s", name, e)
        return default


def save_json(name: str, data) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _path(name).write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


# ---------------------------------------------------------------------------
# 去重存储：{item_id: iso_seen_at}，按 TTL 修剪
# ---------------------------------------------------------------------------
class SeenStore:
    def __init__(self, tracker: str, ttl_days: int = 30):
        self.name = f"seen_{tracker}.json"
        self.ttl_days = ttl_days
        self.data: dict[str, str] = load_json(self.name, {})

    def is_seen(self, item) -> bool:
        return item.id in self.data

    def mark(self, item) -> None:
        self.data[item.id] = now_iso()

    def filter_new(self, items: list) -> list:
        """返回未见过的 items（不改状态，需之后 mark）。"""
        return [it for it in items if not self.is_seen(it)]

    def mark_all(self, items: list) -> None:
        for it in items:
            self.mark(it)

    def _prune(self) -> None:
        cutoff = self.ttl_days
        self.data = {
            k: v for k, v in self.data.items()
            if (days_ago(v) or 0) <= cutoff
        }

    def save(self, dry_run: bool = False) -> None:
        if dry_run:
            return
        self._prune()
        save_json(self.name, self.data)


# ---------------------------------------------------------------------------
# 趋势历史：给行业深潜算「本周 vs 上周增长」用
# 结构: [{"date": "YYYY-MM-DD", "items": [{title,url,source,metrics}, ...]}, ...]
# ---------------------------------------------------------------------------
def append_trend_history(date: str, items: list, keep_days: int = 21, dry_run: bool = False) -> None:
    if dry_run:
        return
    hist = load_json("trend_history.json", [])
    hist = [h for h in hist if h.get("date") != date]  # 同日覆盖
    hist.append({
        "date": date,
        "items": [
            {"title": it.title, "url": it.url, "source": it.source,
             "kind": it.kind, "metrics": it.metrics}
            for it in items
        ],
    })
    hist = hist[-keep_days:]
    save_json("trend_history.json", hist)


def load_trend_history() -> list:
    return load_json("trend_history.json", [])
