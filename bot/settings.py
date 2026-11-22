import json
import os
from urllib.parse import quote


def _int_list(value: str) -> list[int]:
    if not value.strip():
        return []
    if value.strip().startswith("["):
        return [int(item) for item in json.loads(value)]
    return [int(item.strip()) for item in value.split(",") if item.strip()]


class Settings:
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_password = os.getenv("REDIS_PASSWORD", "")
    redis_url = (
        f"redis://:{quote(redis_password, safe='')}@{redis_host}:{redis_port}"
        if redis_password
        else f"redis://{redis_host}:{redis_port}"
    )
    queue_share_url_template = os.getenv(
        "QUEUE_SHARE_URL_TEMPLATE",
        "https://t.me/your_bot/your_app?startapp={subject}",
    )
    group_ids = _int_list(os.getenv("TELEGRAM_GROUP_IDS", ""))


settings = Settings()
