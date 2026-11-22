import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, status

from app.core.config import settings


def verify_telegram_init_data(init_data: str, bot_token: str) -> int:
    """Validate Telegram Web App initData and return its authenticated user ID."""
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing Telegram signature")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Invalid Telegram signature")

    auth_date = int(fields["auth_date"])
    if auth_date > int(time.time()) or int(time.time()) - auth_date > 86400:
        raise ValueError("Expired Telegram authentication data")

    user = json.loads(fields["user"])
    user_id = int(user["id"])
    if user_id <= 0:
        raise ValueError("Invalid Telegram user ID")
    return user_id


async def get_authenticated_tg_id(
    init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> int:
    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram authentication is not configured",
        )
    if not init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram authentication is required",
        )
    try:
        tg_id = verify_telegram_init_data(init_data, settings.telegram_bot_token)
        if settings.telegram_whitelist and tg_id not in settings.telegram_whitelist:
            raise HTTPException(status_code=403, detail="Telegram user is not in the whitelist")
        return tg_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Telegram authentication data",
        ) from None


def require_actor(actor_tg_id: int, authenticated_tg_id: int) -> None:
    if actor_tg_id != authenticated_tg_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telegram identity does not match the requested actor",
        )


def require_admin(tg_id: int) -> None:
    if tg_id not in settings.telegram_admins:
        raise HTTPException(status_code=403, detail="Telegram user is not an administrator")
