from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.subject_repository import SubjectRepository
from typing import List
from app.schemas.subject import SubjectResponse, Subject, ListOfSubjects
from app.schemas.exception import SubjectNotFound, SubjectAlreadyExists


class SubjectService:
    def __init__(self, db: AsyncSession):
        self.repository = SubjectRepository(db)

    async def get_all_subjects(
        self,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> ListOfSubjects:
        subjects = await self.repository.get_all(search=search, skip=skip, limit=limit)
        subject_response = [SubjectResponse.model_validate(s) for s in subjects]
        return ListOfSubjects(
            subject_list=subject_response, total=len(subject_response)
        )

    async def get_subject_by_id(self, id: int) -> SubjectResponse:
        subject = await self.repository.get_by_id(id=id)
        if subject is None:
            raise SubjectNotFound(f"Предмет с id={id} не найден!")
        return SubjectResponse.model_validate(subject)

    async def get_subject_by_name(self, name: str) -> SubjectResponse:
        subject = await self.repository.get_by_name(name=name)
        if subject is None:
            raise SubjectNotFound(f"Предмет '{name}' не найден!")
        return SubjectResponse.model_validate(subject)

    async def create_subject(self, subject_data: Subject) -> SubjectResponse:
        existing = await self.repository.get_by_name(subject_data.name)
        if existing:
            raise SubjectAlreadyExists(f"Предмет '{subject_data.name}' уже существует!")
        subject = await self.repository.create_subject(subject_data=subject_data)
        return SubjectResponse.model_validate(subject)

    async def delete_subject(self, id: int) -> dict:
        deleted = await self.repository.delete_subject(id)
        if not deleted:
            raise SubjectNotFound(f"Предмет с id={id} не найден!")
        return {"message": "subject successfully deleted"}
