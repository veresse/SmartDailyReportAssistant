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
    mindmap_mermaid: str
    summary_overview: str
    items: list[BriefingItemResponse]


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
            summary_overview=b.summary_overview,
            item_count=len(b.items),
        )
        for b in briefings
    ]


@router.get("/briefings/{date}", response_model=BriefingDetailResponse)
def get_briefing(date: str, db: Session = Depends(_get_db)):
    """获取指定日期的早报详情。"""
    briefing = (
        db.query(DailyBriefing)
        .filter(DailyBriefing.date == date)
        .first()
    )

    if not briefing:
        raise HTTPException(status_code=404, detail=f"未找到 {date} 的早报")

    items = [
        BriefingItemResponse(
            id=item.id,
            source=item.source.value,
            title=item.title,
            url=item.url,
            one_line_summary=item.one_line_summary,
            key_points=json.loads(item.key_points) if item.key_points else [],
            importance=item.importance,
            background=item.background,
            category=item.category,
            priority=item.priority,
        )
        for item in briefing.items
    ]

    return BriefingDetailResponse(
        id=briefing.id,
        date=briefing.date,
        status=briefing.status.value,
        mindmap_mermaid=briefing.mindmap_mermaid,
        summary_overview=briefing.summary_overview,
        items=items,
    )


@router.post("/trigger", response_model=TriggerResponse)
def trigger_briefing(date: str | None = None):
    """手动触发早报生成。"""
    from briefing.scheduler.jobs import generate_daily_briefing

    if not date:
        from briefing.config import get_settings
        local_tz = ZoneInfo(get_settings().timezone)
        date = datetime.now(local_tz).strftime("%Y-%m-%d")

    try:
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
    """获取所有已生成早报的日期列表（供日历视图使用）。"""
    briefings = (
        db.query(DailyBriefing.date, DailyBriefing.status)
        .order_by(DailyBriefing.date.desc())
        .all()
    )
    return [{"date": b.date, "status": b.status.value} for b in briefings]
