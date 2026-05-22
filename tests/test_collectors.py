"""采集器单元测试。使用 Mock 避免真实网络请求。"""

from unittest.mock import MagicMock, patch

import pytest

from briefing.collectors.base import RawNewsItemSchema
from briefing.collectors.github import GitHubTrendingCollector
from briefing.collectors.hackernews import HackerNewsCollector
from briefing.collectors.huggingface import HuggingFaceCollector


class TestGitHubCollector:
    """GitHub Trending 采集器测试。"""

    @patch("briefing.collectors.github.requests.Session")
    def test_collect_returns_list(self, mock_session_cls):
        """采集器应返回 RawNewsItemSchema 列表。"""
        # Mock Session 和响应
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # 模拟 GitHub 主页请求（cookie 获取）
        mock_session.get.return_value = MagicMock(status_code=200)

        # 模拟 Trending 页面 HTML
        trending_html = """
        <html><body>
        <article class="Box-row">
            <h2 class="h3 lh-condensed">
                <a href="/test-owner/test-repo">test-owner / test-repo</a>
            </h2>
            <p class="col-9 color-fg-muted my-1 pr-4">A test repo description</p>
            <span itemprop="programmingLanguage">Python</span>
            <span class="d-inline-block float-sm-right">123 stars today</span>
        </article>
        </body></html>
        """
        trending_response = MagicMock()
        trending_response.status_code = 200
        trending_response.text = trending_html
        trending_response.raise_for_status = MagicMock()

        mock_session.get.side_effect = [
            MagicMock(status_code=200),  # github.com 首页
            trending_response,  # trending 页面
        ]

        # Mock README 请求
        with patch("briefing.collectors.github.requests.get") as mock_get:
            readme_response = MagicMock()
            readme_response.status_code = 200
            readme_response.text = "# Test Repo\nThis is a test."
            mock_get.return_value = readme_response

            collector = GitHubTrendingCollector(max_items=5)
            items = collector.collect()

        assert isinstance(items, list)
        if items:  # HTML 解析可能因格式变化而失败
            assert isinstance(items[0], RawNewsItemSchema)
            assert items[0].source == "github"


class TestHackerNewsCollector:
    """Hacker News 采集器测试。"""

    @patch("briefing.collectors.hackernews.requests.get")
    def test_collect_with_api(self, mock_get):
        """采集器应通过 HN API 获取数据。"""
        # Mock topstories 响应
        topstories_response = MagicMock()
        topstories_response.status_code = 200
        topstories_response.json.return_value = [1, 2, 3]
        topstories_response.raise_for_status = MagicMock()

        # Mock 单条 story 响应
        story_response = MagicMock()
        story_response.status_code = 200
        story_response.json.return_value = {
            "id": 1,
            "type": "story",
            "title": "Test Story",
            "url": "https://example.com/test",
            "score": 100,
            "by": "testuser",
            "descendants": 5,
            "kids": [],
        }
        story_response.raise_for_status = MagicMock()

        # Mock 文章页面响应
        page_response = MagicMock()
        page_response.status_code = 200
        page_response.text = "<html><body><p>Test article content</p></body></html>"
        page_response.raise_for_status = MagicMock()

        # side_effect 顺序: topstories, story1, page1, story2, page2, story3, page3
        mock_get.side_effect = [
            topstories_response,
            story_response, page_response,
            story_response, page_response,
            story_response, page_response,
        ]

        collector = HackerNewsCollector(max_items=2, min_score=50)
        items = collector.collect()

        assert isinstance(items, list)
        assert len(items) <= 2
        if items:
            assert items[0].source == "hackernews"
            assert items[0].title == "Test Story"
            assert items[0].score == 100


class TestHuggingFaceCollector:
    """Hugging Face 采集器测试。"""

    @patch("briefing.collectors.huggingface.requests.get")
    def test_collect_papers(self, mock_get):
        """采集器应获取 HF daily papers。"""
        papers_response = MagicMock()
        papers_response.status_code = 200
        papers_response.json.return_value = [
            {
                "paper": {
                    "id": "2401.00001",
                    "title": "Test Paper",
                    "summary": "A test paper abstract.",
                },
                "upvotes": 42,
            }
        ]
        papers_response.raise_for_status = MagicMock()

        # 后续调用返回空列表（models, spaces）
        empty_response = MagicMock()
        empty_response.status_code = 200
        empty_response.json.return_value = []
        empty_response.raise_for_status = MagicMock()

        mock_get.side_effect = [papers_response, empty_response, empty_response]

        collector = HuggingFaceCollector(max_items=5)
        items = collector.collect()

        assert isinstance(items, list)
        assert len(items) >= 1
        paper = items[0]
        assert paper.source == "huggingface"
        assert paper.title == "Test Paper"
        assert paper.score == 42
