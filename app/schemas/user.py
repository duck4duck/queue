from pydantic import BaseModel,HttpUrl

class User(BaseModel):
    name: str
    tg_id: int
    photo_url: HttpUrl | None = None


class UserResponse(User):
    id: int 