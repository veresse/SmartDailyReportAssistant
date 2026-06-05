"""LLM 客户端封装，兼容所有 OpenAI-compatible API。"""

import json
import logging

from openai import OpenAI

from briefing.config import get_settings

logger = logging.getLogger(__name__)

_client_instance: OpenAI | None = None


def get_llm_client() -> OpenAI:
    """获取 OpenAI 兼容客户端（惰性单例）。"""
    global _client_instance
    if _client_instance is None:
        settings = get_settings()
        _client_instance = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    return _client_instance


def chat_completion(
    prompt: str,
    system: str = "你是一个专业的科技新闻分析助手。",
    response_format: str | None = None,
    temperature: float = 0.3,
) -> str:
    """发送 Chat Completion 请求并返回文本结果。

    Args:
        prompt: 用户 prompt
        system: 系统 prompt
        response_format: 若为 "json" 则使用 JSON mode
        temperature: 温度参数

    Returns:
        LLM 响应文本
    """
    settings = get_settings()
    client = get_llm_client()

    kwargs = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }

    if response_format == "json":
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        logger.debug(
            "LLM 调用完成, tokens: %s",
            response.usage.total_tokens if response.usage else "N/A",
        )
        return content
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        raise


def chat_completion_json(
    prompt: str,
    system: str = "你是一个专业的科技新闻分析助手。请始终返回有效的 JSON。",
    temperature: float = 0.3,
) -> dict:
    """发送请求并解析 JSON 响应。"""
    raw = chat_completion(prompt, system, response_format="json", temperature=temperature)
    return json.loads(raw)
