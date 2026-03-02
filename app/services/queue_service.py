from app.repositories.queue_repository import QueueRepository
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.schemas.exception import UserExist,UserNotFound,UserNotExist
from app.schemas.queue import QueueUserInfo,QueueResponse


MAX_POSITIONS_IN_QUEUE = 30

class QueueService:
    def __init__(self,db: AsyncSession,r:Redis):
        self.user_service = UserService(db)
        self.r = QueueRepository(r)

    async def join(self,subject: str,user_id: int, position: int) -> QueueResponse:
        
        user = await self.user_service.get_user_by_tg_id(user_id)

        if user is None:
            raise UserNotFound("Пользователь не найден!")
        
        if position < 1 or position > MAX_POSITIONS_IN_QUEUE:
            raise ValueError("Неккоректное число.Число должно быть от 1 до 30!")


        if await self.r.is_user_in_queue(subject, user_id):
            raise UserExist("Вы уже есть в этйо очереди!")
        
        if await self.r.is_position_taken(subject, position):
            raise UserExist("Место занято!")
        



        await self.r.add(subject,user_id,position)
        return await self.get_queue(subject)
        
    async def leave(self,subject: str,user_id: int, position: int) -> QueueResponse:
        if not await self.r.is_user_in_queue(subject,user_id):
            raise UserNotExist("Пользователь не в очереди!")
        
        await self.r.remove(subject, position)

        return await self.get_queue(subject)
    
    async def get_queue(self,subject: str)-> QueueResponse:
        queue = await self.r.get_queue(subject)
        
        if not queue:
            return QueueResponse(subject=subject,queue=[],total_positions=0,taken_positions=0)
        
        ids = list(queue.values())
        users = []

        if ids:
            users = await self.user_service.get_by_tg_ids(ids)


        user_map = {u.tg_id: u for u in users}

        positions = []
        for position in range(1,MAX_POSITIONS_IN_QUEUE + 1):
            uid = queue.get(position)
            if uid and uid in user_map:
                user = user_map[uid]
                positions.append(QueueUserInfo(
                    position=position,
                    tg_id=uid,
                    name=user.name,
                    photo_url=user.photo_url,
                    is_free=False
                ))
            else:
                positions.append(QueueUserInfo(
                    position=position,
                    is_free=True
                ))
    


        
        return QueueResponse(queue=positions,taken_positions=len(queue),subject=subject,total_positions=len(queue))
    
    async def swap(self,pos1: int,pos2: int,subject: str) -> QueueResponse:
        if not await self.r.is_user_in_queue(subject,pos2):
            raise UserNotFound("Пользователь 1 не найден!")
        
        if not await self.r.is_user_in_queue(subject,pos1):
            raise UserNotFound("Пользователь 2 не найден!")
        
        await self.r.swap(subject,pos1,pos2)
        return await self.r.get_queue(subject)








