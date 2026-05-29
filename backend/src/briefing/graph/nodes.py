"""LangGraph 图节点实现。"""

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from briefing.ai.client import chat_completion_json
from briefing.ai.deduplicator import deduplicate
from briefing.ai.mindmap import generate_mindmap
from briefing.ai.prompt_loader import load_prompt
from briefing.collectors.base import RawNewsItemSchema
from briefing.config import get_settings
from briefing.database import get_session
from briefing.graph.state import BriefingState, NewsItemState
from briefing.models import BriefingItem, BriefingStatus, DailyBriefing, RawNewsItem
from briefing.push.dingtalk import send_mindmap_to_dingtalk
from briefing.tools.memory_retriever import retrieve_relevant_memory
from briefing.tools.web_search import web_search

logger = logging.getLogger(__name__)


def init_node(state: BriefingState) -> dict:
    """初始化节点：数据库查询 + 去重 + 精准记忆加载。"""
    settings = get_settings()
    date_str = state["date_str"]
    session = get_session()

    try:
        # 1. 创建或查找当天的 DailyBriefing
        existing = session.query(DailyBriefing).filter(DailyBriefing.date == date_str).first()
        if existing and existing.status in (BriefingStatus.COMPLETED, BriefingStatus.PROCESSING):
            logger.info("早报 %s 已存在或正在处理", date_str)
            return {"status": "skipped", "briefing_id": existing.id}

        if not existing:
            existing = DailyBriefing(date=date_str, status=BriefingStatus.PROCESSING)
            session.add(existing)
            session.flush()
        else:
            existing.status = BriefingStatus.PROCESSING
            session.query(BriefingItem).filter(BriefingItem.briefing_id == existing.id).delete()
            session.flush()

        briefing_id = existing.id

        # 2. 拉取过去 48 小时的高分数据
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        from datetime import timezone
        db_items = session.query(RawNewsItem).filter(
            RawNewsItem.collected_at >= cutoff,
            RawNewsItem.score >= settings.fetch_store_threshold
        ).all()

        if not db_items:
            existing.status = BriefingStatus.FAILED
            existing.summary_overview = "今日暂无足够高价值的 AI 资讯更新。"
            session.commit()
            return {"status": "failed", "briefing_id": briefing_id}

        schema_items = [
            RawNewsItemSchema(
                source=i.source,
                title=i.title,
                url=i.url,
                description=i.description,
                raw_content=i.raw_content,
                score=i.score,
                published_at=i.published_at,
                ai_tags=json.loads(i.ai_tags) if i.ai_tags else [],
            ) for i in db_items
        ]

        # 3. 同日语义去重
        deduped_items = deduplicate(schema_items)
        deduped_items.sort(key=lambda x: x.score, reverse=True)
        top_items = deduped_items[:settings.collect_max_items]

        # 4. 提取当前所有待处理新闻的 ai_tags
        current_tags = []
        for item in top_items:
            current_tags.extend(item.ai_tags)

        # 5. 调用精准记忆检索
        historical_memory = retrieve_relevant_memory(current_tags)

        # 转换回字典以兼容 State
        raw_news = [item.model_dump() for item in top_items]

        session.commit()

        return {
            "raw_news": raw_news,
            "historical_memory": historical_memory,
            "briefing_id": briefing_id,
            "status": "in_progress",
        }

    except Exception as e:
        session.rollback()
        logger.error("Init Node 异常: %s", e)
        return {"status": "failed"}
    finally:
        session.close()


def analyzer_node(state: dict) -> dict:
    """分析师节点：为单条新闻生成摘要并判断搜索意图。"""
    item = state.get("current_item")
    if not item:
        return {}

    prompt_template = load_prompt("summarizer.txt")
    prompt = prompt_template.format(
        title=item.get("title", ""),
        source=item.get("source", ""),
        url=item.get("url", ""),
        description=item.get("description", "")[:500],
        content=item.get("raw_content", "")[:3000],
        historical_context=state.get("historical_memory", "暂无相关近期记忆。"),
    )

    try:
        result = chat_completion_json(prompt)
        news_state: NewsItemState = {
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
            "raw_content": item.get("raw_content", ""),
            "score": item.get("score", 0),
            "ai_tags": item.get("ai_tags", []),
            "one_line_summary": result.get("one_line_summary", item.get("title", "")),
            "key_points": result.get("key_points", [])[:3],
            "importance": result.get("importance", ""),
            "category": result.get("category", "其他"),
            "needs_research": bool(result.get("needs_research", False)),
            "search_keywords": result.get("search_keywords", []),
            "background": "",
        }
        return {"current_analyzed_item": news_state}
    except Exception as e:
        logger.error("Analyzer Node 分析异常 (%s): %s", item.get("title", "")[:40], e)
        news_state = {
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
            "raw_content": item.get("raw_content", ""),
            "score": item.get("score", 0),
            "ai_tags": item.get("ai_tags", []),
            "one_line_summary": item.get("title", ""),
            "key_points": [],
            "importance": "",
            "category": "其他",
            "needs_research": False,
            "search_keywords": [],
            "background": "",
        }
        return {"current_analyzed_item": news_state}


def researcher_node(state: dict) -> dict:
    """研究员节点：联网搜索并润色摘要。最后写入 processed_items。"""
    item = state.get("current_analyzed_item")
    if not item:
        return {}

    keywords = item.get("search_keywords", [])
    if not keywords:
        return {"processed_items": [item]}

    settings = get_settings()
    max_queries = settings.research_max_queries
    keywords = keywords[:max_queries]

    search_results = {}
    for kw in keywords:
        results = web_search(kw)
        search_results[kw] = results

    lines = []
    for term, results in search_results.items():
        lines.append(f"### {term}")
        if not results:
            lines.append("- 未检索到有效结果")
            continue
        for res in results:
            t = res.get("title", "").strip()
            l = res.get("link", "").strip()
            s = res.get("snippet", "").strip()
            lines.append(f"- {t}\n  链接: {l}\n  摘要: {s}")
    search_context = "\n".join(lines)

    prompt_template = load_prompt("enricher_synthesis.txt")
    prompt = prompt_template.format(
        title=item.get("title", ""),
        summary=item.get("one_line_summary", ""),
        key_points="\n".join(f"- {p}" for p in item.get("key_points", [])),
        terms="\n".join(f"- {kw}" for kw in keywords),
        search_context=search_context,
    )

    from briefing.ai.client import chat_completion
    try:
        background = chat_completion(prompt, response_format=None).strip()
        item["background"] = background
    except Exception as e:
        logger.error("Researcher Node 补充背景失败: %s", e)
        item["background"] = ""

    return {"processed_items": [item]}


def aggregator_node(state: dict) -> dict:
    """聚合节点：如果不需要 research，直接将 item 推入 processed_items。"""
    item = state.get("current_analyzed_item")
    if item:
        return {"processed_items": [item]}
    return {}


def filter_node(state: BriefingState) -> dict:
    """过滤重复已阅节点。"""
    filtered = [
        item for item in state.get("processed_items", [])
        if "[重复已阅]" not in item.get("category", "")
    ]
    return {"processed_items": filtered}


def mindmap_node(state: BriefingState) -> dict:
    """思维导图生成节点。"""
    processed = state.get("processed_items", [])
    if not processed:
        return {"mindmap": ""}
    
    # 构建供给思维导图的输入
    news_for_map = []
    for i, item in enumerate(processed, 1):
        news_for_map.append({
            "index": f"N{i}",
            "title": item.get("title", ""),
            "summary": item.get("one_line_summary", "")
        })
    
    try:
        mindmap_code = generate_mindmap(news_for_map)
        return {"mindmap": mindmap_code}
    except Exception as e:
        logger.error("思维导图生成失败: %s", e)
        return {"mindmap": "mindmap\n  root((今日技术动态))\n    生成失败"}


def publish_node(state: BriefingState) -> dict:
    """持久化与推送节点。"""
    date_str = state["date_str"]
    briefing_id = state["briefing_id"]
    processed = state.get("processed_items", [])
    mindmap_code = state.get("mindmap", "")
    
    if not processed:
        logger.warning("没有可发布的资讯！")
        return {"status": "failed"}

    session = get_session()
    try:
        existing = session.query(DailyBriefing).filter(DailyBriefing.id == briefing_id).first()
        if not existing:
            logger.error("未找到 DailyBriefing 记录")
            return {"status": "failed"}

        # 生成概述
        overview = f"为您精选了 {len(processed)} 条最新 AI 动态。"
        existing.summary_overview = overview
        existing.status = BriefingStatus.COMPLETED

        # 写入条目
        for idx, p in enumerate(processed, 1):
            bi = BriefingItem(
                briefing_id=briefing_id,
                title=p.get("title", ""),
                source=p.get("source", ""),
                url=p.get("url", ""),
                description=p.get("description", ""),
                ai_tags=json.dumps(p.get("ai_tags", [])),
                one_line_summary=p.get("one_line_summary", ""),
                key_points=json.dumps(p.get("key_points", [])),
                importance=p.get("importance", ""),
                category=p.get("category", ""),
                background=p.get("background", ""),
                priority=idx,
            )
            session.add(bi)
        
        session.commit()
        
        # 钉钉推送
        try:
            send_mindmap_to_dingtalk(date_str, overview, mindmap_code, [])
        except Exception as e:
            logger.error("钉钉推送失败: %s", e)

        return {"status": "completed"}
    except Exception as e:
        session.rollback()
        logger.error("Publish Node 持久化异常: %s", e)
        return {"status": "failed"}
    finally:
        session.close()
