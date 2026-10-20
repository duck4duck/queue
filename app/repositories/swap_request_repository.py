import uuid
from datetime import datetime, timezone
from redis.asyncio import Redis

SWAP_REQUEST_TTL = 24 * 60 * 60  # 24 hours


class SwapRequestRepository:

    def __init__(self, r: Redis):
        self.r = r

    def _request_key(self, request_id: str) -> str:
        return f"swap_request:{request_id}"

    def _incoming_key(self, subject: str, tg_id: int) -> str:
        return f"swap_incoming:{subject}:{tg_id}"

    def _outgoing_key(self, subject: str, tg_id: int) -> str:
        return f"swap_outgoing:{subject}:{tg_id}"

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

        await self.r.hset(
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
        await self.r.expire(key, SWAP_REQUEST_TTL)

        # Index for fast lookup
        incoming_key = self._incoming_key(subject, to_tg_id)
        outgoing_key = self._outgoing_key(subject, from_tg_id)
        queue_key = self._queue_requests_key(subject)

        await self.r.sadd(incoming_key, request_id)
        await self.r.expire(incoming_key, SWAP_REQUEST_TTL)
        await self.r.sadd(outgoing_key, request_id)
        await self.r.expire(outgoing_key, SWAP_REQUEST_TTL)
        await self.r.sadd(queue_key, request_id)
        await self.r.expire(queue_key, SWAP_REQUEST_TTL)

        return request_id

    async def get(self, request_id: str) -> dict | None:
        key = self._request_key(request_id)
        data = await self.r.hgetall(key)
        if not data:
            return None
        return data

    async def get_incoming_requests(self, subject: str, tg_id: int) -> list[dict]:
        incoming_key = self._incoming_key(subject, tg_id)
        request_ids = await self.r.smembers(incoming_key)
        requests = []
        for rid in request_ids:
            data = await self.get(rid)
            if data and data.get("status") == "pending":
                requests.append(data)
            elif not data:
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
            elif not data:
                await self.r.srem(outgoing_key, rid)
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
        await self.r.hset(key, "status", status)
        if response_message:
            await self.r.hset(key, "response_message", response_message)

        # If resolved, remove from active queue index
        if status != "pending":
            data = await self.get(request_id)
            if data and "subject" in data:
                await self.r.srem(self._queue_requests_key(data["subject"]), request_id)

    async def delete(self, request_id: str) -> None:
        data = await self.get(request_id)
        if not data:
            return

        subject = data["subject"]
        from_tg_id = int(data["from_tg_id"])
        to_tg_id = int(data["to_tg_id"])

        await self.r.srem(self._incoming_key(subject, to_tg_id), request_id)
        await self.r.srem(self._outgoing_key(subject, from_tg_id), request_id)
        await self.r.srem(self._queue_requests_key(subject), request_id)
        await self.r.delete(self._request_key(request_id))

    async def cancel_all_for_user_in_queue(
        self, subject: str, tg_id: int
    ) -> list[dict]:
        cancelled = []

        # Outgoing
        outgoing = await self.get_outgoing_requests(subject, tg_id)
        for req in outgoing:
            await self.update_status(req["id"], "cancelled")
            cancelled.append(req)

        # Incoming
        incoming = await self.get_incoming_requests(subject, tg_id)
        for req in incoming:
            await self.update_status(req["id"], "cancelled")
            cancelled.append(req)

        return cancelled
