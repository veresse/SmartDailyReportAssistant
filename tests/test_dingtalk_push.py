"""钉钉推送测试。"""

from unittest.mock import MagicMock, patch

import pytest

from briefing.push.dingtalk import (
    DingTalkPushError,
    _build_frontend_briefing_url,
    _build_mermaid_image_url,
    _build_signed_webhook_url,
    send_mindmap_to_dingtalk,
)


def test_build_signed_webhook_url_adds_timestamp_and_sign():
    """启用加签时应追加 timestamp/sign 参数。"""
    webhook = "https://oapi.dingtalk.com/robot/send?access_token=test-token"

    with patch("briefing.push.dingtalk.time.time", return_value=1710000000):
        signed_url = _build_signed_webhook_url(webhook, "SECtest")

    assert "access_token=test-token" in signed_url
    assert "timestamp=1710000000000" in signed_url
    assert "sign=" in signed_url


def test_build_frontend_briefing_url():
    """应构建早报详情页链接。"""
    assert (
        _build_frontend_briefing_url("http://localhost:5173/", "2026-05-22")
        == "http://localhost:5173/briefing/2026-05-22"
    )


def test_build_mermaid_image_url():
    """应构建 Mermaid 图片链接。"""
    image_url = _build_mermaid_image_url("mindmap\n  root((今日技术动态))")

    assert image_url.startswith("https://mermaid.ink/img/")
    assert image_url.endswith("?type=png")


@patch("briefing.push.dingtalk.requests.post")
def test_send_mindmap_to_dingtalk_sends_image_link_and_fallback(mock_post):
    """钉钉推送内容应包含图片链接、前端链接和文字兜底。"""
    response = MagicMock()
    response.json.return_value = {"errcode": 0, "errmsg": "ok"}
    response.raise_for_status.return_value = None
    mock_post.return_value = response

    result = send_mindmap_to_dingtalk(
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test-token",
        secret=None,
        timeout=5,
        date="2026-05-22",
        mindmap_code="mindmap\n  root((今日技术动态))",
        frontend_base_url="http://localhost:5173",
        news_items=[
            {"title": "新闻 A", "one_line_summary": "一句话摘要 A"},
        ],
    )

    payload = mock_post.call_args.kwargs["json"]
    text = payload["markdown"]["text"]
    title = payload["markdown"]["title"]
    assert result["errcode"] == 0
    assert payload["msgtype"] == "markdown"
    assert "https://mermaid.ink/img/" in text
    assert "http://localhost:5173/briefing/2026-05-22" in text
    assert "新闻 A" in text
    assert "一句话摘要 A" in text
    assert "```mermaid" not in text
    # 自定义关键词应出现在 title 和 text 中，以通过钉钉安全校验
    assert "【日报】" in title
    assert "【日报】" in text


@patch("briefing.push.dingtalk.requests.post")
def test_send_mindmap_to_dingtalk_raises_on_dingtalk_error(mock_post):
    """钉钉业务错误应抛出，不能被当成推送成功。"""
    response = MagicMock()
    response.json.return_value = {"errcode": 310000, "errmsg": "签名不匹配"}
    response.raise_for_status.return_value = None
    mock_post.return_value = response

    with pytest.raises(DingTalkPushError):
        send_mindmap_to_dingtalk(
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=test-token",
            secret="SECtest",
            timeout=5,
            date="2026-05-22",
            mindmap_code="mindmap\n  root((今日技术动态))",
            frontend_base_url="http://localhost:5173",
        )
