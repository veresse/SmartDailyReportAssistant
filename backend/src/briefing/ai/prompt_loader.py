"""Prompt 资产文件动态加载器。"""

import logging
from pathlib import Path

from briefing.config import get_settings

logger = logging.getLogger(__name__)

# 缓存：name -> (mtime, content)
_prompt_cache: dict[str, tuple[float, str]] = {}


def _resolve_prompts_dir() -> Path:
    """解析 prompts 目录的绝对路径。"""
    settings = get_settings()
    # prompts_dir 相对于 backend 根目录
    base = Path(__file__).resolve().parent.parent.parent.parent
    return base / settings.prompts_dir


def load_prompt(name: str) -> str:
    """加载指定名称的 Prompt 文件内容。

    基于文件修改时间 (mtime) 做缓存失效，编辑 prompt 后无需重启服务。

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

    current_mtime = path.stat().st_mtime

    cached = _prompt_cache.get(name)
    if cached and cached[0] == current_mtime:
        logger.debug("命中缓存: %s", name)
        return cached[1]

    content = path.read_text(encoding="utf-8")
    _prompt_cache[name] = (current_mtime, content)
    logger.debug("已加载 Prompt 文件: %s (%d 字符)", name, len(content))
    return content
