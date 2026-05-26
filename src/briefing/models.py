"""SQLAlchemy ORM 模型定义。"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    """ORM 基类。"""


class BriefingStatus(str, enum.Enum):
    """早报状态。"""

    COLLECTING = "collecting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RawNewsItem(Base):
    """原始新闻条目，由采集器写入。"""

    __tablename__ = "raw_news_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False)
    description = Column(Text, default="")
    raw_content = Column(Text, default="")
    score = Column(Integer, default=0)
    extra_data = Column(Text, default="{}")  # JSON 格式存储附加字段
    ai_tags = Column(Text, default="[]")  # JSON: AI 提取的实体标签
    published_at = Column(String(50), default="")
    is_pushed_instantly = Column(Boolean, default=False)
    collected_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    briefing_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD


class DailyBriefing(Base):
    """每日早报聚合。"""

    __tablename__ = "daily_briefings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), unique=True, nullable=False, index=True)  # YYYY-MM-DD
    status = Column(
        SAEnum(BriefingStatus), default=BriefingStatus.COLLECTING, nullable=False
    )
    mindmap_mermaid = Column(Text, default="")
    summary_overview = Column(Text, default="")  # 顶部概览文本
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    items = relationship("BriefingItem", back_populates="briefing", order_by="BriefingItem.priority")


class BriefingItem(Base):
    """早报中的单条处理后新闻。"""

    __tablename__ = "briefing_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    briefing_id = Column(Integer, ForeignKey("daily_briefings.id"), nullable=False, index=True)
    source = Column(String(100), nullable=False)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False)
    one_line_summary = Column(Text, default="")  # 一句话结论
    key_points = Column(Text, default="[]")  # JSON: 3个核心要点
    importance = Column(Text, default="")  # 为什么重要
    background = Column(Text, default="")  # AI 补充的背景知识
    category = Column(String(100), default="")  # 分类 Tag
    priority = Column(Integer, default=0)  # 排序优先级（越小越靠前）

    briefing = relationship("DailyBriefing", back_populates="items")
