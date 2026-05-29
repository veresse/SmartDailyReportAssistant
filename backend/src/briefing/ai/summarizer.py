"""@deprecated 摘要生成模块。

注意：自 V0.4 起，本模块已被废弃。相关逻辑已迁移至 `briefing/graph/nodes.py` 的 Analyzer Node 中，
Prompt 已提取为 `prompts/summarizer.txt`。

将每条新闻转化为「一句话结论 + 3个核心要点 + 为什么重要」的标准结构。
"""

import logging

from briefing.ai.client import chat_completion_json

logger = logging.getLogger(__name__)

_CONTEXTUAL_SUMMARY_PROMPT = """你是一个资深的 AI 行业分析师。

【今日新闻】
- 标题：{title}
- 来源：{source}
- URL：{url}
- 描述：{description}
- 原文内容（部分）：{content}

【🧠 短期记忆：近期已阅资讯】
{historical_context}

【任务要求】
1. 去重判断：如果今日新闻与【短期记忆】中某件事完全是重复报道，请务必在 `category` 返回 `[重复已阅]`。
2. 脉络追踪：如果是【短期记忆】中某件事的后续进展，请在摘要中明确指出。
3. 摘要用中文撰写，语言简洁精准。

请返回 JSON：
{{
    "one_line_summary": "一句话概括",
    "key_points": ["要点1", "要点2", "结合历史脉络的分析"],
    "importance": "为什么重要",
    "category": "标签"
}}
"""


def summarize_single(
    title: str,
    source: str,
    url: str,
    description: str,
    content: str,
    historical_context: str = "",
) -> dict:
    """为单条新闻生成结构化摘要。

    Returns:
        包含 one_line_summary, key_points, importance, category 的字典
    """
    prompt = _CONTEXTUAL_SUMMARY_PROMPT.format(
        title=title,
        source=source,
        url=url,
        description=description[:500],
        content=content[:3000],
        historical_context=historical_context or "暂无近期记忆。",
    )

    try:
        result = chat_completion_json(prompt)
        # 确保必需字段存在
        return {
            "one_line_summary": result.get("one_line_summary", title),
            "key_points": result.get("key_points", [])[:3],
            "importance": result.get("importance", ""),
            "category": result.get("category", "其他"),
        }
    except Exception as e:
        logger.error("摘要生成失败 (%s): %s", title[:40], e)
        return {
            "one_line_summary": title,
            "key_points": [],
            "importance": "",
            "category": "其他",
        }

