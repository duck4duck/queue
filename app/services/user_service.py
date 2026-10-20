from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repository import UserRepository
from typing import List, Optional
from app.schemas.user import UserResponse, UserListResponse, User, UserUpdate
from app.schemas.exception import UserNotFound, InvalidRole
from app.core.logger import logger

VALID_ROLES = {"student", "curator"}


class UserService:
    def __init__(self, db: AsyncSession):
        self.repository = UserRepository(db)

    async def get_all_users(
        self,
        search: Optional[str] = None,
        role: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> UserListResponse:
        users = await self.repository.get_all(search=search, role=role, skip=skip, limit=limit)
        user_response = [UserResponse.model_validate(u) for u in users]
        return UserListResponse(users=user_response, total=len(user_response))

    async def get_user_by_id(self, id: int) -> UserResponse:
        user = await self.repository.get_by_id(id=id)
        if user is None:
            raise UserNotFound("Пользователь не найден!")
        return UserResponse.model_validate(user)

    async def get_user_by_tg_id(self, tg_id: int) -> Optional[UserResponse]:
        user = await self.repository.get_by_tg_id(tg_id=tg_id)
        if user is None:
            return None
        return UserResponse.model_validate(user)

    async def get_user_by_username(self, username: str) -> UserResponse:
        user = await self.repository.get_by_username(username=username)
        if user is None:
            raise UserNotFound("Пользователь не найден!")
        return UserResponse.model_validate(user)

    async def create_user(self, user_data: User) -> dict:
        """Upsert user: creates new user or updates info if tg_id already exists."""
        if user_data.role not in VALID_ROLES:
            raise InvalidRole()
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
        if user_data.role is not None and user_data.role not in VALID_ROLES:
            raise InvalidRole()
        user = await self.repository.update_user_by_tg_id(tg_id, user_data)
        if user is None:
            raise UserNotFound("Пользователь не найден!")
        logger.info(f"User updated: tg_id={tg_id}")
        return {"message": "user successfully updated!"}

    async def update_user_by_id(self, id: int, user_data: UserUpdate) -> dict:
        if user_data.role is not None and user_data.role not in VALID_ROLES:
            raise InvalidRole()
        user = await self.repository.update_user_by_id(id, user_data)
        if user is None:
            raise UserNotFound("Пользователь не найден!")
        logger.info(f"User updated: id={id}")
        return {"message": "user successfully updated!"}

    async def set_role(self, tg_id: int, role: str) -> UserResponse:
        if role not in VALID_ROLES:
            raise InvalidRole()
        user = await self.repository.update_user_by_tg_id(tg_id, UserUpdate(role=role))
        if user is None:
            raise UserNotFound("Пользователь не найден!")
        logger.info(f"Role updated for tg_id={tg_id}: '{role}'")
        return UserResponse.model_validate(user)

    async def delete_user_by_id(self, id: int) -> dict:
        result = await self.repository.delete_user_by_id(id)
        if not result:
            raise UserNotFound("Пользователь не найден!")
        logger.info(f"User deleted: id={id}")
        return {"message": "user successfully deleted!"}

    async def delete_user_by_tg_id(self, id: int) -> dict:
        result = await self.repository.delete_user_by_tg_id(id)
        if not result:
            raise UserNotFound("Пользователь не найден!")
        logger.info(f"User deleted: tg_id={id}")
        return {"message": "user successfully deleted!"}

    async def get_by_tg_ids(self, ids: list[int]):
        return await self.repository.get_by_tg_ids(ids)
