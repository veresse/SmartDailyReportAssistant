"""RSS 全网聚合采集器。

负责解析 OPML 文件，使用 feedparser 并发抓取各 RSS 源，过滤出给定时间窗口内的新内容。
"""

import calendar
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import xml.etree.ElementTree as ET
import feedparser

from briefing.collectors.base import RawNewsItemSchema
from briefing.config import get_settings

logger = logging.getLogger(__name__)


def parse_opml(opml_path: str) -> list[dict]:
    """解析 OPML 文件获取订阅源列表。

    Returns:
        包含 name 和 url 的字典列表
    """
    try:
        tree = ET.parse(opml_path)
        root = tree.getroot()
        feeds = []
        for outline in root.findall('.//outline'):
            xml_url = outline.get('xmlUrl')
            if xml_url:
                title = outline.get('title') or outline.get('text') or ""
                feeds.append({"name": title, "url": xml_url})
        logger.info("成功从 %s 解析到 %d 个 RSS 源", opml_path, len(feeds))
        return feeds
    except Exception as e:
        logger.error("解析 OPML 文件失败 (%s): %s", opml_path, e)
        return []


def _parse_time(time_struct) -> datetime | None:
    """尝试将 feedparser 的时间结构转换为 datetime 对象。"""
    if not time_struct:
        return None
    try:
        # feedparser 的 *_parsed 字段是 UTC 的 time.struct_time，
        # 须用 calendar.timegm（而非 time.mktime）来避免本地时区偏移。
        return datetime.fromtimestamp(calendar.timegm(time_struct), timezone.utc)
    except Exception:
        return None


def fetch_feed(source_name: str, feed_url: str, lookback_minutes: int) -> list[RawNewsItemSchema]:
    """抓取单个 RSS 源，过滤出 lookback_minutes 内更新的条目。"""
    items = []
    try:
        feed = feedparser.parse(feed_url)
        now = datetime.now(timezone.utc)
        
        for entry in feed.entries:
            # 提取信息
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue

            # 处理发布时间
            pub_date = _parse_time(entry.get("published_parsed") or entry.get("updated_parsed"))
            if pub_date:
                # 时间过滤：如果早于 lookback_minutes，跳过
                diff = (now - pub_date).total_seconds() / 60
                if diff > lookback_minutes:
                    continue
                pub_date_str = pub_date.isoformat()
            else:
                # 无法解析时间的条目，默认当成新条目处理
                pub_date_str = now.isoformat()

            description = entry.get("summary", "").strip()
            # 有些 feed 将正文放在 content 字段
            content = ""
            if "content" in entry and entry.content:
                content = entry.content[0].get("value", "").strip()
            if not content:
                content = description

            item = RawNewsItemSchema(
                source=source_name or feed_url,
                title=title[:500],
                url=link[:1000],
                description=description[:2000],
                raw_content=content[:5000],
                published_at=pub_date_str,
            )
            items.append(item)
    except Exception as e:
        logger.warning("抓取 RSS 源失败 (%s - %s): %s", source_name, feed_url, e)

    return items


def fetch_all_feeds() -> list[RawNewsItemSchema]:
    """并发抓取 OPML 中的所有 RSS 源。"""
    settings = get_settings()
    opml_path = settings.rss_opml_path
    lookback = settings.rss_lookback_minutes
    
    feeds = parse_opml(opml_path)
    if not feeds:
        return []

    all_items = []
    concurrency = min(20, len(feeds) or 1)
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_feed = {
            executor.submit(fetch_feed, feed["name"], feed["url"], lookback): feed 
            for feed in feeds
        }
        
        for future in as_completed(future_to_feed):
            feed = future_to_feed[future]
            try:
                items = future.result()
                all_items.extend(items)
            except Exception as e:
                logger.error("抓取源 %s 异常: %s", feed["url"], e)
                
    logger.info("所有 RSS 源抓取完成，共提取 %d 条新数据", len(all_items))
    return all_items
