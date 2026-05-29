"""LangGraph 状态定义。"""

import operator
from typing import Annotated, TypedDict


class NewsItemState(TypedDict):
    """单条新闻在图中的流转状态。"""

    title: str
    source: str
    url: str
    description: str
    raw_content: str
    score: int
    ai_tags: list[str]
    # 摘要生成后填充
    one_line_summary: str
    key_points: list[str]
    importance: str
    category: str
    # 意图路由
    needs_research: bool
    search_keywords: list[str]
    # 研究员节点填充
    background: str


class BriefingState(TypedDict):
    """Loop B 全局状态，所有节点通过修改此字典通信。"""

    date_str: str
    raw_news: list[dict]
    processed_items: Annotated[list[NewsItemState], operator.add]
    historical_memory: str
    mindmap: str
    summary_overview: str
    status: str
    # 内部流转状态
    current_item: dict
    current_analyzed_item: NewsItemState
