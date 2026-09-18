"""环境健康检查：PG 连通与迁移状态、Milvus 连通。用法：make doctor"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


async def check_pg() -> None:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            version = await conn.scalar(text("select version()"))
            current = await conn.scalar(text("select version_num from alembic_version"))
            print(f"PG    : {(version or '')[:40]}...")
            print(f"迁移  : alembic_version = {current}")
    except Exception as exc:  # noqa: BLE001
        print(f"PG    : 连接失败 - {exc}")
    finally:
        await engine.dispose()


def check_milvus() -> None:
    try:
        from pymilvus import MilvusClient

        client = MilvusClient(uri=settings.milvus_uri)
        print(f"Milvus: {client.get_server_version()}")
    except Exception as exc:  # noqa: BLE001
        print(f"Milvus: 连接失败 - {exc}")


async def main() -> None:
    await check_pg()
    check_milvus()


if __name__ == "__main__":
    asyncio.run(main())
