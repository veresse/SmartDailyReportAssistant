"""事件级去重：候选召回器 (Retriever)。"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone

from briefing.config import get_settings
from briefing.database import get_session_ctx
from briefing.models import RawNewsItem
from briefing.tools.embedding import cosine_similarity

logger = logging.getLogger(__name__)


def retrieve_candidates(new_embedding: list[float], new_fingerprint: dict, lookback_days: int, topk: int) -> tuple[list[dict], int]:
    """
    通过硬规则（时间窗口）过滤，并进行 Numpy 暴力 TopK 召回。
    
    返回：
        (candidates, compute_time_ms)
        candidates 列表项: {"id": int, "url": str, "title": str, "embedding": list, "fingerprint": dict, "text_sim": float}
    """
    if not new_embedding:
        return [], 0
        
    start_time = time.time()
    
    with get_session_ctx() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        # 护栏 A: 仅在近 lookback_days 并且有 embedding 的数据中召回
        query = session.query(
            RawNewsItem.id,
            RawNewsItem.url,
            RawNewsItem.title,
            RawNewsItem.embedding_vector,
            RawNewsItem.event_fingerprint
        ).filter(
            RawNewsItem.collected_at >= cutoff,
            RawNewsItem.embedding_vector != "",
            RawNewsItem.embedding_vector.isnot(None)
        )
        
        # 可以在这里增加初步的指纹实体匹配，如果数据库支持 JSON 提取。
        # SQLite 的 JSON 支持可用，但为了极致简单，我们全部取出在内存做 Numpy 计算。
        recent_items = query.all()
        
    candidates = []
    
    for item in recent_items:
        try:
            existing_vec = json.loads(item.embedding_vector)
            sim = cosine_similarity(new_embedding, existing_vec)
            
            fp = {}
            if item.event_fingerprint:
                fp = json.loads(item.event_fingerprint)
                
            candidates.append({
                "id": item.id,
                "url": item.url,
                "title": item.title,
                "embedding": existing_vec,
                "fingerprint": fp,
                "text_sim": sim
            })
        except Exception as e:
            logger.debug(f"解析已有向量失败: {e}")
            continue
            
    # 按相似度降序
    candidates.sort(key=lambda x: x["text_sim"], reverse=True)
    
    # 截取 TopK
    top_candidates = candidates[:topk]
    
    compute_time_ms = int((time.time() - start_time) * 1000)
    logger.debug(f"Retriever 召回 {len(top_candidates)} 个候选，耗时 {compute_time_ms}ms (总基数 {len(recent_items)})")
    
    return top_candidates, compute_time_ms
