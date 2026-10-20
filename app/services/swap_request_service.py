from app.repositories.queue_repository import QueueRepository
from app.repositories.swap_request_repository import SwapRequestRepository
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.core.logger import logger
from app.schemas.exception import (
    UserNotFound,
    UserNotInQueue,
    SwapRequestNotFound,
    SwapRequestAlreadyExists,
    SwapRequestExpired,
    InvalidPosition,
    PositionEmpty,
    Forbidden,
    QueuePaused,
)
from app.schemas.swap_request import SwapRequestInfo, SwapRequestListResponse


class SwapRequestService:
    def __init__(self, db: AsyncSession, r: Redis):
        self.user_service = UserService(db)
        self.queue_repo = QueueRepository(r)
        self.swap_repo = SwapRequestRepository(r)

    async def create_swap_request(
        self,
        subject: str,
        from_tg_id: int,
        to_position: int,
        message: str = "",
    ) -> SwapRequestInfo:
        """Create a swap proposal from from_tg_id to whoever is at to_position, attaching a text message."""
        if await self.queue_repo.is_queue_paused(subject):
            raise QueuePaused("Очередь приостановлена! Обмен временно недоступен.")

        from_user = await self.user_service.get_user_by_tg_id(from_tg_id)
        if from_user is None:
            raise UserNotFound("Пользователь не найден!")

        if not await self.queue_repo.is_user_in_queue(subject, from_tg_id):
            raise UserNotInQueue("Вы не состоите в этой очереди!")

        from_position = await self.queue_repo.get_position(subject, from_tg_id)
        if from_position is None:
            raise UserNotInQueue("Не удалось определить вашу позицию в очереди!")

        if from_position == to_position:
            raise InvalidPosition("Нельзя обменяться с самим собой!")

        to_tg_id = await self.queue_repo.get_user_at_position(subject, to_position)
        if to_tg_id is None:
            raise PositionEmpty(f"На позиции {to_position} никого нет!")

        to_user = await self.user_service.get_user_by_tg_id(to_tg_id)
        if to_user is None:
            raise UserNotFound("Пользователь на целевой позиции не найден!")

        if await self.swap_repo.has_pending_outgoing(subject, from_tg_id):
            raise SwapRequestAlreadyExists(
                "У вас уже есть активный запрос на обмен в этой очереди! Дождитесь ответа или отмените его."
            )

        request_id = await self.swap_repo.create(
            subject=subject,
            from_tg_id=from_tg_id,
            to_tg_id=to_tg_id,
            from_position=from_position,
            to_position=to_position,
            message=message,
        )

        logger.info(
            f"Swap proposal created in '{subject}': {from_user.name} (#{from_position}) -> "
            f"{to_user.name} (#{to_position}). Msg: '{message}'"
        )

        created_data = await self.swap_repo.get(request_id)
        created_at = created_data.get("created_at", "") if created_data else ""

        return SwapRequestInfo(
            id=request_id,
            subject=subject,
            from_tg_id=from_tg_id,
            to_tg_id=to_tg_id,
            from_position=from_position,
            to_position=to_position,
            from_name=from_user.name,
            to_name=to_user.name,
            message=message,
            status="pending",
            created_at=created_at,
        )

    async def accept_swap_request(
        self, request_id: str, tg_id: int, message: str = ""
    ) -> SwapRequestInfo:
        """Accept an incoming swap request. Swaps positions in Redis immediately."""
        data = await self.swap_repo.get(request_id)
        if data is None:
            raise SwapRequestNotFound("Запрос на обмен не найден или срок его действия истёк!")

        if data["status"] != "pending":
            raise SwapRequestExpired(f"Запрос уже обработан (статус: {data['status']})")

        to_tg_id = int(data["to_tg_id"])
        if tg_id != to_tg_id:
            raise Forbidden("Только адресат запроса может принять обмен!")

        subject = data["subject"]
        if await self.queue_repo.is_queue_paused(subject):
            raise QueuePaused("Очередь приостановлена! Обмен временно недоступен.")

        from_tg_id = int(data["from_tg_id"])
        from_position = int(data["from_position"])
        to_position = int(data["to_position"])

        # Validate users are still at their respective positions
        current_from_pos = await self.queue_repo.get_position(subject, from_tg_id)
        current_to_pos = await self.queue_repo.get_position(subject, to_tg_id)

        if current_from_pos != from_position or current_to_pos != to_position:
            await self.swap_repo.update_status(request_id, "expired")
            logger.warning(
                f"Swap request {request_id} expired: positions changed (expected #{from_position}/#{to_position}, "
                f"found #{current_from_pos}/#{current_to_pos})"
            )
            raise SwapRequestExpired(
                "Позиции участников изменились с момента отправки запроса. Запрос аннулирован."
            )

        # Execute the swap
        await self.queue_repo.swap(subject, from_position, to_position)
        await self.swap_repo.update_status(request_id, "accepted", message)

        from_user = await self.user_service.get_user_by_tg_id(from_tg_id)
        to_user = await self.user_service.get_user_by_tg_id(to_tg_id)
        from_name = from_user.name if from_user else f"ID {from_tg_id}"
        to_name = to_user.name if to_user else f"ID {to_tg_id}"

        await self.queue_repo.log_event(
            subject,
            "swap",
            f"Обмен подтверждён: {from_name} и {to_name} поменялись местами (#{from_position} ↔ #{to_position})",
        )
        logger.info(f"Swap request {request_id} accepted in '{subject}': {from_name} ↔ {to_name}")

        return SwapRequestInfo(
            id=request_id,
            subject=subject,
            from_tg_id=from_tg_id,
            to_tg_id=to_tg_id,
            from_position=to_position,
            to_position=from_position,
            from_name=from_name,
            to_name=to_name,
            message=data.get("message", ""),
            status="accepted",
            response_message=message,
            created_at=data.get("created_at", ""),
        )

    async def reject_swap_request(
        self, request_id: str, tg_id: int, message: str = ""
    ) -> SwapRequestInfo:
        """Reject an incoming swap request with an optional explanation message."""
        data = await self.swap_repo.get(request_id)
        if data is None:
            raise SwapRequestNotFound("Запрос на обмен не найден или срок его действия истёк!")

        if data["status"] != "pending":
            raise SwapRequestExpired(f"Запрос уже обработан (статус: {data['status']})")

        to_tg_id = int(data["to_tg_id"])
        if tg_id != to_tg_id:
            raise Forbidden("Только адресат запроса может отклонить обмен!")

        await self.swap_repo.update_status(request_id, "rejected", message)

        from_tg_id = int(data["from_tg_id"])
        from_user = await self.user_service.get_user_by_tg_id(from_tg_id)
        to_user = await self.user_service.get_user_by_tg_id(to_tg_id)

        logger.info(f"Swap request {request_id} rejected by tg_id={tg_id}. Msg: '{message}'")

        return SwapRequestInfo(
            id=request_id,
            subject=data["subject"],
            from_tg_id=from_tg_id,
            to_tg_id=to_tg_id,
            from_position=int(data["from_position"]),
            to_position=int(data["to_position"]),
            from_name=from_user.name if from_user else None,
            to_name=to_user.name if to_user else None,
            message=data.get("message", ""),
            status="rejected",
            response_message=message,
            created_at=data.get("created_at", ""),
        )

    async def cancel_swap_request(
        self, request_id: str, tg_id: int
    ) -> SwapRequestInfo:
        """Cancel a pending outgoing swap request (sender only)."""
        data = await self.swap_repo.get(request_id)
        if data is None:
            raise SwapRequestNotFound("Запрос на обмен не найден или срок его действия истёк!")

        if data["status"] != "pending":
            raise SwapRequestExpired(f"Запрос уже обработан (статус: {data['status']})")

        from_tg_id = int(data["from_tg_id"])
        if tg_id != from_tg_id:
            raise Forbidden("Только отправитель может отменить свой запрос на обмен!")

        await self.swap_repo.update_status(request_id, "cancelled")
        await self.swap_repo.delete(request_id)

        logger.info(f"Swap request {request_id} cancelled by sender tg_id={tg_id}")

        return SwapRequestInfo(
            id=request_id,
            subject=data["subject"],
            from_tg_id=from_tg_id,
            to_tg_id=int(data["to_tg_id"]),
            from_position=int(data["from_position"]),
            to_position=int(data["to_position"]),
            message=data.get("message", ""),
            status="cancelled",
            created_at=data.get("created_at", ""),
        )

    async def get_incoming_requests(
        self, subject: str, tg_id: int
    ) -> SwapRequestListResponse:
        requests = await self.swap_repo.get_incoming_requests(subject, tg_id)
        result = []
        for req in requests:
            from_user = await self.user_service.get_user_by_tg_id(int(req["from_tg_id"]))
            to_user = await self.user_service.get_user_by_tg_id(int(req["to_tg_id"]))
            result.append(
                SwapRequestInfo(
                    id=req["id"],
                    subject=req["subject"],
                    from_tg_id=int(req["from_tg_id"]),
                    to_tg_id=int(req["to_tg_id"]),
                    from_position=int(req["from_position"]),
                    to_position=int(req["to_position"]),
                    from_name=from_user.name if from_user else None,
                    to_name=to_user.name if to_user else None,
                    message=req.get("message", ""),
                    status=req["status"],
                    created_at=req.get("created_at", ""),
                )
            )
        return SwapRequestListResponse(requests=result, total=len(result))

    async def get_outgoing_requests(
        self, subject: str, tg_id: int
    ) -> SwapRequestListResponse:
        requests = await self.swap_repo.get_outgoing_requests(subject, tg_id)
        result = []
        for req in requests:
            from_user = await self.user_service.get_user_by_tg_id(int(req["from_tg_id"]))
            to_user = await self.user_service.get_user_by_tg_id(int(req["to_tg_id"]))
            result.append(
                SwapRequestInfo(
                    id=req["id"],
                    subject=req["subject"],
                    from_tg_id=int(req["from_tg_id"]),
                    to_tg_id=int(req["to_tg_id"]),
                    from_position=int(req["from_position"]),
                    to_position=int(req["to_position"]),
                    from_name=from_user.name if from_user else None,
                    to_name=to_user.name if to_user else None,
                    message=req.get("message", ""),
                    status=req["status"],
                    created_at=req.get("created_at", ""),
                )
            )
        return SwapRequestListResponse(requests=result, total=len(result))
