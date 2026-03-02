from fastapi import WebSocket, Depends, APIRouter, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.api.ws_manager import manager
from app.db.postgres.database import get_db
from app.db.redis.redis_client import get_redis
from app.services.queue_service import QueueService
import json

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/queue/{subject}")
async def queue_websocket(
    websocket: WebSocket,
    subject: str,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):

    await manager.connect(websocket, subject)
    queue_service = QueueService(db, r)

    try:
        queue_data = await queue_service.get_queue(subject)
        await websocket.send_json(
            {"event": "queue_updated", "data": queue_data.model_dump(mode="json")}
        )

        while True:
            raw = await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket, subject)
