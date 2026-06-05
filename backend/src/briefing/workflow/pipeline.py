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
from briefing.database import get_session, get_session_ctx
from briefing.models import BriefingItem, BriefingStatus, DailyBriefing, RawNewsItem
from briefing.tools.memory_retriever import retrieve_relevant_memory

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _aggregate(date_str: str) -> tuple[dict, str]:
    """聚集前一日与当日高分资讯，按分类整合。

    Returns:
        (slot_data_by_category, briefing_template)
    """
    settings = get_settings()

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        prev_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        prev_date = date_str

    with get_session_ctx() as session:
        items = session.query(RawNewsItem).filter(
            RawNewsItem.briefing_date.in_([date_str, prev_date]),
            RawNewsItem.score >= settings.fetch_store_threshold
        ).all()

        slot_data_by_category: dict[str, list] = {}

        # LLM event_category → 内部分类键的映射表
        CATEGORY_MAP = {
            "技术发布(Tech)": "Tech",
            "开源项目(OpenSource)": "OpenSource",
            "商业融资(Biz)": "Biz",
            "人事变动(HR)": "HR",
            "政策监管(Policy)": "Policy",
        }
        # 兜底：按关键字模糊匹配
        CATEGORY_FALLBACK_KEYS = [
            ("Tech", ["Tech", "技术"]),
            ("OpenSource", ["OpenSource", "开源"]),
            ("Biz", ["Biz", "商业", "融资"]),
            ("HR", ["HR", "人事"]),
            ("Policy", ["Policy", "政策"]),
        ]

        for item in items:
            try:
                slot = json.loads(item.slot_json)
                cat = slot.get("meta_routing", {}).get("event_category", "其他")

                # 精确匹配优先
                cat_key = CATEGORY_MAP.get(cat)
                # 兜底模糊匹配
                if not cat_key:
                    for key, keywords in CATEGORY_FALLBACK_KEYS:
                        if any(kw in cat for kw in keywords):
                            cat_key = key
                            break
                if not cat_key:
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

        # 按 collect_max_items 截断，防止单日数据过多导致 LLM token 溢出
        total = sum(len(v) for v in slot_data_by_category.values())
        if total > settings.collect_max_items:
            # 按分数全局排序后截取
            all_items = []
            for cat_key, cat_items in slot_data_by_category.items():
                for it in cat_items:
                    all_items.append((cat_key, it))
            all_items.sort(key=lambda x: x[1].get("score", 0), reverse=True)
            trimmed = all_items[:settings.collect_max_items]
            slot_data_by_category = {}
            for cat_key, it in trimmed:
                slot_data_by_category.setdefault(cat_key, []).append(it)

        template = load_prompt("briefing_template.md")
        template = template.replace("{date}", date_str)

        return slot_data_by_category, template


def _fill(slot_data_by_category: dict, template: str, feedback: str = "无",
          historical_context: str = "") -> str:
    """调用 LLM 灌装模板，返回 filled_markdown。"""
    logger.info("执行 Filler 步骤...")

    slot_data_json = json.dumps(slot_data_by_category, ensure_ascii=False, indent=2)

    prompt_tmpl = load_prompt("briefing_filler.txt")
    prompt = prompt_tmpl.format(
        slot_data_json=slot_data_json,
        briefing_template=template,
        validator_feedback=feedback,
        historical_context=historical_context or "暂无近期记忆。",
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
             validation_result: dict, retry_count: int,
             slot_data_by_category: dict | None = None) -> str:
    """最终发布：写入数据库，包括 BriefingItem 记录。

    Returns:
        "completed" 或 "failed"
    """
    logger.info("执行 Publisher 步骤...")

    with get_session_ctx() as session:
        briefing = session.get(DailyBriefing, briefing_id)
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

        # 清除旧 BriefingItem 记录，防止重复触发时累积
        session.query(BriefingItem).filter(BriefingItem.briefing_id == briefing_id).delete()

        # 写入 BriefingItem 记录，供 memory_retriever 使用
        if slot_data_by_category:
            priority = 0
            for cat_key, items in slot_data_by_category.items():
                for item in items:
                    details = item.get("details", {})
                    core_facts = details.get("core_facts", {})
                    analytical = details.get("ai_analytical_depth", {})

                    brief_item = BriefingItem(
                        briefing_id=briefing_id,
                        source=item.get("source", ""),
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        one_line_summary=core_facts.get("one_sentence_summary", ""),
                        key_points=json.dumps(core_facts.get("hard_metrics", []), ensure_ascii=False),
                        importance=analytical.get("industry_ripple_effect", ""),
                        background=analytical.get("technical_innovation", ""),
                        category=cat_key,
                        priority=priority,
                    )
                    session.add(brief_item)
                    priority += 1

        try:
            session.commit()
            return "completed"
        except Exception as e:
            session.rollback()
            logger.error("Publisher 写入失败: %s", e)
            return "failed"


def run_briefing_workflow(date_str: str | None = None) -> int | None:
    """执行 Loop B 早报生成工作流。

    流程：aggregate → fill → validate → (retry or publish)
    """
    settings = get_settings()
    if not date_str:
        date_str = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d")

    logger.info("开始生成 %s 的早报...", date_str)

    # 初始化 DailyBriefing 记录
    with get_session_ctx() as session:
        briefing = session.query(DailyBriefing).filter_by(date=date_str).first()
        if not briefing:
            briefing = DailyBriefing(date=date_str, status=BriefingStatus.PROCESSING)
            session.add(briefing)
        else:
            briefing.status = BriefingStatus.PROCESSING
            briefing.retry_count = 0
            briefing.full_markdown = ""
            briefing.mindmap_mermaid = ""
        try:
            session.commit()
            briefing_id = briefing.id
        except Exception as e:
            session.rollback()
            logger.error("初始化早报记录失败: %s", e)
            return None

    try:
        # Step 1: Aggregate
        slot_data, template = _aggregate(date_str)

        if not slot_data:
            logger.warning("没有足够的高分新闻来生成 %s 的早报", date_str)
            with get_session_ctx() as session:
                b = session.get(DailyBriefing, briefing_id)
                if b:
                    b.status = BriefingStatus.FAILED
                    b.full_markdown = "今日暂无足够高价值的资讯更新。"
                session.commit()
            return briefing_id

        # Step 1.5: 精准记忆检索
        all_tags = []
        for cat_items in slot_data.values():
            for item in cat_items:
                entities = item.get("details", {}).get("meta_routing", {}).get("key_entities", [])
                all_tags.extend(entities)
        historical_context = retrieve_relevant_memory(all_tags)
        if historical_context:
            logger.info("已检索到 %d 条历史记忆", len(historical_context.splitlines()))
        else:
            logger.info("无相关历史记忆")

        # Step 2-3: Fill → Validate → Retry Loop
        feedback = "无"
        retry_count = 0
        filled_markdown = ""
        mindmap_code = ""
        validation_result: dict = {}

        for attempt in range(MAX_RETRIES + 1):
            filled_markdown = _fill(slot_data, template, feedback, historical_context)
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
            validation_result, retry_count, slot_data,
        )
        logger.info("早报 %s 生成完毕，状态: %s", date_str, status)
        return briefing_id

    except Exception as e:
        logger.error("执行早报生成流失败: %s", e)
        with get_session_ctx() as session:
            b = session.get(DailyBriefing, briefing_id)
            if b:
                b.status = BriefingStatus.FAILED
            try:
                session.commit()
            except Exception:
                session.rollback()
        return None
