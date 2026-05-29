"""LangGraph 工作流编译与执行入口。"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.graph import StateGraph, END

from briefing.config import get_settings
from briefing.graph.state import BriefingState
from briefing.graph.nodes import (
    init_node,
    analyzer_node,
    researcher_node,
    aggregator_node,
    filter_node,
    mindmap_node,
    publish_node,
)
from briefing.graph.edges import fan_out_to_analyzers, route_after_analysis

logger = logging.getLogger(__name__)


def build_briefing_graph() -> StateGraph:
    """构建并编译 Loop B 的 LangGraph 工作流。"""
    graph = StateGraph(BriefingState)

    # 注册节点
    graph.add_node("init", init_node)
    graph.add_node("analyzer", analyzer_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("aggregator", aggregator_node)
    graph.add_node("filter", filter_node)
    graph.add_node("mindmap", mindmap_node)
    graph.add_node("publish", publish_node)

    # 构建边
    graph.set_entry_point("init")
    graph.add_conditional_edges("init", fan_out_to_analyzers)
    
    # Send 分支内部路由
    graph.add_conditional_edges("analyzer", route_after_analysis, {
        "researcher": "researcher",
        "aggregator": "aggregator",
    })
    
    graph.add_edge("researcher", "filter")
    graph.add_edge("aggregator", "filter")
    graph.add_edge("filter", "mindmap")
    graph.add_edge("mindmap", "publish")
    graph.add_edge("publish", END)

    return graph.compile()


def run_briefing_graph(date_str: str | None = None) -> int | None:
    """执行 Loop B 工作流，供 jobs.py 调用。

    Args:
        date_str: 目标日期，默认为今天

    Returns:
        DailyBriefing.id 或 None
    """
    settings = get_settings()
    if not date_str:
        date_str = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d")

    graph = build_briefing_graph()
    initial_state: BriefingState = {
        "date_str": date_str,
        "raw_news": [],
        "processed_items": [],
        "historical_memory": "",
        "mindmap": "",
        "summary_overview": "",
        "status": "init",
        "briefing_id": 0,
        "current_item": {},
        "current_analyzed_item": {
            "title": "", "source": "", "url": "", "description": "",
            "raw_content": "", "score": 0, "ai_tags": [], "one_line_summary": "",
            "key_points": [], "importance": "", "category": "", "needs_research": False,
            "search_keywords": [], "background": ""
        },
    }

    try:
        final_state = graph.invoke(initial_state)
        return final_state.get("briefing_id")
    except Exception as e:
        logger.error("LangGraph 工作流执行异常: %s", e)
        return None
