"""Web Scraper 工具：提取网页纯文本正文。"""

import logging
import trafilatura
from briefing.config import get_settings

logger = logging.getLogger(__name__)


import ipaddress
import socket
from urllib.parse import urlparse

def _validate_url(url: str) -> bool:
    """验证 URL 是否安全，防止 SSRF 攻击。"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
            
        hostname = parsed.hostname
        if not hostname:
            return False
            
        try:
            ip_str = socket.gethostbyname(hostname)
        except socket.gaierror:
            return False
            
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False
            
        return True
    except Exception:
        return False


def scrape_url(url: str) -> str:
    """抓取目标 URL 的纯文本正文。

    Args:
        url: 目标网页 URL

    Returns:
        截取后的纯文本正文。失败时返回空字符串。
    """
    settings = get_settings()
    
    if not _validate_url(url):
        logger.warning("Web Scraper 安全拦截: 非法或私有 URL %s", url)
        return ""
        
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
