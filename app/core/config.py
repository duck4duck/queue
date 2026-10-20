from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "Queue Management API"
    app_version: str = "2.1.0"
    debug: bool = True
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
    redis_password: str = "1111"
    redis_insight_port: str = "5540"
    redis_max_connections: int = 50

    # CORS
    cors_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True

    # Queue limits
    default_max_positions: int = 30
    queue_ttl_days: int = 14
    swap_request_ttl_hours: int = 24

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
