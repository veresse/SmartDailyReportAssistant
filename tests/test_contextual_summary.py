from unittest.mock import patch
from briefing.ai.summarizer import summarize_single

@patch("briefing.ai.summarizer.chat_completion_json")
def test_summarize_single_passes_historical_context(mock_llm):
    mock_llm.return_value = {
        "one_line_summary": "summary",
        "key_points": [],
        "importance": "",
        "category": "[重复已阅]"
    }
    result = summarize_single("title", "source", "url", "desc", "content", historical_context="history")
    
    # Verify the fallback handling and parsing
    assert result["category"] == "[重复已阅]"
    
    # Verify prompt construction includes the historical context
    prompt_used = mock_llm.call_args.args[0]
    assert "history" in prompt_used
    assert "短期记忆：近期已阅资讯" in prompt_used
