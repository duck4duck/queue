from pydantic import BaseModel


class UserDto(BaseModel):
    tg_id: int
    position:int 


class SwapDto(BaseModel):
    position1: int
    position2: int