"""FastAPI 路由定义。提供早报数据 API 供前端消费。"""

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from briefing.database import get_session
from briefing.models import BriefingStatus, DailyBriefing, BriefingItem, RawNewsItem

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["briefing"])


# ---- Response Schemas ----

class RawNewsItemResponse(BaseModel):
    """单条采集新闻响应。"""

    id: int
    source: str
    title: str
    url: str
    description: str
    score: int
    tech_utility_score: int = 0
    macro_impact_score: int = 0
    published_at: str
    collected_at: datetime
    is_pushed_instantly: bool


class BriefingItemResponse(BaseModel):
    """单条早报新闻响应。"""

    id: int
    source: str
    title: str
    url: str
    one_line_summary: str
    key_points: list[str]
    importance: str
    background: str
    category: str
    priority: int


class BriefingDetailResponse(BaseModel):
    """单日早报详情响应。"""

    id: int
    date: str
    status: str
    full_markdown: str
    mindmap_mermaid: str
    retry_count: int


class BriefingListItem(BaseModel):
    """早报列表项。"""

    id: int
    date: str
    status: str
    summary_overview: str
    item_count: int


class TriggerResponse(BaseModel):
    """手动触发响应。"""

    message: str
    briefing_id: int | None = None


class DeleteBriefingResponse(BaseModel):
    """删除早报响应。"""

    message: str
    date: str
    deleted_items: int
    deleted_raw_items: int


# ---- Helper ----

def _get_db():
    """获取数据库 session（FastAPI 依赖）。"""
    session = get_session()
    try:
        yield session
    finally:
        session.close()


# ---- Endpoints ----

@router.get("/briefings", response_model=list[BriefingListItem])
def list_briefings(
    limit: int = 30,
    db: Session = Depends(_get_db),
):
    """获取早报列表（按日期倒序）。"""
    briefings = (
        db.query(DailyBriefing)
        .order_by(DailyBriefing.date.desc())
        .limit(limit)
        .all()
    )

    return [
        BriefingListItem(
            id=b.id,
            date=b.date,
            status=b.status.value,
            summary_overview=b.full_markdown[:100] + "..." if b.full_markdown else "生成中...",
            item_count=0,
        )
        for b in briefings
    ]


@router.get("/briefings/{date}", response_model=BriefingDetailResponse | None)
def get_briefing(date: str, db: Session = Depends(_get_db)):
    """获取指定日期的早报详情。"""
    briefing = (
        db.query(DailyBriefing)
        .filter(DailyBriefing.date == date)
        .first()
    )

    if not briefing:
        return None

    return BriefingDetailResponse(
        id=briefing.id,
        date=briefing.date,
        status=briefing.status.value,
        full_markdown=briefing.full_markdown,
        mindmap_mermaid=briefing.mindmap_mermaid,
        retry_count=briefing.retry_count,
    )


@router.post("/trigger", response_model=TriggerResponse)
def trigger_briefing(date: str | None = None, loop: str = "A"):
    """手动触发早报或抓取。loop="A" 为高频抓取，loop="B" 为晨报生成。"""
    from briefing.scheduler.jobs import fetch_and_instant_push, generate_daily_briefing
    
    if loop == "A":
        try:
            # 这里的调用最好是异步或放到后台执行，这里为了简单直接调用（如果抓取很慢可能会超时）
            import threading
            threading.Thread(target=fetch_and_instant_push).start()
            return TriggerResponse(message="已触发高频抓取与打分 (后台运行中)")
        except Exception as e:
            logger.error("触发 Loop A 失败: %s", e)
            raise HTTPException(status_code=500, detail=f"触发失败: {e}") from e

    if not date:
        from briefing.config import get_settings
        local_tz = ZoneInfo(get_settings().timezone)
        date = datetime.now(local_tz).strftime("%Y-%m-%d")

    try:
        # 这里原来的逻辑是同步调用，为了前端能立刻拿到状态，也可以放到后台
        # 考虑到兼容性，暂时保持原样（如果太慢可以后续改异步）
        briefing_id = generate_daily_briefing(date_str=date)
        return TriggerResponse(
            message=f"早报 {date} 生成完成",
            briefing_id=briefing_id,
        )
    except Exception as e:
        logger.error("手动触发失败: %s", e)
        raise HTTPException(status_code=500, detail=f"早报生成失败: {e}") from e


@router.delete("/briefings/{date}", response_model=DeleteBriefingResponse)
def delete_briefing(date: str, db: Session = Depends(_get_db)):
    """删除指定日期早报及其关联数据。"""
    briefing = (
        db.query(DailyBriefing)
        .filter(DailyBriefing.date == date)
        .first()
    )

    if not briefing:
        raise HTTPException(status_code=404, detail=f"未找到 {date} 的早报")

    if briefing.status in (BriefingStatus.COLLECTING, BriefingStatus.PROCESSING):
        raise HTTPException(status_code=409, detail="早报正在生成中，暂不能删除")

    try:
        deleted_items = (
            db.query(BriefingItem)
            .filter(BriefingItem.briefing_id == briefing.id)
            .delete(synchronize_session=False)
        )
        deleted_raw_items = (
            db.query(RawNewsItem)
            .filter(RawNewsItem.briefing_date == date)
            .delete(synchronize_session=False)
        )
        db.delete(briefing)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("删除早报失败: %s", e)
        raise HTTPException(status_code=500, detail=f"删除早报失败: {e}") from e

    return DeleteBriefingResponse(
        message=f"早报 {date} 已删除，可重新生成",
        date=date,
        deleted_items=deleted_items,
        deleted_raw_items=deleted_raw_items,
    )


@router.get("/dates")
def get_available_dates(db: Session = Depends(_get_db)):
    """获取所有已生成早报或有采集数据的日期列表（供日历视图使用）。"""
    from sqlalchemy import func
    
    # 1. 获取所有存在 feed 的日期及其数量
    feed_counts = (
        db.query(RawNewsItem.briefing_date, func.count(RawNewsItem.id).label("count"))
        .group_by(RawNewsItem.briefing_date)
        .all()
    )
    feed_map = {row.briefing_date: row.count for row in feed_counts}

    # 2. 获取所有已生成早报的日期
    briefings = (
        db.query(DailyBriefing.date, DailyBriefing.status)
        .all()
    )
    briefing_map = {b.date: b.status.value for b in briefings}

    # 3. 合并日期集合
    all_dates = sorted(set(feed_map.keys()) | set(briefing_map.keys()), reverse=True)

    return [
        {
            "date": date,
            "status": briefing_map.get(date),
            "feed_count": feed_map.get(date, 0),
        }
        for date in all_dates
    ]

@router.get("/feed/{date}", response_model=list[RawNewsItemResponse])
def get_feed(date: str, limit: int = 200, db: Session = Depends(_get_db)):
    """获取指定日期的实时采集资讯流。"""
    items = (
        db.query(RawNewsItem)
        .filter(RawNewsItem.briefing_date == date)
        .order_by(RawNewsItem.score.desc())
        .limit(limit)
        .all()
    )
    return items
