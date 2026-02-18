import time 
from redis.asyncio import Redis

class QueueRepository:

    def __init__(self,r: Redis):
        self.r = r

    def _queue_key (self,subject: str) -> str:
        return f"queue:{subject}"
    
    async def queue_exists(self,subject) -> str:
        return await self.r.exists(self._queue_key(subject)) == 1
    
    async def add(self,subject: str,user_id: str) -> None:
        score = time.time()
        await self.r.zadd(self._queue_key(subject),{user_id: score})

    async def remove(self,subject: str,user_id: str) -> None:
        await self.r.zrem(self._queue_key(subject),user_id)

    async def exists(self,subject: str,user_id: str) -> bool:
        return await self.r.zrank(self._queue_key(subject),user_id) is not None
    
    async def get_queue(self,subject: str) -> list[dict]:
        members = await self.r.zrange(self._queue_key(subject),0,-1)
        
        result = []
        for i,uid in enumerate(members,1):
            result.append({"position":i,"id": uid})
        return result

    async def get_position(self,subject: str,user_id: str) -> int | None:
        rank = await self.r.zrank(self._queue_key(subject),user_id)
        if rank is not None:
            return rank + 1
        
        return None
    
    async def swap(self,subject: str,uid1: str,uid2: str) -> None:
        key = self._queue_key(subject)
        score1 = await self.r.zscore(key,uid1)
        score2 = await self.r.zscore(key,uid2)

        if score1 is not None and score2 is not None:
            pipe = self.r.pipeline(transaction=True)
            await pipe.zadd(key,{uid1:score2})
            await pipe.zadd(key,{uid2,score1})
            await pipe.execute()

    async def clear(self,subject: str) -> None:
        await self.r.delete(self._queue_key(subject))
    