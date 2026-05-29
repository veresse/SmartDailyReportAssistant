"""AI 打分模块。

为 RSS 新闻评估分数 (0-100)，用于决定是否即时推送或入库。
"""

import logging

from briefing.ai.client import chat_completion_json
from briefing.collectors.base import RawNewsItemSchema
from briefing.config import get_settings

logger = logging.getLogger(__name__)

from briefing.ai.prompt_loader import load_prompt


def score_single_news(item: RawNewsItemSchema) -> RawNewsItemSchema:
    """为单条新闻打分，并原地更新 score 和 extra_data 字段。

    Args:
        item: 未打分的新闻条目
        
    Returns:
        打分后的新闻条目（同一对象）
    """
    text_to_eval = item.description.strip()
    if not text_to_eval:
        text_to_eval = item.raw_content.strip()
    
    settings = get_settings()
    
    prompt_template = load_prompt("scorer.txt")
    prompt = prompt_template.format(
        user_persona=settings.user_persona,
        source=item.source,
        title=item.title,
        description=text_to_eval[:1500]
    )
    
    try:
        result = chat_completion_json(prompt, temperature=0.1)
        score = result.get("score", 0)
        analysis = result.get("analysis", "")
        ai_tags = result.get("ai_tags", [])
        
        if not isinstance(ai_tags, list):
            ai_tags = []
            
        item.score = min(max(int(score), 0), 100)
        item.extra_data["score_reason"] = analysis
        item.ai_tags = [str(tag) for tag in ai_tags]
    except Exception as e:
        logger.warning("打分失败 (%s): %s", item.title[:40], e)
        item.score = 0
        item.extra_data["score_reason"] = "AI 评估异常"
        item.ai_tags = []
        
    return item
