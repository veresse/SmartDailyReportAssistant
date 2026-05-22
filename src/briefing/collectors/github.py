"""GitHub Trending 数据采集器。

基于 test/github_trending.py 重构为模块化采集器。
"""

import json
import logging
import time

import requests
from bs4 import BeautifulSoup

from briefing.collectors.base import BaseCollector, RawNewsItemSchema

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _fetch_readme(full_name: str) -> str:
    """获取仓库 README.md 内容，尝试 main/master 分支。"""
    base_raw_url = f"https://raw.githubusercontent.com/{full_name}"

    for branch in ["main", "master"]:
        readme_url = f"{base_raw_url}/{branch}/README.md"
        try:
            response = requests.get(readme_url, headers=_HEADERS, timeout=10)
            if response.status_code == 200:
                logger.debug("成功获取 README: %s", readme_url)
                return response.text[:5000]
        except requests.RequestException as e:
            logger.warning("获取 README 失败 (%s): %s", readme_url, e)
            continue

    return ""


class GitHubTrendingCollector(BaseCollector):
    """从 GitHub Trending 页面抓取热门仓库信息。"""

    def collect(self) -> list[RawNewsItemSchema]:
        """抓取 GitHub Trending 页面并返回标准化新闻列表。"""
        url = "https://github.com/trending"
        items: list[RawNewsItemSchema] = []

        try:
            session = requests.Session()
            session.get("https://github.com", headers=_HEADERS, timeout=10)
            time.sleep(2)

            response = session.get(url, headers=_HEADERS, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            articles = soup.find_all("article", class_="Box-row")

            for article in articles[: self.max_items]:
                item = self._parse_article(article)
                if item:
                    items.append(item)
                    time.sleep(1)  # 礼貌性延迟

        except requests.RequestException as e:
            logger.error("GitHub Trending 采集失败: %s", e)

        logger.info("GitHub Trending 采集完成，共 %d 条", len(items))
        return items

    def _parse_article(self, article) -> RawNewsItemSchema | None:
        """解析单个 Trending 仓库条目。"""
        h2 = article.find("h2", class_="h3 lh-condensed")
        if not h2:
            return None

        a_tag = h2.find("a")
        if not a_tag:
            return None

        full_name = a_tag["href"].strip("/")
        repo_url = f"https://github.com/{full_name}"

        # 描述
        desc_p = article.find("p", class_="col-9 color-fg-muted my-1 pr-4")
        description = desc_p.get_text(strip=True) if desc_p else ""

        # 语言
        lang_span = article.find("span", itemprop="programmingLanguage")
        language = lang_span.get_text(strip=True) if lang_span else "Unknown"

        # 今日星数
        stars_today = 0
        stars_span = article.find("span", class_="d-inline-block float-sm-right")
        if stars_span:
            stars_text = stars_span.get_text(strip=True).split()[0]
            try:
                stars_today = int(stars_text.replace(",", ""))
            except ValueError:
                pass

        # README 内容
        logger.info("正在处理: %s", full_name)
        readme_content = _fetch_readme(full_name)

        return RawNewsItemSchema(
            source="github",
            title=full_name,
            url=repo_url,
            description=description,
            raw_content=readme_content,
            score=stars_today,
            extra_data=json.loads(json.dumps({
                "language": language,
                "stars_today": stars_today,
            })),
        )
