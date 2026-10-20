from pydantic import BaseModel, ConfigDict
from typing import List


class QueueUserInfo(BaseModel):
    name: str | None = None
    tg_id: int | None = None
    position: int
    target_position: int | None = None
    photo_url: str | None = None
    is_free: bool

    model_config = ConfigDict(from_attributes=True)


class QueueResponse(BaseModel):
    subject: str
    queue: list[QueueUserInfo]
    total_positions: int
    taken_positions: int
    is_paused: bool = False

    model_config = ConfigDict(from_attributes=True)


class QueueMetaInfo(BaseModel):
    subject: str
    subject_name: str
    queue_type: str
    created_by_tg_id: int
    created_by_name: str | None = None
    created_at: str
    taken_positions: int = 0
    total_positions: int = 30
    is_paused: bool = False

    model_config = ConfigDict(from_attributes=True)


class QueueListResponse(BaseModel):
    queues: list[QueueMetaInfo]
    total: int

    model_config = ConfigDict(from_attributes=True)


class MyPositionResponse(BaseModel):
    in_queue: bool
    subject: str
    position: int | None = None
    people_ahead: int = 0
    is_next: bool = False
    estimated_wait_minutes: int = 0

    model_config = ConfigDict(from_attributes=True)


class SwapCandidate(BaseModel):
    position: int
    tg_id: int
    name: str
    photo_url: str | None = None
    slots_difference: int

    model_config = ConfigDict(from_attributes=True)


class QueueStatsResponse(BaseModel):
    subject: str
    total_positions: int
    taken_positions: int
    free_positions: int
    occupancy_percent: float
    is_paused: bool
    active_swap_requests: int

    model_config = ConfigDict(from_attributes=True)
