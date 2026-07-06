"""静态站生成器：output/*.md（日报）+ output/transcripts/*.json（转录）→ site/dist/。

页面：
- index.html：按日期倒序列出每天的四类日报（观点/趋势/御三家动态/深读）+ 订阅表单
- d/<date>-<tracker>.html：日报正文（markdown→HTML，裸 URL 自动变链接）
- t/<slug>.html：转录页，中文详解 + 英文原稿，JS 按钮切换

无需额外依赖（用已有的 markdown 库）。部署后把站点基址设进 RADAR_SITE_BASE，
Buttondown 用户名设进 BUTTONDOWN_USERNAME。
"""

from __future__ import annotations

import html
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import markdown as md

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
TRANSCRIPTS = OUTPUT / "transcripts"
DIST = ROOT / "site" / "dist"

TRACKER = {"thinker": "观点", "trend": "趋势", "feature": "御三家动态", "deepdive": "深读"}
TRACKER_ORDER = ["thinker", "trend", "feature", "deepdive"]
TRACKER_EMOJI = {"thinker": "🧠", "trend": "📡", "feature": "🚀", "deepdive": "🔍"}
BUTTONDOWN_USER = os.getenv("BUTTONDOWN_USERNAME", "").strip()
SITE_TITLE = os.getenv("RADAR_SITE_TITLE", "信息雷达")
# GitHub 项目页挂在 /<repo>/ 下，内部链接要带这个前缀（用户/组织页或自定义域留空）
BASE = (os.getenv("RADAR_BASE_PATH") or "").rstrip("/")

_URL_LINE = re.compile(r"^(https?://\S+)$", re.MULTILINE)

CSS = """
:root{--fg:#1a1a1a;--mut:#666;--line:#eee;--acc:#2b6cb0;--bg:#fff}
@media(prefers-color-scheme:dark){:root{--fg:#e6e6e6;--mut:#999;--line:#2a2a2a;--acc:#6ea8ff;--bg:#141414}}
*{box-sizing:border-box}
body{font-family:-apple-system,"Segoe UI","PingFang SC",sans-serif;line-height:1.7;color:var(--fg);
background:var(--bg);max-width:760px;margin:0 auto;padding:28px 20px 80px}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:22px}h2{font-size:18px;margin-top:28px}h3{font-size:15px;margin:16px 0 4px}
hr{border:none;border-top:1px solid var(--line);margin:20px 0}
.mut{color:var(--mut);font-size:13px}
.card{border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
.card a.t{font-weight:600;font-size:16px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0}
.chip{border:1px solid var(--line);border-radius:20px;padding:3px 12px;font-size:13px}
.sub{border:1px solid var(--line);border-radius:10px;padding:16px;margin:18px 0;background:rgba(127,127,127,.05)}
.sub input[type=email]{padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);width:min(280px,60%)}
.sub input[type=submit]{padding:8px 16px;border:none;border-radius:8px;background:var(--acc);color:#fff;cursor:pointer}
.toggle{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;margin:14px 0}
.toggle button{padding:6px 16px;border:none;background:var(--bg);color:var(--fg);cursor:pointer;font-size:14px}
.toggle button.on{background:var(--acc);color:#fff}
pre.raw{white-space:pre-wrap;word-break:break-word;font-family:inherit;background:rgba(127,127,127,.06);
padding:14px;border-radius:8px;font-size:14px;line-height:1.8}
"""


def _shell(title: str, body: str) -> str:
    return (f"<!doctype html><html lang=zh><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>"
            f"<p class=mut><a href='{BASE}/'>← {html.escape(SITE_TITLE)}</a></p>{body}</body></html>")


def _sub_form() -> str:
    if not BUTTONDOWN_USER:
        return ("<div class=sub><b>订阅</b><p class=mut>（部署后设置 BUTTONDOWN_USERNAME 即可开启邮件订阅）</p></div>")
    u = html.escape(BUTTONDOWN_USER)
    return (f"<div class=sub><b>📮 订阅每日情报</b>"
            f"<form action='https://buttondown.com/api/emails/embed-subscribe/{u}' method=post "
            f"target=popupwindow onsubmit=\"window.open('https://buttondown.com/{u}','popupwindow')\">"
            f"<div class=row><input type=email name=email placeholder='your@email.com' required>"
            f"<input type=submit value='订阅'></div></form></div>")


def _md_to_html(text: str) -> str:
    linked = _URL_LINE.sub(r"[\1](\1)", text)
    return md.markdown(linked, extensions=["extra", "nl2br", "sane_lists"])


def _render_digests() -> dict:
    by_date: dict = defaultdict(dict)
    for f in OUTPUT.glob("*.md"):
        m = re.match(r"(\d{4}-\d{2}-\d{2})-(\w+)\.md", f.name)
        if not m:
            continue
        date, tracker = m.group(1), m.group(2)
        by_date[date][tracker] = f
        body = _md_to_html(f.read_text("utf-8"))
        (DIST / "d").mkdir(parents=True, exist_ok=True)
        (DIST / "d" / f"{date}-{tracker}.html").write_text(
            _shell(f"{TRACKER.get(tracker, tracker)} · {date}", body), "utf-8")
    return by_date


def _render_transcripts() -> None:
    if not TRANSCRIPTS.exists():
        return
    (DIST / "t").mkdir(parents=True, exist_ok=True)
    for j in TRANSCRIPTS.glob("*.json"):
        try:
            r = json.loads(j.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        detail_html = _md_to_html(r.get("detail_zh", ""))
        transcript = html.escape(r.get("transcript", ""))
        raw_label = "英文原稿" if r.get("orig_lang") == "en" else "全文"
        head = (f"<h1>{html.escape(r.get('title',''))}</h1>"
                f"<p class=mut>{html.escape(r.get('author',''))} · "
                f"<a href='{html.escape(r.get('url',''))}'>原链接</a></p>")
        toggle = (f"<div class=toggle><button id=b1 class=on onclick=\"sw('d')\">中文详解</button>"
                  f"<button id=b2 onclick=\"sw('r')\">{raw_label}</button></div>")
        body = (f"{head}{toggle}"
                f"<div id=d>{detail_html}</div>"
                f"<pre class=raw id=r style='display:none'>{transcript}</pre>"
                "<script>function sw(x){var d=document;"
                "d.getElementById('d').style.display=x=='d'?'block':'none';"
                "d.getElementById('r').style.display=x=='r'?'block':'none';"
                "d.getElementById('b1').className=x=='d'?'on':'';"
                "d.getElementById('b2').className=x=='r'?'on':'';}</script>")
        (DIST / "t" / f"{r['slug']}.html").write_text(
            _shell(r.get("title", "转录"), body), "utf-8")


def _render_index(by_date: dict) -> None:
    parts = [f"<h1>{html.escape(SITE_TITLE)}</h1>",
             "<p class=mut>个人 AI 信息雷达 · 观点 / 趋势 / 御三家动态 / 深读</p>",
             _sub_form()]
    for date in sorted(by_date, reverse=True):
        trackers = by_date[date]
        links = []
        for t in TRACKER_ORDER:
            if t in trackers:
                links.append(f"<a class=chip href='{BASE}/d/{date}-{t}.html'>{TRACKER_EMOJI[t]} {TRACKER[t]}</a>")
        parts.append(f"<div class=card><div class=mut>{date}</div><div class=row>{''.join(links)}</div></div>")
    (DIST / "index.html").write_text(_shell(SITE_TITLE, "".join(parts)), "utf-8")


def build() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    (DIST / ".nojekyll").write_text("", "utf-8")  # GitHub Pages: 别用 Jekyll
    by_date = _render_digests()
    _render_transcripts()
    _render_index(by_date)
    print(f"[site] built {len(by_date)} 天, {len(list((DIST/'t').glob('*.html'))) if (DIST/'t').exists() else 0} 转录页 → {DIST}")


if __name__ == "__main__":
    build()
