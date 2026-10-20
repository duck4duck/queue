from pydantic import BaseModel, ConfigDict


class SwapRequestInfo(BaseModel):
    id: str
    subject: str
    from_tg_id: int
    to_tg_id: int
    from_position: int
    to_position: int
    from_name: str | None = None
    to_name: str | None = None
    message: str = ""
    status: str = "pending"  # pending / accepted / rejected / cancelled / expired
    response_message: str | None = None
    created_at: str = ""

    model_config = ConfigDict(from_attributes=True)


class SwapRequestListResponse(BaseModel):
    requests: list[SwapRequestInfo]
    total: int

    model_config = ConfigDict(from_attributes=True)
