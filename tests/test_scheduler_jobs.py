"""调度流水线辅助函数测试。"""

from unittest.mock import patch

from briefing.collectors.base import RawNewsItemSchema
from briefing.models import BriefingStatus, DailyBriefing
from briefing.scheduler.jobs import (
    _process_news_items_parallel,
    _push_mindmap_to_dingtalk,
    mark_interrupted_briefings_failed,
)


def _make_item(index: int) -> RawNewsItemSchema:
    return RawNewsItemSchema(
        source="github",
        title=f"Item {index}",
        url=f"https://example.com/{index}",
        description=f"Description {index}",
        raw_content=f"Content {index}",
        score=100 - index,
    )


@patch("briefing.scheduler.jobs.enrich_background")
@patch("briefing.scheduler.jobs.summarize_single")
def test_process_news_items_parallel_preserves_item_mapping(mock_summarize, mock_enrich):
    """并行处理后，每条摘要/背景仍对应原始新闻。"""

    def summarize_side_effect(title, source, url, description, content):
        return {
            "one_line_summary": f"summary:{title}",
            "key_points": [title, source, url],
            "importance": f"importance:{description}",
            "category": "测试",
        }

    def enrich_side_effect(title, summary, key_points):
        return f"background:{title}:{summary}:{key_points[0]}"

    mock_summarize.side_effect = summarize_side_effect
    mock_enrich.side_effect = enrich_side_effect

    items = [_make_item(i) for i in range(5)]
    processed = _process_news_items_parallel(items, concurrency=3)

    assert [item["title"] for item in processed] == [item.title for item in items]
    assert processed[2]["one_line_summary"] == "summary:Item 2"
    assert processed[2]["background"] == "background:Item 2:summary:Item 2:Item 2"
    assert processed[2]["_input_index"] == 2


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def query(self, model):
        return _FakeQuery(self.rows)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@patch("briefing.scheduler.jobs.get_session")
def test_mark_interrupted_briefings_failed_marks_running_records(mock_get_session):
    """启动恢复时，运行中的旧任务会被标记为失败。"""
    rows = [
        DailyBriefing(date="2026-05-20", status=BriefingStatus.PROCESSING),
        DailyBriefing(date="2026-05-21", status=BriefingStatus.COLLECTING),
    ]
    session = _FakeSession(rows)
    mock_get_session.return_value = session

    recovered = mark_interrupted_briefings_failed()

    assert recovered == 2
    assert all(row.status == BriefingStatus.FAILED for row in rows)
    assert rows[0].summary_overview == "上次生成过程中服务中断，任务未完成，可重新生成。"
    assert session.committed is True
    assert session.closed is True


class _FakeSettings:
    dingtalk_webhook_url = "https://oapi.dingtalk.com/robot/send?access_token=test-token"
    dingtalk_secret = "SECtest"
    dingtalk_timeout = 10
    frontend_base_url = "http://localhost:5173"
    dingtalk_summary_max_items = 20


@patch("briefing.scheduler.jobs.send_mindmap_to_dingtalk")
def test_push_mindmap_to_dingtalk_swallows_push_errors(mock_send):
    """钉钉推送失败不应影响早报生成主流程。"""
    mock_send.side_effect = Exception("network error")

    _push_mindmap_to_dingtalk(_FakeSettings(), "2026-05-22", "mindmap\n  root((x))")

    mock_send.assert_called_once()
