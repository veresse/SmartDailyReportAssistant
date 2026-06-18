"""早报生成与双轨推送流程编排。"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import text

from briefing.collectors.rss import fetch_all_feeds
from briefing.config import get_settings
from briefing.database import get_session, get_session_ctx
from briefing.models import (
    BriefingStatus,
    DailyBriefing,
    RawNewsItem,
)
from briefing.tools.web_scraper import scrape_url
from briefing.tools.text_cleaner import clean_raw_content, extract_feature_text
from briefing.tools.embedding import get_embedding

from briefing.tools.web_search import web_search
from briefing.ai.client import chat_completion_json
from briefing.ai.prompt_loader import load_prompt
from briefing.push.push_throttle import should_push, record_push

logger = logging.getLogger(__name__)


def _bounded_workers(requested: int, total: int) -> int:
    return min(max(1, requested), total or 1)


def process_single_item(item, llm_trigger_count=0):
    """Loop A 处理单条新闻的完整流水线。"""
    settings = get_settings()
    
    # 1. 粗洗与按需补水
    raw_text = f"{item.title}\n{item.description}\n{item.raw_content}"
    cleaned = clean_raw_content(raw_text, settings.scraper_max_chars)
    
    if len(cleaned) < settings.scraper_min_length:
        logger.debug("内容过短，尝试全文抓取: %s", item.url)
        full_text = scrape_url(item.url)
        if full_text:
            cleaned = clean_raw_content(f"{item.title}\n{full_text}", settings.scraper_max_chars)
            
    if len(cleaned) < 50:
        return None  # 抓取失败或仍太短
        
    feature_text = extract_feature_text(cleaned)
    feature_windows_json = json.dumps([feature_text], ensure_ascii=False)
    
    # 2. Embedding 向量化
    embedding = get_embedding(feature_text)
    if not embedding:
        return None
        
    # 3. 候选召回
    from briefing.tools.dedup_retriever import retrieve_candidates
    candidates, compute_time_ms = retrieve_candidates(
        embedding, {}, settings.dedup_lookback_days, settings.dedup_topk
    )
    
    # 4. 预先硬阈值拦截（节省后续所有 LLM 成本）
    if candidates and candidates[0]["text_sim"] >= settings.dedup_reject_threshold:
        logger.info(f"硬规则拦截 (相似度 {candidates[0]['text_sim']:.4f}): {item.title}")
        from briefing.tools.dedup_decider import _log_decision
        _log_decision(item.url, candidates, "reject", candidates[0]["url"], "threshold_rule_early", "预拦截", candidates[0]["text_sim"], compute_time_ms)
        return None

    # 5. 诊断预判
    diag_prompt_tmpl = load_prompt("diagnostor.txt")
    diag_prompt = diag_prompt_tmpl.format(feature_text=feature_text)
    try:
        diag_res = chat_completion_json(diag_prompt, temperature=0.1)
    except Exception as e:
        logger.error("诊断预判失败: %s", e)
        return None
        
    # 6. 按需 RAG 搜索
    rag_context = "无补充背景"
    if diag_res.get("needs_background_check") and diag_res.get("search_query"):
        query = diag_res["search_query"]
        intent = diag_res.get("search_intent", "补充背景")
        logger.info("触发 RAG 搜索 (意图: %s): %s", intent, query)
        search_res = web_search(query)
        if search_res:
            rag_context = "\n".join(f"- {r['title']}: {r['snippet']}" for r in search_res)
            
    # 7. 槽位抽取与指纹生成
    persona = load_prompt("persona.txt")
    extractor_tmpl = load_prompt("slot_extractor.txt")
    extractor_prompt = extractor_tmpl.format(
        user_persona=persona,
        cleaned_text=cleaned,
        rag_context=rag_context,
        event_category=diag_res.get("event_category", "其他"),
        key_entities=", ".join(diag_res.get("key_entities", [])),
    )
    
    try:
        slot_json = chat_completion_json(extractor_prompt, temperature=0.2)
    except Exception as e:
        logger.error("槽位提取失败: %s", e)
        return None

    new_fingerprint = slot_json.get("event_fingerprint", {})
    summary = slot_json.get("core_facts", {}).get("one_sentence_summary", item.title)

    # 8. 灰度决策（结合最新生成的指纹）
    from briefing.tools.dedup_decider import decide_duplicate
    status, ref_url, decider, rationale, max_sim = decide_duplicate(
        item.url, new_fingerprint, summary, candidates, compute_time_ms, llm_trigger_count
    )
    
    if status == "reject":
        logger.info(f"最终去重拦截 ({decider}): {item.title}")
        return None

    # 9. Persona 计算双维分数
    from briefing.tools.persona_matcher import calculate_persona_score
    scoring = slot_json.get("scoring_alignment", {})
    tech = scoring.get("tech_utility_score", 0)
    macro = scoring.get("macro_impact_score", 0)
    
    cat = new_fingerprint.get("category_short", "Tech")
    entities = new_fingerprint.get("key_entities", [])
    metrics = slot_json.get("core_facts", {}).get("hard_metrics", [])
    actionables = slot_json.get("core_facts", {}).get("developer_actionables", [])
    
    final_score, persona_rationale = calculate_persona_score(cat, entities, metrics, actionables, tech, macro)
    
    return {
        "item": item,
        "cleaned_text": cleaned,
        "feature_text": feature_text,
        "feature_windows_json": feature_windows_json,
        "embedding": embedding,
        "slot_json": slot_json,
        "event_fingerprint": new_fingerprint,
        "tech_utility_score": tech,
        "macro_impact_score": macro,
        "persona_match_score": final_score - int(tech * settings.tech_weight + macro * settings.macro_weight),
        "persona_match_rationale": persona_rationale,
        "scoring_rationale": scoring.get("scoring_rationale", ""),
        "final_score": final_score,
        "dedup_status": status,
        "dedup_ref_url": ref_url,
        "dedup_decider": decider,
        "dedup_rationale": rationale,
        "dedup_similarity": max_sim
    }


def fetch_and_instant_push():
    """Loop A: 高频抓取与即时推送。"""
    logger.info("开始执行 Loop A: 高频 RSS 抓取与深度定性管线...")
    settings = get_settings()

    raw_items = fetch_all_feeds()
    if not raw_items:
        logger.info("Loop A 完成：无新数据")
        return

    # 简单 URL 去重
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
    with get_session_ctx() as session:
        existing_urls = {
            url[0] for url in session.query(RawNewsItem.url).filter(
                RawNewsItem.collected_at >= recent_cutoff
            ).all()
        }
    
    new_items = [i for i in raw_items if i.url not in existing_urls]
    if not new_items:
        logger.info("Loop A 完成：抓取的数据已在数据库中存在")
        return

    logger.info("开始处理 %d 条新数据...", len(new_items))
    processed_results = []
    
    import threading
    llm_count_lock = threading.Lock()
    state = {"llm_count": 0}
    
    def process_with_count(item):
        with llm_count_lock:
            current_count = state["llm_count"]
        res = process_single_item(item, current_count)
        if res and res.get("dedup_decider") == "llm_eval":
            with llm_count_lock:
                state["llm_count"] += 1
        return res

    with ThreadPoolExecutor(max_workers=_bounded_workers(settings.llm_concurrency, len(new_items))) as executor:
        future_to_item = {executor.submit(process_with_count, item): item for item in new_items}
        for future in as_completed(future_to_item):
            res = future.result()
            if res:
                processed_results.append(res)

    to_insert = []
    pushed_items = []
    for res in processed_results:
        if res["final_score"] >= settings.fetch_store_threshold:
            db_item = RawNewsItem(
                source=res["item"].source,
                title=res["item"].title,
                url=res["item"].url,
                cleaned_text=res["cleaned_text"],
                feature_text=res["feature_text"],
                feature_windows_json=res["feature_windows_json"],
                score=res["final_score"],
                slot_json=json.dumps(res["slot_json"], ensure_ascii=False),
                tech_utility_score=res["tech_utility_score"],
                macro_impact_score=res["macro_impact_score"],
                scoring_rationale=res["scoring_rationale"],
                embedding_model=settings.embedding_model,
                embedding_vector=json.dumps(res["embedding"]),
                event_fingerprint=json.dumps(res["event_fingerprint"], ensure_ascii=False),
                dedup_status=res["dedup_status"],
                dedup_ref_url=res["dedup_ref_url"],
                dedup_decider=res["dedup_decider"],
                dedup_rationale=res["dedup_rationale"],
                dedup_similarity=res["dedup_similarity"],
                persona_match_score=res["persona_match_score"],
                persona_match_rationale=res["persona_match_rationale"],
                published_at=res["item"].published_at,
                briefing_date=datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d"),
            )
            
            # 防抖与即时推送判断 (V0.6 改为 based on category + top_entity)
            if res["final_score"] >= settings.instant_push_threshold:
                cat = res["event_fingerprint"].get("category_short", "Tech")
                ent = res["event_fingerprint"].get("top_entity", "Other")
                push_key = [cat, ent]
                
                if should_push(push_key):
                    push_ok = _send_instant_push(res)
                    if push_ok:
                        record_push(push_key)
                        db_item.is_pushed_instantly = True
                    elif settings.dingtalk_webhook_url:
                        logger.info("即时推送失败，稍后可能合并推送: %s", res["item"].title)
                        pushed_items.append(res)
                elif settings.dingtalk_webhook_url:
                    logger.info("防抖熔断，稍后可能合并推送: %s", res["item"].title)
                    pushed_items.append(res)
                    
            to_insert.append(db_item)

    if to_insert:
        max_score = max(i.score for i in to_insert)
        with get_session_ctx() as session:
            session.add_all(to_insert)
            session.commit()
        logger.info("Loop A 完成：新增入库 %d 条，最高分: %d", len(to_insert), max_score)
    else:
        logger.info("Loop A 完成：无满足分数门槛的数据入库")

    # 合并推送 (如果被熔断的很多)
    if len(pushed_items) >= settings.push_throttle_max:
        _send_merged_push(pushed_items)


def _send_instant_push(res: dict) -> bool:
    """发送即时快讯到钉钉。返回是否成功。"""
    settings = get_settings()
    if not settings.dingtalk_webhook_url:
        return False

    import requests
    from briefing.push.dingtalk import _build_signed_webhook_url
    
    url = _build_signed_webhook_url(settings.dingtalk_webhook_url, settings.dingtalk_secret)
    item = res["item"]
    keyword = settings.dingtalk_keyword
    
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"{keyword} ⚡ AI 突发快讯：{item.title}",
            "text": (
                f"### {keyword} ⚡ AI 重磅快讯 ({res['final_score']}分)\n\n"
                f"**[{item.title}]({item.url})**\n\n"
                f"> {res['slot_json'].get('core_facts', {}).get('one_sentence_summary', item.title)}\n\n"
                f"**上榜理由**：{res['scoring_rationale']}\n\n"
                f"*{item.source}*"
            )
        }
    }
    
    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=settings.dingtalk_timeout)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error("即时快讯发送失败: %s", e)
        return False


def _send_merged_push(items: list[dict]):
    """发送合并突发事件推送。"""
    settings = get_settings()
    if not settings.dingtalk_webhook_url:
        return
        
    import requests
    from briefing.push.dingtalk import _build_signed_webhook_url
    
    url = _build_signed_webhook_url(settings.dingtalk_webhook_url, settings.dingtalk_secret)
    keyword = settings.dingtalk_keyword
    
    titles = "\n".join(f"- {res['item'].title}" for res in items[:5])
    if len(items) > 5:
        titles += f"\n- ...等 {len(items)} 条相关资讯"
        
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"{keyword} 🔄 突发事件多源追踪合集",
            "text": (
                f"### {keyword} 🔄 突发事件多源追踪合集\n\n"
                f"系统检测到近期有多篇高分相关资讯，已触发合并推送：\n\n"
                f"{titles}\n\n"
                f"请前往系统查看详细聚合早报。"
            )
        }
    }
    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=settings.dingtalk_timeout)
        resp.raise_for_status()
    except Exception as e:
        logger.error("合并推送发送失败: %s", e)


def generate_daily_briefing(date_str: str | None = None) -> int | None:
    """Loop B: 每日晨报聚合推送。"""
    from briefing.workflow.pipeline import run_briefing_workflow
    return run_briefing_workflow(date_str)


def mark_interrupted_briefings_failed() -> int:
    with get_session_ctx() as session:
        interrupted = session.query(DailyBriefing).filter(
            DailyBriefing.status.in_([BriefingStatus.PROCESSING, BriefingStatus.COLLECTING])
        ).all()
        count = len(interrupted)
        for b in interrupted:
            b.status = BriefingStatus.FAILED
        session.commit()
        return count


def cleanup_memory():
    """Loop C: 数据库清理。"""
    logger.info("开始清理过期数据与磁盘碎片...")
    with get_session_ctx() as session:
        settings = get_settings()
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.cleanup_retention_days)
        
        # 1. 清理过期 RawNewsItem
        deleted = session.query(RawNewsItem).filter(RawNewsItem.collected_at < cutoff).delete()
        session.commit()
        logger.info("已清理 %d 条过期原始新闻数据", deleted)
        
        # 2. 定期 VACUUM（每周一执行）
        if datetime.now().weekday() == 0:
            session.execute(text("VACUUM"))
            session.commit()
            logger.info("已执行 VACUUM，释放 SQLite 磁盘碎片")
            
        # 3. 清理过期 DedupLog 和 DedupPairCache
        from briefing.models import DedupLog, DedupPairCache
        session.query(DedupLog).filter(DedupLog.created_at < cutoff).delete()
        session.query(DedupPairCache).filter(DedupPairCache.created_at < cutoff).delete()
        session.commit()
        logger.info("已清理过期缓存与日志")
