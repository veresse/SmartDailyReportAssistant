"""LangGraph 条件路由边定义。"""

import logging

from langgraph.constants import Send

from briefing.graph.state import BriefingState

logger = logging.getLogger(__name__)


def fan_out_to_analyzers(state: BriefingState) -> list[Send]:
    """Fan-Out 边：为每条新闻创建独立的 Analyzer 分支。

    使用 LangGraph 的 Send API 实现 Map-Reduce 模式。
    """
    raw_news = state.get("raw_news", [])
    if not raw_news:
        logger.warning("fan_out_to_analyzers: raw_news 为空，不产生分支")
        return []

    sends = []
    for item in raw_news:
        # 给 analyzer 传递它自己的一份 BriefingState 副本，附加 current_item
        # 注意 Send API 的参数是目标节点名和节点输入状态
        node_input = state.copy()
        node_input["current_item"] = item
        sends.append(Send("analyzer", node_input))
        
    return sends


def route_after_analysis(state: dict) -> str:
    """条件边：根据 needs_research 决定走 Researcher 还是直接聚合。"""
    # 这个是在 Send 分支内部执行的
    # processed_items 由于用了 operator.add 会追加
    processed = state.get("processed_items", [])
    if not processed:
        return "aggregator"

    latest = processed[-1]
    if latest.get("needs_research", False):
        return "researcher"
    return "aggregator"
