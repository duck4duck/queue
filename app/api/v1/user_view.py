from fastapi import APIRouter, status, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.schemas.user import UserResponse, User, UserListResponse, UserUpdate
from app.schemas.dto import SetRoleDto
from app.schemas.exception import UserNotFound
from app.db.postgres.database import get_db
from app.services.user_service import UserService
from app.api.auth import get_authenticated_tg_id, require_actor
from app.db.redis.redis_client import get_redis

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=UserListResponse, status_code=status.HTTP_200_OK)
async def get_users(
    search: str | None = None,
    role: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get list of users with optional search and role filtering."""
    user_service = UserService(db=db)
    return await user_service.get_all_users(search=search, role=role, skip=skip, limit=limit)


@router.get("/{tg_id}", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_user(tg_id: int, db: AsyncSession = Depends(get_db)):
    """Get user by Telegram ID."""
    user_service = UserService(db=db)
    user = await user_service.get_user_by_tg_id(tg_id=tg_id)
    if user is None:
        raise UserNotFound()
    return user


@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/add_user", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_or_update_user(
    user_info: User,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
):
    """Upsert user (creates if new, updates name/photo if existing)."""
    require_actor(user_info.tg_id, authenticated_tg_id)
    user_service = UserService(db=db)
    return await user_service.create_user(user_info)


@router.put("/{tg_id}")
async def update_user(
    tg_id: int,
    user_data: UserUpdate,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
):
    """Update user information."""
    require_actor(tg_id, authenticated_tg_id)
    user_service = UserService(db=db)
    return await user_service.update_user_by_tg_id(tg_id, user_data)


@router.patch("/{tg_id}/role", response_model=UserResponse)
async def set_user_role(
    tg_id: int,
    role_data: SetRoleDto,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
):
    """Set role for user: 'student' or 'curator'."""
    user_service = UserService(db=db)
    return await user_service.set_role(tg_id, role_data.role, authenticated_tg_id)


@router.delete("/{tg_id}")
async def delete_user(
    tg_id: int,
    authenticated_tg_id: int = Depends(get_authenticated_tg_id),
    db: AsyncSession = Depends(get_db),
    r: Redis = Depends(get_redis),
):
    """Delete user by Telegram ID."""
    user_service = UserService(db=db, r=r)
    await user_service.require_curator(authenticated_tg_id)
    return await user_service.delete_user_by_tg_id(tg_id)
