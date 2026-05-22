"""集中配置管理，从 .env 文件加载所有环境变量。"""

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

    # 数据采集
    collect_max_items: int = Field(default=20, description="每个平台最大采集条数")
    collector_concurrency: int = Field(default=3, description="数据采集器并发数")
    llm_concurrency: int = Field(default=5, description="LLM 摘要/背景处理并发数")
    ai_filter_enabled: bool = Field(default=True, description="是否启用 AI 相关新闻过滤")
    ai_filter_batch_size: int = Field(default=50, description="AI 新闻过滤批大小")
    ai_filter_target_audience: str = Field(
        default="AI 开发者、AI 研究员和关注大模型应用的技术团队",
        description="AI 新闻过滤的目标读者群体",
    )

    # 调度
    schedule_hour: int = Field(default=6, description="调度执行小时")
    schedule_minute: int = Field(default=0, description="调度执行分钟")
    timezone: str = Field(default="Asia/Shanghai", description="系统时区")

    # 推送（Phase 2，可选）
    frontend_base_url: str = Field(default="http://localhost:5173", description="前端访问地址")
    feishu_webhook_url: str | None = Field(default=None, description="飞书 Webhook URL")
    dingtalk_webhook_url: str | None = Field(default=None, description="钉钉 Webhook URL")
    dingtalk_secret: str | None = Field(default=None, description="钉钉机器人加签密钥")
    dingtalk_timeout: int = Field(default=10, description="钉钉推送超时时间（秒）")
    dingtalk_summary_max_items: int = Field(default=20, description="钉钉兜底新闻摘要最大条数")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    """获取配置单例。"""
    return Settings()
