import uuid
from datetime import datetime, timezone
from redis.asyncio import Redis
from redis.exceptions import WatchError
from app.core.config import settings
from app.repositories.queue_repository import QueueRepository
from app.schemas.exception import (
    QueueNotFound,
    QueuePaused,
    SwapRequestAlreadyExists,
    SwapRequestExpired,
)


class SwapRequestRepository:

    def __init__(self, r: Redis):
        self.r = r
        self.queue_repo = QueueRepository(r)

    @staticmethod
    def _belongs_to_queue(data: dict, meta: dict) -> bool:
        created_at = meta.get("created_at")
        if not created_at:
            return False
        request_revision = data.get("queue_revision")
        if request_revision:
            return request_revision == QueueRepository.get_revision(meta)
        return not meta.get("revision") and data.get("created_at", "") >= created_at

    @property
    def ttl(self) -> int:
        return settings.swap_request_ttl_hours * 3600

    def _request_key(self, request_id: str) -> str:
        return f"swap_request:{request_id}"

    def _incoming_key(self, subject: str, tg_id: int) -> str:
        return f"swap_incoming:{subject}:{tg_id}"

    def _outgoing_key(self, subject: str, tg_id: int) -> str:
        return f"swap_outgoing:{subject}:{tg_id}"

    def _user_all_incoming_key(self, tg_id: int) -> str:
        return f"swap_user_incoming:{tg_id}"

    def _user_all_outgoing_key(self, tg_id: int) -> str:
        return f"swap_user_outgoing:{tg_id}"

    def _queue_requests_key(self, subject: str) -> str:
        return f"swap_queue:{subject}"

    async def create(
        self,
        subject: str,
        from_tg_id: int,
        to_tg_id: int,
        from_position: int,
        to_position: int,
        message: str = "",
    ) -> str:
        request_id = str(uuid.uuid4())
        key = self._request_key(request_id)
        ttl = self.ttl

        incoming_key = self._incoming_key(subject, to_tg_id)
        outgoing_key = self._outgoing_key(subject, from_tg_id)
        user_incoming_key = self._user_all_incoming_key(to_tg_id)
        user_outgoing_key = self._user_all_outgoing_key(from_tg_id)
        queue_key = self._queue_requests_key(subject)

        meta_key = self.queue_repo._meta_key(subject)
        slots_key = self.queue_repo._queue_key(subject)

        async with self.r.pipeline() as pipe:
            while True:
                try:
                    await pipe.watch(meta_key, slots_key, outgoing_key)
                    meta = await pipe.hgetall(meta_key)
                    if not meta.get("created_at"):
                        raise QueueNotFound()
                    if meta.get("is_paused") == "true":
                        raise QueuePaused()
                    occupants = await pipe.hmget(slots_key, str(from_position), str(to_position))
                    if occupants != [str(from_tg_id), str(to_tg_id)]:
                        raise SwapRequestExpired("Позиции изменились. Обновите очередь и повторите запрос.")
                    for pending_id in await pipe.smembers(outgoing_key):
                        pending = await pipe.hgetall(self._request_key(pending_id))
                        if pending.get("status") == "pending" and self._belongs_to_queue(pending, meta):
                            raise SwapRequestAlreadyExists()

                    pipe.multi()
                    pipe.hset(key, mapping={
                        "id": request_id,
                        "subject": subject,
                        "from_tg_id": str(from_tg_id),
                        "to_tg_id": str(to_tg_id),
                        "from_position": str(from_position),
                        "to_position": str(to_position),
                        "message": message,
                        "status": "pending",
                        "response_message": "",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "queue_revision": self.queue_repo.get_revision(meta),
                    })
                    pipe.expire(key, ttl)
                    for index in (incoming_key, outgoing_key, user_incoming_key, user_outgoing_key, queue_key):
                        pipe.sadd(index, request_id)
                        pipe.expire(index, ttl)
                    await pipe.execute()
                    return request_id
                except WatchError:
                    continue

    async def get(self, request_id: str) -> dict | None:
        key = self._request_key(request_id)
        data = await self.r.hgetall(key)
        return data if data else None

    async def get_incoming_requests(self, subject: str, tg_id: int) -> list[dict]:
        incoming_key = self._incoming_key(subject, tg_id)
        request_ids = await self.r.smembers(incoming_key)
        requests = []
        for rid in request_ids:
            data = await self.get(rid)
            if await self._is_pending(data):
                requests.append(data)
            else:
                await self.r.srem(incoming_key, rid)
        return requests

    async def get_outgoing_requests(self, subject: str, tg_id: int) -> list[dict]:
        outgoing_key = self._outgoing_key(subject, tg_id)
        request_ids = await self.r.smembers(outgoing_key)
        requests = []
        for rid in request_ids:
            data = await self.get(rid)
            if await self._is_pending(data):
                requests.append(data)
            else:
                await self.r.srem(outgoing_key, rid)
        return requests

    async def get_all_incoming_requests(self, tg_id: int) -> list[dict]:
        user_key = self._user_all_incoming_key(tg_id)
        request_ids = await self.r.smembers(user_key)
        # Fallback to scan if user index is empty (for backward compatibility)
        if not request_ids:
            keys = [k async for k in self.r.scan_iter(match=f"swap_incoming:*:{tg_id}")]
            for k in keys:
                request_ids.update(await self.r.smembers(k))

        requests = []
        for rid in request_ids:
            data = await self.get(rid)
            if await self._is_pending(data):
                requests.append(data)
            else:
                await self.r.srem(user_key, rid)
        return requests

    async def get_all_outgoing_requests(self, tg_id: int) -> list[dict]:
        user_key = self._user_all_outgoing_key(tg_id)
        request_ids = await self.r.smembers(user_key)
        # Fallback to scan if user index is empty (for backward compatibility)
        if not request_ids:
            keys = [k async for k in self.r.scan_iter(match=f"swap_outgoing:*:{tg_id}")]
            for k in keys:
                request_ids.update(await self.r.smembers(k))

        requests = []
        for rid in request_ids:
            data = await self.get(rid)
            if await self._is_pending(data):
                requests.append(data)
            else:
                await self.r.srem(user_key, rid)
        return requests

    async def _is_pending(self, data: dict | None) -> bool:
        if not data or data.get("status") != "pending":
            return False
        meta = await self.queue_repo.get_queue_meta(data["subject"])
        return self._belongs_to_queue(data, meta or {})

    async def count_active_for_queue(self, subject: str) -> int:
        queue_key = self._queue_requests_key(subject)
        request_ids = await self.r.smembers(queue_key)
        meta = await self.queue_repo.get_queue_meta(subject) or {}
        count = 0
        for rid in request_ids:
            data = await self.get(rid)
            if data and data.get("status") == "pending" and self._belongs_to_queue(data, meta):
                count += 1
            else:
                await self.r.srem(queue_key, rid)
        return count

    async def update_status(
        self, request_id: str, status: str, response_message: str = ""
    ) -> str | None:
        """Resolve a pending request and, on acceptance, swap its occupants in the same transaction."""
        key = self._request_key(request_id)
        async with self.r.pipeline() as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    data = await pipe.hgetall(key)
                    if data.get("status") != "pending":
                        return None

                    subject = data["subject"]
                    from_id = int(data["from_tg_id"])
                    to_id = int(data["to_tg_id"])
                    meta_key = self.queue_repo._meta_key(subject)
                    await pipe.watch(meta_key)
                    meta = await pipe.hgetall(meta_key)
                    resolved = status if self._belongs_to_queue(data, meta) else "expired"
                    if resolved == "accepted":
                        if meta.get("is_paused") == "true":
                            raise QueuePaused()
                        slots_key = self.queue_repo._queue_key(subject)
                        await pipe.watch(slots_key)
                        first, second = data["from_position"], data["to_position"]
                        occupants = await pipe.hmget(slots_key, first, second)
                        if occupants != [data["from_tg_id"], data["to_tg_id"]]:
                            resolved = "expired"

                    pipe.multi()
                    if resolved == "accepted":
                        pipe.hset(slots_key, mapping={first: occupants[1], second: occupants[0]})
                    pipe.hset(key, mapping={
                        "status": resolved,
                        "response_message": response_message if resolved == status else "",
                    })
                    pipe.srem(self._queue_requests_key(subject), request_id)
                    pipe.srem(self._incoming_key(subject, to_id), request_id)
                    pipe.srem(self._user_all_incoming_key(to_id), request_id)
                    pipe.srem(self._outgoing_key(subject, from_id), request_id)
                    pipe.srem(self._user_all_outgoing_key(from_id), request_id)
                    await pipe.execute()
                    return resolved
                except WatchError:
                    continue

    async def delete(self, request_id: str) -> None:
        data = await self.get(request_id)
        if not data:
            return

        subject = data["subject"]
        from_tg_id = int(data["from_tg_id"])
        to_tg_id = int(data["to_tg_id"])

        pipe = self.r.pipeline(transaction=True)
        pipe.srem(self._incoming_key(subject, to_tg_id), request_id)
        pipe.srem(self._outgoing_key(subject, from_tg_id), request_id)
        pipe.srem(self._user_all_incoming_key(to_tg_id), request_id)
        pipe.srem(self._user_all_outgoing_key(from_tg_id), request_id)
        pipe.srem(self._queue_requests_key(subject), request_id)
        pipe.delete(self._request_key(request_id))
        await pipe.execute()

    async def cancel_all_for_user_in_queue(
        self, subject: str, tg_id: int
    ) -> list[dict]:
        cancelled = []
        outgoing = await self.get_outgoing_requests(subject, tg_id)
        for req in outgoing:
            if await self.update_status(req["id"], "cancelled") == "cancelled":
                cancelled.append(req)

        incoming = await self.get_incoming_requests(subject, tg_id)
        for req in incoming:
            if await self.update_status(req["id"], "cancelled") == "cancelled":
                cancelled.append(req)

        return cancelled
