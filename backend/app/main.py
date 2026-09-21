"""看板 Agent 后端入口。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import approvals, artifacts, cards, comments, health, notices, projects, ws
from app.api.settings import router as settings_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.engine.agent import create_checkpointer
from app.ws.manager import manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("board-agent backend starting (debug=%s)", settings.debug)
    # 启动期一次性初始化 checkpointer：避免首个执行任务在业务请求中
    # 触发 CREATE INDEX CONCURRENTLY（多任务并发时会互相等锁挂死）
    try:
        await create_checkpointer()
    except Exception:
        logger.exception("startup checkpointer init failed; will lazy-init on first execution")
    manager.start()
    yield
    manager.stop()
    logger.info("board-agent backend stopped")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(artifacts.router)
app.include_router(projects.router)
app.include_router(cards.router)
app.include_router(approvals.router)
app.include_router(comments.router)
app.include_router(notices.router)
app.include_router(settings_router)
app.include_router(ws.router)
