"""看板 Agent 后端入口。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import artifacts, cards, comments, health, notices, projects
from app.api.settings import router as settings_router
from app.core.config import settings
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("board-agent backend starting (debug=%s)", settings.debug)
    # 阶段 1 起在此接入事件总线 / 数据库连接
    yield
    logger.info("board-agent backend stopped")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(artifacts.router)
app.include_router(projects.router)
app.include_router(cards.router)
app.include_router(comments.router)
app.include_router(notices.router)
app.include_router(settings_router)
