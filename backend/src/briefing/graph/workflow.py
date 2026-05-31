"""LangGraph 工作流组装与执行引擎。"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from langgraph.graph import StateGraph, END

from briefing.config import get_settings
from briefing.database import get_session
from briefing.models import BriefingStatus, DailyBriefing
from briefing.graph.state import BriefingGraphState
from briefing.graph.nodes import aggregator_node, filler_node, validator_node, publisher_node
from briefing.graph.edges import route_after_validation

logger = logging.getLogger(__name__)


def build_briefing_graph():
    """组装 V0.5 早报生成图。"""
    graph = StateGraph(BriefingGraphState)

    graph.add_node("aggregator", aggregator_node)
    graph.add_node("filler", filler_node)
    graph.add_node("validator", validator_node)
    graph.add_node("publisher", publisher_node)

    graph.set_entry_point("aggregator")
    graph.add_edge("aggregator", "filler")
    graph.add_edge("filler", "validator")
    graph.add_conditional_edges("validator", route_after_validation, {
        "filler": "filler",
        "publisher": "publisher",
    })
    graph.add_edge("publisher", END)

    return graph.compile()


def run_briefing_graph(date_str: str | None = None) -> int | None:
    """执行 V0.5 早报生成流。"""
    settings = get_settings()
    if not date_str:
        date_str = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d")

    session = get_session()
    try:
        # 创建或重置 DailyBriefing 记录
        briefing = session.query(DailyBriefing).filter_by(date=date_str).first()
        if not briefing:
            briefing = DailyBriefing(date=date_str, status=BriefingStatus.PROCESSING)
            session.add(briefing)
        else:
            briefing.status = BriefingStatus.PROCESSING
            briefing.retry_count = 0
            briefing.full_markdown = ""
            briefing.mindmap_mermaid = ""
        session.commit()
        briefing_id = briefing.id
    except Exception as e:
        session.rollback()
        logger.error("初始化早报记录失败: %s", e)
        return None
    finally:
        session.close()

    initial_state = {
        "date_str": date_str,
        "briefing_id": briefing_id,
        "max_retries": 3,
        "retry_count": 0,
        "status": "init",
        "slot_data_by_category": {},
        "briefing_template": "",
        "filled_markdown": "",
        "mindmap_code": "",
        "validation_result": {}
    }

    try:
        app = build_briefing_graph()
        final_state = app.invoke(initial_state)
        return briefing_id
    except Exception as e:
        logger.error("执行早报生成流失败: %s", e)
        session = get_session()
        try:
            b = session.query(DailyBriefing).get(briefing_id)
            if b:
                b.status = BriefingStatus.FAILED
            session.commit()
        except:
            session.rollback()
        finally:
            session.close()
        return None
