from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings


engine = create_async_engine(url=settings.database_url)

AsyncSessionLocal = async_sessionmaker(
    expire_on_commit=False, autoflush=False, bind=engine
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


