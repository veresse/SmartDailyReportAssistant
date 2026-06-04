"""集中配置管理，从 .env 文件加载所有环境变量。"""

from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用全局配置。"""

    # LLM
    llm_api_key: str = Field(description="LLM API Key")
    llm_base_url: str = Field(default="https://api.openai.com/v1", description="LLM API Base URL")
    llm_model: str = Field(default="gpt-4o", description="LLM 模型名称")

    # 数据库
    database_url: str = Field(
        default="sqlite:///./data/briefing.db",
        description="数据库连接字符串（默认 SQLite）",
    )

    # RSS与数据采集
    rss_opml_path: str = Field(default="data_source/rss.opml", description="RSS OPML 文件路径")
    rss_fetch_interval_minutes: int = Field(default=30, description="RSS 抓取间隔分钟")
    rss_lookback_minutes: int = Field(default=120, description="RSS 抓取回溯窗口（分钟）")
    llm_concurrency: int = Field(default=5, description="LLM 处理并发数")

    
    # V0.5 Embedding
    embedding_model: str = Field(default="text-embedding-3-small", description="Embedding 模型名称")

    # V0.5 去重与防抖
    dedup_pass_threshold: float = Field(default=0.80, description="向量去重放行阈值")
    dedup_reject_threshold: float = Field(default=0.95, description="向量去重丢弃阈值")
    push_throttle_window: int = Field(default=1800, description="防抖窗口秒数")
    push_throttle_max: int = Field(default=3, description="窗口内最大推送次数")

    # V0.4 Content Hydration (部分沿用)
    scraper_min_length: int = Field(
        default=50,
        description="RSS description 低于此字符数则触发全文抓取",
    )
    scraper_max_chars: int = Field(
        default=5000,
        description="Web Scraper 截取正文的最大字符数",
    )

    # V0.4 Prompt 资产路径
    prompts_dir: str = Field(
        default="prompts",
        description="Prompt 资产文件目录（相对于 backend 根目录）",
    )

    collect_max_items: int = Field(default=20, description="晨报最多收录的新闻条数")

    # 推送与打分阈值
    instant_push_threshold: int = Field(default=90, description="即时推送分数阈值")
    fetch_store_threshold: int = Field(default=60, description="入库分数阈值")
    
    # 调度
    schedule_hour: int = Field(default=8, description="晨报调度执行小时")
    schedule_minute: int = Field(default=0, description="晨报调度执行分钟")
    timezone: str = Field(default="Asia/Shanghai", description="系统时区")

    # 数据清理
    cleanup_hour: int = Field(default=3, description="数据清理执行小时")
    cleanup_minute: int = Field(default=0, description="数据清理执行分钟")
    cleanup_retention_days: int = Field(default=7, description="数据保留天数")

    # 推送（Phase 2，可选）
    frontend_base_url: str = Field(default="http://localhost:5173", description="前端访问地址")
    dingtalk_webhook_url: str | None = Field(default=None, description="钉钉 Webhook URL")
    dingtalk_secret: str | None = Field(default=None, description="钉钉机器人加签密钥（加签模式时填写）")
    dingtalk_keyword: str = Field(default="【日报】", description="钉钉机器人自定义关键词（关键词模式时填写）")
    dingtalk_timeout: int = Field(default=10, description="钉钉推送超时时间（秒）")
    dingtalk_summary_max_items: int = Field(default=20, description="钉钉兜底新闻摘要最大条数")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """获取配置单例。"""
    return Settings()
