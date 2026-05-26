from unittest.mock import patch
from briefing.ai.scorer import score_single_news
from briefing.collectors.base import RawNewsItemSchema

@patch("briefing.ai.scorer.chat_completion_json")
def test_score_single_news_extracts_tags_and_analysis(mock_llm):
    mock_llm.return_value = {
        "score": 90,
        "analysis": "Great news",
        "ai_tags": ["tag1", "tag2"]
    }
    item = RawNewsItemSchema(source="x", title="title", url="y", description="z")
    result = score_single_news(item)
    
    assert result.score == 90
    assert result.extra_data.get("score_reason") == "Great news"
    assert result.ai_tags == ["tag1", "tag2"]

@patch("briefing.ai.scorer.chat_completion_json")
def test_score_single_news_handles_missing_tags(mock_llm):
    mock_llm.return_value = {
        "score": 60,
        "analysis": "Okay news",
    }
    item = RawNewsItemSchema(source="x", title="title", url="y", description="z")
    result = score_single_news(item)
    
    assert result.score == 60
    assert result.ai_tags == []
