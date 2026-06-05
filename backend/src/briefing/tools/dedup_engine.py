"""双轨前置去重引擎。"""

import json
import logging
from datetime import datetime, timedelta, timezone

from briefing.config import get_settings
from briefing.database import get_session_ctx
from briefing.models import RawNewsItem
from briefing.tools.embedding import cosine_similarity
from briefing.ai.client import chat_completion_json

logger = logging.getLogger(__name__)


def check_duplicate(feature_text: str, embedding: list[float]) -> str | tuple[str, str]:
    """检查新文本是否与近 7 天热库数据重复。

    Returns:
        "pass" | "reject" | ("review", similar_text)
    """
    settings = get_settings()
    if not embedding:
        return "pass"

    with get_session_ctx() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent_items = session.query(
            RawNewsItem.feature_text,
            RawNewsItem.embedding_vector
        ).filter(
            RawNewsItem.collected_at >= cutoff,
            RawNewsItem.embedding_vector != ""
        ).all()

        max_sim = 0.0
        similar_text = ""

        for item in recent_items:
            if not item.embedding_vector:
                continue
            try:
                existing_vec = json.loads(item.embedding_vector)
                sim = cosine_similarity(embedding, existing_vec)
                if sim > max_sim:
                    max_sim = sim
                    similar_text = item.feature_text

                if sim >= settings.dedup_reject_threshold:
                    logger.debug("去重拦截: %.2f >= %.2f", sim, settings.dedup_reject_threshold)
                    return "reject"
            except Exception:
                continue
        
        if max_sim >= settings.dedup_pass_threshold:
            logger.debug("去重灰度区间: %.2f (阈值 %.2f)", max_sim, settings.dedup_pass_threshold)
            return "review", similar_text

        return "pass"


def llm_dedup_review(new_text: str, similar_text: str) -> bool:
    """LLM 灰度区间语义裁决。返回 True 表示是重复，应丢弃。"""
    prompt = f"""请判断以下两段新闻是否在报道同一件事。

## 新闻 A（新入库候选）
{new_text[:500]}

## 新闻 B（已入库候选重合）
{similar_text[:500]}

请仅返回 JSON：
{{"is_duplicate": true/false, "reason": "判断理由"}}"""

    try:
        result = chat_completion_json(prompt, temperature=0.1)
        return result.get("is_duplicate", False)
    except Exception as e:
        logger.error("LLM 去重裁决失败: %s", e)
        return False  # 裁决失败时放行
