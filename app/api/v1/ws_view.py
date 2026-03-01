from fastapi import WebSocket,Depends,APIRouter,WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.api.ws_manager import manager
from app.db.postgres.database import get_db
from app.db.redis.redis_client import get_redis
from app.services.queue_service import QueueService
import json
from app.schemas.queue import QueueUserInfo,QueueActionType

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/queue/{subject}")
async def queue_websocket(websocket: WebSocket,subject: str,db: AsyncSession = Depends(get_db),r: Redis = Depends(get_redis)):
    
    await manager.connect(websocket,subject)
    queue_servive = QueueService(db,r)

    try:
        queue_data = await queue_servive.get_queue(subject)
        await websocket.send_json({
            "event": "queue_updated",
            "data": queue_data.model_dump("json")
        })

        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            action = QueueUserInfo(**data)

            if action.action == QueueActionType.JOIN:
                await queue_servive.join(subject,action.tg_id)

            elif action.action == QueueActionType.LEAVE:
                await queue_servive.leave(subject,action.tg_id)

            elif action.action == QueueActionType.SWAP:
                await queue_servive.swap(action.tg_id,action.target_tg_id,subject)

            else:
                await websocket.send_json({
                    "event": "error",
                    "data": {"message":f"Unknown action:{action.action}"}
                })

            queue_data = await queue_servive.get_queue(subject)

            await manager.broadcast(subject,{
                "event": "queue_updated",
                "data": queue_data.model_dump(mode="json")
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket,subject)


    except Exception as e:
        await websocket.send_json({
            "event": "error",
            "data": {"message":str(e)}
        })
        manager.disconnect(websocket,subject)