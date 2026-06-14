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
    Float,
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
    url = Column(String(1000), nullable=False, unique=True)
    cleaned_text = Column(Text, default="")
    feature_text = Column(String(500), default="")
    feature_windows_json = Column(Text, default="[]")
    
    score = Column(Integer, default=0)
    slot_json = Column(Text, default="{}")
    tech_utility_score = Column(Integer, default=0)
    macro_impact_score = Column(Integer, default=0)
    scoring_rationale = Column(Text, default="")
    
    embedding_model = Column(String(100), default="")
    embedding_dim = Column(Integer, default=0)
    embedding_input_version = Column(String(50), default="text_windows_v1")
    embedding_vector = Column(Text, default="")
    
    fingerprint_version = Column(String(50), default="fingerprint_v1")
    event_fingerprint = Column(Text, default="")
    fingerprint_embedding_vector = Column(Text, default="")
    
    dedup_status = Column(String(20), default="pass")
    dedup_ref_url = Column(String(1000), default="")
    dedup_rationale = Column(Text, default="")
    dedup_decider = Column(String(20), default="")
    dedup_similarity = Column(Float, default=0.0)
    
    persona_match_score = Column(Integer, default=0)
    persona_match_rationale = Column(Text, default="")

    published_at = Column(String(50), default="")
    is_pushed_instantly = Column(Boolean, default=False)
    collected_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    briefing_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD


class DedupLog(Base):
    """去重决策日志。"""

    __tablename__ = "dedup_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    news_url = Column(String(1000), index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    lookback_days = Column(Integer, default=7)
    topk = Column(Integer, default=20)
    
    # 候选集合：[{url, text_sim, fp_sim, rule_hits, decided_duplicate, rationale}, ...]
    candidates_json = Column(Text, default="[]")
    
    # 最终决策摘要
    final_status = Column(String(20), default="pass")
    final_ref_url = Column(String(1000), default="")
    final_decider = Column(String(20), default="")
    final_rationale = Column(Text, default="")
    final_similarity = Column(Float, default=0.0)
    
    # 指标观测护栏
    compute_time_ms = Column(Integer, default=0)
    candidate_count = Column(Integer, default=0)

    # 版本与配置快照
    embedding_model = Column(String(100), default="")
    embedding_input_version = Column(String(50), default="")
    fingerprint_version = Column(String(50), default="")
    config_snapshot_json = Column(Text, default="{}")


class DedupPairCache(Base):
    """LLM 去重判定的缓存。"""
    
    __tablename__ = "dedup_pair_cache"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint_hash_a = Column(String(64), nullable=False, index=True)
    fingerprint_hash_b = Column(String(64), nullable=False, index=True)
    is_duplicate = Column(Boolean, nullable=False)
    rationale = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DailyBriefing(Base):
    """每日早报聚合。"""

    __tablename__ = "daily_briefings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), unique=True, nullable=False, index=True)  # YYYY-MM-DD
    status = Column(
        SAEnum(BriefingStatus), default=BriefingStatus.PROCESSING, nullable=False
    )
    full_markdown = Column(Text, default="")
    mindmap_mermaid = Column(Text, default="")
    retry_count = Column(Integer, default=0)
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
