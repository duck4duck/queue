from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.schemas.user import User as UserCreate, UserUpdate
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(
        self,
        search: str | None = None,
        role: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        stmt = select(User)
        if search:
            stmt = stmt.where(User.name.ilike(f"%{search}%"))
        if role:
            stmt = stmt.where(User.role == role)
        stmt = stmt.order_by(User.id).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, id: int) -> User | None:
        stmt = select(User).where(User.id == id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_tg_id(self, tg_id: int) -> User | None:
        stmt = select(User).where(User.tg_id == tg_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.name == username).order_by(User.id).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_user(self, user_data: UserCreate) -> tuple[User, bool]:
        """Creates user or updates name/photo if tg_id already exists.
        Returns (user, is_created)."""
        stmt = insert(User).values(**user_data.model_dump(mode="json"))
        create = stmt.on_conflict_do_nothing(index_elements=[User.tg_id]).returning(User)
        fields = user_data.model_dump(include={"name", "photo_url"}, exclude_none=True)
        update_existing = (
            update(User).where(User.tg_id == user_data.tg_id).values(**fields).returning(User)
        )
        while True:
            db_user = (await self.db.execute(create)).scalar_one_or_none()
            if db_user is not None:
                await self.db.commit()
                return db_user, True
            db_user = (await self.db.execute(update_existing)).scalar_one_or_none()
            if db_user is not None:
                await self.db.commit()
                return db_user, False
            # A concurrent delete removed the conflicting record. Retry the insert.

    async def update_user_by_tg_id(self, tg_id: int, user_data: UserUpdate) -> User | None:
        stmt = select(User).where(User.tg_id == tg_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return None
        fields = user_data.model_dump(exclude_unset=True, mode="json")
        for field in ("name", "role"):
            if fields.get(field) is None:
                fields.pop(field, None)
        for key, value in fields.items():
            setattr(user, key, value)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_by_tg_ids(self, ids: list[int]) -> list[User]:
        stmt = select(User).where(User.tg_id.in_(ids))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_user_by_id(self, id: int) -> bool:
        stmt = select(User).where(User.id == id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return False
        await self.db.delete(user)
        await self.db.commit()
        return True

    async def delete_user_by_tg_id(self, tg_id: int) -> bool:
        stmt = select(User).where(User.tg_id == tg_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return False
        await self.db.delete(user)
        await self.db.commit()
        return True
