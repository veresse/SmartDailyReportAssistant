"""AI 处理模块单元测试。使用 Mock 避免真实 LLM 调用。"""

import json
from unittest.mock import patch, MagicMock

import pytest

from briefing.collectors.base import RawNewsItemSchema
from briefing.ai.deduplicator import deduplicate
from briefing.ai.filter import filter_ai_related
from briefing.ai.summarizer import summarize_single
from briefing.ai.enricher import enrich_background, extract_background_terms
from briefing.ai.mindmap import generate_mindmap


def _make_items(n: int) -> list[RawNewsItemSchema]:
    """创建测试用的新闻条目列表。"""
    return [
        RawNewsItemSchema(
            source="github",
            title=f"Test Item {i}",
            url=f"https://example.com/{i}",
            description=f"Description for item {i}",
            raw_content=f"Content for item {i}",
            score=100 - i,
        )
        for i in range(n)
    ]


class TestDeduplicator:
    """语义去重模块测试。"""

    @patch("briefing.ai.deduplicator.chat_completion_json")
    def test_deduplicate_merges_duplicates(self, mock_llm):
        """去重应合并指向同一事件的新闻。"""
        items = _make_items(3)

        # LLM 返回：item 0 和 item 2 是同一事件
        mock_llm.return_value = {
            "groups": [
                {"primary_index": 0, "merged_indices": [0, 2], "reason": "same event"},
                {"primary_index": 1, "merged_indices": [1], "reason": "unique"},
            ]
        }

        result = deduplicate(items)
        assert len(result) == 2
        assert result[0].title == "Test Item 0"
        assert result[1].title == "Test Item 1"

    def test_deduplicate_single_item(self):
        """单条新闻不需要去重。"""
        items = _make_items(1)
        result = deduplicate(items)
        assert len(result) == 1

    @patch("briefing.ai.deduplicator.chat_completion_json")
    def test_deduplicate_llm_failure_returns_original(self, mock_llm):
        """LLM 调用失败时应返回原始列表。"""
        mock_llm.side_effect = Exception("LLM API error")
        items = _make_items(3)
        result = deduplicate(items)
        assert len(result) == 3


class TestNewsFilter:
    """AI 相关新闻过滤测试。"""

    @patch("briefing.ai.filter.chat_completion_json")
    def test_filter_ai_related_keeps_selected_indices(self, mock_llm):
        """应只保留模型判断为 AI 相关的新闻。"""
        mock_llm.return_value = {"ai_related_indices": [0, 2], "rejected_indices": [1]}
        items = _make_items(3)

        result = filter_ai_related(items, audience="AI 开发者", batch_size=10)

        assert [item.title for item in result] == ["Test Item 0", "Test Item 2"]

    @patch("briefing.ai.filter.chat_completion_json")
    def test_filter_ai_related_failure_keeps_original_batch(self, mock_llm):
        """过滤失败时保留原始批次，避免丢新闻。"""
        mock_llm.side_effect = Exception("LLM error")
        items = _make_items(2)

        result = filter_ai_related(items, audience="AI 开发者", batch_size=10)

        assert result == items


class TestSummarizer:
    """结构化摘要模块测试。"""

    @patch("briefing.ai.summarizer.chat_completion_json")
    def test_summarize_single(self, mock_llm):
        """应返回标准化摘要结构。"""
        mock_llm.return_value = {
            "one_line_summary": "测试摘要",
            "key_points": ["要点1", "要点2", "要点3"],
            "importance": "测试重要性",
            "category": "开源项目",
        }

        result = summarize_single(
            title="Test",
            source="github",
            url="https://example.com",
            description="desc",
            content="content",
        )

        assert result["one_line_summary"] == "测试摘要"
        assert len(result["key_points"]) == 3
        assert result["category"] == "开源项目"

    @patch("briefing.ai.summarizer.chat_completion_json")
    def test_summarize_failure_returns_fallback(self, mock_llm):
        """LLM 失败时应返回降级结果。"""
        mock_llm.side_effect = Exception("LLM error")
        result = summarize_single("Fallback Title", "github", "", "", "")
        assert result["one_line_summary"] == "Fallback Title"
        assert result["key_points"] == []


class TestEnricher:
    """背景补充模块测试。"""

    @patch("briefing.ai.enricher.chat_completion_json")
    def test_extract_background_terms(self, mock_llm):
        """应从摘要中提取适合检索的关键词。"""
        mock_llm.return_value = {"terms": ["LLaMA 3", "Meta AI", "Transformer"]}

        result = extract_background_terms(
            "LLaMA 3 发布",
            "Meta 发布新模型",
            ["性能提升", "支持更长上下文"],
        )

        assert result == ["LLaMA 3", "Meta AI", "Transformer"]

    @patch("briefing.ai.enricher.chat_completion_json")
    def test_extract_background_terms_fallback(self, mock_llm):
        """术语提取失败时应使用标题/要点兜底。"""
        mock_llm.side_effect = Exception("LLM error")

        result = extract_background_terms(
            "MiniCPM-V-4.6 发布",
            "新多模态模型发布",
            ["MiniCPM-V-4.6 支持端侧部署"],
        )

        assert "MiniCPM-V-4.6" in result

    @patch("briefing.ai.enricher.web_search")
    @patch("briefing.ai.enricher.chat_completion_json")
    @patch("briefing.ai.enricher.chat_completion")
    def test_enrich_background(self, mock_llm, mock_terms, mock_search):
        """应结合检索结果生成 Markdown 格式背景知识。"""
        mock_terms.return_value = {"terms": ["LLaMA 3"]}
        mock_search.return_value = [
            {
                "title": "LLaMA 3 overview",
                "link": "https://example.com/llama3",
                "snippet": "LLaMA 3 is a family of open models from Meta.",
            }
        ]
        mock_llm.return_value = "**LLaMA** 是 Meta 开发的开源大语言模型。"

        result = enrich_background("LLaMA 3 发布", "Meta 发布新模型", ["性能提升"])

        assert "LLaMA" in result
        prompt = mock_llm.call_args.args[0]
        assert "LLaMA 3 overview" in prompt
        assert "https://example.com/llama3" in prompt

    @patch("briefing.ai.enricher.web_search")
    @patch("briefing.ai.enricher.chat_completion_json")
    @patch("briefing.ai.enricher.chat_completion")
    def test_enrich_failure_returns_empty(self, mock_llm, mock_terms, mock_search):
        """LLM 失败时应返回空字符串。"""
        mock_terms.return_value = {"terms": ["Test"]}
        mock_search.return_value = []
        mock_llm.side_effect = Exception("LLM error")

        result = enrich_background("Test", "summary", ["point"])

        assert result == ""


class TestMindmap:
    """思维导图生成模块测试。"""

    @patch("briefing.ai.mindmap.chat_completion")
    def test_generate_mindmap(self, mock_llm):
        """应返回有效的 Mermaid mindmap 代码。"""
        mock_llm.return_value = """mindmap
  root((今日技术动态))
    开源项目
      Test Project"""

        items = [{"title": "Test", "category": "开源项目", "one_line_summary": "测试"}]
        result = generate_mindmap(items)
        assert "mindmap" in result
        assert "root" in result

    @patch("briefing.ai.mindmap.chat_completion")
    def test_generate_mindmap_prompt_includes_node_numbers(self, mock_llm):
        """传给模型的新闻列表应包含稳定编号，供前端节点跳转使用。"""
        mock_llm.return_value = "mindmap\n  root((今日技术动态))\n    AI\n      N1 Test"

        items = [
            {
                "title": "Test",
                "category": "开源项目",
                "one_line_summary": "测试",
                "priority": 0,
            }
        ]
        generate_mindmap(items)

        prompt = mock_llm.call_args.args[0]
        assert "N1" in prompt

    def test_generate_mindmap_empty(self):
        """空列表应返回空字符串。"""
        result = generate_mindmap([])
        assert result == ""

    @patch("briefing.ai.mindmap.chat_completion")
    def test_generate_mindmap_failure(self, mock_llm):
        """LLM 失败时应返回降级内容。"""
        mock_llm.side_effect = Exception("LLM error")
        items = [{"title": "Test", "category": "其他", "one_line_summary": "测试"}]
        result = generate_mindmap(items)
        assert "mindmap" in result
        assert "生成失败" in result
