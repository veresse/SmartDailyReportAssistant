"""AI 打分模块。

为 RSS 新闻评估分数 (0-100)，用于决定是否即时推送或入库。
"""

import logging

from briefing.ai.client import chat_completion_json
from briefing.collectors.base import RawNewsItemSchema
from briefing.config import get_settings

logger = logging.getLogger(__name__)

_PERSONALIZED_SCORING_PROMPT = """你是一个专属于我的私人 AI 技术助理。请根据我的【个人画像与偏好】，评估以下新闻对我的实际阅读价值。

## 👨‍💻 我的个人画像
{user_persona}

## 📰 新闻信息
- 来源：{source}
- 标题：{title}
- 摘要：{description}

## 📊 任务规则
1. 价值评估 (0-100分)：严格匹配我的画像。精准踩中痛点给 85 分以上；非关注领域或公关水文绝不超过 59 分。
2. 实体提取：提取 1-3 个核心专有名词作为标签。

请仅返回 JSON 格式：
{{
    "analysis": "评估理由",
    "score": 85,
    "ai_tags": ["标签1", "标签2"]
}}
"""


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
    
    prompt = _PERSONALIZED_SCORING_PROMPT.format(
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
