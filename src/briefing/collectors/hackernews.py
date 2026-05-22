"""Hacker News 数据采集器。

使用 HN 官方 Firebase API 获取数据，比 HTML 解析更稳定。
参考: https://github.com/HackerNews/API
"""

import json
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from briefing.collectors.base import BaseCollector, RawNewsItemSchema

logger = logging.getLogger(__name__)

_HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
_MAX_COMMENTS = 10


def _fetch_item(item_id: int) -> dict | None:
    """通过 HN API 获取单个 item。"""
    try:
        resp = requests.get(f"{_HN_API_BASE}/item/{item_id}.json", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("获取 HN item %d 失败: %s", item_id, e)
        return None


def _fetch_article_content(url: str) -> str:
    """智能抓取链接内容：GitHub 仓库取 README，其他取页面文本。"""
    if not url:
        return ""

    github_match = re.match(r"https?://github\.com/([^/]+)/([^/]+)", url)
    if github_match:
        owner, repo = github_match.groups()
        repo = repo.split("/")[0]
        return _fetch_github_readme(owner, repo)

    return _fetch_page_text(url)


def _fetch_github_readme(owner: str, repo: str) -> str:
    """获取 GitHub README 内容。"""
    for branch in ["main", "master"]:
        readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
        try:
            resp = requests.get(readme_url, headers=_HEADERS, timeout=10)
            if resp.status_code == 200:
                return resp.text[:5000]
        except requests.RequestException:
            continue
    return ""


def _fetch_page_text(url: str) -> str:
    """抓取普通网页的可见文本。"""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        body = soup.find("body")
        text = body.get_text(separator="\n", strip=True) if body else ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)[:8000]
    except requests.RequestException as e:
        logger.warning("抓取页面失败 (%s): %s", url, e)
        return ""


def _fetch_top_comments(item_data: dict) -> list[str]:
    """获取 HN 帖子的前 N 条评论文本。"""
    kid_ids = item_data.get("kids", [])[:_MAX_COMMENTS]
    comments = []
    for kid_id in kid_ids:
        kid = _fetch_item(kid_id)
        if kid and kid.get("text"):
            # 简单去 HTML 标签
            soup = BeautifulSoup(kid["text"], "html.parser")
            comments.append(soup.get_text(strip=True))
        time.sleep(0.3)
    return comments


class HackerNewsCollector(BaseCollector):
    """从 Hacker News API 抓取 Top Stories。"""

    def __init__(self, max_items: int = 20, min_score: int = 10):
        super().__init__(max_items)
        self.min_score = min_score

    def collect(self) -> list[RawNewsItemSchema]:
        """通过 HN Firebase API 获取 Top Stories。"""
        items: list[RawNewsItemSchema] = []

        try:
            resp = requests.get(f"{_HN_API_BASE}/topstories.json", timeout=10)
            resp.raise_for_status()
            story_ids = resp.json()[:50]  # 多取一些，后续按 score 过滤
        except requests.RequestException as e:
            logger.error("HN Top Stories 列表获取失败: %s", e)
            return items

        collected = 0
        for story_id in story_ids:
            if collected >= self.max_items:
                break

            story = _fetch_item(story_id)
            if not story or story.get("type") != "story":
                continue

            score = story.get("score", 0)
            if score < self.min_score:
                continue

            title = story.get("title", "")
            url = story.get("url", f"https://news.ycombinator.com/item?id={story_id}")

            logger.info("正在处理 HN: %s (score=%d)", title[:60], score)

            # 抓取文章内容
            article_content = ""
            if url and "news.ycombinator.com" not in url:
                article_content = _fetch_article_content(url)
                time.sleep(1)

            # 获取评论
            comments = _fetch_top_comments(story)

            items.append(RawNewsItemSchema(
                source="hackernews",
                title=title,
                url=url,
                description=story.get("text", ""),  # 自帖文本（Show HN 等）
                raw_content=article_content,
                score=score,
                extra_data={
                    "hn_id": story_id,
                    "author": story.get("by", ""),
                    "comment_count": story.get("descendants", 0),
                    "comments": comments,
                },
            ))
            collected += 1
            time.sleep(0.5)

        logger.info("Hacker News 采集完成，共 %d 条", len(items))
        return items
