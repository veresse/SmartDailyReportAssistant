"""Embedding 向量化与余弦相似度计算工具。"""

import logging
import numpy as np
from openai import OpenAI
from briefing.config import get_settings

logger = logging.getLogger(__name__)


def get_embedding(text: str) -> list[float]:
    """调用 Embedding API 获取文本向量。"""
    settings = get_settings()
    if not text:
        return []
    try:
        client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        response = client.embeddings.create(
            model=settings.embedding_model,
            input=text[:8000],  # 截断防溢出
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error("Embedding 失败: %s", e)
        return []


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    if not vec_a or not vec_b:
        return 0.0
    a = np.array(vec_a)
    b = np.array(vec_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
