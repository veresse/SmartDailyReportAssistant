"""调度流水线辅助函数测试。"""

from unittest.mock import patch

from briefing.collectors.base import RawNewsItemSchema
from briefing.models import BriefingStatus, DailyBriefing
from briefing.scheduler.jobs import (
    _process_digest_item,
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
def test_process_digest_item_returns_correct_structure(mock_summarize, mock_enrich):
    """_process_digest_item 应返回包含 raw_item, summary, background 的字典。"""

    mock_summarize.return_value = {
        "one_line_summary": "summary:Item 0",
        "key_points": ["point1", "point2", "point3"],
        "importance": "importance:Description 0",
        "category": "测试",
    }
    mock_enrich.return_value = "background:Item 0"

    item = _make_item(0)
    result = _process_digest_item(item, trigger_ddgs=True)

    assert result["raw_item"] is item
    assert result["summary"]["one_line_summary"] == "summary:Item 0"
    assert result["background"] == "background:Item 0"
    mock_summarize.assert_called_once()
    mock_enrich.assert_called_once()


@patch("briefing.scheduler.jobs.enrich_background")
@patch("briefing.scheduler.jobs.summarize_single")
def test_process_digest_item_skips_background_when_not_triggered(mock_summarize, mock_enrich):
    """trigger_ddgs=False 时不应调用背景补充。"""

    mock_summarize.return_value = {
        "one_line_summary": "summary",
        "key_points": [],
        "importance": "",
        "category": "其他",
    }

    item = _make_item(0)
    result = _process_digest_item(item, trigger_ddgs=False)

    assert result["background"] == ""
    mock_enrich.assert_not_called()


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
    assert session.committed is True
    assert session.closed is True
