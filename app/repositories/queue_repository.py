import time 
from redis import Redis

class QueueRepository:

    def __init__(self,r: Redis):
        self.r = r

    def _queue_key (self,subject: str) -> str:
        return f"queue:{subject}"
    
    def queue_exists(self,subject) -> str:
        return self.r.exists(self._queue_key(subject)) == 1
    
    def add(self,subject: str,user_id: str,name: str) -> None:
        score = time.time()
        self.r.zadd(self._queue_key(subject),{user_id: score})

    def remove(self,subject: str,user_id: str) -> None:
        self.r.zrem(self._queue_key(subject),user_id)

    def exists(self,subject: str,user_id: str) -> bool:
        return self.r.zrank(self._queue_key(subject),user_id) is not None
    
    def get_all(self,subject: str) -> list[dict]:
        members = self.r.zrange(self._queue_key(subject),0,-1)
        
        result = []
        for i,uid in enumerate(members,1):
            result.append({"position":i,"id": uid})

    def get_position(self,subject: str,user_id: str) -> int | None:
        rank = self.r.zrank(self._queue_key(subject),user_id)
        if rank is not None:
            return rank + 1
        
        return None
    
    def swap(self,subject: str,uid1: str,uid2: str) -> None:
        key = self._queue_key(subject)
        score1 = self.r.zscore(key,uid1)
        score2 = self.r.zscore(key,uid2)

        if score1 is not None and score2 is not None:
            pipe = self.r.pipeline()
            pipe.zadd(key,{uid1:score2})
            pipe.zadd(key,{uid2,score1})
            pipe.execute()

    def clear(self,subject: str) -> None:
        pipe = self.r.pipeline()
        pipe.delete(self._queue_key(subject))
        pipe.execute()
    