"""WebSocket 骨架测试：连接/心跳/事件推送。"""

from starlette.testclient import TestClient

from app.core.event_bus import Event, EventType, bus
from app.main import app


def test_ws_connect_and_ping_pong():
    """连接成功；ping → pong。"""
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws") as ws:
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong", "payload": {}}


def test_ws_receives_notification_event():
    """事件总线 NOTIFICATION → WS 推送 {type, payload}。"""
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws") as ws:
            tc.portal.call(
                bus.publish,
                Event(
                    EventType.NOTIFICATION,
                    {
                        "notice_id": 7,
                        "category": "completed",
                        "content": "AI 处理完成",
                        "project_id": 1,
                        "card_id": 2,
                    },
                ),
            )
            msg = ws.receive_json()
            assert msg["type"] == "notification"
            assert msg["payload"]["notice_id"] == 7
            assert msg["payload"]["card_id"] == 2


def test_ws_receives_card_updated_event():
    """card.updated 事件同样经 WS 推送（阶段 3 视图刷新依赖）。"""
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws") as ws:
            tc.portal.call(
                bus.publish,
                Event(EventType.CARD_UPDATED, {"card_id": 3, "status": "in_progress"}),
            )
            msg = ws.receive_json()
            assert msg["type"] == "card.updated"
            assert msg["payload"]["card_id"] == 3
