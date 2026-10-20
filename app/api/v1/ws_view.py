import json
from fastapi import WebSocket, Depends, APIRouter, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.api.ws_manager import manager
from app.db.postgres.database import get_db
from app.db.redis.redis_client import get_redis
from app.services.queue_service import QueueService
from app.core.logger import logger

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/queue/{subject}")
async def queue_websocket(
    websocket: WebSocket,
    subject: str,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Queue room WebSocket: broadcasts real-time queue changes to everyone viewing this queue."""
    client_host = websocket.client.host if websocket.client else "unknown"
    await manager.connect(websocket, subject)
    logger.info(f"WebSocket connected to queue '{subject}' from {client_host}")

    queue_service = QueueService(db, r)

    try:
        queue_data = await queue_service.get_queue(subject)
        await websocket.send_json(
            {"event": "queue_updated", "data": queue_data.model_dump(mode="json")}
        )

        while True:
            raw = await websocket.receive_text()
            # Handle client heartbeat/ping
            try:
                msg = json.loads(raw)
                if isinstance(msg, dict) and msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                if raw.strip().lower() == "ping":
                    await websocket.send_text("pong")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected from queue '{subject}' ({client_host})")
        manager.disconnect(websocket, subject)
    except Exception as e:
        logger.error(f"WebSocket error for queue '{subject}' ({client_host}): {e}")
        manager.disconnect(websocket, subject)


@router.websocket("/ws/user/{tg_id}")
async def user_websocket(
    websocket: WebSocket,
    tg_id: int,
):
    """Personal WebSocket: delivers private real-time push notifications to a specific user."""
    client_host = websocket.client.host if websocket.client else "unknown"
    await manager.connect_user(websocket, tg_id)
    logger.info(f"Personal WebSocket connected for user tg_id={tg_id} from {client_host}")

    try:
        await websocket.send_json(
            {"event": "connected", "message": f"Personal notifications active for user {tg_id}"}
        )

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if isinstance(msg, dict) and msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                if raw.strip().lower() == "ping":
                    await websocket.send_text("pong")

    except WebSocketDisconnect:
        logger.info(f"Personal WebSocket disconnected for user tg_id={tg_id} ({client_host})")
        manager.disconnect_user(websocket, tg_id)
    except Exception as e:
        logger.error(f"Personal WebSocket error for user tg_id={tg_id} ({client_host}): {e}")
        manager.disconnect_user(websocket, tg_id)
