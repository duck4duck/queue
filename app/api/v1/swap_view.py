import json
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.db.postgres.database import get_db
from app.db.redis.redis_client import get_redis
from app.api.auth import get_authenticated_tg_id, require_actor
from app.api.ws_manager import manager
from app.services.swap_request_service import SwapRequestService
from app.services.queue_service import QueueService
from app.schemas.dto import SwapRequestCreateDto, SwapRequestRespondDto, SwapRequestCancelDto

router = APIRouter(prefix="/queue", tags=["swap-requests"])


@router.post("/{subject}/swap-request")
async def create_swap_request(
    subject: str,
    data: SwapRequestCreateDto,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    require_actor(data.from_tg_id, authenticated_tg_id)
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
            "subject": subject,
            "data": result_json | {"message": "", "response_message": ""},
        },
    )

    # Personal push notification to recipient
    note = f' "{data.message}"' if data.message else ""
    await manager.send_to_user(
        result.to_tg_id,
        {
            "event": "incoming_swap_request",
            "data": result_json,
            "message": f"{result.from_name or 'Пользователь'} предлагает обмен (место {result.from_position} ↔ {result.to_position}){note}",
        },
    )
    queue_meta = await service.queue_repo.get_queue_meta(result.subject) or {}
    await r.publish("queue_events", json.dumps({
        "type": "swap_request",
        "to_tg_id": result.to_tg_id,
        "from_name": result.from_name,
        "subject": result.subject,
        "subject_name": queue_meta.get("subject_name"),
        "queue_type": queue_meta.get("queue_type"),
        "from_position": result.from_position,
        "to_position": result.to_position,
        "message": result.message,
    }))

    return {"status": "swap_request_created", "data": result_json}


@router.get("/{subject}/swap-requests/incoming/{tg_id}")
async def get_incoming_swap_requests(
    subject: str,
    tg_id: int,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    require_actor(tg_id, authenticated_tg_id)
    """Get all pending swap requests received by this user in this queue (or all queues if subject=='all')."""
    service = SwapRequestService(db, r)
    if subject == "all":
        return await service.get_all_incoming_requests(tg_id)
    return await service.get_incoming_requests(subject, tg_id)


@router.get("/{subject}/swap-requests/outgoing/{tg_id}")
async def get_outgoing_swap_requests(
    subject: str,
    tg_id: int,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    require_actor(tg_id, authenticated_tg_id)
    """Get all pending swap requests sent by this user in this queue (or all queues if subject=='all')."""
    service = SwapRequestService(db, r)
    if subject == "all":
        return await service.get_all_outgoing_requests(tg_id)
    return await service.get_outgoing_requests(subject, tg_id)


@router.post("/swap-request/{request_id}/accept")
async def accept_swap_request(
    request_id: str,
    data: SwapRequestRespondDto,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    require_actor(data.tg_id, authenticated_tg_id)
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

    # Broadcast queue update to room and all users
    event_swap = {
        "event": "swap_request_accepted",
        "subject": result.subject,
        "swap": result_json | {"message": "", "response_message": ""},
        "data": queue_json,
    }
    await manager.broadcast_room_and_all(result.subject, event_swap)

    # Personal push notification to sender that their swap was accepted!
    await manager.send_to_user(
        result.from_tg_id,
        {
            "event": "swap_accepted",
            "subject": result.subject,
            "data": result_json,
            "message": f"{result.to_name or 'Пользователь'} принял ваш запрос на обмен!",
        },
    )

    return {"status": "accepted", "data": result_json}


@router.post("/swap-request/{request_id}/reject")
async def reject_swap_request(
    request_id: str,
    data: SwapRequestRespondDto,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    require_actor(data.tg_id, authenticated_tg_id)
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
            "subject": result.subject,
            "data": result_json | {"message": "", "response_message": ""},
        },
    )

    # Personal push notification to sender that their swap was rejected
    await manager.send_to_user(
        result.from_tg_id,
        {
            "event": "swap_rejected",
            "subject": result.subject,
            "data": result_json,
            "message": f"{result.to_name or 'Пользователь'} отклонил ваш запрос на обмен",
        },
    )

    return {"status": "rejected", "data": result_json}


@router.post("/swap-request/{request_id}/cancel")
async def cancel_swap_request(
    request_id: str,
    data: SwapRequestCancelDto,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    require_actor(data.tg_id, authenticated_tg_id)
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
            "subject": result.subject,
            "data": result_json | {"message": "", "response_message": ""},
        },
    )

    # Personal notification to the recipient that the request was cancelled
    await manager.send_to_user(
        result.to_tg_id,
        {
            "event": "swap_cancelled",
            "subject": result.subject,
            "data": result_json,
            "message": "Запрос на обмен был отозван отправителем.",
        },
    )

    return {"status": "cancelled", "data": result_json}
