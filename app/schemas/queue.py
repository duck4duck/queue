from enum import Enum
from pydantic import BaseModel, HttpUrl, ConfigDict


class QueueUserInfo(BaseModel):
    name: str | None = None
    position: int | None = None
    target_position: int | None = None
    position: int
    photo_url: HttpUrl | None = None
    is_free: bool

    model_config = ConfigDict(from_attributes=True)


class QueueResponse(BaseModel):
    subject: str
    queue: list[QueueUserInfo]
    total_positions: int
    taken_positions: int

    model_config = ConfigDict(from_attributes=True)
