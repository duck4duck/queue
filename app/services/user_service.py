from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repository import UserRepository
from typing import List,Optional
from app.schemas.user import UserResponse

class UserService:
    def __init__(self, db: AsyncSession):
        self.repository = UserRepository(db)

    async def get_all_users(self) -> List[UserResponse]:
        users = await self.repository.get_all()
        return [UserResponse.model_validate(u) for u in users]

    async def get_user_by_id(self,id: int) -> UserResponse:
        user = await self.repository.get_by_id(id=id)
        return UserResponse.model_validate(user)
    
    async def get_user_by_tg_id(self,tg_id: int) -> UserResponse:
        user = await self.repository.get_by_tg_id(tg_id=tg_id)
        return UserResponse.model_validate(user)
    
    async def get_user_by_tg_id(self,username: str) -> UserResponse:
        user = await self.repository.get_by_username(username=username)
        return UserResponse.model_validate(user)