"""AI 打分模块。

为 RSS 新闻评估分数 (0-100)，用于决定是否即时推送或入库。
"""

import logging

from briefing.ai.client import chat_completion_json
from briefing.collectors.base import RawNewsItemSchema

logger = logging.getLogger(__name__)

_SCORING_PROMPT_TEMPLATE = """你是一个资深的 AI 领域技术分析师。请为以下新闻条目进行评估并打分（0-100分）。

## 评估标准
- 90-100分：具有重大行业影响力的突破性新闻（如 GPT-4 / Llama 3 发布、重大 AI 开源模型发布、影响深远的 AI 技术突破或严重安全漏洞）。
- 70-89分：值得关注的重要技术更新、优秀的 AI 开源项目发布、有深度价值的 AI 研究论文或技术文章。
- 60-69分：常规 AI 技术动态、小版本更新、普通的工具发布。
- 0-59分：非 AI 相关内容、水文、PR稿件、过度营销或重复信息。

## 新闻信息
- 来源：{source}
- 标题：{title}
- 描述摘要：{description}

请仅返回以下 JSON 格式：
{{
    "score": 85,
    "reason": "简要的打分理由（一句话）"
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
    
    prompt = _SCORING_PROMPT_TEMPLATE.format(
        source=item.source,
        title=item.title,
        description=text_to_eval[:1500]
    )
    
    try:
        result = chat_completion_json(prompt, temperature=0.1)
        score = result.get("score", 0)
        reason = result.get("reason", "")
        
        item.score = min(max(int(score), 0), 100)
        item.extra_data["score_reason"] = reason
    except Exception as e:
        logger.warning("打分失败 (%s): %s", item.title[:40], e)
        item.score = 0
        item.extra_data["score_reason"] = "AI 评估异常"
        
    return item
