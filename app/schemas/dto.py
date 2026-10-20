from pydantic import BaseModel


class UserDto(BaseModel):
    tg_id: int
    position: int


class SwapDto(BaseModel):
    position1: int
    position2: int


class SwapRequestCreateDto(BaseModel):
    """User A wants to swap with whoever is at to_position, attaching a text message."""
    from_tg_id: int
    to_position: int
    message: str = ""


class SwapRequestRespondDto(BaseModel):
    """Accept or reject a swap request with an optional message."""
    tg_id: int
    message: str = ""


class KickDto(BaseModel):
    """Curator kicks a user from the queue."""
    curator_tg_id: int
    target_tg_id: int


class QueueCreateDto(BaseModel):
    """Create a new queue for a subject (e.g. subject: 'Math', queue_type: 'Lab 1')."""
    subject_name: str
    queue_type: str
    created_by_tg_id: int


class AdvanceQueueDto(BaseModel):
    """Curator marks the current person as done and advances queue."""
    curator_tg_id: int


class PauseQueueDto(BaseModel):
    """Curator pauses or resumes queue."""
    curator_tg_id: int
    paused: bool


class ClearQueueDto(BaseModel):
    """Curator resets/clears all participants from the queue without deleting it."""
    curator_tg_id: int


class SetRoleDto(BaseModel):
    """Assign a role to a user ('student' or 'curator')."""
    role: str
