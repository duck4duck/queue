import json
from datetime import datetime, timezone
from redis.asyncio import Redis
from app.core.config import settings
from app.core.datetime_utils import parse_utc_datetime
from app.core.logger import logger

TWO_WEEKS_SECONDS = settings.queue_ttl_days * 24 * 60 * 60
MAX_HISTORY_ITEMS = 50


class QueueRepository:

    def __init__(self, r: Redis):
        self.r = r

    def _queue_key(self, subject: str) -> str:
        return f"queue:{subject}"

    def _meta_key(self, subject: str) -> str:
        return f"queue_meta:{subject}"

    def _history_key(self, subject: str) -> str:
        return f"queue_history:{subject}"

    # ──────────────────── Queue State ────────────────────

    async def queue_exists(self, subject: str) -> bool:
        return await self.r.exists(self._queue_key(subject)) == 1

    async def meta_exists(self, subject: str) -> bool:
        return await self.r.exists(self._meta_key(subject)) == 1

    async def add(self, subject: str, user_id: int, position: int) -> bool:
        """Atomic slot assignment. Uses HSETNX to prevent race conditions.
        Returns True if slot was acquired, False if already taken."""
        key = self._queue_key(subject)
        is_new = not await self.r.exists(key)

        acquired = await self.r.hsetnx(key, str(position), str(user_id))
        if not acquired:
            return False

        if is_new:
            meta_ttl = await self.r.ttl(self._meta_key(subject))
            ttl = meta_ttl if (meta_ttl and meta_ttl > 0) else TWO_WEEKS_SECONDS
            await self.r.expire(key, ttl)

        return True

    async def remove(self, subject: str, position: int) -> None:
        await self.r.hdel(self._queue_key(subject), str(position))

    async def remove_by_user(self, subject: str, user_id: int) -> int | None:
        """Remove user from queue, returns the freed position if found."""
        key = self._queue_key(subject)
        users = await self.r.hgetall(key)
        for position, uid in users.items():
            if str(user_id) == uid:
                await self.r.hdel(key, position)
                return int(position)
        return None

    async def is_position_taken(self, subject: str, position: int) -> bool:
        return await self.r.hexists(self._queue_key(subject), str(position))

    async def is_user_in_queue(self, subject: str, user_id: int) -> bool:
        key = self._queue_key(subject)
        users = await self.r.hgetall(key)
        return str(user_id) in users.values()

    async def get_position(self, subject: str, user_id: int) -> int | None:
        key = self._queue_key(subject)
        users = await self.r.hgetall(key)
        for position, uid in users.items():
            if str(user_id) == uid:
                return int(position)
        return None

    async def get_user_at_position(self, subject: str, position: int) -> int | None:
        uid = await self.r.hget(self._queue_key(subject), str(position))
        return int(uid) if uid is not None else None

    async def get_first_in_line(self, subject: str) -> tuple[int, int] | None:
        """Returns (position, user_id) of the lowest occupied slot."""
        queue = await self.get_queue(subject)
        if not queue:
            return None
        min_pos = min(queue.keys())
        return min_pos, queue[min_pos]

    async def get_queue(self, subject: str) -> dict[int, int]:
        key = self._queue_key(subject)
        users = await self.r.hgetall(key)
        return {int(slot): int(uid) for slot, uid in users.items()}

    async def swap(self, subject: str, pos1: int, pos2: int) -> None:
        key = self._queue_key(subject)
        uid1 = await self.r.hget(key, str(pos1))
        uid2 = await self.r.hget(key, str(pos2))

        if uid1 and uid2:
            pipe = self.r.pipeline(transaction=True)
            pipe.hset(key, str(pos1), uid2)
            pipe.hset(key, str(pos2), uid1)
            await pipe.execute()

    async def clear_participants(self, subject: str) -> None:
        """Clears only the student participants, keeping queue metadata and history."""
        await self.r.delete(self._queue_key(subject))

    async def clear(self, subject: str) -> None:
        pipe = self.r.pipeline(transaction=True)
        pipe.delete(self._queue_key(subject))
        pipe.delete(self._meta_key(subject))
        pipe.delete(self._history_key(subject))
        pipe.srem("active_queues", subject)
        await pipe.execute()

    async def size(self, subject: str) -> int:
        return await self.r.hlen(self._queue_key(subject))

    # ──────────────────── Queue Metadata & Settings ────────────────────

    async def create_queue_meta(
        self,
        subject: str,
        subject_name: str,
        queue_type: str,
        created_by_tg_id: int,
        auto_delete_at: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        key = self._meta_key(subject)
        now = datetime.now(timezone.utc).isoformat()
        ttl = ttl_seconds if (ttl_seconds is not None and ttl_seconds > 0) else TWO_WEEKS_SECONDS
        mapping = {
            "subject": subject,
            "subject_name": subject_name,
            "queue_type": queue_type,
            "created_by_tg_id": str(created_by_tg_id),
            "created_at": now,
            "is_paused": "false",
        }
        if auto_delete_at:
            mapping["auto_delete_at"] = auto_delete_at

        pipe = self.r.pipeline(transaction=True)
        pipe.hset(key, mapping=mapping)
        pipe.expire(key, ttl)
        pipe.sadd("active_queues", subject)
        await pipe.execute()

    async def update_auto_delete(
        self,
        subject: str,
        auto_delete_at: str | None,
        ttl_seconds: int | None = None,
    ) -> None:
        key = self._meta_key(subject)
        queue_key = self._queue_key(subject)
        history_key = self._history_key(subject)
        ttl = (
            ttl_seconds
            if (ttl_seconds is not None and ttl_seconds > 0)
            else TWO_WEEKS_SECONDS
        )

        pipe = self.r.pipeline(transaction=True)
        if auto_delete_at:
            pipe.hset(key, "auto_delete_at", auto_delete_at)
        else:
            pipe.hdel(key, "auto_delete_at")

        pipe.expire(key, ttl)
        pipe.expire(queue_key, ttl)
        pipe.expire(history_key, ttl)
        await pipe.execute()

    async def get_queue_meta(self, subject: str) -> dict | None:
        key = self._meta_key(subject)
        data = await self.r.hgetall(key)
        return data if data else None

    async def set_queue_pause(self, subject: str, paused: bool) -> None:
        key = self._meta_key(subject)
        await self.r.hset(key, "is_paused", "true" if paused else "false")

    async def is_queue_paused(self, subject: str) -> bool:
        key = self._meta_key(subject)
        val = await self.r.hget(key, "is_paused")
        return val == "true"

    async def get_all_active_queue_keys(self) -> list[str]:
        # smembers returns a snapshot, so safe to prune dead entries
        members = await self.r.smembers("active_queues")
        active = []
        for subject in members:
            if await self.r.exists(self._queue_key(subject)) or await self.r.exists(
                self._meta_key(subject)
            ):
                active.append(subject)
            else:
                await self.r.srem("active_queues", subject)
        return active

    async def cleanup_expired_queues(self) -> list[str]:
        """Checks all active queues for expiration, deletes expired ones, and returns their keys."""
        members = await self.r.smembers("active_queues")
        deleted = []
        now = datetime.now(timezone.utc)
        for subject in members:
            has_queue = await self.r.exists(self._queue_key(subject))
            has_meta = await self.r.exists(self._meta_key(subject))
            if not has_queue and not has_meta:
                await self.r.srem("active_queues", subject)
                deleted.append(subject)
                continue

            meta = await self.get_queue_meta(subject)
            if not meta:
                await self.clear(subject)
                deleted.append(subject)
                continue

            auto_delete_at = meta.get("auto_delete_at")
            if auto_delete_at:
                exp_dt = parse_utc_datetime(auto_delete_at)
                if exp_dt and now >= exp_dt:
                    queue = await self.get_queue(subject)
                    for uid in queue.values():
                        await self.remove_user_from_index(uid, subject)
                    await self.clear(subject)
                    deleted.append(subject)
        return deleted

    # ──────────────────── User Participation Index ────────────────────

    async def add_user_to_index(self, user_id: int, subject: str) -> None:
        await self.r.sadd(f"user_queues:{user_id}", subject)

    async def remove_user_from_index(self, user_id: int, subject: str) -> None:
        await self.r.srem(f"user_queues:{user_id}", subject)

    async def get_user_queues(self, user_id: int) -> list[str]:
        members = await self.r.smembers(f"user_queues:{user_id}")
        active = []
        for subject in members:
            if await self.r.exists(self._queue_key(subject)):
                active.append(subject)
            else:
                await self.r.srem(f"user_queues:{user_id}", subject)
        return active

    # ──────────────────── Activity History Log ────────────────────

    async def log_event(self, subject: str, event_type: str, text: str) -> None:
        """Append an entry to the recent activity history list."""
        key = self._history_key(subject)
        entry = json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "text": text,
        }, ensure_ascii=False)

        pipe = self.r.pipeline(transaction=True)
        pipe.lpush(key, entry)
        pipe.ltrim(key, 0, MAX_HISTORY_ITEMS - 1)
        meta_ttl = await self.r.ttl(self._meta_key(subject))
        ttl = meta_ttl if (meta_ttl and meta_ttl > 0) else TWO_WEEKS_SECONDS
        pipe.expire(key, ttl)
        await pipe.execute()

    async def get_history(self, subject: str, limit: int = 20) -> list[dict]:
        """Fetch latest activity log entries for the queue."""
        key = self._history_key(subject)
        items = await self.r.lrange(key, 0, limit - 1)
        res = []
        for raw in items:
            try:
                res.append(json.loads(raw))
            except Exception:
                continue
        return res
