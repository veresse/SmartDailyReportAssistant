"""Web Scraper 工具：提取网页纯文本正文。"""

import logging
import trafilatura
from briefing.config import get_settings

logger = logging.getLogger(__name__)


def scrape_url(url: str) -> str:
    """抓取目标 URL 的纯文本正文。

    Args:
        url: 目标网页 URL

    Returns:
        截取后的纯文本正文。失败时返回空字符串。
    """
    settings = get_settings()
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            logger.warning("Web Scraper 下载失败: %s", url)
            return ""

        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        if not text:
            logger.warning("Web Scraper 正文提取为空: %s", url)
            return ""

        return text[: settings.scraper_max_chars]

    except Exception as e:
        logger.error("Web Scraper 异常 (%s): %s", url, e)
        return ""
