"""Persona 匹配器，计算事件对目标读者的实用价值。"""

import json
import logging
from typing import Tuple

from briefing.ai.client import chat_completion_json
from briefing.config import get_settings
from briefing.ai.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


def calculate_persona_score(
    event_category: str,
    key_entities: list[str],
    hard_metrics: list[str],
    developer_actionables: list[str],
    tech_score: int,
    macro_score: int
) -> Tuple[int, str]:
    """
    计算基于 Persona 的加权总分。
    
    返回：
        (final_score, rationale)
    """
    settings = get_settings()
    persona_txt = load_prompt("persona.txt")
    
    # 简单的加分逻辑：如果有实际可操作项 (Github, API等)，直接提高 Persona 分数。
    # 复杂的逻辑可以通过 LLM 进行，但基于“简单优先”，如果需要可以用一次轻量级 LLM 调用。
    # 这里我们使用 LLM 评估其对 Persona 的具体匹配度 (0-100)。
    
    prompt = f"""请根据目标读者画像，评估当前新闻事件对他们的价值匹配度（0-100分）。

【目标读者画像】
{persona_txt}

【当前事件核心要素】
分类: {event_category}
核心实体: {", ".join(key_entities)}
硬核指标: {", ".join(hard_metrics)}
开发者行动项: {", ".join(developer_actionables)}

请仅返回 JSON：
{{"persona_match_score": 整数, "rationale": "极简判定理由"}}"""

    persona_match_score = 0
    rationale = "无特殊行动项"
    
    try:
        res = chat_completion_json(prompt, temperature=0.1)
        persona_match_score = res.get("persona_match_score", 0)
        rationale = res.get("rationale", rationale)
    except Exception as e:
        logger.error(f"Persona 匹配评估失败: {e}")
        
    final_score = int(
        tech_score * settings.tech_weight +
        macro_score * settings.macro_weight +
        persona_match_score * settings.persona_weight
    )
    
    # 分数限制在 0-100
    final_score = max(0, min(100, final_score))
    
    return final_score, rationale
