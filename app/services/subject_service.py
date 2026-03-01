from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.subject_repository import SubjectRepository
from typing import List,Optional
from app.schemas.subject import SubjectResponse,Subject,ListOfSubjects


class SubjectService:
    def __init__(self,db:AsyncSession):
        self.repository = SubjectRepository(db)

    async def get_all_subjects(self) -> List[SubjectResponse]:
        subjects = await self.repository.get_all()
        subject_response = [SubjectResponse.model_validate(s) for s in subjects]

        return ListOfSubjects(subject_list=subject_response,total=len(subject_response))
    
    async def get_subject_by_id(self,id:int) -> SubjectResponse:
        subject = await self.repository.get_by_id(id=id)
        return SubjectResponse.model_validate(subject)
    
    async def get_subject_by_name(self,name: str) -> SubjectResponse:
        subject = await self.repository.get_by_name(name=name)
        return SubjectResponse.model_validate(subject)
    
    async def create_subject(self,subject_data:Subject):
        subject = self.repository.create_subject(subject_data=subject_data)
        return {"message":"subject succefully created"}
        