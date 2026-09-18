"""WebSocket 连接管理器（TECH-DESIGN §4）。

- 单机单用户：全局连接集合，事件广播给所有在线连接。
- 订阅事件总线：NOTIFICATION 等事件 → 序列化后推前端（{type, payload}）。
- 每个连接独立任务，异常/断开自动清理。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from fastapi import WebSocket

from app.core.event_bus import Event, EventType, bus

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._unsubscribes: list[Callable[[], None]] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("ws connected (total=%s)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("ws disconnected (total=%s)", len(self._connections))

    async def broadcast(self, message: dict) -> None:
        if not self._connections:
            return
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(message)
            except Exception:  # 单连接失败不影响其他连接
                logger.warning("ws send failed, dropping connection")
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def _on_event(self, event: Event) -> None:
        """事件总线 → WS 推送：统一 {type, payload} 协议。"""
        await self.broadcast({"type": event.event_type.value, "payload": event.payload})

    def start(self) -> None:
        """注册事件总线订阅（应用启动时调用）。"""
        for event_type in EventType:
            self._unsubscribes.append(bus.subscribe(event_type, self._on_event))
        logger.info("ws manager subscribed to event bus (%s types)", len(EventType))

    def stop(self) -> None:
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes.clear()
        logger.info("ws manager unsubscribed from event bus")


manager = ConnectionManager()


async def ws_endpoint(ws: WebSocket) -> None:
    """/ws 端点：接受连接，保持心跳，客户端可发 ping 探活。"""
    await manager.connect(ws)
    try:
        while True:
            try:
                message = await ws.receive_json()
                if message.get("type") == "ping":
                    await ws.send_json({"type": "pong", "payload": {}})
            except Exception:
                break
    finally:
        manager.disconnect(ws)
