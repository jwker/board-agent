"""设置 Pydantic 模型。"""

from pydantic import BaseModel, Field


class LLMSettingsIn(BaseModel):
    providers: list[dict] = Field(default_factory=list)
    default: dict | None = None


class ProjectModelIn(BaseModel):
    provider_id: str = ""
    model: str = ""


class VectorSettingsIn(BaseModel):
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    dims: int = 0


class EmailSettingsIn(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_pass: str = ""
    from_addr: str = ""
    to_addr: str = ""


class ToolLLMIn(BaseModel):
    """工具模型：标题提炼等轻任务专用，完全独立配置（不复用大模型列表）。"""

    name: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    enable_thinking: bool | None = None
