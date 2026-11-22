import json
from typing import Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from sqlalchemy.engine import URL


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
