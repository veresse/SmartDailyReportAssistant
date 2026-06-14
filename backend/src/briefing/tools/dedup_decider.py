"""事件级去重：决策器 (Decider)。"""

import json
import logging
from typing import Literal
import hashlib

from briefing.config import get_settings
from briefing.database import get_session_ctx
from briefing.models import DedupLog, DedupPairCache
from briefing.ai.client import chat_completion_json

logger = logging.getLogger(__name__)


def _hash_fingerprint(fp: dict) -> str:
    """对指纹进行哈希。"""
    s = json.dumps(fp, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _check_cache(hash_a: str, hash_b: str) -> tuple[bool, bool, str]:
    """检查 LLM 判决缓存。返回 (is_hit, is_duplicate, rationale)。"""
    # 确保 hash_a < hash_b 从而无视顺序
    if hash_a > hash_b:
        hash_a, hash_b = hash_b, hash_a
        
    with get_session_ctx() as session:
        cache = session.query(DedupPairCache).filter_by(
            fingerprint_hash_a=hash_a,
            fingerprint_hash_b=hash_b
        ).first()
        
        if cache:
            return True, cache.is_duplicate, cache.rationale
    return False, False, ""


def _set_cache(hash_a: str, hash_b: str, is_duplicate: bool, rationale: str):
    """设置 LLM 判决缓存。"""
    if hash_a > hash_b:
        hash_a, hash_b = hash_b, hash_a
        
    with get_session_ctx() as session:
        cache = DedupPairCache(
            fingerprint_hash_a=hash_a,
            fingerprint_hash_b=hash_b,
            is_duplicate=is_duplicate,
            rationale=rationale
        )
        session.add(cache)
        session.commit()


def decide_duplicate(
    new_url: str,
    new_fingerprint: dict,
    new_summary: str,
    candidates: list[dict],
    compute_time_ms: int,
    llm_trigger_count: int
) -> tuple[Literal["pass", "reject"], str, str, str, float]:
    """
    两阶段判决：硬阈值 + 灰度 LLM。
    
    返回：
        (status, ref_url, decider, rationale, similarity)
        status: "pass" 或 "reject"
    """
    settings = get_settings()
    
    if not candidates:
        _log_decision(new_url, [], "pass", "", "none", "无候选对象", 0.0, compute_time_ms)
        return "pass", "", "none", "无候选对象", 0.0

    # 1. 硬阈值判断
    for cand in candidates:
        sim = cand["text_sim"]
        
        # 硬拒绝
        if sim >= settings.dedup_reject_threshold:
            msg = f"相似度 {sim:.4f} >= 拒绝阈值 {settings.dedup_reject_threshold}"
            logger.info(f"硬规则拦截: {msg}")
            _log_decision(new_url, candidates, "reject", cand["url"], "threshold_rule", msg, sim, compute_time_ms)
            return "reject", cand["url"], "threshold_rule", msg, sim

    # 2. 灰区判定
    if not settings.dedup_gray_llm:
        cand = candidates[0]
        msg = f"未开启灰度，最大相似度 {cand['text_sim']:.4f} < {settings.dedup_reject_threshold}，放行"
        _log_decision(new_url, candidates, "pass", "", "threshold_rule", msg, cand['text_sim'], compute_time_ms)
        return "pass", "", "threshold_rule", msg, cand['text_sim']
        
    # 在灰区内，取 TopN 个进行 LLM 判断
    top_n_candidates = [c for c in candidates if c["text_sim"] >= settings.dedup_pass_threshold][:settings.dedup_gray_topn]
    
    if not top_n_candidates:
        cand = candidates[0]
        msg = f"候选最大相似度 {cand['text_sim']:.4f} < 灰区放行阈值 {settings.dedup_pass_threshold}"
        _log_decision(new_url, candidates, "pass", "", "threshold_rule", msg, cand['text_sim'], compute_time_ms)
        return "pass", "", "threshold_rule", msg, cand['text_sim']

    new_fp_hash = _hash_fingerprint(new_fingerprint)

    for cand in top_n_candidates:
        sim = cand["text_sim"]
        cand_fp = cand.get("fingerprint", {})
        cand_fp_hash = _hash_fingerprint(cand_fp)
        
        # 护栏 B: 检查缓存
        is_hit, is_dup, rationale = _check_cache(new_fp_hash, cand_fp_hash)
        if is_hit:
            if is_dup:
                msg = f"缓存命中：重复 ({rationale})"
                _log_decision(new_url, candidates, "reject", cand["url"], "llm_cache", msg, sim, compute_time_ms)
                return "reject", cand["url"], "llm_cache", msg, sim
            else:
                continue # 不重复，看下一个候选
                
        # 护栏 C: 并发上限检查
        if llm_trigger_count >= settings.dedup_gray_limit:
            msg = f"灰区限流触发，默认放行 (限额 {settings.dedup_gray_limit})"
            logger.warning(msg)
            _log_decision(new_url, candidates, "pass", "", "throttle", msg, sim, compute_time_ms)
            return "pass", "", "throttle", msg, sim

        # 护栏 D: 简化输入的 LLM 调用
        llm_trigger_count += 1
        prompt = f"""请判断以下两个事件指纹和摘要是否在描述同一个核心新闻事件。
请忽略来源不同或口吻不同，只关注：是否在报道同一家公司的同一个具体行为。

【事件 A (新)】
指纹: {json.dumps(new_fingerprint, ensure_ascii=False)}
摘要: {new_summary}

【事件 B (库中候选)】
指纹: {json.dumps(cand_fp, ensure_ascii=False)}
标题: {cand["title"]}

请仅返回 JSON：{{"is_duplicate": true/false, "reason": "极简理由"}}"""

        try:
            res = chat_completion_json(prompt, temperature=0.1)
            is_dup = res.get("is_duplicate", False)
            rationale = res.get("reason", "无理由")
            
            _set_cache(new_fp_hash, cand_fp_hash, is_dup, rationale)
            
            if is_dup:
                msg = f"LLM 判定重复：{rationale}"
                _log_decision(new_url, candidates, "reject", cand["url"], "llm_eval", msg, sim, compute_time_ms)
                return "reject", cand["url"], "llm_eval", msg, sim
                
        except Exception as e:
            logger.error(f"灰度 LLM 失败: {e}")
            continue

    # 全部裁决不重复
    cand = top_n_candidates[0]
    msg = "灰度区 LLM 判定均不重复，放行"
    _log_decision(new_url, candidates, "pass", "", "llm_eval", msg, cand["text_sim"], compute_time_ms)
    return "pass", "", "llm_eval", msg, cand["text_sim"]


def _log_decision(
    new_url: str,
    candidates: list,
    status: str,
    ref_url: str,
    decider: str,
    rationale: str,
    similarity: float,
    compute_time_ms: int
):
    """记录决策快照到 DedupLog。"""
    settings = get_settings()
    
    # 简化的候选对象摘要（只存核心信息）
    cands_json = json.dumps([{
        "url": c["url"], 
        "text_sim": round(c["text_sim"], 4)
    } for c in candidates], ensure_ascii=False)
    
    with get_session_ctx() as session:
        log = DedupLog(
            news_url=new_url,
            lookback_days=settings.dedup_lookback_days,
            topk=settings.dedup_topk,
            candidates_json=cands_json,
            final_status=status,
            final_ref_url=ref_url,
            final_decider=decider,
            final_rationale=rationale,
            final_similarity=similarity,
            compute_time_ms=compute_time_ms,
            candidate_count=len(candidates),
            embedding_model=settings.embedding_model
        )
        session.add(log)
        session.commit()
