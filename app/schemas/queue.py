from enum import Enum
from pydantic import BaseModel,HttpUrl,ConfigDict



class QueueActionType(str,Enum):
    JOIN = "join"
    LEAVE = "leave"
    SWAP = "swap"
    GET = "get"

class QueueUserInfo(BaseModel):
    action: QueueActionType
    name: str
    tg_id: int | None = None
    target_tg_id: int | None = None
    position: int | None = None
    photo_url: HttpUrl | None = None
    is_free: bool

    model_config = ConfigDict(from_attributes=True)



class QueueResponse(BaseModel):
    subject: str
    queue: list[QueueUserInfo]
    total_positions: int
    taken_positions: int

    model_config = ConfigDict(from_attributes=True)
