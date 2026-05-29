"""技术演进思维导图生成模块。

利用 LLM 提取当天新闻的共性主题，生成 Mermaid mindmap 代码。
"""

import logging

from briefing.ai.client import chat_completion

logger = logging.getLogger(__name__)

from briefing.ai.prompt_loader import load_prompt


def generate_mindmap(news_items: list[dict]) -> str:
    """根据当天新闻生成 Mermaid 思维导图代码。

    Args:
        news_items: 包含 title, category, one_line_summary 的新闻列表

    Returns:
        Mermaid mindmap 代码字符串
    """
    if not news_items:
        return ""

    news_list = "\n".join(
        f"- N{item.get('priority', i) + 1} [{item.get('category', '其他')}] "
        f"{item.get('title', '')} — {item.get('one_line_summary', '')}"
        for i, item in enumerate(news_items)
    )

    prompt_template = load_prompt("mindmap.txt")
    prompt = prompt_template.format(news_list=news_list)

    try:
        result = chat_completion(prompt, response_format=None, temperature=0.5)

        # 清洗结果：移除可能的 markdown 代码块标记
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # 移除首尾的 ``` 行
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        # 基础校验
        if "mindmap" not in cleaned:
            logger.warning("生成的内容不包含 mindmap 关键字，尝试修正")
            cleaned = "mindmap\n  root((今日技术动态))\n    待分析\n      暂无数据"

        logger.info("思维导图生成完成，%d 字符", len(cleaned))
        return cleaned

    except Exception as e:
        logger.error("思维导图生成失败: %s", e)
        return "mindmap\n  root((今日技术动态))\n    生成失败"
