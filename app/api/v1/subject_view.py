from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres.database import get_db
from app.services.subject_service import SubjectService
from app.schemas.subject import Subject, SubjectResponse, ListOfSubjects

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


@router.get("", response_model=ListOfSubjects, status_code=status.HTTP_200_OK)
async def get_all_subjects(
    search: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Get the catalog of all available subjects with optional search query."""
    service = SubjectService(db)
    return await service.get_all_subjects(search=search, skip=skip, limit=limit)


@router.get("/{id}", response_model=SubjectResponse, status_code=status.HTTP_200_OK)
async def get_subject_by_id(id: int, db: AsyncSession = Depends(get_db)):
    """Get subject by its database ID."""
    service = SubjectService(db)
    return await service.get_subject_by_id(id)


@router.post("", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(subject: Subject, db: AsyncSession = Depends(get_db)):
    """Create a new subject in the catalog (e.g. 'Математика', 'Физика')."""
    service = SubjectService(db)
    return await service.create_subject(subject)


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_subject(id: int, db: AsyncSession = Depends(get_db)):
    """Delete a subject by its ID."""
    service = SubjectService(db)
    return await service.delete_subject(id)
