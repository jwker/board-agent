"""事件总线测试：订阅分发、类型过滤、异常隔离、取消订阅。"""

import pytest

from app.core.event_bus import Event, EventBus, EventType


@pytest.fixture()
def bus():
    return EventBus()


async def test_subscriber_receives_matching_event(bus):
    """订阅者收到匹配类型的事件，payload 原样可达。"""
    received: list[Event] = []
    bus.subscribe(EventType.CARD_UPDATED, received.append)

    event = Event(EventType.CARD_UPDATED, {"card_id": 1, "status": "in_progress"})
    await bus.publish(event)

    assert len(received) == 1
    assert received[0].payload["card_id"] == 1
    assert received[0].occurred_at is not None


async def test_unmatched_type_not_delivered(bus):
    """未订阅的类型不触发订阅者。"""
    calls = 0

    async def handler(event: Event) -> None:
        nonlocal calls
        calls += 1

    bus.subscribe(EventType.NOTIFICATION, handler)
    await bus.publish(Event(EventType.COMMENT_CREATED, {"card_id": 1}))
    await bus.publish(Event(EventType.NOTIFICATION, {"card_id": 2}))

    assert calls == 1


async def test_multiple_subscribers_all_receive(bus):
    """同一事件的多个订阅者都收到。"""
    got: list[str] = []

    async def a(event: Event) -> None:
        got.append("a")

    async def b(event: Event) -> None:
        got.append("b")

    bus.subscribe(EventType.CARD_STEP, a)
    bus.subscribe(EventType.CARD_STEP, b)
    await bus.publish(Event(EventType.CARD_STEP, {"step": "1/5"}))

    assert sorted(got) == ["a", "b"]


async def test_handler_failure_isolated(bus):
    """一个订阅者抛错，不影响其他订阅者，且 publish 不向外抛。"""
    got: list[str] = []

    async def bad(event: Event) -> None:
        raise ValueError("boom")

    async def good(event: Event) -> None:
        got.append("ok")

    bus.subscribe(EventType.APPROVAL_PENDING, bad)
    bus.subscribe(EventType.APPROVAL_PENDING, good)

    await bus.publish(Event(EventType.APPROVAL_PENDING, {"card_id": 1}))
    assert got == ["ok"]


async def test_unsubscribe_stops_delivery(bus):
    """取消订阅后不再收到事件。"""
    calls = 0

    async def handler(event: Event) -> None:
        nonlocal calls
        calls += 1

    unsubscribe = bus.subscribe(EventType.CARD_UPDATED, handler)
    await bus.publish(Event(EventType.CARD_UPDATED, {"card_id": 1}))
    unsubscribe()
    await bus.publish(Event(EventType.CARD_UPDATED, {"card_id": 2}))

    assert calls == 1
