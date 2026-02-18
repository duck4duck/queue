from pydantic import BaseModel,HttpUrl,ConfigDict
from typing import List


class User(BaseModel):
    name: str
    tg_id: int
    photo_url: HttpUrl | None = None

    model_config = ConfigDict(from_attributes=True)

class QueueUser(User):
    position: str | None = None


class Queue(BaseModel):
    subject: str
    users:List[QueueUser]
    total: int


class ListOfQueueUser(BaseModel):
    users: List[QueueUser]
    total: int

    model_config = ConfigDict(from_attributes=True)


class UserResponse(User):
    id: int 


class UserListResponse(BaseModel):
    users:List[UserResponse]
    total: int 

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: str | None = None
    photo_url: HttpUrl | None = None

    model_config = ConfigDict(from_attributes=True)

