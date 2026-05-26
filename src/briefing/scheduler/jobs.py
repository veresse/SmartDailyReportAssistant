"""早报生成与双轨推送流程编排。"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from briefing.ai.deduplicator import deduplicate
from briefing.ai.enricher import enrich_background
from rapidfuzz import fuzz
from briefing.ai.mindmap import generate_mindmap
from briefing.ai.scorer import score_single_news
from briefing.ai.summarizer import summarize_single
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

        # 3. 并发打分
        logger.info("开始为 %d 条新数据进行 AI 打分", len(new_items))
        scored_items = []
        with ThreadPoolExecutor(max_workers=_bounded_workers(settings.llm_concurrency, len(new_items))) as executor:
            future_to_item = {executor.submit(score_single_news, item): item for item in new_items}
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


def _process_digest_item(item, trigger_ddgs: bool, historical_context: str = "") -> dict:
    """为单条晨报新闻生成摘要和补充背景。"""
    # 摘要
    summary = summarize_single(
        title=item.title,
        source=item.source,
        url=item.url,
        description=item.description,
        content=item.raw_content,
        historical_context=historical_context,
    )
    
    # 背景补充
    background = ""
    if trigger_ddgs:
        key_points = summary.get("key_points", [])
        background = enrich_background(item.title, summary.get("one_line_summary", ""), key_points)

    return {
        "raw_item": item,
        "summary": summary,
        "background": background,
    }


def generate_daily_briefing(date_str: str | None = None) -> int | None:
    """Loop B: 每日晨报聚合推送。"""
    settings = get_settings()
    local_tz = ZoneInfo(settings.timezone)
    if not date_str:
        date_str = datetime.now(local_tz).strftime("%Y-%m-%d")

    logger.info("开始生成 %s 的每日早报...", date_str)
    session = get_session()

    try:
        # 1. 检查是否已生成
        existing = session.query(DailyBriefing).filter(DailyBriefing.date == date_str).first()
        if existing and existing.status in (BriefingStatus.COMPLETED, BriefingStatus.PROCESSING):
            logger.info("早报 %s 已存在或正在处理", date_str)
            return existing.id

        if not existing:
            existing = DailyBriefing(date=date_str, status=BriefingStatus.PROCESSING)
            session.add(existing)
            session.flush()
        else:
            existing.status = BriefingStatus.PROCESSING
            # 清理旧子项
            session.query(BriefingItem).filter(BriefingItem.briefing_id == existing.id).delete()
            session.flush()

        # 2. 读取过去 48 小时内高分数据 (score >= 60)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        db_items = session.query(RawNewsItem).filter(
            RawNewsItem.collected_at >= cutoff,
            RawNewsItem.score >= settings.fetch_store_threshold
        ).all()
        
        if not db_items:
            logger.warning("没有足够的新闻来生成 %s 的早报", date_str)
            existing.status = BriefingStatus.FAILED
            existing.summary_overview = "今日暂无足够高价值的 AI 资讯更新。"
            session.commit()
            return existing.id

        # 转换为 Schema 进行语义去重
        from briefing.collectors.base import RawNewsItemSchema
        schema_items = [
            RawNewsItemSchema(
                source=i.source,
                title=i.title,
                url=i.url,
                description=i.description,
                raw_content=i.raw_content,
                score=i.score,
                published_at=i.published_at,
            ) for i in db_items
        ]
        
        # 3. 语义去重
        deduped_items = deduplicate(schema_items)

        # 4. 构建历史上下文
        history_cutoff = (
            datetime.now(local_tz) - timedelta(days=settings.context_lookback_days)
        ).strftime("%Y-%m-%d")
        
        history_items = (
            session.query(BriefingItem)
            .join(DailyBriefing)
            .filter(DailyBriefing.date >= history_cutoff)
            .order_by(DailyBriefing.date.desc(), BriefingItem.priority.asc())
            .limit(settings.context_max_items)
            .all()
        )
        
        historical_context = ""
        if history_items:
            lines = [f"- [{item.briefing.date}] {item.title}：{item.one_line_summary}" for item in history_items]
            historical_context = "\n".join(lines)

        # 按分数排序取 top N
        deduped_items.sort(key=lambda x: x.score, reverse=True)
        top_items = deduped_items[:settings.collect_max_items]

        # 4. 并发摘要和背景补充
        processed_results = []
        with ThreadPoolExecutor(max_workers=_bounded_workers(settings.llm_concurrency, len(top_items))) as executor:
            futures = []
            for item in top_items:
                trigger_ddgs = (item.score >= settings.ddgs_trigger_threshold)
                futures.append(executor.submit(_process_digest_item, item, trigger_ddgs, historical_context))
                
            for future in as_completed(futures):
                try:
                    processed_results.append(future.result())
                except Exception as e:
                    logger.error("处理单条新闻异常: %s", e)

        # 过滤跨天重复
        processed_results = [
            r for r in processed_results
            if "[重复已阅]" not in r["summary"].get("category", "")
        ]

        # 5. 生成思维导图
        mindmap_data = [
            {"title": r["raw_item"].title, "category": r["summary"].get("category", "其他"), "one_line_summary": r["summary"].get("one_line_summary", "")}
            for r in processed_results
        ]
        mindmap_code = generate_mindmap(mindmap_data)

        # 6. 保存入库
        existing.mindmap_mermaid = mindmap_code
        existing.summary_overview = f"为您精选了过去 48 小时内最具价值的 {len(processed_results)} 条 AI 领域资讯。"
        existing.status = BriefingStatus.COMPLETED

        briefing_items = []
        for i, res in enumerate(processed_results):
            raw = res["raw_item"]
            summary = res["summary"]
            b_item = BriefingItem(
                briefing_id=existing.id,
                source=raw.source,
                title=raw.title,
                url=raw.url,
                one_line_summary=summary.get("one_line_summary", ""),
                key_points=json.dumps(summary.get("key_points", []), ensure_ascii=False),
                importance=summary.get("importance", ""),
                background=res["background"],
                category=summary.get("category", "其他"),
                priority=i,
            )
            briefing_items.append(b_item)
            
        session.add_all(briefing_items)
        session.commit()
        logger.info("早报 %s 生成成功并已入库", date_str)

        # 7. 推送钉钉
        if settings.dingtalk_webhook_url:
            news_fallback = [
                {"title": r["raw_item"].title, "one_line_summary": r["summary"].get("one_line_summary", "")}
                for r in processed_results
            ]
            try:
                send_mindmap_to_dingtalk(
                    webhook_url=settings.dingtalk_webhook_url,
                    date=date_str,
                    mindmap_code=mindmap_code,
                    frontend_base_url=settings.frontend_base_url,
                    news_items=news_fallback,
                    summary_max_items=settings.dingtalk_summary_max_items,
                    secret=settings.dingtalk_secret,
                    keyword=settings.dingtalk_keyword,
                )
                logger.info("早报 %s 推送钉钉成功", date_str)
            except Exception as e:
                logger.error("早报推送钉钉失败: %s", e)

        return existing.id

    except Exception as e:
        session.rollback()
        logger.error("生成早报异常: %s", e)
        existing = session.query(DailyBriefing).filter(DailyBriefing.date == date_str).first()
        if existing:
            existing.status = BriefingStatus.FAILED
            session.commit()
        return None
    finally:
        session.close()


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
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.cleanup_retention_days)
        deleted = session.query(RawNewsItem).filter(RawNewsItem.collected_at < cutoff).delete()
        session.commit()
        logger.info("已清理 %d 条过期原始新闻数据", deleted)
    except Exception as e:
        session.rollback()
        logger.error("数据清理异常: %s", e)
    finally:
        session.close()
