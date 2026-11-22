from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres.database import get_db
from app.services.subject_service import SubjectService
from app.services.user_service import UserService
from app.api.auth import get_authenticated_tg_id
from app.schemas.subject import Subject, SubjectResponse, ListOfSubjects

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


@router.get("", response_model=ListOfSubjects, status_code=status.HTTP_200_OK)
async def get_all_subjects(
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
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
async def create_subject(
    subject: Subject,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new subject in the catalog (e.g. 'РњР°С‚РµРјР°С‚РёРєР°', 'Р¤РёР·РёРєР°')."""
    await UserService(db).require_curator(authenticated_tg_id)
    service = SubjectService(db)
    return await service.create_subject(subject)


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_subject(
    id: int,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a subject by its ID."""
    await UserService(db).require_curator(authenticated_tg_id)
    service = SubjectService(db)
    return await service.delete_subject(id)


@router.delete("/by-name/{name}", status_code=status.HTTP_200_OK)
async def delete_subject_by_name(
    name: str,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a subject by its exact name."""
    await UserService(db).require_curator(authenticated_tg_id)
    service = SubjectService(db)
    return await service.delete_subject_by_name(name)
