import uuid
from datetime import datetime, timezone
from redis.asyncio import Redis
from app.core.config import settings


class SwapRequestRepository:

    def __init__(self, r: Redis):
        self.r = r

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
        now = datetime.now(timezone.utc).isoformat()
        ttl = self.ttl

        incoming_key = self._incoming_key(subject, to_tg_id)
        outgoing_key = self._outgoing_key(subject, from_tg_id)
        user_incoming_key = self._user_all_incoming_key(to_tg_id)
        user_outgoing_key = self._user_all_outgoing_key(from_tg_id)
        queue_key = self._queue_requests_key(subject)

        pipe = self.r.pipeline(transaction=True)
        pipe.hset(
            key,
            mapping={
                "id": request_id,
                "subject": subject,
                "from_tg_id": str(from_tg_id),
                "to_tg_id": str(to_tg_id),
                "from_position": str(from_position),
                "to_position": str(to_position),
                "message": message,
                "status": "pending",
                "response_message": "",
                "created_at": now,
            },
        )
        pipe.expire(key, ttl)

        pipe.sadd(incoming_key, request_id)
        pipe.expire(incoming_key, ttl)
        pipe.sadd(outgoing_key, request_id)
        pipe.expire(outgoing_key, ttl)
        pipe.sadd(user_incoming_key, request_id)
        pipe.expire(user_incoming_key, ttl)
        pipe.sadd(user_outgoing_key, request_id)
        pipe.expire(user_outgoing_key, ttl)
        pipe.sadd(queue_key, request_id)
        pipe.expire(queue_key, ttl)

        await pipe.execute()
        return request_id

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
            if data and data.get("status") == "pending":
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
            if data and data.get("status") == "pending":
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
            if data and data.get("status") == "pending":
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
            if data and data.get("status") == "pending":
                requests.append(data)
            else:
                await self.r.srem(user_key, rid)
        return requests

    async def has_pending_outgoing(self, subject: str, from_tg_id: int) -> bool:
        outgoing = await self.get_outgoing_requests(subject, from_tg_id)
        return len(outgoing) > 0

    async def count_active_for_queue(self, subject: str) -> int:
        queue_key = self._queue_requests_key(subject)
        request_ids = await self.r.smembers(queue_key)
        count = 0
        for rid in request_ids:
            data = await self.get(rid)
            if data and data.get("status") == "pending":
                count += 1
            elif not data:
                await self.r.srem(queue_key, rid)
        return count

    async def update_status(
        self, request_id: str, status: str, response_message: str = ""
    ) -> None:
        key = self._request_key(request_id)
        data = await self.get(request_id)

        pipe = self.r.pipeline(transaction=True)
        pipe.hset(key, "status", status)
        if response_message:
            pipe.hset(key, "response_message", response_message)

        # If resolved or cancelled, remove from all active pending indices
        if status != "pending" and data:
            subject = data.get("subject")
            to_tg_id = data.get("to_tg_id")
            from_tg_id = data.get("from_tg_id")
            if subject:
                pipe.srem(self._queue_requests_key(subject), request_id)
                if to_tg_id:
                    pipe.srem(self._incoming_key(subject, int(to_tg_id)), request_id)
                    pipe.srem(self._user_all_incoming_key(int(to_tg_id)), request_id)
                if from_tg_id:
                    pipe.srem(self._outgoing_key(subject, int(from_tg_id)), request_id)
                    pipe.srem(self._user_all_outgoing_key(int(from_tg_id)), request_id)

        await pipe.execute()

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
            await self.update_status(req["id"], "cancelled")
            cancelled.append(req)

        incoming = await self.get_incoming_requests(subject, tg_id)
        for req in incoming:
            await self.update_status(req["id"], "cancelled")
            cancelled.append(req)

        return cancelled
