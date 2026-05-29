"""早报生成与双轨推送流程编排。"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from rapidfuzz import fuzz
from briefing.ai.scorer import score_single_news
from briefing.collectors.rss import fetch_all_feeds
from briefing.config import get_settings
from briefing.tools.web_scraper import scrape_url
from briefing.collectors.rss import fetch_all_feeds
from briefing.config import get_settings
from briefing.database import get_session
from briefing.models import (
    BriefingItem,
    BriefingStatus,
    DailyBriefing,
    RawNewsItem,
)
from briefing.push.dingtalk import send_mindmap_to_dingtalk

logger = logging.getLogger(__name__)


def _bounded_workers(requested: int, total: int) -> int:
    """根据任务总数限制线程数。"""
    return min(max(1, requested), total or 1)


def _is_title_duplicate(new_title: str, existing_titles: list[str], threshold: float) -> bool:
    """判断新标题是否与已有标题过度相似。"""
    target = int(threshold * 100)
    for existing in existing_titles:
        if fuzz.ratio(new_title, existing) >= target:
            return True
    return False


def fetch_and_instant_push():
    """Loop A: 高频抓取与即时推送。"""
    logger.info("开始执行 Loop A: 高频 RSS 抓取与即时推送...")
    settings = get_settings()
    session = get_session()

    try:
        # 1. 并发抓取所有 RSS 源
        raw_items = fetch_all_feeds()
        if not raw_items:
            logger.info("Loop A 完成：无新数据")
            return

        # 2. 基于 URL 简单去重 (过滤掉数据库已有的)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        existing_urls = {
            url[0] for url in session.query(RawNewsItem.url).filter(
                RawNewsItem.collected_at >= recent_cutoff
            ).all()
        }
        
        # 获取过去 24 小时内 score >= 60 的标题，用于标题查重
        title_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_titles = [
            t[0] for t in session.query(RawNewsItem.title).filter(
                RawNewsItem.collected_at >= title_cutoff,
                RawNewsItem.score >= settings.fetch_store_threshold
            ).all()
        ]
        
        new_items = []
        for item in raw_items:
            if item.url not in existing_urls:
                if not _is_title_duplicate(item.title, recent_titles, settings.title_similarity_threshold):
                    new_items.append(item)
                    existing_urls.add(item.url)
                    recent_titles.append(item.title)
                else:
                    logger.info("标题过于相似，丢弃: %s", item.title)
                
        if not new_items:
            logger.info("Loop A 完成：抓取的数据已在数据库中存在")
            return

        # 3. Content Hydration 按需补水
        hydrated_items = []
        for item in new_items:
            if len(item.description.strip()) < settings.scraper_min_length:
                logger.info("摘要过短 (%d 字符)，触发补水: %s", len(item.description), item.title[:40])
                full_text = scrape_url(item.url)
                if full_text:
                    # 原地更新 Pydantic 模型（这里使用 model_copy 因为是不可变模型更好，或者直接修改如果支持）
                    # Pydantic v2 可以直接用 model_copy 
                    item = item.model_copy(update={"description": full_text})
            hydrated_items.append(item)

        # 4. 并发打分
        logger.info("开始为 %d 条新数据进行 AI 打分", len(hydrated_items))
        scored_items = []
        with ThreadPoolExecutor(max_workers=_bounded_workers(settings.llm_concurrency, len(hydrated_items))) as executor:
            future_to_item = {executor.submit(score_single_news, item): item for item in hydrated_items}
            for future in as_completed(future_to_item):
                try:
                    scored_items.append(future.result())
                except Exception as e:
                    logger.error("打分异常: %s", e)

        # 4. 筛选入库与即时推送
        to_insert = []
        for item in scored_items:
            if item.score >= settings.fetch_store_threshold:
                db_item = RawNewsItem(
                    source=item.source,
                    title=item.title,
                    url=item.url,
                    description=item.description,
                    raw_content=item.raw_content,
                    score=item.score,
                    extra_data=json.dumps(item.extra_data, ensure_ascii=False),
                    ai_tags=json.dumps(getattr(item, "ai_tags", []), ensure_ascii=False),
                    published_at=item.published_at,
                    briefing_date=datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d"),
                )
                
                # 即时推送判断
                if item.score >= settings.instant_push_threshold:
                    _send_instant_push(item)
                    db_item.is_pushed_instantly = True
                    
                to_insert.append(db_item)

        if to_insert:
            session.add_all(to_insert)
            session.commit()
            logger.info("Loop A 完成：新增入库 %d 条，最高分: %d", 
                        len(to_insert), max(i.score for i in to_insert))
        else:
            logger.info("Loop A 完成：无满足分数门槛的数据入库")

    except Exception as e:
        session.rollback()
        logger.error("Loop A 异常: %s", e)
    finally:
        session.close()


def _send_instant_push(item):
    """发送即时快讯到钉钉。"""
    settings = get_settings()
    if not settings.dingtalk_webhook_url:
        return

    import requests
    from briefing.push.dingtalk import _build_signed_webhook_url
    
    url = _build_signed_webhook_url(settings.dingtalk_webhook_url, settings.dingtalk_secret)
    score_reason = item.extra_data.get("score_reason", "")
    keyword = settings.dingtalk_keyword
    
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"{keyword} ⚡ AI 突发快讯：{item.title}",
            "text": (
                f"### {keyword} ⚡ AI 重磅快讯 ({item.score}分)\n\n"
                f"**[{item.title}]({item.url})**\n\n"
                f"> {item.description[:300]}...\n\n"
                f"**上榜理由**：{score_reason}\n\n"
                f"*{item.source}*"
            )
        }
    }
    
    try:
        requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=settings.dingtalk_timeout)
        logger.info("已发送即时快讯: %s", item.title)
    except Exception as e:
        logger.error("即时快讯发送失败: %s", e)


def generate_daily_briefing(date_str: str | None = None) -> int | None:
    """Loop B: 每日晨报聚合推送 — 委托给 LangGraph 工作流。"""
    from briefing.graph.workflow import run_briefing_graph
    return run_briefing_graph(date_str)


def mark_interrupted_briefings_failed() -> int:
    """将上次进程中断遗留的运行中早报标记为失败。"""
    session = get_session()
    try:
        interrupted = session.query(DailyBriefing).filter(
            DailyBriefing.status.in_([BriefingStatus.PROCESSING, BriefingStatus.COLLECTING])
        ).all()
        count = len(interrupted)
        for b in interrupted:
            b.status = BriefingStatus.FAILED
        session.commit()
        return count
    except Exception as e:
        session.rollback()
        logger.error("恢复中断状态异常: %s", e)
        return 0
    finally:
        session.close()


def cleanup_memory():
    """Loop C: 数据库清理。"""
    logger.info("开始清理过期数据...")
    session = get_session()
    try:
        # 删除过期数据的 RawNewsItem
        settings = get_settings()
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.cleanup_retention_days)
        deleted = session.query(RawNewsItem).filter(RawNewsItem.collected_at < cutoff).delete()
        session.commit()
        logger.info("已清理 %d 条过期原始新闻数据", deleted)
    except Exception as e:
        session.rollback()
        logger.error("数据清理异常: %s", e)
    finally:
        session.close()
