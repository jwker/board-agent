"""健康检查：探活 + 版本信息。"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": "board-agent", "version": "0.1.0"}
