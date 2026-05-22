"""钉钉机器人推送。"""

import base64
import hashlib
import hmac
import logging
import time
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

import requests

logger = logging.getLogger(__name__)


class DingTalkPushError(RuntimeError):
    """钉钉推送失败。"""


def _build_signed_webhook_url(webhook_url: str, secret: str | None) -> str:
    """根据钉钉加签规则为 webhook URL 添加 timestamp/sign。"""
    webhook_url = webhook_url.strip()
    secret = secret.strip() if secret else None

    if not secret:
        return webhook_url

    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = base64.b64encode(digest).decode("utf-8")

    parsed = urlparse(webhook_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["timestamp"] = timestamp
    query["sign"] = sign
    return urlunparse(parsed._replace(query=urlencode(query)))


def _build_frontend_briefing_url(frontend_base_url: str, date: str) -> str:
    """构建前端早报详情页链接。"""
    return f"{frontend_base_url.strip().rstrip('/')}/briefing/{quote(date)}"


def _build_mermaid_image_url(mindmap_code: str) -> str:
    """构建 Mermaid 图片渲染链接。"""
    encoded = base64.urlsafe_b64encode(mindmap_code.strip().encode("utf-8"))
    return f"https://mermaid.ink/img/{encoded.decode('ascii').rstrip('=')}?type=png"


def _format_news_fallback(news_items: list[dict] | None, max_items: int) -> str:
    """生成钉钉不支持图片点击时的文字兜底摘要。"""
    if not news_items:
        return ""

    lines = ["\n\n#### 核心新闻摘要"]
    for i, item in enumerate(news_items[:max_items], start=1):
        title = str(item.get("title", "")).strip() or "未命名新闻"
        summary = str(item.get("one_line_summary", "")).strip() or "暂无摘要"
        lines.append(f"{i}. **{title}**：{summary}")

    if len(news_items) > max_items:
        lines.append(f"\n还有 {len(news_items) - max_items} 条新闻，请在前端查看完整早报。")
    return "\n".join(lines)


def send_mindmap_to_dingtalk(
    webhook_url: str,
    date: str,
    mindmap_code: str,
    frontend_base_url: str,
    news_items: list[dict] | None = None,
    summary_max_items: int = 20,
    secret: str | None = None,
    timeout: int = 10,
) -> dict:
    """将思维导图图片和前端详情链接推送到钉钉群机器人。"""
    if not webhook_url:
        raise ValueError("DingTalk webhook URL is required")
    if not mindmap_code.strip():
        raise ValueError("Mindmap content is empty")

    signed_url = _build_signed_webhook_url(webhook_url, secret)
    detail_url = _build_frontend_briefing_url(frontend_base_url, date)
    image_url = _build_mermaid_image_url(mindmap_code)
    fallback_text = _format_news_fallback(news_items, summary_max_items)
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"{date} 技术演进思维导图",
            "text": (
                f"### {date} 技术演进思维导图\n\n"
                f"[![{date} 技术演进思维导图]({image_url})]({detail_url})\n\n"
                f"如果图片无法点击，请打开：[查看完整早报]({detail_url})"
                f"{fallback_text}"
            ),
        },
    }

    response = requests.post(
        signed_url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    response.raise_for_status()
    result = response.json()

    if result.get("errcode") not in (0, None):
        raise DingTalkPushError(f"钉钉推送返回异常: {result}")
    return result
