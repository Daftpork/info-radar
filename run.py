#!/usr/bin/env python3
"""信息雷达 CLI 入口。

用法：
    python run.py thinker   [--dry-run]
    python run.py trend     [--dry-run]
    python run.py feature   [--dry-run]
    python run.py deepdive  [--dry-run]

--dry-run：抓取 + 生成 digest 并打印到 stdout，不发邮件、不写 state。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import sys

TRACKERS = ("thinker", "feature", "trend", "deepdive")


def main() -> int:
    parser = argparse.ArgumentParser(description="信息雷达 — 个人 AI 情报 tracker")
    parser.add_argument("tracker", choices=TRACKERS, help="要运行的 tracker")
    parser.add_argument("--dry-run", action="store_true", help="只打印不发送/不落库")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        module = importlib.import_module(f"trackers.{args.tracker}")
    except ModuleNotFoundError as e:
        # 该 tracker 尚未实现
        print(f"[run] tracker '{args.tracker}' 尚未实现: {e}", file=sys.stderr)
        return 2

    code = asyncio.run(module.run(dry_run=args.dry_run)) or 0

    # token 用量：打印 + 落库（dry-run 不落库）
    from core import llm, state
    from core.util import today_str
    usage = llm.usage_summary()
    logging.getLogger("run").info(
        "token 用量 | 调用 %d 次, 输入 %d, 输出 %d, 合计 %d | 按模型: %s",
        usage["calls"], usage["prompt"], usage["completion"], usage["total"], usage["by_model"],
    )
    state.record_usage(args.tracker, today_str(), usage, dry_run=args.dry_run)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
