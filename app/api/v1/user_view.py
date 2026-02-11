from fastapi import APIRouter,status,Depends
from app.schemas.user import UserResponse,User,UserListResponse
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres.database import get_db
from app.services.user_service import UserService

router = APIRouter(
    prefix="/api/users",
    tags=["users"]
)

@router.get("",response_model=UserListResponse,status_code=status.HTTP_200_OK)
async def get_users(db: AsyncSession = Depends(get_db)):
    user_service = UserService(db=db)
    return await user_service.get_all_users()

@router.get("/{user_id}",response_model=UserResponse,status_code=status.HTTP_200_OK)
async def get_user(user_id: int,db: AsyncSession = Depends(get_db)):
    user_service = UserService(db=db)
    return await user_service.get_user_by_id(id=user_id)


@router.post("/add_user")
async def add_user(user_info:User,db:AsyncSession = Depends(get_db)):
    user_service = UserService(db)
    return await user_service.create_user(user_info)


