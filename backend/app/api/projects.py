"""项目 API：首页项目列表、新建、归档/恢复、详情（不能删除）。"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.db.enums import CardStatus, ProjectStatus
from app.db.models import Project
from app.schemas.project import (
    ProjectCreate,
    ProjectListItem,
    ProjectOut,
    ProjectStats,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _collect_stats(project: Project) -> ProjectStats:
    """由已加载的卡片集合统计（selectin 已预载）。"""
    return ProjectStats(
        total=len(project.cards),
        in_progress=sum(1 for c in project.cards if c.status == CardStatus.IN_PROGRESS.value),
        done=sum(1 for c in project.cards if c.status == CardStatus.DONE.value),
    )


@router.get("", response_model=list[ProjectListItem])
async def list_projects(
    include_archived: bool = True,
    session: AsyncSession = Depends(get_session),
) -> list[ProjectListItem]:
    """项目列表（默认含归档，前端分组展示；含卡片统计）。"""
    stmt = select(Project).order_by(Project.status, Project.id.desc())
    if not include_archived:
        stmt = stmt.where(Project.status == ProjectStatus.ACTIVE.value)
    projects = list((await session.execute(stmt)).scalars().all())
    items = [ProjectListItem.model_validate(p) for p in projects]
    for item, project in zip(items, projects, strict=False):
        item.stats = _collect_stats(project)
    return items


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_session),
) -> Project:
    """新建项目（名称唯一；授权目录存在且填写 AGENT.md 时写入目录根）。"""
    exists = (
        await session.execute(select(Project).where(Project.name == body.name))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"项目已存在: {body.name}")

    project = Project(
        name=body.name,
        description=body.description,
        directory=body.directory,
        directory_status=body.directory_status,
        agent_md=body.agent_md,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)

    _write_agent_md(project)
    logger.info("project created: %s (id=%s)", project.name, project.id)
    return project


def _write_agent_md(project: Project) -> None:
    """把 AGENT.md 写入授权目录根（仅目录真实存在时；失败不阻塞创建）。"""
    if not (project.directory and project.agent_md):
        return
    target = Path(project.directory).expanduser()
    if not target.is_dir():
        logger.warning("授权目录不存在，跳过写入 AGENT.md: %s", target)
        return
    try:
        (target / "AGENT.md").write_text(project.agent_md, encoding="utf-8")
        logger.info("AGENT.md 已写入 %s", target / "AGENT.md")
    except OSError as exc:
        logger.error("写入 AGENT.md 失败: %s", exc)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, session: AsyncSession = Depends(get_session)) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
) -> Project:
    """归档/恢复（status 仅接受 active / archived）。"""
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if body.status not in {ProjectStatus.ACTIVE.value, ProjectStatus.ARCHIVED.value}:
        raise HTTPException(status_code=422, detail="非法状态")

    project.status = body.status
    await session.commit()
    await session.refresh(project)
    logger.info("project %s -> %s (id=%s)", project.name, body.status, project.id)
    return project
