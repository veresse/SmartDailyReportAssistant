"""早报生成完整流程编排。

从数据采集到 AI 处理，完整的管道执行逻辑。
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

from briefing.ai.deduplicator import deduplicate
from briefing.ai.enricher import enrich_background
from briefing.ai.filter import filter_ai_related
from briefing.ai.mindmap import generate_mindmap
from briefing.ai.summarizer import summarize_single
from briefing.collectors.github import GitHubTrendingCollector
from briefing.collectors.hackernews import HackerNewsCollector
from briefing.collectors.huggingface import HuggingFaceCollector
from briefing.config import get_settings
from briefing.database import get_session, init_db
from briefing.models import (
    BriefingItem,
    BriefingStatus,
    DailyBriefing,
    RawNewsItem,
    SourcePlatform,
)
from briefing.push.dingtalk import send_mindmap_to_dingtalk

logger = logging.getLogger(__name__)


RUNNING_STATUSES = (BriefingStatus.COLLECTING, BriefingStatus.PROCESSING)


def _bounded_workers(requested: int, total: int) -> int:
    """根据任务总数限制线程数，至少返回 1。"""
    return max(1, min(requested, total))


def _collect_all(max_items: int, concurrency: int) -> list:
    """从所有平台并行采集数据。"""
    collectors = [
        GitHubTrendingCollector(max_items=max_items),
        HackerNewsCollector(max_items=max_items),
        HuggingFaceCollector(max_items=max_items),
    ]

    def run_collector(collector):
        try:
            items = collector.collect()
            logger.info(
                "%s 采集了 %d 条",
                collector.__class__.__name__,
                len(items),
            )
            return items
        except Exception as e:
            logger.error("%s 采集失败: %s", collector.__class__.__name__, e)
            return []

    results_by_index: list[list] = [[] for _ in collectors]
    max_workers = _bounded_workers(concurrency, len(collectors))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(run_collector, collector): i
            for i, collector in enumerate(collectors)
        }
        for future in as_completed(future_to_index):
            results_by_index[future_to_index[future]] = future.result()

    all_items = []
    for items in results_by_index:
        all_items.extend(items)

    return all_items


def _process_news_item(index: int, total: int, item) -> dict:
    """为单条新闻生成摘要和背景；供线程池并发调用。"""
    logger.info("处理 [%d/%d] %s", index + 1, total, item.title[:40])

    summary = summarize_single(
        title=item.title,
        source=item.source,
        url=item.url,
        description=item.description,
        content=item.raw_content,
    )

    logger.info("背景补充 [%d/%d] %s", index + 1, total, item.title[:40])
    background = enrich_background(
        title=item.title,
        summary=summary["one_line_summary"],
        key_points=summary["key_points"],
    )

    return {
        **summary,
        "title": item.title,
        "url": item.url,
        "source": item.source,
        "background": background,
        "score": item.score,
        "_input_index": index,
    }


def _process_news_items_parallel(items: list, concurrency: int) -> list[dict]:
    """并行执行每条新闻的摘要和背景补充。"""
    if not items:
        return []

    total = len(items)
    max_workers = _bounded_workers(concurrency, total)
    logger.info("并行处理 %d 条新闻，LLM 并发数=%d", total, max_workers)

    processed_items: list[dict | None] = [None] * total
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(_process_news_item, i, total, item): i
            for i, item in enumerate(items)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            processed_items[index] = future.result()

    return [item for item in processed_items if item is not None]


def mark_interrupted_briefings_failed() -> int:
    """将上次进程中断遗留的运行中早报标记为失败。"""
    session = get_session()
    try:
        interrupted = (
            session.query(DailyBriefing)
            .filter(DailyBriefing.status.in_(RUNNING_STATUSES))
            .all()
        )
        for briefing in interrupted:
            logger.warning(
                "发现上次中断遗留的早报任务，标记为失败: %s (%s)",
                briefing.date,
                briefing.status.value,
            )
            briefing.status = BriefingStatus.FAILED
            if not briefing.summary_overview:
                briefing.summary_overview = "上次生成过程中服务中断，任务未完成，可重新生成。"

        if interrupted:
            session.commit()
        return len(interrupted)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _push_mindmap_to_dingtalk(
    settings,
    date_str: str,
    mindmap_code: str,
    news_items: list[dict] | None = None,
) -> None:
    """配置了钉钉 webhook 时推送思维导图。"""
    if not settings.dingtalk_webhook_url:
        return
    if not mindmap_code.strip():
        logger.info("思维导图为空，跳过钉钉推送")
        return

    try:
        send_mindmap_to_dingtalk(
            webhook_url=settings.dingtalk_webhook_url,
            secret=settings.dingtalk_secret,
            timeout=settings.dingtalk_timeout,
            date=date_str,
            mindmap_code=mindmap_code,
            frontend_base_url=settings.frontend_base_url,
            news_items=news_items,
            summary_max_items=settings.dingtalk_summary_max_items,
        )
        logger.info("钉钉思维导图推送完成: %s", date_str)
    except Exception as e:
        logger.error("钉钉思维导图推送失败: %s", e)


def generate_daily_briefing(date_str: str | None = None) -> int | None:
    """执行完整的早报生成流程。

    Args:
        date_str: 日报日期 (YYYY-MM-DD)，默认今天

    Returns:
        生成的 DailyBriefing ID，失败返回 None
    """
    settings = get_settings()
    local_tz = ZoneInfo(settings.timezone)

    if not date_str:
        date_str = datetime.now(local_tz).strftime("%Y-%m-%d")

    init_db()

    logger.info("====== 开始生成 %s 的早报 ======", date_str)

    # 1. 检查是否已生成
    briefing = None
    session = get_session()
    try:
        existing = (
            session.query(DailyBriefing)
            .filter(DailyBriefing.date == date_str)
            .first()
        )
        if existing and existing.status == BriefingStatus.COMPLETED:
            logger.info("日期 %s 的早报已存在且已完成，跳过", date_str)
            return existing.id

        # 创建或复用早报记录
        if existing:
            briefing = existing
            briefing.status = BriefingStatus.COLLECTING
        else:
            briefing = DailyBriefing(date=date_str, status=BriefingStatus.COLLECTING)
            session.add(briefing)
        session.commit()
        briefing_id = briefing.id

        # 2. 数据采集
        logger.info("[Step 1/5] 数据采集...")
        raw_items = _collect_all(
            max_items=settings.collect_max_items,
            concurrency=settings.collector_concurrency,
        )
        logger.info("总计采集 %d 条原始新闻", len(raw_items))

        # 保存原始数据
        for item in raw_items:
            raw_record = RawNewsItem(
                source=SourcePlatform(item.source),
                title=item.title,
                url=item.url,
                description=item.description,
                raw_content=item.raw_content[:10000],
                score=item.score,
                extra_data=json.dumps(item.extra_data, ensure_ascii=False),
                briefing_date=date_str,
            )
            session.add(raw_record)
        session.commit()

        # 3. 语义去重
        briefing.status = BriefingStatus.PROCESSING
        session.commit()

        logger.info("[Step 2/5] 语义去重...")
        deduped_items = deduplicate(raw_items)
        logger.info("去重后剩余 %d 条", len(deduped_items))

        if settings.ai_filter_enabled:
            logger.info("[Step 3/6] AI 相关新闻过滤...")
            filtered_items = filter_ai_related(
                deduped_items,
                audience=settings.ai_filter_target_audience,
                batch_size=settings.ai_filter_batch_size,
            )
            logger.info("AI 过滤后剩余 %d 条", len(filtered_items))
        else:
            filtered_items = deduped_items

        # 4. 结构化摘要 + 背景补充
        logger.info("[Step 4/6] 结构化摘要 + 背景补充...")
        processed_items = _process_news_items_parallel(
            filtered_items,
            concurrency=settings.llm_concurrency,
        )

        # 按 score 排序，赋优先级
        processed_items.sort(
            key=lambda x: (-x.get("score", 0), x.get("_input_index", 0))
        )
        for i, item in enumerate(processed_items):
            item["priority"] = i

        # 5. 生成思维导图
        logger.info("[Step 5/6] 生成思维导图...")
        mindmap_code = generate_mindmap(processed_items)

        # 6. 持久化处理结果
        briefing.mindmap_mermaid = mindmap_code
        briefing.summary_overview = (
            f"今日共收录 {len(processed_items)} 条技术新闻"
        )
        briefing.status = BriefingStatus.COMPLETED

        for item in processed_items:
            briefing_item = BriefingItem(
                briefing_id=briefing_id,
                source=SourcePlatform(item["source"]),
                title=item["title"],
                url=item["url"],
                one_line_summary=item["one_line_summary"],
                key_points=json.dumps(item["key_points"], ensure_ascii=False),
                importance=item["importance"],
                background=item["background"],
                category=item["category"],
                priority=item["priority"],
            )
            session.add(briefing_item)

        session.commit()
        _push_mindmap_to_dingtalk(settings, date_str, mindmap_code, processed_items)
        logger.info("====== %s 的早报生成完成，共 %d 条 ======", date_str, len(processed_items))
        return briefing_id

    except Exception as e:
        logger.error("早报生成失败: %s", e)
        session.rollback()
        if briefing is not None:
            try:
                briefing.status = BriefingStatus.FAILED
                session.commit()
            except Exception:
                logger.error("标记早报失败状态时出错，已忽略")
                session.rollback()
        raise
    finally:
        session.close()
