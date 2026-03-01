from fastapi import APIRouter,Depends
from app.services.queue_service import QueueService
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.db.postgres.database import get_db
from app.db.redis.redis_client import get_redis
from app.api.ws_manager import manager

router = APIRouter(prefix="/queue",tags=["queue"])


@router.get("/{subject}")
async def get_queue(subject: str,db: AsyncSession = Depends(get_db),r: Redis = Depends(get_redis)):
    queue_service = QueueService(db,r)
    
    return await queue_service.get_queue(subject)

@router.post("/{subject}/join")
async def join_queue(subject: str,tg_id: int,position: int,db: AsyncSession = Depends(get_db),r: Redis = Depends(get_redis)):
    queue_service = QueueService(db,r)

    await queue_service.join(subject,tg_id,position)

    queue_data = await queue_service.get_queue(subject)
    await manager.broadcast(subject,{
        "event": "queue_updated",
        "data": queue_data.model_dump(mode="json")
    })

    return {"status":"joined"}

@router.post("/{subject}/leave")
async def leave_queue(subject: str,tg_id: int,position: int,db: AsyncSession = Depends(get_db),r: Redis = Depends(get_redis)):
    queue_service = QueueService(db,r)

    await queue_service.leave(subject,tg_id,position)

    queue_data = await queue_service.get_queue(subject)
    await manager.broadcast(subject,{
        "event": "queue_updated",
        "data": queue_data.model_dump(mode="json")
    })

    return {"status":"left"}

@router.post("/{subject}/swap")
async def swap_in_queue(subject: str,position1: int,position2: int,db: AsyncSession = Depends(get_db),r: Redis = Depends(get_redis)):
    queue_service = QueueService(db,r)

    await queue_service.swap(position1,position2,subject)

    queue_data = await queue_service.get_queue(subject)
    await manager.broadcast(subject,{
        "event": "queue_updated",
        "data": queue_data.model_dump(mode="json")
    })

    return {"status":"swapped"}