"""LangGraph 节点实现。"""

import json
import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from briefing.ai.client import chat_completion, chat_completion_json
from briefing.ai.prompt_loader import load_prompt
from briefing.config import get_settings
from briefing.database import get_session
from briefing.models import BriefingStatus, DailyBriefing, RawNewsItem
from briefing.graph.state import BriefingGraphState

logger = logging.getLogger(__name__)


def aggregator_node(state: BriefingGraphState) -> dict:
    """聚集前一日与当日高分资讯，按分类整合。"""
    settings = get_settings()
    session = get_session()
    
    target_date = state.get("date_str")
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        prev_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        prev_date = target_date
        
    try:
        # 提取这两天的入库新闻
        items = session.query(RawNewsItem).filter(
            RawNewsItem.briefing_date.in_([target_date, prev_date]),
            RawNewsItem.score >= settings.fetch_store_threshold
        ).all()
        
        # 按分数排序，或者按 category 分组
        slot_data_by_category = {}
        for item in items:
            try:
                slot = json.loads(item.slot_json)
                cat = slot.get("meta_routing", {}).get("event_category", "其他")
                # 简化分类，匹配模板
                if "Tech" in cat or "技术" in cat: cat_key = "Tech"
                elif "OpenSource" in cat or "开源" in cat: cat_key = "OpenSource"
                elif "Biz" in cat or "商业" in cat or "融资" in cat: cat_key = "Biz"
                elif "HR" in cat or "人事" in cat: cat_key = "HR"
                elif "Policy" in cat or "政策" in cat: cat_key = "Policy"
                else: cat_key = "Tech" # 兜底
                
                if cat_key not in slot_data_by_category:
                    slot_data_by_category[cat_key] = []
                    
                slot_data_by_category[cat_key].append({
                    "title": item.title,
                    "url": item.url,
                    "score": item.score,
                    "source": item.source,
                    "details": slot
                })
            except Exception:
                continue
                
        # 加载模板
        template = load_prompt("briefing_template.md")
        # 替换日期变量
        template = template.replace("{date}", target_date)
        
        return {
            "slot_data_by_category": slot_data_by_category,
            "briefing_template": template,
            "status": "filling"
        }
    finally:
        session.close()


def filler_node(state: BriefingGraphState) -> dict:
    """调用 LLM 灌装模板。"""
    logger.info("执行 Filler 节点...")
    
    slot_data_json = json.dumps(state.get("slot_data_by_category", {}), ensure_ascii=False, indent=2)
    template = state.get("briefing_template", "")
    
    val_res = state.get("validation_result", {})
    feedback = val_res.get("feedback", "无") if val_res else "无"
    
    prompt_tmpl = load_prompt("briefing_filler.txt")
    prompt = prompt_tmpl.format(
        slot_data_json=slot_data_json,
        briefing_template=template,
        validator_feedback=feedback
    )
    
    try:
        filled_markdown = chat_completion(prompt, temperature=0.3)
        # 清除可能的 markdown 包裹
        if filled_markdown.startswith("```markdown"):
            filled_markdown = filled_markdown[11:].strip()
        if filled_markdown.endswith("```"):
            filled_markdown = filled_markdown[:-3].strip()
            
        return {"filled_markdown": filled_markdown}
    except Exception as e:
        logger.error("Filler 失败: %s", e)
        return {"filled_markdown": template} # 兜底返回空模板


def validator_node(state: BriefingGraphState) -> dict:
    """执行文档质检。"""
    logger.info("执行 Validator 节点 (retry: %d)...", state.get("retry_count", 0))
    
    filled_markdown = state.get("filled_markdown", "")
    slot_data_json = json.dumps(state.get("slot_data_by_category", {}), ensure_ascii=False)
    
    prompt_tmpl = load_prompt("validator.txt")
    prompt = prompt_tmpl.format(
        filled_markdown=filled_markdown,
        slot_data_json=slot_data_json
    )
    
    try:
        val_res = chat_completion_json(prompt, temperature=0.1)
    except Exception as e:
        logger.error("Validator 调用失败: %s", e)
        val_res = {"is_valid": False, "errors": ["质检请求失败"], "feedback": "重试"}
        
    is_valid = val_res.get("is_valid", False)
    
    # 提取 mermaid 代码以便存为单独字段
    mindmap_code = ""
    mermaid_match = re.search(r'```mermaid\n(.*?)```', filled_markdown, re.DOTALL)
    if mermaid_match:
        mindmap_code = mermaid_match.group(1).strip()
    elif is_valid: # 如果没报错但找不到 mermaid，也强制报错
        is_valid = False
        val_res["is_valid"] = False
        val_res["feedback"] = "未能找到 ```mermaid 块，请确保正确生成了思维导图"
        
    return {
        "validation_result": val_res,
        "mindmap_code": mindmap_code,
        "retry_count": state.get("retry_count", 0) + (1 if not is_valid else 0)
    }


def publisher_node(state: BriefingGraphState) -> dict:
    """最终发布节点。"""
    logger.info("执行 Publisher 节点...")
    
    session = get_session()
    try:
        briefing = session.query(DailyBriefing).get(state["briefing_id"])
        if not briefing:
            return {"status": "failed"}
            
        markdown = state.get("filled_markdown", "")
        mindmap = state.get("mindmap_code", "")
        
        # 如果是降级发布（即超过最大重试，仍然无效）
        val_res = state.get("validation_result", {})
        if not val_res.get("is_valid", True):
            logger.warning("触发降级发布，抹除损坏的 mermaid 块")
            # 抹除 mermaid 块
            markdown = re.sub(r'```mermaid.*?```', '*(思维导图生成失败)*', markdown, flags=re.DOTALL)
            mindmap = ""
            
        briefing.full_markdown = markdown
        briefing.mindmap_mermaid = mindmap
        briefing.retry_count = state.get("retry_count", 0)
        briefing.status = BriefingStatus.COMPLETED
        
        session.commit()
        return {"status": "completed"}
    except Exception as e:
        session.rollback()
        logger.error("Publisher 写入失败: %s", e)
        return {"status": "failed"}
    finally:
        session.close()
