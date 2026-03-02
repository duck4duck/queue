import time
from redis.asyncio import Redis


class QueueRepository:

    def __init__(self, r: Redis):
        self.r = r

    def _queue_key(self, subject: str) -> str:
        return f"queue:{subject}"

    async def queue_exists(self, subject: str) -> str:
        return await self.r.exists(self._queue_key(subject)) == 1

    async def add(self, subject: str, user_id: int, position: int) -> None:
        await self.r.hset(self._queue_key(subject), position, user_id)

    async def remove(self, subject: str, position: int) -> None:
        await self.r.hdel(self._queue_key(subject), position)

    async def remove_by_user(self, subject: str, user_id: int) -> bool:
        key = self._queue_key(subject)
        users = await self.r.hgetall(key)
        for position, uid in users.items():
            if user_id == uid:
                await self.r.hdel(key, position)
                return

    async def is_position_taken(self, subject: str, position: int):
        return await self.r.hexists(self._queue_key(subject), position)

    async def is_user_in_queue(self, subject: str, user_id: int) -> bool:
        key = self._queue_key(subject)
        users = await self.r.hgetall(key)
        for position, uid in users.items():
            if user_id == uid:

                return True

        return False

    async def get_position(self, subject: str, user_id: int) -> bool:
        key = self._queue_key(subject)
        users = await self.r.hgetall(key)
        for position, uid in users.items():
            if user_id == uid:

                return int(position)

        return None

    async def get_queue(self, subject: int) -> dict:
        key = self._queue_key(subject)
        users = await self.r.hgetall(key)
        return {int(slot): int(uid) for slot, uid in users.items()}

    async def swap(self, subject: str, pos1: int, pos2: int) -> None:
        key = self._queue_key(subject)
        uid1 = await self.r.hget(key, pos1)
        uid2 = await self.r.hget(key, pos2)

        pipe = self.r.pipeline(transaction=True)
        if uid1 and uid2:
            pipe.hset(key, pos1, uid2)
            pipe.hset(key, pos2, uid1)

        await pipe.execute()

    async def clear(self, subject: str) -> None:
        await self.r.delete(self._queue_key(subject))

    async def size(self, subject: str):
        return await self.r.hlen(self.get_queue(subject))
