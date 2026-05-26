"""RSS 采集器单元测试。使用 Mock 避免真实网络请求。"""

from unittest.mock import MagicMock, patch

import pytest

from briefing.collectors.base import RawNewsItemSchema


class TestFetchFeed:
    """RSS fetch_feed 测试。"""

    @patch("briefing.collectors.rss.feedparser.parse")
    def test_fetch_feed_returns_items(self, mock_parse):
        """fetch_feed 应返回 RawNewsItemSchema 列表。"""
        import time
        from briefing.collectors.rss import fetch_feed

        now_struct = time.gmtime()

        mock_entry = {
            "title": "Test Article",
            "link": "https://example.com/test",
            "summary": "A test article description.",
            "published_parsed": now_struct,
        }

        mock_feed = MagicMock()
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed

        items = fetch_feed("TestSource", "https://example.com/feed.xml", lookback_minutes=120)

        assert isinstance(items, list)
        assert len(items) == 1
        assert isinstance(items[0], RawNewsItemSchema)
        assert items[0].source == "TestSource"
        assert items[0].title == "Test Article"
        assert items[0].url == "https://example.com/test"

    @patch("briefing.collectors.rss.feedparser.parse")
    def test_fetch_feed_filters_old_entries(self, mock_parse):
        """超出 lookback 窗口的条目应被过滤掉。"""
        import time
        from briefing.collectors.rss import fetch_feed

        # 创建一个 3 天前的时间戳
        old_time = time.gmtime(time.time() - 3 * 86400)

        mock_entry = {
            "title": "Old Article",
            "link": "https://example.com/old",
            "summary": "An old article.",
            "published_parsed": old_time,
        }

        mock_feed = MagicMock()
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed

        items = fetch_feed("TestSource", "https://example.com/feed.xml", lookback_minutes=120)

        assert isinstance(items, list)
        assert len(items) == 0

    @patch("briefing.collectors.rss.feedparser.parse")
    def test_fetch_feed_skips_entries_without_title_or_link(self, mock_parse):
        """缺少标题或链接的条目应被跳过。"""
        from briefing.collectors.rss import fetch_feed

        mock_feed = MagicMock()
        mock_feed.entries = [
            {"title": "", "link": "https://example.com/test"},
            {"title": "No Link", "link": ""},
            {"title": "   ", "link": "https://example.com/test2"},
        ]
        mock_parse.return_value = mock_feed

        items = fetch_feed("TestSource", "https://example.com/feed.xml", lookback_minutes=120)

        assert isinstance(items, list)
        assert len(items) == 0
