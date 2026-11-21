from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tg_id: int = Field(gt=0)
    photo_url: str | None = Field(default=None, max_length=2048)
    role: str = "student"

    model_config = ConfigDict(from_attributes=True)


class UserResponse(User):
    id: int


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    photo_url: str | None = Field(default=None, max_length=2048)
    role: str | None = None

    model_config = ConfigDict(from_attributes=True)
