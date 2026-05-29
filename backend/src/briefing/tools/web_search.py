"""Web Search 工具：DuckDuckGo 联网搜索封装。"""

import logging

logger = logging.getLogger(__name__)


def web_search(query: str, max_results: int = 3) -> list[dict]:
    """执行 DuckDuckGo 搜索并返回结构化结果。

    Args:
        query: 搜索关键词
        max_results: 最大返回条数

    Returns:
        包含 title, link, snippet 的字典列表
    """
    from ddgs import DDGS

    try:
        with DDGS() as ddgs:
            results = []
            for result in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": result.get("title", ""),
                    "link": result.get("href", ""),
                    "snippet": result.get("body", ""),
                })
        return results
    except Exception as e:
        logger.error("Web Search 异常 (%s): %s", query, e)
        return []
