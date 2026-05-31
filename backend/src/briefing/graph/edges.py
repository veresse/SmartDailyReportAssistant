"""条件路由定义。"""

from briefing.graph.state import BriefingGraphState

def route_after_validation(state: BriefingGraphState) -> str:
    """条件路由：质检通过 → publisher，失败且可重试 → filler，否则降级发布。"""
    result = state.get("validation_result", {})
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if result.get("is_valid", False):
        return "publisher"

    if retry_count < max_retries:
        return "filler"  # 带 feedback 返工

    # 降级：抹除出错部分，强行发布
    return "publisher"
