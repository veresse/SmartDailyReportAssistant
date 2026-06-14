"""开发者 Debug API，用于观察去重引擎和系统各环节状态。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from briefing.database import get_session
from briefing.models import RawNewsItem, DedupLog, DedupPairCache

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _get_db():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


@router.get("/news/{news_id}")
def debug_news_pipeline(news_id: int, db: Session = Depends(_get_db)):
    """查询单条新闻的处理全链路状态。"""
    item = db.query(RawNewsItem).filter(RawNewsItem.id == news_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="News not found")

    # 查询去重日志
    dedup_log = db.query(DedupLog).filter(DedupLog.news_url == item.url).first()

    return {
        "id": item.id,
        "title": item.title,
        "url": item.url,
        "collected_at": item.collected_at,
        "briefing_date": item.briefing_date,
        "pipeline_data": {
            "feature_windows": item.feature_windows_json,
            "event_fingerprint": item.event_fingerprint,
            "slot_json": item.slot_json
        },
        "scoring": {
            "final_score": item.score,
            "tech_score": item.tech_utility_score,
            "macro_score": item.macro_impact_score,
            "persona_score": item.persona_match_score,
            "scoring_rationale": item.scoring_rationale,
            "persona_rationale": item.persona_match_rationale
        },
        "deduplication": {
            "status": item.dedup_status,
            "ref_url": item.dedup_ref_url,
            "decider": item.dedup_decider,
            "similarity": item.dedup_similarity,
            "rationale": item.dedup_rationale
        },
        "dedup_log_trace": {
            "compute_time_ms": dedup_log.compute_time_ms if dedup_log else None,
            "candidate_count": dedup_log.candidate_count if dedup_log else None,
            "candidates_json": dedup_log.candidates_json if dedup_log else "[]"
        }
    }


@router.get("/dedup_cache")
def debug_dedup_cache(db: Session = Depends(_get_db)):
    """查询当前的 LLM 去重缓存。"""
    caches = db.query(DedupPairCache).order_by(DedupPairCache.created_at.desc()).limit(50).all()
    return [
        {
            "id": c.id,
            "hash_a": c.fingerprint_hash_a,
            "hash_b": c.fingerprint_hash_b,
            "is_duplicate": c.is_duplicate,
            "rationale": c.rationale,
            "created_at": c.created_at
        }
        for c in caches
    ]
