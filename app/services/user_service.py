from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repository import UserRepository
from typing import List,Optional
from app.schemas.user import UserResponse,UserListResponse,User,UserUpdate


class UserService:
    def __init__(self, db: AsyncSession):
        self.repository = UserRepository(db)

    async def get_all_users(self) -> List[UserResponse]:
        users = await self.repository.get_all()
        user_response = [UserResponse.model_validate(u) for u in users]

        return UserListResponse(users=user_response,total=len(user_response))

    async def get_user_by_id(self,id: int) -> UserResponse:
        user = await self.repository.get_by_id(id=id)
        return UserResponse.model_validate(user)
    
    async def get_user_by_tg_id(self,tg_id: int) -> UserResponse:
        user = await self.repository.get_by_tg_id(tg_id=tg_id)
        return UserResponse.model_validate(user)
    
    async def get_user_by_username(self,username: str) -> UserResponse:
        user = await self.repository.get_by_username(username=username)
        return UserResponse.model_validate(user)
    
    async def create_user(self,user_data:User):
        user = await self.repository.create_user(user_data=user_data)
        return {"message":"user sucessfully added!"}

    async def update_user_by_tg_id(self,tg_id: int,user_data: UserUpdate):
        user = await self.repository.update_user_by_tg_id(tg_id,user_data)
        return {"message":"user succefully updated!"}
    
    async def update_user_by_id(self,id: int,user_data: UserUpdate):
        user = await self.repository.update_user_by_id(id,user_data)
        return {"message":"user succefully updated!"}
    
    async def delete_user_by_id(self,id: int):
        user = await self.repository.delete_user_by_id(id)
        return {"message":"user succefully deleted!"}
    
    async def delete_user_by_tg_id(self,id: int):
        user = await self.repository.delete_user_by_tg_id(id)
        return {"message":"user succefully deleted!"}
    
    async def get_by_tg_ids(self,ids:list[int]) -> list[User]:
        users = await self.repository.get_by_tg_ids(ids)
        return users