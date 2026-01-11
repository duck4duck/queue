from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.user import User as UserCreate
from typing import List, Optional
from sqlalchemy import select


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
        db_user = User(**user_data.model_dump())
        self.db.add(db_user)
        await self.db.commit()
        await self.db.refresh(db_user)
        return db_user
