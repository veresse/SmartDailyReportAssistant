"""V0.5 LangGraph 状态定义。"""

from typing import TypedDict


class BriefingGraphState(TypedDict):
    """Loop B 全局状态。"""
    date_str: str                          # 目标日期
    slot_data_by_category: dict            # 按 event_category 分组的槽位 JSON 数组
    briefing_template: str                 # 预设的 Markdown 模版
    filled_markdown: str                   # Filler 产出的完整 Markdown
    mindmap_code: str                      # 从 Markdown 中提取的 Mermaid 代码
    validation_result: dict                # Validator 产出 {"is_valid": bool, "errors": [], "feedback": ""}
    retry_count: int                       # 当前返工次数
    max_retries: int                       # 最大返工次数 (default=3)
    status: str                            # "init" | "filling" | "validating" | "completed" | "failed"
    briefing_id: int                       # DailyBriefing.id
