"""通用小工具：时间处理。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))  # 北京时间


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_str(tz: timezone = CST) -> str:
    """本地日期 YYYY-MM-DD（默认北京时区）。"""
    return datetime.now(tz).strftime("%Y-%m-%d")


def parse_iso(s: str) -> datetime | None:
    """尽量解析各种 ISO 时间串，返回带时区的 datetime；失败返回 None。"""
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # 回退：feedparser 常见的 RFC822 已在别处转好；这里再试几个格式
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def within_hours(iso: str, hours: float) -> bool:
    """时间戳是否在过去 hours 小时内。无法解析时返回 True（宁可多收不漏）。"""
    dt = parse_iso(iso)
    if dt is None:
        return True
    return (datetime.now(timezone.utc) - dt) <= timedelta(hours=hours)


def days_ago(iso: str) -> float | None:
    dt = parse_iso(iso)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
