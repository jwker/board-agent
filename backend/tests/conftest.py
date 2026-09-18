"""pytest 全局夹具：测试环境隔离（board_test 库 + 临时目录 + 造数工厂）。

约定：
- 本文件必须在任何 app 导入之前执行（pytest 加载 conftest 先于测试模块），
  因此在此设置环境变量，确保 app.core.config.settings 读到测试连接串。
- 每个测试自动清空数据表；迁移在首个测试前自动执行。
"""

import os

# 指向测试库（先于 app 导入设置）
os.environ["DATABASE_URL"] = "postgresql+asyncpg://board:board@localhost:5433/board_test"
os.environ["MILVUS_URI"] = "http://localhost:19531"

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models import Base
from app.main import app

_ALL_TABLES = list(Base.metadata.tables.keys())


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    """首次会话前把 board_test 迁移到最新（用测试连接串）。"""
    from alembic.config import Config

    from alembic import command

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
async def engine():
    """每个测试一个引擎：与测试的事件循环绑定，用完 dispose（避免跨 loop 复用）。"""
    engine = create_async_engine(settings.database_url)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def session_maker(engine):
    """每测试清空全部表，返回会话工厂（供测试与 HTTP 依赖注入共用同一引擎）。"""
    await _truncate_all(engine)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture()
async def session(session_maker):
    """每个测试一个会话；结束自动关闭归还连接。"""
    async with session_maker() as s:
        yield s


async def _truncate_all(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE " + ", ".join(f'"{t}"' for t in _ALL_TABLES) + " RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture()
async def client(session_maker):
    """HTTP 客户端：httpx ASGI 直连同一事件循环；API 的数据库依赖注入测试引擎。"""
    from httpx import ASGITransport, AsyncClient

    from app.db.deps import get_session

    async def override_get_session():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def tmp_project_dir(tmp_path):
    """临时授权目录（沙箱/文件测试用）。"""
    return tmp_path
