"""FastAPI 应用入口。"""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from briefing.api.routes import router
from briefing.config import get_settings
from briefing.database import init_db
from briefing.scheduler.jobs import (
    fetch_and_instant_push,
    generate_daily_briefing,
    mark_interrupted_briefings_failed,
    cleanup_memory,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化数据库和调度器。"""
    settings = get_settings()
    init_db()
    recovered_count = mark_interrupted_briefings_failed()
    if recovered_count:
        logger.warning("已恢复 %d 个中断遗留的早报任务", recovered_count)

    # 配置定时任务
    # Loop B: 每天定时晨报
    scheduler.add_job(
        generate_daily_briefing,
        trigger=CronTrigger(hour=settings.schedule_hour, minute=settings.schedule_minute),
        id="daily_briefing",
        name="Loop B: 每日早报生成",
        replace_existing=True,
    )
    
    # Loop A: 高频抓取与即时推送 (每 30 分钟)
    from apscheduler.triggers.interval import IntervalTrigger
    scheduler.add_job(
        fetch_and_instant_push,
        trigger=IntervalTrigger(minutes=settings.rss_fetch_interval_minutes),
        id="fetch_and_instant_push",
        name="Loop A: 高频抓取与即时推送",
        replace_existing=True,
    )

    # 数据清理任务（新增）
    scheduler.add_job(
        cleanup_memory,
        trigger=CronTrigger(
            hour=settings.cleanup_hour,
            minute=settings.cleanup_minute,
            timezone=settings.timezone,
        ),
        id="cleanup_old_data",
        name="数据清理：过期数据删除",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "调度器已启动：\n"
        "- Loop A: 每 %d 分钟执行一次\n"
        "- Loop B: 每天 %02d:%02d 执行\n"
        "- 数据清理: 每天 %02d:%02d 执行",
        settings.rss_fetch_interval_minutes,
        settings.schedule_hour,
        settings.schedule_minute,
        settings.cleanup_hour,
        settings.cleanup_minute,
    )

    yield

    scheduler.shutdown()
    logger.info("调度器已关闭")


app = FastAPI(
    title="智能 AI 开发者早报系统",
    description="自动化、个性化的 AI 新闻聚合与分发平台",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - 允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health_check():
    """健康检查端点。"""
    return {"status": "ok"}
