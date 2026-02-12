from fastapi import APIRouter,status,Depends
from app.schemas.user import UserResponse,User,UserListResponse,UserUpdate
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

@router.get("/{tg_id}",response_model=UserResponse,status_code=status.HTTP_200_OK)
async def get_user(tg_id: int,db: AsyncSession = Depends(get_db)):
    user_service = UserService(db=db)
    return await user_service.get_user_by_tg_id(id=tg_id)


@router.post("/add_user")
async def add_user(user_info:User,db:AsyncSession = Depends(get_db)):
    user_service = UserService(db)
    return await user_service.create_user(user_info)

@router.put("/{tg_id}")
async def update_user(tg_id: int,user_data:UserUpdate,db:AsyncSession = Depends(get_db)):
    user_service = UserService(db)
    return await user_service.update_user_by_tg_id(tg_id,user_data)

@router.delete("/{tg_id}")
async def delete_user(tg_id: int,db: AsyncSession = Depends(get_db)):
    user_service = UserService(db)
    return await user_service.delete_user_by_tg_id(tg_id)


