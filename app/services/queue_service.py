from app.repositories.queue_repository import QueueRepository
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.schemas.exception import UserExist,UserNotFound,UserNotExist
from app.schemas.user import QueueUser,Queue

class QueueService:
    def __init__(self,db: AsyncSession,r:Redis):
        self.user_service = UserService(db)
        self.r = QueueRepository(r)

    async def join(self,subject: str,user_id: str) -> list[dict]:
        user = await self.user_service.get_user_by_tg_id(user_id)

        if user is None:
            raise UserNotFound("Пользователь не найден!")
        
        if await self.r.exists(subject,user_id):
            raise UserExist("Пользователь уже есть!")

        await self.r.add(subject,user_id)
        return await self.r.get_queue(subject)
        
    async def leave(self,subject: str,user_id: str) -> list[dict]:
        if not self.r.exists(subject,user_id):
            raise UserNotExist("Пользователь не в очереди!")
        
        await self.r.remove(subject,user_id)

        return await self.r.get_queue(subject)
    
    async def get_queue(self,subject: str) -> list[dict]:
        queue = self.r.get_queue(subject)
        if not queue:
            return []
        
        ids = [item[id] for item in queue]
        users = await self.user_service.get_by_tg_ids(ids)

        user_map = {u.tg_id: u for u in users}

        entries = []
        for position, tg_id in enumerate(ids, 1):
            if tg_id in user_map:
                entries.append(
                    QueueUser(
                        position=position,
                        tg_id=tg_id,
                        name=user_map[tg_id].name,
                        photo_url=user_map[tg_id].photo_url
                    )

                )
        
        return Queue(users=entries,total=len(entries),subject=subject)







