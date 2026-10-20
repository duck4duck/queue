from fastapi import APIRouter, status, Depends
from app.schemas.user import UserResponse, User, UserListResponse, UserUpdate
from app.schemas.dto import SetRoleDto
from app.schemas.exception import UserNotFound
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres.database import get_db
from app.services.user_service import UserService

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=UserListResponse, status_code=status.HTTP_200_OK)
async def get_users(
    search: str | None = None,
    role: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Get list of users with optional search and role filtering."""
    user_service = UserService(db=db)
    return await user_service.get_all_users(search=search, role=role, skip=skip, limit=limit)


@router.get("/{tg_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_user(tg_id: int, db: AsyncSession = Depends(get_db)):
    user_service = UserService(db=db)
    user = await user_service.get_user_by_tg_id(tg_id=tg_id)
    if user is None:
        raise UserNotFound("Пользователь не найден!")
    return user


@router.post("/add_user")
async def add_user(user_info: User, db: AsyncSession = Depends(get_db)):
    user_service = UserService(db)
    return await user_service.create_user(user_info)


@router.put("/{tg_id}")
async def update_user(
    tg_id: int, user_data: UserUpdate, db: AsyncSession = Depends(get_db)
):
    user_service = UserService(db)
    return await user_service.update_user_by_tg_id(tg_id, user_data)


@router.patch("/{tg_id}/role", response_model=UserResponse)
async def set_user_role(
    tg_id: int, role_data: SetRoleDto, db: AsyncSession = Depends(get_db)
):
    """Set role for user: 'student' or 'curator'."""
    user_service = UserService(db)
    return await user_service.set_role(tg_id, role_data.role)


@router.delete("/{tg_id}")
async def delete_user(tg_id: int, db: AsyncSession = Depends(get_db)):
    user_service = UserService(db)
    return await user_service.delete_user_by_tg_id(tg_id)
