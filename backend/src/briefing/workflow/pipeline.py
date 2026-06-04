"""Loop B 早报生成工作流：纯 Python 实现。

将原 LangGraph 的 aggregator → filler → validator → publisher 管线
重写为简洁的函数调用 + while 重试循环。
"""

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

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _aggregate(date_str: str) -> tuple[dict, str]:
    """聚集前一日与当日高分资讯，按分类整合。

    Returns:
        (slot_data_by_category, briefing_template)
    """
    settings = get_settings()
    session = get_session()

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        prev_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        prev_date = date_str

    try:
        items = session.query(RawNewsItem).filter(
            RawNewsItem.briefing_date.in_([date_str, prev_date]),
            RawNewsItem.score >= settings.fetch_store_threshold
        ).all()

        slot_data_by_category: dict[str, list] = {}
        for item in items:
            try:
                slot = json.loads(item.slot_json)
                cat = slot.get("meta_routing", {}).get("event_category", "其他")
                if "Tech" in cat or "技术" in cat:
                    cat_key = "Tech"
                elif "OpenSource" in cat or "开源" in cat:
                    cat_key = "OpenSource"
                elif "Biz" in cat or "商业" in cat or "融资" in cat:
                    cat_key = "Biz"
                elif "HR" in cat or "人事" in cat:
                    cat_key = "HR"
                elif "Policy" in cat or "政策" in cat:
                    cat_key = "Policy"
                else:
                    cat_key = "Tech"

                if cat_key not in slot_data_by_category:
                    slot_data_by_category[cat_key] = []

                slot_data_by_category[cat_key].append({
                    "title": item.title,
                    "url": item.url,
                    "score": item.score,
                    "source": item.source,
                    "details": slot,
                })
            except Exception:
                continue

        template = load_prompt("briefing_template.md")
        template = template.replace("{date}", date_str)

        return slot_data_by_category, template
    finally:
        session.close()


def _fill(slot_data_by_category: dict, template: str, feedback: str = "无") -> str:
    """调用 LLM 灌装模板，返回 filled_markdown。"""
    logger.info("执行 Filler 步骤...")

    slot_data_json = json.dumps(slot_data_by_category, ensure_ascii=False, indent=2)

    prompt_tmpl = load_prompt("briefing_filler.txt")
    prompt = prompt_tmpl.format(
        slot_data_json=slot_data_json,
        briefing_template=template,
        validator_feedback=feedback,
    )

    try:
        filled_markdown = chat_completion(prompt, temperature=0.3)
        if filled_markdown.startswith("```markdown"):
            filled_markdown = filled_markdown[11:].strip()
        if filled_markdown.endswith("```"):
            filled_markdown = filled_markdown[:-3].strip()
        return filled_markdown
    except Exception as e:
        logger.error("Filler 失败: %s", e)
        return template


def _validate(filled_markdown: str, slot_data_by_category: dict) -> tuple[dict, str]:
    """执行文档质检。

    Returns:
        (validation_result, mindmap_code)
    """
    logger.info("执行 Validator 步骤...")

    slot_data_json = json.dumps(slot_data_by_category, ensure_ascii=False)

    prompt_tmpl = load_prompt("validator.txt")
    prompt = prompt_tmpl.format(
        filled_markdown=filled_markdown,
        slot_data_json=slot_data_json,
    )

    try:
        val_res = chat_completion_json(prompt, temperature=0.1)
    except Exception as e:
        logger.error("Validator 调用失败: %s", e)
        val_res = {"is_valid": False, "errors": ["质检请求失败"], "feedback": "重试"}

    is_valid = val_res.get("is_valid", False)

    mindmap_code = ""
    mermaid_match = re.search(r'```mermaid\n(.*?)```', filled_markdown, re.DOTALL)
    if mermaid_match:
        mindmap_code = mermaid_match.group(1).strip()
    elif is_valid:
        is_valid = False
        val_res["is_valid"] = False
        val_res["feedback"] = "未能找到 ```mermaid 块，请确保正确生成了思维导图"

    return val_res, mindmap_code


def _publish(briefing_id: int, filled_markdown: str, mindmap_code: str,
             validation_result: dict, retry_count: int) -> str:
    """最终发布：写入数据库。

    Returns:
        "completed" 或 "failed"
    """
    logger.info("执行 Publisher 步骤...")

    session = get_session()
    try:
        briefing = session.query(DailyBriefing).get(briefing_id)
        if not briefing:
            return "failed"

        markdown = filled_markdown

        if not validation_result.get("is_valid", True):
            logger.warning("触发降级发布，抹除损坏的 mermaid 块")
            markdown = re.sub(
                r'```mermaid.*?```',
                '*(思维导图生成失败)*',
                markdown,
                flags=re.DOTALL,
            )
            mindmap_code = ""

        briefing.full_markdown = markdown
        briefing.mindmap_mermaid = mindmap_code
        briefing.retry_count = retry_count
        briefing.status = BriefingStatus.COMPLETED

        session.commit()
        return "completed"
    except Exception as e:
        session.rollback()
        logger.error("Publisher 写入失败: %s", e)
        return "failed"
    finally:
        session.close()


def run_briefing_workflow(date_str: str | None = None) -> int | None:
    """执行 Loop B 早报生成工作流。

    流程：aggregate → fill → validate → (retry or publish)
    """
    settings = get_settings()
    if not date_str:
        date_str = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d")

    logger.info("开始生成 %s 的早报...", date_str)

    # 初始化 DailyBriefing 记录
    session = get_session()
    try:
        briefing = session.query(DailyBriefing).filter_by(date=date_str).first()
        if not briefing:
            briefing = DailyBriefing(date=date_str, status=BriefingStatus.PROCESSING)
            session.add(briefing)
        else:
            briefing.status = BriefingStatus.PROCESSING
            briefing.retry_count = 0
            briefing.full_markdown = ""
            briefing.mindmap_mermaid = ""
        session.commit()
        briefing_id = briefing.id
    except Exception as e:
        session.rollback()
        logger.error("初始化早报记录失败: %s", e)
        return None
    finally:
        session.close()

    try:
        # Step 1: Aggregate
        slot_data, template = _aggregate(date_str)

        if not slot_data:
            logger.warning("没有足够的高分新闻来生成 %s 的早报", date_str)
            session = get_session()
            try:
                b = session.query(DailyBriefing).get(briefing_id)
                if b:
                    b.status = BriefingStatus.FAILED
                    b.full_markdown = "今日暂无足够高价值的资讯更新。"
                session.commit()
            finally:
                session.close()
            return briefing_id

        # Step 2-3: Fill → Validate → Retry Loop
        feedback = "无"
        retry_count = 0
        filled_markdown = ""
        mindmap_code = ""
        validation_result: dict = {}

        for attempt in range(MAX_RETRIES + 1):
            filled_markdown = _fill(slot_data, template, feedback)
            validation_result, mindmap_code = _validate(filled_markdown, slot_data)

            if validation_result.get("is_valid", False):
                logger.info("质检通过 (attempt %d)", attempt + 1)
                break

            retry_count += 1
            feedback = validation_result.get("feedback", "请修复上述问题")
            logger.warning(
                "质检未通过 (attempt %d/%d): %s",
                attempt + 1,
                MAX_RETRIES + 1,
                feedback,
            )

        # Step 4: Publish
        status = _publish(
            briefing_id, filled_markdown, mindmap_code,
            validation_result, retry_count,
        )
        logger.info("早报 %s 生成完毕，状态: %s", date_str, status)
        return briefing_id

    except Exception as e:
        logger.error("执行早报生成流失败: %s", e)
        session = get_session()
        try:
            b = session.query(DailyBriefing).get(briefing_id)
            if b:
                b.status = BriefingStatus.FAILED
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()
        return None
