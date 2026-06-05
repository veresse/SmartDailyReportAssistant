"""数据库引擎与 Session 管理。"""

import logging
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from briefing.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def get_engine():
    """获取数据库引擎（惰性单例）。"""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url

        kwargs = {"echo": False}

        if url.startswith("sqlite"):
            # SQLite: 确保数据目录存在 + 允许多线程访问
            db_path = url.replace("sqlite:///", "")
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            # PostgreSQL 等：启用连接池预检
            kwargs["pool_pre_ping"] = True

        _engine = create_engine(url, **kwargs)
        logger.info("数据库引擎已创建: %s", url)
    return _engine


def get_session_factory():
    """获取 Session 工厂。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory


def get_session() -> Session:
    """创建一个新的数据库 Session。

    建议优先使用 get_session_ctx() 上下文管理器，可自动关闭 session。
    """
    factory = get_session_factory()
    return factory()


@contextmanager
def get_session_ctx():
    """上下文管理器形式的 Session，退出时自动关闭。"""
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def init_db():
    """根据 ORM 模型创建所有数据表。"""
    from briefing.models import Base

    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("数据库表已初始化")

