"""Memory Retriever 工具：轻量级历史记忆精准检索。"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from briefing.config import get_settings
from briefing.database import get_session
from briefing.models import BriefingItem, DailyBriefing

logger = logging.getLogger(__name__)


def retrieve_relevant_memory(
    current_tags: list[str],
    lookback_days: int | None = None,
    max_items: int | None = None,
) -> str:
    """基于当日新闻标签，检索与之相关的历史早报记忆。

    Args:
        current_tags: 当日新闻的所有 ai_tags 聚合列表
        lookback_days: 向前追溯天数（默认读取配置）
        max_items: 最大返回条数（默认读取配置）

    Returns:
        格式化的历史记忆字符串，可直接注入 Prompt
    """
    settings = get_settings()
    lookback_days = lookback_days or settings.context_lookback_days
    max_items = max_items or settings.context_max_items

    if not current_tags:
        return ""

    local_tz = ZoneInfo(settings.timezone)
    cutoff_date = (
        datetime.now(local_tz) - timedelta(days=lookback_days)
    ).strftime("%Y-%m-%d")

    session = get_session()
    try:
        history_items = (
            session.query(BriefingItem)
            .join(DailyBriefing)
            .filter(DailyBriefing.date >= cutoff_date)
            .order_by(DailyBriefing.date.desc(), BriefingItem.priority.asc())
            .all()
        )

        if not history_items:
            return ""

        # 构建标签关键词集合（小写化）
        tag_keywords = {tag.lower().strip() for tag in current_tags if tag.strip()}

        # 词频交集过滤
        relevant = []
        for item in history_items:
            text = f"{item.title} {item.one_line_summary}".lower()
            if any(keyword in text for keyword in tag_keywords):
                relevant.append(item)
            if len(relevant) >= max_items:
                break

        if not relevant:
            return ""

        lines = [
            f"- [{item.briefing.date}] {item.title}：{item.one_line_summary}"
            for item in relevant
        ]
        logger.info(
            "记忆检索完成：%d 个标签匹配到 %d 条历史记录",
            len(tag_keywords),
            len(relevant),
        )
        return "\n".join(lines)

    finally:
        session.close()
