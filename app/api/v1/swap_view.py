from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.db.postgres.database import get_db
from app.db.redis.redis_client import get_redis
from app.api.ws_manager import manager
from app.services.swap_request_service import SwapRequestService
from app.services.queue_service import QueueService
from app.schemas.dto import SwapRequestCreateDto, SwapRequestRespondDto

router = APIRouter(prefix="/queue", tags=["swap-requests"])


@router.post("/{subject}/swap-request")
async def create_swap_request(
    subject: str,
    data: SwapRequestCreateDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Create a swap proposal from user A to whoever is at to_position, attaching a text message."""
    service = SwapRequestService(db, r)

    result = await service.create_swap_request(
        subject=subject,
        from_tg_id=data.from_tg_id,
        to_position=data.to_position,
        message=data.message,
    )

    result_json = result.model_dump(mode="json")

    # Broadcast to room
    await manager.broadcast(
        subject,
        {
            "event": "swap_request_created",
            "data": result_json,
        },
    )

    # Personal push notification to recipient
    await manager.send_to_user(
        result.to_tg_id,
        {
            "event": "incoming_swap_request",
            "data": result_json,
            "message": f"{result.from_name or 'Пользователь'} предлагает вам поменяться местами (место {result.from_position} ↔ {result.to_position}). Сообщение: {data.message}",
        },
    )

    return {"status": "swap_request_created", "data": result_json}


@router.get("/{subject}/swap-requests/incoming/{tg_id}")
async def get_incoming_swap_requests(
    subject: str,
    tg_id: int,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Get all pending swap requests received by this user in this queue."""
    service = SwapRequestService(db, r)
    return await service.get_incoming_requests(subject, tg_id)


@router.get("/{subject}/swap-requests/outgoing/{tg_id}")
async def get_outgoing_swap_requests(
    subject: str,
    tg_id: int,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Get all pending swap requests sent by this user in this queue."""
    service = SwapRequestService(db, r)
    return await service.get_outgoing_requests(subject, tg_id)


@router.post("/swap-request/{request_id}/accept")
async def accept_swap_request(
    request_id: str,
    data: SwapRequestRespondDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Accept an incoming swap request with an optional response message.
    Positions are immediately swapped and real-time updates broadcast."""
    service = SwapRequestService(db, r)

    result = await service.accept_swap_request(
        request_id=request_id,
        tg_id=data.tg_id,
        message=data.message,
    )

    # Get updated queue state
    queue_service = QueueService(db, r)
    queue_data = await queue_service.get_queue(result.subject)

    result_json = result.model_dump(mode="json")
    queue_json = queue_data.model_dump(mode="json")

    # Broadcast queue update to room
    await manager.broadcast(
        result.subject,
        {
            "event": "swap_request_accepted",
            "swap": result_json,
            "data": queue_json,
        },
    )

    # Personal push notification to sender that their swap was accepted!
    await manager.send_to_user(
        result.from_tg_id,
        {
            "event": "swap_accepted",
            "data": result_json,
            "message": f"{result.to_name or 'Пользователь'} принял ваш запрос на обмен! Ответ: {data.message}",
        },
    )

    return {"status": "accepted", "data": result_json}


@router.post("/swap-request/{request_id}/reject")
async def reject_swap_request(
    request_id: str,
    data: SwapRequestRespondDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Reject an incoming swap request with an optional explanation message."""
    service = SwapRequestService(db, r)

    result = await service.reject_swap_request(
        request_id=request_id,
        tg_id=data.tg_id,
        message=data.message,
    )

    result_json = result.model_dump(mode="json")

    # Broadcast to room
    await manager.broadcast(
        result.subject,
        {
            "event": "swap_request_rejected",
            "data": result_json,
        },
    )

    # Personal push notification to sender that their swap was rejected
    await manager.send_to_user(
        result.from_tg_id,
        {
            "event": "swap_rejected",
            "data": result_json,
            "message": f"{result.to_name or 'Пользователь'} отклонил ваш запрос на обмен. Причина: {data.message}",
        },
    )

    return {"status": "rejected", "data": result_json}


@router.post("/swap-request/{request_id}/cancel")
async def cancel_swap_request(
    request_id: str,
    data: SwapRequestRespondDto,
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Cancel a pending outgoing swap request (sender only)."""
    service = SwapRequestService(db, r)

    result = await service.cancel_swap_request(
        request_id=request_id,
        tg_id=data.tg_id,
    )

    result_json = result.model_dump(mode="json")

    await manager.broadcast(
        result.subject,
        {
            "event": "swap_request_cancelled",
            "data": result_json,
        },
    )

    # Personal notification to the recipient that the request was cancelled
    await manager.send_to_user(
        result.to_tg_id,
        {
            "event": "swap_cancelled",
            "data": result_json,
            "message": "Запрос на обмен был отозван отправителем.",
        },
    )

    return {"status": "cancelled", "data": result_json}
