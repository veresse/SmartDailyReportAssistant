"""Prompt 资产文件动态加载器。"""

import logging
from functools import lru_cache
from pathlib import Path

from briefing.config import get_settings

logger = logging.getLogger(__name__)


def _resolve_prompts_dir() -> Path:
    """解析 prompts 目录的绝对路径。"""
    settings = get_settings()
    # prompts_dir 相对于 backend 根目录
    base = Path(__file__).resolve().parent.parent.parent.parent
    return base / settings.prompts_dir


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """加载指定名称的 Prompt 文件内容。

    Args:
        name: 文件名（不含路径），如 "scorer.txt"

    Returns:
        Prompt 文本内容

    Raises:
        FileNotFoundError: 文件不存在时抛出
    """
    path = _resolve_prompts_dir() / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {path}")
    content = path.read_text(encoding="utf-8")
    logger.debug("已加载 Prompt 文件: %s (%d 字符)", name, len(content))
    return content
