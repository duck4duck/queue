from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.user import User as UserCreate,UserUpdate
from typing import List, Optional
from sqlalchemy import select,delete


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(self) -> List[User]:
        stmt = select(User)
        result = await self.db.execute(stmt)
        users = result.scalars().all()
        return users

    async def get_by_id(self, id: int) -> Optional[User]:
        stmt = select(User).where(User.id == id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        return user

    async def get_by_tg_id(self, tg_id: int) -> Optional[User]:
        stmt = select(User).where(User.tg_id == tg_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        return user

    async def get_by_username(self, username: str):
        stmt = select(User).where(User.name == username)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        return user

    async def create_user(self, user_data: UserCreate) -> User:
        db_user = User(**user_data.model_dump(mode="json"))
        self.db.add(db_user)
        await self.db.commit()
        await self.db.refresh(db_user)
        return db_user
    
    async def update_user_by_tg_id(self,tg_id:int,user_data: UserUpdate):
        stmt = select(User).where(User.tg_id == tg_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        update_data = user_data.model_dump(exclude_unset=True,mode="json")
        for key,value in update_data.items():
            setattr(user,key,value)
        await self.db.commit()
        await self.db.refresh(user)
        return user
    
    async def get_by_tg_ids(self,ids:list[int]):
        stmt = select(User).where(User.tg_id.in_(ids))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_user_by_id(self,id:int,user_data: UserUpdate):
        stmt = select(User).where(User.id == id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        update_data = user_data.model_dump(exclude_unset=True)
        for key,value in update_data.items():
            setattr(user,key,value)
        await self.db.commit()
        await self.db.refresh()
        return user
    

    async def delete_user_by_id(self,id: int):
        stmt = select(User).where(User.id == id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        self.db.delete(user)
        self.db.commit()
        return True
    

    async def delete_user_by_tg_id(self,tg_id: int):
        stmt = select(User).where(User.tg_id == tg_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        self.db.delete(user)
        self.db.commit()
        return True














