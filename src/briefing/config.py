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
    # V0.3 个性化配置
    user_persona: str = Field(
        default="我是一名关注 AI 发展的技术人员，偏好开源项目和硬核技术解析，不看软文。",
        description="注入给 LLM 的私人画像描述",
    )
    
    # V0.3 去重配置
    title_similarity_threshold: float = Field(
        default=0.85, description="Loop A 标题相似度硬拦截阈值"
    )
    
    # V0.3 上下文配置
    context_lookback_days: int = Field(
        default=3, description="Loop B 向前追溯历史脉络的天数"
    )
    context_max_items: int = Field(
        default=45, description="Loop B 注入历史上下文的最大条数"
    )
    
    # V0.3 数据清理配置
    cleanup_retention_days: int = Field(
        default=7, description="数据库垃圾数据保留天数"
    )
    cleanup_hour: int = Field(default=3, description="数据清理任务执行小时")
    cleanup_minute: int = Field(default=0, description="数据清理任务执行分钟")

    collect_max_items: int = Field(default=20, description="晨报最多收录的新闻条数")

    # 推送与打分阈值
    instant_push_threshold: int = Field(default=90, description="即时推送分数阈值")
    fetch_store_threshold: int = Field(default=60, description="入库分数阈值")
    ddgs_trigger_threshold: int = Field(default=70, description="触发 DDGS 联网检索分数阈值")
    
    # 调度
    schedule_hour: int = Field(default=8, description="晨报调度执行小时")
    schedule_minute: int = Field(default=0, description="晨报调度执行分钟")
    timezone: str = Field(default="Asia/Shanghai", description="系统时区")

    # 推送（Phase 2，可选）
    frontend_base_url: str = Field(default="http://localhost:5173", description="前端访问地址")
    dingtalk_webhook_url: str | None = Field(default=None, description="钉钉 Webhook URL")
    dingtalk_secret: str | None = Field(default=None, description="钉钉机器人加签密钥（加签模式时填写）")
    dingtalk_keyword: str = Field(default="【日报】", description="钉钉机器人自定义关键词（关键词模式时填写）")
    dingtalk_timeout: int = Field(default=10, description="钉钉推送超时时间（秒）")
    dingtalk_summary_max_items: int = Field(default=20, description="钉钉兜底新闻摘要最大条数")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """获取配置单例。"""
    return Settings()
