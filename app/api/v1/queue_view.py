from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.db.postgres.database import get_db
from app.db.redis.redis_client import get_redis
from app.api.ws_manager import manager
from app.services.queue_service import QueueService
from app.core.logger import logger
from app.schemas.dto import (
    SwapDto,
    UserDto,
    KickDto,
    QueueCreateDto,
    AdvanceQueueDto,
    PauseQueueDto,
    ClearQueueDto,
)
from app.schemas.queue import (
    MyPositionResponse,
    SwapCandidate,
    QueueStatsResponse,
)

router = APIRouter(prefix="/queue", tags=["queue"])


@router.post("/create")
async def create_queue(
    data: QueueCreateDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Create a new queue under a subject (e.g. subject_name='Математика', queue_type='Лаба 1')."""
    queue_service = QueueService(db, r)
    meta = await queue_service.create_queue(
        subject_name=data.subject_name,
        queue_type=data.queue_type,
        created_by_tg_id=data.created_by_tg_id,
    )
    return {"status": "created", "data": meta.model_dump(mode="json")}


@router.get("/list")
async def list_queues(
    search: str | None = Query(None, description="Search keyword in queue name"),
    subject_name: str | None = Query(None, description="Filter by exact subject name"),
    is_paused: bool | None = Query(None, description="Filter by paused status"),
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """List active queues with optional search and filters."""
    queue_service = QueueService(db, r)
    return await queue_service.list_queues(
        search=search, subject_name=subject_name, is_paused=is_paused
    )


@router.get("/list/{subject_name}")
async def list_queues_by_subject(
    subject_name: str,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """List all active queues for a specific subject (e.g. all labs/seminars for Physics)."""
    queue_service = QueueService(db, r)
    return await queue_service.list_queues_by_subject(subject_name)


@router.get("/user/{tg_id}/queues")
async def get_user_queues(
    tg_id: int,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Get all queues where the given user is currently registered."""
    queue_service = QueueService(db, r)
    queues = await queue_service.get_user_queues(tg_id)
    return {"queues": [q.model_dump(mode="json") for q in queues], "total": len(queues)}


@router.get("/{subject}")
async def get_queue(
    subject: str,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Get full state of a queue (slots 1..30)."""
    queue_service = QueueService(db, r)
    return await queue_service.get_queue(subject)


@router.get("/{subject}/my-position/{tg_id}", response_model=MyPositionResponse)
async def get_my_position(
    subject: str,
    tg_id: int,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Check user's place in line, how many people are ahead, and estimated wait time."""
    queue_service = QueueService(db, r)
    return await queue_service.get_my_position(subject, tg_id)


@router.get("/{subject}/swap-candidates/{tg_id}", response_model=list[SwapCandidate])
async def get_swap_candidates(
    subject: str,
    tg_id: int,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Get all users currently ahead of this student in line who are eligible for exchange."""
    queue_service = QueueService(db, r)
    return await queue_service.get_swap_candidates(subject, tg_id)


@router.get("/{subject}/stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    subject: str,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Get real-time statistics (total, taken, free slots, occupancy %, active swap requests)."""
    queue_service = QueueService(db, r)
    return await queue_service.get_stats(subject)


@router.get("/{subject}/history")
async def get_queue_history(
    subject: str,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Get recent activity audit trail for the queue (joins, leaves, kicks, swaps)."""
    queue_service = QueueService(db, r)
    history = await queue_service.get_history(subject, limit)
    return {"subject": subject, "history": history, "total": len(history)}


@router.post("/{subject}/join")
async def join_queue(
    subject: str,
    user_data: UserDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Join the queue at a specified free position (1..30)."""
    queue_service = QueueService(db, r)
    await queue_service.join(subject, user_data.tg_id, user_data.position)

    queue_data = await queue_service.get_queue(subject)
    await manager.broadcast(
        subject, {"event": "queue_updated", "data": queue_data.model_dump(mode="json")}
    )

    return {"status": "joined"}


@router.post("/{subject}/leave")
async def leave_queue(
    subject: str,
    user_data: UserDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Leave the queue."""
    queue_service = QueueService(db, r)
    await queue_service.leave(subject, user_data.tg_id, user_data.position)

    queue_data = await queue_service.get_queue(subject)
    await manager.broadcast(
        subject, {"event": "queue_updated", "data": queue_data.model_dump(mode="json")}
    )

    return {"status": "left"}


@router.post("/{subject}/kick")
async def kick_from_queue(
    subject: str,
    data: KickDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Curator removes a student from the queue."""
    queue_service = QueueService(db, r)
    await queue_service.kick(subject, data.curator_tg_id, data.target_tg_id)

    queue_data = await queue_service.get_queue(subject)
    await manager.broadcast(
        subject,
        {
            "event": "queue_updated",
            "data": queue_data.model_dump(mode="json"),
            "kicked_tg_id": data.target_tg_id,
        },
    )

    await manager.send_to_user(
        data.target_tg_id,
        {
            "event": "kicked",
            "subject": subject,
            "message": "Вы были удалены из очереди курирующим.",
        },
    )

    return {"status": "kicked"}


@router.post("/{subject}/advance")
async def advance_queue(
    subject: str,
    data: AdvanceQueueDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Curator calls 'Next': marks current person in front as completed and removes them."""
    queue_service = QueueService(db, r)
    completed_user_id, updated_queue = await queue_service.advance_queue(
        subject, data.curator_tg_id
    )

    await manager.broadcast(
        subject,
        {
            "event": "queue_advanced",
            "completed_tg_id": completed_user_id,
            "data": updated_queue.model_dump(mode="json"),
        },
    )

    await manager.send_to_user(
        completed_user_id,
        {
            "event": "submission_completed",
            "subject": subject,
            "message": "Ваша сдача завершена!",
        },
    )

    first_in_line = await queue_service.r.get_first_in_line(subject)
    if first_in_line:
        _, next_uid = first_in_line
        await manager.send_to_user(
            next_uid,
            {
                "event": "your_turn",
                "subject": subject,
                "message": "Вы следующий в очереди! Подойдите к преподавателю.",
            },
        )

    return {"status": "advanced", "completed_tg_id": completed_user_id}


@router.post("/{subject}/pause")
async def pause_queue(
    subject: str,
    data: PauseQueueDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Curator pauses or resumes queue."""
    queue_service = QueueService(db, r)
    meta = await queue_service.pause_queue(subject, data.curator_tg_id, data.paused)

    await manager.broadcast(
        subject,
        {
            "event": "queue_paused" if data.paused else "queue_resumed",
            "subject": subject,
            "is_paused": data.paused,
        },
    )

    return {"status": "paused" if data.paused else "resumed", "data": meta.model_dump(mode="json")}


@router.post("/{subject}/clear")
async def clear_queue(
    subject: str,
    data: ClearQueueDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Curator resets/clears all participants from the queue without deleting the queue."""
    queue_service = QueueService(db, r)
    updated_queue = await queue_service.clear_queue(subject, data.curator_tg_id)

    await manager.broadcast(
        subject,
        {
            "event": "queue_cleared",
            "subject": subject,
            "data": updated_queue.model_dump(mode="json"),
        },
    )

    return {"status": "cleared", "data": updated_queue.model_dump(mode="json")}


@router.delete("/{subject}")
async def delete_queue(
    subject: str,
    curator_tg_id: int = Query(..., description="Telegram ID of the curator performing the deletion"),
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Curator deletes the entire queue."""
    queue_service = QueueService(db, r)
    await queue_service.delete_queue(subject, curator_tg_id)

    await manager.broadcast(subject, {"event": "queue_deleted", "subject": subject})

    return {"status": "deleted"}


@router.post("/{subject}/swap")
async def swap_in_queue(
    subject: str,
    user_data: SwapDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Direct instant swap between positions (legacy/manual swap)."""
    queue_service = QueueService(db, r)
    await queue_service.swap(user_data.position1, user_data.position2, subject)

    queue_data = await queue_service.get_queue(subject)
    await manager.broadcast(
        subject, {"event": "queue_updated", "data": queue_data.model_dump(mode="json")}
    )

    return {"status": "swapped"}
