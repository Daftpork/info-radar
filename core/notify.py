"""邮件送达 — SMTP（Gmail 应用专用密码），markdown → HTML。

改自 need-discovery/notifier.py，泛化成 send_email(subject, markdown_body)。
不用 Resend（follow-builders 用 resend.dev 沙盒域名被 QQ 判垃圾）；Gmail SMTP 发信
从真实 Gmail 出，送达 QQ 更稳。dry_run 只打印不发送。
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import markdown as md
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_HTML_STYLE = """
<style>
  body { font-family: -apple-system, "Segoe UI", "PingFang SC", sans-serif;
         line-height: 1.6; color: #222; max-width: 720px; margin: 0 auto; }
  h1 { font-size: 20px; } h2 { font-size: 17px; margin-top: 24px; }
  h3 { font-size: 15px; margin: 14px 0 4px; }
  a { color: #2b6cb0; text-decoration: none; }
  hr { border: none; border-top: 1px solid #eee; margin: 18px 0; }
  code { background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }
  blockquote { border-left: 3px solid #ddd; margin: 6px 0; padding-left: 12px; color: #555; }
</style>
"""


def _get_email_config() -> dict | None:
    email_to = os.getenv("EMAIL_TO", "").strip()
    email_from = os.getenv("EMAIL_FROM", "").strip()
    email_password = os.getenv("EMAIL_PASSWORD", "").strip()
    if not (email_to and email_from and email_password):
        return None
    return {
        "to": email_to,
        "from": email_from,
        "password": email_password,
        "host": os.getenv("EMAIL_SMTP_HOST") or "smtp.gmail.com",
        "port": int(os.getenv("EMAIL_SMTP_PORT") or "587"),
    }


def _markdown_to_html(body: str) -> str:
    html = md.markdown(body, extensions=["extra", "sane_lists", "nl2br"])
    return f"<html><head>{_HTML_STYLE}</head><body>{html}</body></html>"


def send_email(subject: str, markdown_body: str, *, dry_run: bool = False) -> bool:
    """发一封 markdown 正文的邮件。dry_run 或未配置时只打印，返回 False。"""
    if dry_run:
        print(f"\n===== [DRY-RUN] {subject} =====\n")
        print(markdown_body)
        print("\n===== end =====\n")
        return True

    config = _get_email_config()
    if not config:
        logger.warning("邮件未配置（EMAIL_TO/FROM/PASSWORD），改为打印")
        print(f"\n===== {subject}（未发送）=====\n")
        print(markdown_body)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["from"]
    msg["To"] = config["to"]
    msg.attach(MIMEText(markdown_body, "plain", "utf-8"))
    msg.attach(MIMEText(_markdown_to_html(markdown_body), "html", "utf-8"))

    try:
        with smtplib.SMTP(config["host"], config["port"], timeout=20) as server:
            server.starttls()
            server.login(config["from"], config["password"])
            server.send_message(msg)
        logger.info("邮件已发送 → %s", config["to"])
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("邮件发送失败: %s", e)
        return False
