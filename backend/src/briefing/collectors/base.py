"""采集器标准化数据模型。"""

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
    published_at: str = ""
    ai_tags: list[str] = Field(default_factory=list)
