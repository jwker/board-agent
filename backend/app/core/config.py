"""应用配置：从环境变量 / .env 加载，全项目唯一入口。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "board-agent"
    debug: bool = True

    # 数据库（本地 docker-compose 端口映射）
    database_url: str = "postgresql+asyncpg://board:board@localhost:5433/board"

    # 向量库（Milvus standalone）
    milvus_uri: str = "http://localhost:19531"

    # 产物根目录（默认 ~/.board-agent/artifacts）
    artifacts_root: str = str(Path.home() / ".board-agent" / "artifacts")

    # 模型（阶段 3 接入时填写）
    deepseek_api_key: str | None = None
    openai_api_key: str | None = None

    # 邮件（阶段 4 审批邮件提醒时填写）
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None


settings = Settings()
