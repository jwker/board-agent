"""WebSocket 路由：/ws。"""

from fastapi import APIRouter, WebSocket

from app.ws.manager import ws_endpoint

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws_endpoint(ws)
