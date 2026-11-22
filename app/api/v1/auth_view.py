from fastapi import APIRouter, Depends

from app.api.auth import get_authenticated_tg_id
from app.core.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
async def get_current_user(tg_id: int = Depends(get_authenticated_tg_id)):
    return {
        "tg_id": tg_id,
        "is_admin": tg_id in settings.telegram_admins,
        "is_whitelisted": True,
    }
