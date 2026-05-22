"""采集器抽象基类与标准化数据模型。"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class RawNewsItemSchema(BaseModel):
    """采集器输出的标准化新闻条目。"""

    source: str
    title: str
    url: str
    description: str = ""
    raw_content: str = ""
    score: int = 0
    extra_data: dict = Field(default_factory=dict)


class BaseCollector(ABC):
    """采集器抽象基类。所有平台采集器需实现 collect 方法。"""

    def __init__(self, max_items: int = 20):
        self.max_items = max_items

    @abstractmethod
    def collect(self) -> list[RawNewsItemSchema]:
        """执行数据采集，返回标准化的新闻列表。"""
