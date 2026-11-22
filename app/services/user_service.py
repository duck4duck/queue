from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repository import UserRepository
from app.repositories.queue_repository import QueueRepository
from app.repositories.swap_request_repository import SwapRequestRepository
from app.schemas.user import UserResponse, UserListResponse, User, UserUpdate
from app.schemas.exception import UserNotFound, InvalidRole
from app.core.logger import logger
from app.schemas.exception import Forbidden
from redis.asyncio import Redis

VALID_ROLES = {"student", "curator"}


class UserService:
    def __init__(self, db: AsyncSession, r: Redis | None = None):
        self.repository = UserRepository(db)
        self.queue_repository = QueueRepository(r) if r is not None else None
        self.swap_repository = SwapRequestRepository(r) if r is not None else None

    async def _remove_user_from_queues(self, tg_id: int) -> None:
        if self.queue_repository is None or self.swap_repository is None:
            raise RuntimeError("Redis is required to delete a user")
        for subject in await self.queue_repository.get_all_active_queue_keys():
            position = await self.queue_repository.remove_by_user(subject, tg_id)
            if position is None:
                continue
            await self.swap_repository.cancel_all_for_user_in_queue(subject, tg_id)
            await self.queue_repository.log_event(
                subject, "user_deleted", f"Участник #{tg_id} удален из системы"
            )

        pending_requests = await self.swap_repository.get_all_incoming_requests(tg_id)
        pending_requests.extend(await self.swap_repository.get_all_outgoing_requests(tg_id))
        for request_id in {request["id"] for request in pending_requests}:
            await self.swap_repository.update_status(request_id, "cancelled")

    async def get_all_users(
        self,
        search: str | None = None,
        role: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> UserListResponse:
        users = await self.repository.get_all(search=search, role=role, skip=skip, limit=limit)
        user_response = [UserResponse.model_validate(u) for u in users]
        return UserListResponse(users=user_response, total=len(user_response))

    async def get_user_by_id(self, id: int) -> UserResponse:
        user = await self.repository.get_by_id(id=id)
        if user is None:
            raise UserNotFound()
        return UserResponse.model_validate(user)

    async def get_user_by_tg_id(self, tg_id: int) -> UserResponse | None:
        user = await self.repository.get_by_tg_id(tg_id=tg_id)
        if user is None:
            return None
        return UserResponse.model_validate(user)

    async def get_user_by_username(self, username: str) -> UserResponse:
        user = await self.repository.get_by_username(username=username)
        if user is None:
            raise UserNotFound()
        return UserResponse.model_validate(user)

    async def create_user(self, user_data: User) -> dict:
        """Upsert user: creates new user or updates info if tg_id already exists."""
        if user_data.role != "student":
            raise Forbidden("Новая учетная запись создается с ролью студента.")
        user, is_created = await self.repository.upsert_user(user_data=user_data)
        action = "created" if is_created else "updated"
        logger.info(f"User {action}: {user.name} (tg_id={user.tg_id}, role={user.role})")
        return {
            "message": f"user successfully {action}!",
            "id": user.id,
            "tg_id": user.tg_id,
            "role": user.role,
        }

    async def update_user_by_tg_id(self, tg_id: int, user_data: UserUpdate) -> dict:
        if user_data.role is not None:
            raise Forbidden("Изменять роль можно только через административный метод.")
        user = await self.repository.update_user_by_tg_id(tg_id, user_data)
        if user is None:
            raise UserNotFound()
        logger.info(f"User updated: tg_id={tg_id}")
        return {"message": "user successfully updated!"}

    async def set_role(self, tg_id: int, role: str, actor_tg_id: int) -> UserResponse:
        if role not in VALID_ROLES:
            raise InvalidRole()
        actor = await self.repository.get_by_tg_id(actor_tg_id)
        if actor is None:
            raise UserNotFound()
        if actor.role != "curator":
            raise Forbidden("Только куратор может изменять роли пользователей!")
        user = await self.repository.update_user_by_tg_id(tg_id, UserUpdate(role=role))
        if user is None:
            raise UserNotFound()
        logger.info(f"Role updated for tg_id={tg_id}: '{role}'")
        return UserResponse.model_validate(user)

    async def require_curator(self, tg_id: int) -> None:
        user = await self.repository.get_by_tg_id(tg_id)
        if user is None:
            raise UserNotFound()
        if user.role != "curator":
            raise Forbidden("Для этого действия необходима роль куратора.")

    async def delete_user_by_id(self, id: int) -> dict:
        user = await self.repository.get_by_id(id)
        if user is None:
            raise UserNotFound()
        await self._remove_user_from_queues(user.tg_id)
        result = await self.repository.delete_user_by_id(id)
        if not result:
            raise UserNotFound()
        logger.info(f"User deleted: id={id}")
        return {"message": "user successfully deleted!"}

    async def delete_user_by_tg_id(self, tg_id: int) -> dict:
        user = await self.repository.get_by_tg_id(tg_id)
        if user is None:
            raise UserNotFound()
        await self._remove_user_from_queues(user.tg_id)
        result = await self.repository.delete_user_by_tg_id(tg_id)
        if not result:
            raise UserNotFound()
        logger.info(f"User deleted: tg_id={tg_id}")
        return {"message": "user successfully deleted!"}

    async def get_by_tg_ids(self, ids: list[int]) -> list[UserResponse]:
        users = await self.repository.get_by_tg_ids(ids)
        return [UserResponse.model_validate(u) for u in users]
