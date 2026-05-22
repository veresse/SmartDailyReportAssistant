"""技术演进思维导图生成模块。

利用 LLM 提取当天新闻的共性主题，生成 Mermaid mindmap 代码。
"""

import logging

from briefing.ai.client import chat_completion

logger = logging.getLogger(__name__)

_MINDMAP_PROMPT_TEMPLATE = """你是一个技术趋势分析专家。请分析以下今日科技新闻，提取共性主题，生成一张技术演进思维导图。

## 今日新闻列表
{news_list}

## 任务
1. 将新闻按共性主题进行逻辑聚类（如"开源大模型动态"、"前端框架更新"、"AI 应用"等）
2. 生成 Mermaid mindmap 代码
3. 根节点为"今日技术动态"
4. 每个主题分支下列出对应的具体新闻标题（简化为短语）
5. 每个具体新闻叶子节点必须以输入中的编号开头，例如"N1 LLaMA 3 发布"，编号不要改写、不要遗漏

## 输出要求
- 只输出 Mermaid 代码，不要其他文字
- 使用 mindmap 语法
- 标签中不要出现括号等 Mermaid 特殊字符
- 控制在 3-6 个主题分支
- 主题分支不要使用编号，只有具体新闻叶子节点使用 N1/N2 这种编号

示例格式:
```mermaid
mindmap
  root((今日技术动态))
    开源大模型
      N1 LLaMA 3 发布
      N2 Mistral 新模型
    AI 应用
      N3 GitHub Copilot 更新
```

请直接输出 mermaid 代码块中的内容，不需要 ```mermaid 包裹。
"""


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

    prompt = _MINDMAP_PROMPT_TEMPLATE.format(news_list=news_list)

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
