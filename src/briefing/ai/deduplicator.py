"""多源新闻语义去重模块。

将来自不同平台但指向同一事件的新闻进行合并。
"""

import json
import logging

from briefing.ai.client import chat_completion_json
from briefing.collectors.base import RawNewsItemSchema

logger = logging.getLogger(__name__)

_DEDUP_PROMPT_TEMPLATE = """你是一个新闻分析专家。请分析以下来自多个平台的新闻列表，找出指向同一事件/项目/话题的重复新闻，将它们分组合并。

## 新闻列表
{news_list}

## 任务
1. 分析每条新闻的标题和描述，判断哪些新闻是关于同一个事件/项目
2. 将相关新闻归为一组，每组选择信息最丰富的一条作为主条目
3. 对于没有重复的新闻，单独成组

## 输出格式（JSON）
{{
    "groups": [
        {{
            "primary_index": 0,
            "merged_indices": [0, 5],
            "reason": "两条新闻都是关于同一个 GitHub 项目 xxx"
        }}
    ]
}}

其中 primary_index 是该组中信息最丰富的条目索引（0-based），merged_indices 包含该组所有条目的索引。
"""


def deduplicate(items: list[RawNewsItemSchema]) -> list[RawNewsItemSchema]:
    """对新闻列表进行语义去重。

    Args:
        items: 原始新闻列表

    Returns:
        去重后的新闻列表
    """
    if len(items) <= 1:
        return items

    # 构建给 LLM 的新闻摘要列表
    news_summary = "\n".join(
        f"[{i}] 来源={item.source} | 标题={item.title} | 描述={item.description[:100]}"
        for i, item in enumerate(items)
    )

    prompt = _DEDUP_PROMPT_TEMPLATE.format(news_list=news_summary)

    try:
        result = chat_completion_json(prompt)
        groups = result.get("groups", [])

        # 提取每组的主条目索引
        merged_set: set[int] = set()
        primary_indices: list[int] = []

        for group in groups:
            primary = group.get("primary_index", 0)
            merged = group.get("merged_indices", [primary])

            if primary not in merged_set:
                primary_indices.append(primary)

            for idx in merged:
                merged_set.add(idx)

        # 添加未被分组的条目
        for i in range(len(items)):
            if i not in merged_set:
                primary_indices.append(i)

        deduped = [items[i] for i in sorted(primary_indices) if i < len(items)]
        logger.info("去重完成: %d -> %d 条", len(items), len(deduped))
        return deduped

    except Exception as e:
        logger.error("去重处理失败，返回原始列表: %s", e)
        return items
