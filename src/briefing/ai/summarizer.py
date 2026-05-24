"""结构化摘要生成模块。

将每条新闻转化为「一句话结论 + 3个核心要点 + 为什么重要」的标准结构。
"""

import logging

from briefing.ai.client import chat_completion_json

logger = logging.getLogger(__name__)

_SUMMARIZE_PROMPT_TEMPLATE = """你是一个专业的科技新闻编辑。请为以下新闻生成结构化摘要。

## 新闻信息
- 标题: {title}
- 来源: {source}
- URL: {url}
- 描述: {description}
- 原文内容（部分）: {content}

## 输出格式（JSON）
{{
    "one_line_summary": "一句话概括这条新闻的核心信息（中文，不超过50字）",
    "key_points": [
        "核心要点1（中文）",
        "核心要点2（中文）",
        "核心要点3（中文）"
    ],
    "importance": "为什么这条新闻对开发者/研究员重要（中文，1-2句话）",
    "category": "分类标签（如：开源项目、AI模型、前端框架、安全、DevOps 等）"
}}

要求：
1. 摘要用中文撰写
2. 语言简洁精准，突出技术价值
3. key_points 正好3个
"""


def summarize_single(
    title: str,
    source: str,
    url: str,
    description: str,
    content: str,
) -> dict:
    """为单条新闻生成结构化摘要。

    Returns:
        包含 one_line_summary, key_points, importance, category 的字典
    """
    prompt = _SUMMARIZE_PROMPT_TEMPLATE.format(
        title=title,
        source=source,
        url=url,
        description=description[:500],
        content=content[:3000],
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

