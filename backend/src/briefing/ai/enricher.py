"""@deprecated 背景补充模块。

注意：自 V0.4 起，本模块已被废弃。
- 联网搜索功能已迁移至 `tools/web_search.py`
- 背景合成逻辑已迁移至 `briefing/graph/nodes.py` 的 Researcher Node 中
- Prompt 已提取为 `prompts/enricher_*.txt`。

识别新闻中的专业术语、缩写或新项目，结合联网检索结果补充背景释义。
"""

import logging
import re

from briefing.ai.client import chat_completion, chat_completion_json

logger = logging.getLogger(__name__)

_MAX_SEARCH_TERMS = 4
_SEARCH_RESULTS_PER_TERM = 3

_TERM_EXTRACTION_PROMPT_TEMPLATE = """你是科技新闻术语识别助手。请从以下新闻摘要中提取适合联网检索的关键词。

## 新闻信息
- 标题: {title}
- 一句话摘要: {summary}
- 核心要点:
{key_points}

## 提取范围
只提取对背景知识补充有帮助的：
- 专业术语
- 技术缩写
- 新公司/组织
- 新项目/框架/模型/工具
- 产品名或论文/系统名

## 要求
1. 不要提取泛泛的词，例如"模型"、"平台"、"开发者"、"发布"。
2. 优先提取标题和要点中最具体、最可能需要查新的词。
3. 最多返回 {max_terms} 个。

请只返回 JSON:
{{
  "terms": ["术语1", "术语2"]
}}
"""

_ENRICH_PROMPT_TEMPLATE = """你是一位资深的科技领域百科编辑。请为以下新闻补充背景知识，帮助读者快速理解新闻上下文。

## 新闻信息
- 标题: {title}
- 一句话摘要: {summary}
- 核心要点: {key_points}

## 已识别需解释/检索的关键词
{terms}

## 联网检索结果
{search_context}

## 任务
1. 结合新闻信息和联网检索结果，为关键词提供简洁背景释义
2. 优先使用检索结果中的最新信息；检索结果不足时可用常识补充，但不要编造具体事实
3. 如果涉及某个技术的发展历程，简要说明其演进脉络
4. 关键说法后可附 1-2 个来源链接

## 输出要求
- 用中文撰写
- 使用 Markdown 格式
- 内容控制在 200 字以内
- 重点解释对理解新闻最关键的概念
"""


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """执行网络搜索并返回结果。"""
    from ddgs import DDGS

    with DDGS() as ddgs:
        results = []
        for result in ddgs.text(query, max_results=max_results):
            results.append({
                "title": result.get("title", ""),
                "link": result.get("href", ""),
                "snippet": result.get("body", ""),
            })
    return results


def _fallback_terms(title: str, key_points: list[str], max_terms: int) -> list[str]:
    """术语提取失败时的轻量兜底。"""
    text = " ".join([title, *key_points])
    candidates = re.findall(r"[A-Za-z][A-Za-z0-9_.+-]{2,}(?:[- ][A-Za-z0-9_.+]+)*", text)

    terms = []
    seen = set()
    for candidate in candidates:
        cleaned = candidate.strip(" -_.,:;()[]{}")
        if not cleaned or cleaned.lower() in seen:
            continue
        if cleaned.lower() in {"the", "and", "for", "with", "from", "model", "platform"}:
            continue
        terms.append(cleaned)
        seen.add(cleaned.lower())
        if len(terms) >= max_terms:
            break
    return terms


def extract_background_terms(
    title: str,
    summary: str,
    key_points: list[str],
    max_terms: int = _MAX_SEARCH_TERMS,
) -> list[str]:
    """从摘要信息中提取要联网检索的背景关键词。"""
    prompt = _TERM_EXTRACTION_PROMPT_TEMPLATE.format(
        title=title,
        summary=summary,
        key_points="\n".join(f"- {p}" for p in key_points),
        max_terms=max_terms,
    )

    try:
        result = chat_completion_json(prompt, temperature=0.1)
        raw_terms = result.get("terms", [])
        terms = []
        seen = set()
        for term in raw_terms:
            if not isinstance(term, str):
                continue
            cleaned = term.strip()
            if not cleaned or cleaned.lower() in seen:
                continue
            terms.append(cleaned)
            seen.add(cleaned.lower())
            if len(terms) >= max_terms:
                break
        if terms:
            return terms
    except Exception as e:
        logger.warning("背景关键词提取失败，使用兜底规则 (%s): %s", title[:40], e)

    return _fallback_terms(title, key_points, max_terms)


def _format_search_context(search_results: dict[str, list[dict]]) -> str:
    """将搜索结果格式化为 LLM 可读上下文。"""
    if not search_results:
        return "无可用联网检索结果。"

    lines = []
    for term, results in search_results.items():
        lines.append(f"### {term}")
        if not results:
            lines.append("- 未检索到有效结果")
            continue
        for result in results:
            title = result.get("title", "").strip()
            link = result.get("link", "").strip()
            snippet = result.get("snippet", "").strip()
            lines.append(f"- {title}\n  链接: {link}\n  摘要: {snippet}")
    return "\n".join(lines)


def collect_background_search_results(
    terms: list[str],
    max_results_per_term: int = _SEARCH_RESULTS_PER_TERM,
) -> dict[str, list[dict]]:
    """按术语执行联网检索。"""
    search_results = {}
    for term in terms:
        try:
            search_results[term] = web_search(term, max_results=max_results_per_term)
        except Exception as e:
            logger.warning("背景联网检索失败 (%s): %s", term, e)
            search_results[term] = []
    return search_results


def enrich_background(title: str, summary: str, key_points: list[str]) -> str:
    """为单条新闻补充背景知识。

    Args:
        title: 新闻标题
        summary: 一句话摘要
        key_points: 核心要点列表

    Returns:
        Markdown 格式的背景知识文本
    """
    terms = extract_background_terms(title, summary, key_points)
    search_results = collect_background_search_results(terms)

    prompt = _ENRICH_PROMPT_TEMPLATE.format(
        title=title,
        summary=summary,
        key_points="\n".join(f"- {p}" for p in key_points),
        terms="\n".join(f"- {term}" for term in terms) if terms else "无",
        search_context=_format_search_context(search_results),
    )

    try:
        result = chat_completion(prompt, response_format=None)
        return result.strip()
    except Exception as e:
        logger.error("背景补充失败 (%s): %s", title[:40], e)
        return ""
