from app.repositories.queue_repository import QueueRepository
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession
from redis import Redis

class QueueService:
    def __init__(self,db: AsyncSession,r:Redis):
        self.db = UserService(db)
        self.r = QueueRepository(r)