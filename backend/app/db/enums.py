"""枚举与常量：状态、类型、通知类别等。"""

from enum import StrEnum


class CardStatus(StrEnum):
    """卡片状态（PRD 状态机）。"""

    BACKLOG = "backlog"  # 积压：AI 不可执行
    TODO = "todo"  # 待办：AI 可领取
    IN_PROGRESS = "in_progress"  # 进行中：AI 执行中
    DONE = "done"  # 已完成
    ARCHIVED = "archived"  # 归档：仅用户主动触发

    # 提示标签（进行中卡片上的细分状态，独立于主状态）
    PROMPT_NONE = "prompt_none"  # AI 未开始
    PROMPT_RUNNING = "prompt_running"  # AI 处理中
    PROMPT_WAITING_APPROVAL = "prompt_waiting_approval"  # 等待人工审批
    PROMPT_DONE = "prompt_done"  # AI 处理完成


class CardType(StrEnum):
    """卡片类型（7 类，另有自定义标签维度）。"""

    REQUIREMENT = "requirement"  # 需求
    BUG = "bug"  # 缺陷
    REFACTOR = "refactor"  # 重构
    OPTIMIZE = "optimize"  # 优化
    TASK = "task"  # 任务
    RESEARCH = "research"  # 调研
    DOC = "doc"  # 文档


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CommentAuthor(StrEnum):
    USER = "user"
    AI = "ai"


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NoticeCategory(StrEnum):
    """通知五类。"""

    APPROVAL_WAITING = "approval_waiting"  # 等待人工审批
    COMPLETED = "completed"  # AI 处理完成
    FAILED = "failed"  # 任务失败
    TIMEOUT_REJECTED = "timeout_rejected"  # 审批超时已拒绝
    CLARIFY = "clarify"  # 需要澄清


class ArtifactType(StrEnum):
    PDF = "pdf"
    IMAGE = "image"
    CODE = "code"
    HTML = "html"
    OTHER = "other"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SettingScope(StrEnum):
    GLOBAL = "global"
    PROJECT = "project"
