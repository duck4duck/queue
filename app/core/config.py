from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Queue"
    debug: bool = True
    db_host: str
    db_port: str
    db_name: str
    db_user: str
    db_password: str
    redis_host: str
    redis_port: str
    redis_password: str
    redis_insight_port: str
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


    class Config:
       env_file = ".env"



settings = Settings()

