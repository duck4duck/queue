from sqlalchemy.ext.asyncio import AsyncSession
from app.models.subject import Subject
from app.schemas.subject import Subject as SubjectCreate
from typing import List, Optional
from sqlalchemy import select


class SubjectRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(self) -> List[Subject]:
        stmt = select(Subject)
        result = await self.db.execute(stmt)
        subjects = result.scalars().all()
        return subjects

    async def get_by_id(self, id: int) -> Optional[Subject]:
        stmt = select(Subject).where(Subject.id == id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        return user

    async def get_by_name(self, name: str):
        stmt = select(Subject).where(Subject.name == name)
        result = await self.db.execute(stmt)
        subject = result.scalar_one_or_none()
        return subject

    async def create_subject(self, subject_data: SubjectCreate):
        db_subject = Subject(**subject_data.model_dump(mode="json"))
        self.db.add(db_subject)
        await self.db.commit()
        await self.db.refresh(db_subject)
        return db_subject

    async def update_subject(self, subject_data: Subject):
        pass
