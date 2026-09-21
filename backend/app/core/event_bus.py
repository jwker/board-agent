"""进程内异步事件总线（TECH-DESIGN §4：引擎回调 → 总线 → WS 推送 / 通知落库）。

单机应用，无需消息队列：pub/sub + 异步分发 + 订阅者异常隔离。
事件类型见 EventType；payload 为 dict，携带 card_id / project_id 等上下文。
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)

Handler = Callable[["Event"], Awaitable[None]]


class EventType(StrEnum):
    CARD_UPDATED = "card.updated"  # 卡片状态/提示标签/字段变更
    CARD_STREAM = "card.stream"  # AI 回复流式增量文本（delta）
    CARD_STEP = "card.step"  # AI 执行步骤（步骤 x/y）
    COMMENT_CREATED = "comment.created"  # 新评论
    APPROVAL_PENDING = "approval.pending"  # 等待人工审批
    APPROVAL_RESOLVED = "approval.resolved"  # 审批已处理（批准/拒绝/超时）
    ARTIFACT_UPDATED = "artifact.updated"  # 产物新增
    NOTIFICATION = "notification"  # 通知（五类之一）


@dataclass(slots=True)
class Event:
    event_type: EventType
    payload: dict
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __str__(self) -> str:  # 日志友好
        return f"Event({self.event_type.value}, {self.payload})"


class EventBus:
    """异步发布订阅。订阅者抛出的异常只记录日志，不影响其他订阅者。"""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> Callable[[], None]:
        """订阅某类事件，返回取消订阅函数。"""
        self._subscribers[event_type].append(handler)
        logger.debug("subscribed %s -> %s", event_type.value, getattr(handler, "__name__", handler))

        def unsubscribe() -> None:
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    async def publish(self, event: Event) -> None:
        """分发事件：所有订阅者并行执行，单个失败仅记日志（异常隔离）。"""
        handlers = list(self._subscribers.get(event.event_type, []))
        if not handlers:
            return
        results = await asyncio.gather(
            *(self._safe_call(h, event) for h in handlers), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                logger.error("event handler failed: %s (%s)", event, result)

    async def _safe_call(self, handler: Handler, event: Event) -> None:
        try:
            await handler(event)
        except Exception:  # 隔离订阅者错误：记录并继续
            logger.exception("event handler %s raised", getattr(handler, "__name__", handler))
            raise


# 全局单例（应用内共享）
bus = EventBus()
