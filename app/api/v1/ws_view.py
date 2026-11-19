import json
from fastapi import WebSocket, APIRouter, WebSocketDisconnect
from redis.asyncio import Redis
from app.api.ws_manager import manager
from app.db.postgres.database import AsyncSessionLocal
from app.db.redis.redis_client import get_redis_client
from app.services.queue_service import QueueService
from app.core.logger import logger

router = APIRouter(tags=["websocket"])


async def _handle_ping_pong(websocket: WebSocket, raw: str) -> None:
    """Handle heartbeat ping/pong messages from clients."""
    try:
        msg = json.loads(raw)
        if isinstance(msg, dict) and msg.get("type") == "ping":
            await websocket.send_json({"type": "pong"})
            return
    except Exception:
        pass

    if raw.strip().lower() == "ping":
        await websocket.send_text("pong")


@router.websocket("/ws/queue/{subject}")
async def queue_websocket(websocket: WebSocket, subject: str):
    """Queue room WebSocket: broadcasts real-time queue changes to everyone viewing this queue."""
    client_host = websocket.client.host if websocket.client else "unknown"
    await manager.connect(websocket, subject)
    logger.info(f"WebSocket connected to queue '{subject}' from {client_host}")

    # Fetch initial state using a short-lived DB session to avoid holding connections open
    r = get_redis_client()
    try:
        async with AsyncSessionLocal() as db:
            queue_service = QueueService(db, r)
            queue_data = await queue_service.get_queue(subject)

        await websocket.send_json(
            {"event": "queue_updated", "data": queue_data.model_dump(mode="json")}
        )

        while True:
            raw = await websocket.receive_text()
            await _handle_ping_pong(websocket, raw)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected from queue '{subject}' ({client_host})")
        manager.disconnect(websocket, subject)
    except Exception as e:
        logger.error(f"WebSocket error for queue '{subject}' ({client_host}): {e}")
        manager.disconnect(websocket, subject)


@router.websocket("/ws/user/{tg_id}")
async def user_websocket(websocket: WebSocket, tg_id: int):
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
            await _handle_ping_pong(websocket, raw)

    except WebSocketDisconnect:
        logger.info(f"Personal WebSocket disconnected for user tg_id={tg_id} ({client_host})")
        manager.disconnect_user(websocket, tg_id)
    except Exception as e:
        logger.error(f"Personal WebSocket error for user tg_id={tg_id} ({client_host}): {e}")
        manager.disconnect_user(websocket, tg_id)
