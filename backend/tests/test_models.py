"""A2 数据层测试：模型映射、字段默认值、关系与级联（TEST-PLAN A2 第一部分）。"""

from sqlalchemy import select

from app.db.enums import CardStatus, CommentAuthor, ExecutionStatus
from app.db.models import Artifact, Card, Comment, Execution, Notice, Setting
from tests.factories import make_card, make_comment, make_project


async def test_project_card_comment_chain(session):
    """项目 → 卡片 → 评论 全链路创建与关系回读。"""
    project = await make_project(session, name="链式项目")
    card = await make_card(session, project=project, title="链式卡片")
    await make_comment(session, card=card, content="第一条")
    await make_comment(
        session, card=card, author=CommentAuthor.AI.value, thread_id="thr-1", content="AI 回复"
    )
    await session.commit()

    got = (await session.execute(select(Card).where(Card.id == card.id))).scalar_one()
    assert got.title == "链式卡片"
    assert got.project.name == "链式项目"
    assert len(got.comments) == 2
    ai_comment = next(c for c in got.comments if c.author == CommentAuthor.AI.value)
    assert ai_comment.thread_id == "thr-1"


async def test_card_defaults(session):
    """卡片字段默认值：状态=积压、只读=关。"""
    project = await make_project(session)
    card = await make_card(session, project=project)
    await session.commit()
    assert card.status == CardStatus.BACKLOG.value
    assert card.read_only is False


async def test_project_delete_cascades(session):
    """删除项目级联删除卡片与评论。"""
    project = await make_project(session, name="级联项目")
    card = await make_card(session, project=project)
    await make_comment(session, card=card)
    await session.commit()

    await session.delete(project)
    await session.commit()

    assert (
        await session.execute(select(Card).where(Card.id == card.id))
    ).scalar_one_or_none() is None
    assert (await session.execute(select(Comment))).scalars().all() == []


async def test_auxiliary_models(session):
    """辅助模型：执行记录 / 通知 / 产物 / 配置可创建回读。"""
    project = await make_project(session)
    card = await make_card(session, project=project)
    session.add(Execution(card_id=card.id, thread_id="thr-1", status=ExecutionStatus.QUEUED.value))
    session.add(
        Notice(
            category="approval_waiting", content="等待审批", project_id=project.id, card_id=card.id
        )
    )
    session.add(
        Artifact(
            card_id=card.id,
            project_id=project.id,
            filename="a.pdf",
            file_type="pdf",
            size=100,
            path="p/a.pdf",
        )
    )
    session.add(
        Setting(scope="project", project_id=project.id, key="auto_pickup", value={"enabled": True})
    )
    await session.commit()

    assert (
        await session.execute(select(Execution).where(Execution.card_id == card.id))
    ).scalar_one().thread_id == "thr-1"
    assert (await session.execute(select(Notice))).scalar_one().read is False
    assert (await session.execute(select(Artifact))).scalar_one().size == 100
    assert (await session.execute(select(Setting))).scalar_one().value == {"enabled": True}
