from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Queue"
    debug: bool = True
    database_url: str
    class Config:
       env_files = ".env"



settings = Settings()