"""AI 相关新闻过滤模块。"""

import logging

from briefing.ai.client import chat_completion_json
from briefing.collectors.base import RawNewsItemSchema

logger = logging.getLogger(__name__)

_AI_FILTER_PROMPT_TEMPLATE = """你是一个面向特定读者群体的科技新闻筛选编辑。

## 目标读者
{audience}

## 新闻候选列表
{news_list}

## 筛选规则
1. 只保留与 AI 明确相关的新闻，例如大模型、机器学习、AI Agent、多模态、生成式 AI、模型推理/训练/评测、AI 开发工具、AI 基础设施、AI 安全与治理、AI 产品能力。
2. 如果标题足以判断，优先根据标题判断；标题不足时结合描述和内容摘要判断。
3. 排除泛前端、泛 DevOps、泛安全、泛编程语言、泛开源项目等与 AI 没有直接关系的新闻。
4. 对目标读者没有明显 AI 价值的新闻不要保留。

## 输出格式
请只返回 JSON:
{{
  "ai_related_indices": [0, 3, 5],
  "rejected_indices": [1, 2, 4]
}}

索引必须来自候选列表中的 0-based index。
"""


def _build_news_list(items: list[RawNewsItemSchema]) -> str:
    lines = []
    for i, item in enumerate(items):
        title = item.title.strip() or "(无标题)"
        description = item.description.strip() or item.raw_content.strip()[:500]
        lines.append(
            f"[{i}] 来源={item.source}\n"
            f"标题={title}\n"
            f"描述/内容摘要={description[:700]}"
        )
    return "\n\n".join(lines)


def filter_ai_related(
    items: list[RawNewsItemSchema],
    audience: str,
    batch_size: int = 50,
) -> list[RawNewsItemSchema]:
    """使用 LLM 筛选出 AI 相关新闻。"""
    if not items:
        return []

    filtered_items: list[RawNewsItemSchema] = []
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        prompt = _AI_FILTER_PROMPT_TEMPLATE.format(
            audience=audience,
            news_list=_build_news_list(batch),
        )

        try:
            result = chat_completion_json(prompt, temperature=0.1)
            selected = result.get("ai_related_indices", [])
            selected_indices = []
            for idx in selected:
                if isinstance(idx, int) and 0 <= idx < len(batch):
                    selected_indices.append(idx)

            logger.info(
                "AI 过滤完成: batch %d-%d, %d -> %d 条",
                start,
                start + len(batch) - 1,
                len(batch),
                len(selected_indices),
            )
            filtered_items.extend(batch[idx] for idx in sorted(set(selected_indices)))
        except Exception as e:
            logger.error("AI 新闻过滤失败，保留当前批次原始列表: %s", e)
            filtered_items.extend(batch)

    return filtered_items
