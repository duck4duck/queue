from sqlalchemy.ext.asyncio import AsyncSession
from app.models.subject import Subject
from app.schemas.subject import Subject as SubjectCreate
from sqlalchemy import select


class SubjectRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(
        self,
        search: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Subject]:
        stmt = select(Subject)
        if search:
            stmt = stmt.where(Subject.name.ilike(f"%{search}%"))
        stmt = stmt.offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, id: int) -> Subject | None:
        stmt = select(Subject).where(Subject.id == id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Subject | None:
        stmt = select(Subject).where(Subject.name == name)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_subject(self, subject_data: SubjectCreate) -> Subject:
        db_subject = Subject(name=subject_data.name)
        self.db.add(db_subject)
        await self.db.commit()
        await self.db.refresh(db_subject)
        return db_subject

    async def delete_subject(self, id: int) -> bool:
        stmt = select(Subject).where(Subject.id == id)
        result = await self.db.execute(stmt)
        subject = result.scalar_one_or_none()
        if subject is None:
            return False
        await self.db.delete(subject)
        await self.db.commit()
        return True
