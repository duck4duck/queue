import json
from typing import Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from sqlalchemy.engine import URL


# Telegram IDs can be placed here while access lists are being managed in code.
# An empty participant list means that every authenticated Telegram user is allowed.
TELEGRAM_WHITELIST_IDS: list[int] = []
TELEGRAM_ADMIN_IDS: list[int] = [1006402153,997211041,893807304,1122397134]
DEFAULT_QUEUE_SHARE_URL_TEMPLATE = "https://t.me/queue_college_bot/queue?startapp={subject}"


class Settings(BaseSettings):
    app_name: str = "Queue Management API"
    app_version: str = "2.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # Database
    db_host: str = "localhost"
    db_port: str = "5432"
    db_name: str = "myapp_db"
    db_user: str = "myapp_user"
    db_password: str = "strong_password"

    # Redis
    redis_host: str = "localhost"
    redis_port: str = "6379"
    redis_password: str = ""
    redis_max_connections: int = 50
    telegram_bot_token: str = ""
    telegram_whitelist: list[int] = TELEGRAM_WHITELIST_IDS
    telegram_admins: list[int] = TELEGRAM_ADMIN_IDS
    queue_share_url_template: str = DEFAULT_QUEUE_SHARE_URL_TEMPLATE

    # CORS
    cors_origins: Union[list[str], str] = ["*"]
    cors_allow_credentials: bool = True

    # Queue limits
    default_max_positions: int = 30
    queue_ttl_days: int = 14
    swap_request_ttl_hours: int = 24

    @field_validator("cors_origins", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: Union[list[str], str]) -> list[str]:
        if isinstance(v, str):
            v_stripped = v.strip()
            if v_stripped.startswith("[") and v_stripped.endswith("]"):
                try:
                    parsed = json.loads(v_stripped)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return [str(i) for i in v]

    @field_validator("telegram_whitelist", "telegram_admins", mode="before")
    @classmethod
    def parse_telegram_ids(cls, value: list[int] | str) -> list[int]:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = []
            else:
                value = value.split(",") if value else []
        return [int(item) for item in value if str(item).strip()]

    @property
    def database_url(self) -> str:
        url = URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=int(self.db_port),
            database=self.db_name,
        )
        return url.render_as_string(hide_password=False)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
