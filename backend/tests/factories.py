"""测试造数工厂：一键创建项目/卡片/评论（默认值 + 可覆盖）。均为 async（session 是异步会话）。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CardStatus, CardType, CommentAuthor, Priority, ProjectStatus
from app.db.models import Card, Comment, Project


async def make_project(session: AsyncSession, **overrides) -> Project:
    """默认造一个项目；kwargs 覆盖字段。"""
    data = {
        "name": "测试项目",
        "description": "由 factory 创建",
        "status": ProjectStatus.ACTIVE.value,
    }
    data.update(overrides)
    project = Project(**data)
    session.add(project)
    await session.flush()
    return project


async def make_card(session: AsyncSession, project: Project | None = None, **overrides) -> Card:
    """默认造一张卡片（挂在项目下）；kwargs 覆盖字段。"""
    project = project or await make_project(session)
    data = {
        "project_id": project.id,
        "title": "测试卡片",
        "content": "主贴内容",
        "card_type": CardType.TASK.value,
        "priority": Priority.MEDIUM.value,
        "status": CardStatus.BACKLOG.value,
        "read_only": False,
    }
    data.update(overrides)
    card = Card(**data)
    session.add(card)
    await session.flush()
    return card


async def make_comment(
    session: AsyncSession, card: Card, author: str = CommentAuthor.USER.value, **overrides
) -> Comment:
    """默认造一条用户评论；kwargs 覆盖字段。"""
    data = {"card_id": card.id, "author": author, "content": "评论内容"}
    data.update(overrides)
    comment = Comment(**data)
    session.add(comment)
    await session.flush()
    return comment
