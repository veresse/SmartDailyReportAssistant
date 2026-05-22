"""Hugging Face 数据采集器。

通过 Hugging Face 官方 API 获取 Trending Papers、Models、Spaces。
基于 test/huggingfacedailypaper.py 重构。
"""

import json
import logging
import re

import requests

from briefing.collectors.base import BaseCollector, RawNewsItemSchema

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "HF-Daily-Report-Bot/2.0",
    "Accept": "application/json",
}


def _get_repo_description(repo_id: str, repo_type: str = "model") -> str:
    """从 Hugging Face 仓库 README 中提取第一段有效文本作为简介。"""
    if repo_type == "space":
        url = f"https://huggingface.co/spaces/{repo_id}/raw/main/README.md"
    else:
        url = f"https://huggingface.co/{repo_id}/raw/main/README.md"

    try:
        res = requests.get(url, timeout=5)
        if res.status_code != 200:
            return ""

        for line in res.text.split("\n"):
            line = line.strip()
            if line and not line.startswith(("#", "![", "---", "<")):
                if len(line) > 40:
                    clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", line)
                    clean = clean.replace("**", "").replace("*", "").replace("`", "")
                    return clean[:250] + "..." if len(clean) > 250 else clean
    except requests.RequestException:
        pass

    return ""


class HuggingFaceCollector(BaseCollector):
    """从 Hugging Face API 获取每日趋势数据。"""

    def collect(self) -> list[RawNewsItemSchema]:
        """获取 HF trending papers + models + spaces。"""
        items: list[RawNewsItemSchema] = []
        items.extend(self._collect_papers())
        items.extend(self._collect_models())
        items.extend(self._collect_spaces())
        logger.info("Hugging Face 采集完成，共 %d 条", len(items))
        return items

    def _collect_papers(self) -> list[RawNewsItemSchema]:
        """获取每日热门论文。"""
        items = []
        try:
            resp = requests.get(
                "https://huggingface.co/api/daily_papers",
                headers=_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            papers = resp.json()

            for p in papers[: self.max_items]:
                paper_info = p.get("paper", {})
                arxiv_id = paper_info.get("id", "")
                abstract = paper_info.get("summary", "").replace("\n", " ").strip()

                items.append(RawNewsItemSchema(
                    source="huggingface",
                    title=paper_info.get("title", "无标题"),
                    url=f"https://huggingface.co/papers/{arxiv_id}",
                    description=abstract[:300],
                    raw_content=abstract,
                    score=p.get("upvotes", 0),
                    extra_data={"type": "paper", "arxiv_id": arxiv_id},
                ))
        except requests.RequestException as e:
            logger.error("HF 论文获取失败: %s", e)
        return items

    def _collect_models(self) -> list[RawNewsItemSchema]:
        """获取热门模型。"""
        items = []
        try:
            resp = requests.get(
                "https://huggingface.co/api/models",
                params={"sort": "trendingScore", "limit": self.max_items},
                headers=_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            models = resp.json()

            for m in models:
                model_id = m.get("id", "")
                logger.debug("解析模型: %s", model_id)
                description = _get_repo_description(model_id, "model")

                items.append(RawNewsItemSchema(
                    source="huggingface",
                    title=model_id,
                    url=f"https://huggingface.co/{model_id}",
                    description=description,
                    score=m.get("likes", 0),
                    extra_data={
                        "type": "model",
                        "task_type": m.get("pipeline_tag", ""),
                        "downloads": m.get("downloads", 0),
                    },
                ))
        except requests.RequestException as e:
            logger.error("HF 模型获取失败: %s", e)
        return items

    def _collect_spaces(self) -> list[RawNewsItemSchema]:
        """获取热门 Spaces。"""
        items = []
        try:
            resp = requests.get(
                "https://huggingface.co/api/spaces",
                params={"sort": "trendingScore", "limit": self.max_items},
                headers=_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            spaces = resp.json()

            for s in spaces:
                space_id = s.get("id", "")
                logger.debug("解析 Space: %s", space_id)
                description = _get_repo_description(space_id, "space")

                items.append(RawNewsItemSchema(
                    source="huggingface",
                    title=space_id,
                    url=f"https://huggingface.co/spaces/{space_id}",
                    description=description,
                    score=s.get("likes", 0),
                    extra_data={
                        "type": "space",
                        "framework": s.get("sdk", ""),
                    },
                ))
        except requests.RequestException as e:
            logger.error("HF Spaces 获取失败: %s", e)
        return items
