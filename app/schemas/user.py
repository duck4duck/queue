from pydantic import BaseModel, ConfigDict
from typing import List


class User(BaseModel):
    name: str
    tg_id: int
    photo_url: str | None = None
    role: str = "student"

    model_config = ConfigDict(from_attributes=True)


class UserResponse(User):
    id: int


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: str | None = None
    photo_url: str | None = None
    role: str | None = None

    model_config = ConfigDict(from_attributes=True)
