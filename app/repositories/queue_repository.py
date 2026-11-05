import json
from datetime import datetime, timezone
from redis.asyncio import Redis
from app.core.config import settings
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

        # Atomic set if not exists
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
        for position, uid in users.items():
            if str(user_id) == uid:
                return True
        return False

    async def get_position(self, subject: str, user_id: int) -> int | None:
        key = self._queue_key(subject)
        users = await self.r.hgetall(key)
        for position, uid in users.items():
            if str(user_id) == uid:
                return int(position)
        return None

    async def get_user_at_position(self, subject: str, position: int) -> int | None:
        uid = await self.r.hget(self._queue_key(subject), str(position))
        if uid is not None:
            return int(uid)
        return None

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
        await self.r.delete(self._queue_key(subject))
        await self.r.delete(self._meta_key(subject))
        await self.r.delete(self._history_key(subject))
        await self.r.srem("active_queues", subject)

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
        await self.r.hset(key, mapping=mapping)
        await self.r.expire(key, ttl)
        await self.r.sadd("active_queues", subject)

    async def update_auto_delete(
        self,
        subject: str,
        auto_delete_at: str | None,
        ttl_seconds: int | None = None,
    ) -> None:
        key = self._meta_key(subject)
        queue_key = self._queue_key(subject)
        history_key = self._history_key(subject)
        if auto_delete_at:
            await self.r.hset(key, "auto_delete_at", auto_delete_at)
            ttl = ttl_seconds if (ttl_seconds is not None and ttl_seconds > 0) else TWO_WEEKS_SECONDS
            await self.r.expire(key, ttl)
            if await self.r.exists(queue_key):
                await self.r.expire(queue_key, ttl)
            if await self.r.exists(history_key):
                await self.r.expire(history_key, ttl)
        else:
            await self.r.hdel(key, "auto_delete_at")
            await self.r.expire(key, TWO_WEEKS_SECONDS)
            if await self.r.exists(queue_key):
                await self.r.expire(queue_key, TWO_WEEKS_SECONDS)
            if await self.r.exists(history_key):
                await self.r.expire(history_key, TWO_WEEKS_SECONDS)

    async def get_queue_meta(self, subject: str) -> dict | None:
        key = self._meta_key(subject)
        data = await self.r.hgetall(key)
        if not data:
            return None
        return data

    async def set_queue_pause(self, subject: str, paused: bool) -> None:
        key = self._meta_key(subject)
        await self.r.hset(key, "is_paused", "true" if paused else "false")

    async def is_queue_paused(self, subject: str) -> bool:
        key = self._meta_key(subject)
        val = await self.r.hget(key, "is_paused")
        return val == "true"

    async def get_all_active_queue_keys(self) -> list[str]:
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
                try:
                    exp_dt = datetime.fromisoformat(auto_delete_at.replace("Z", "+00:00"))
                    if exp_dt.tzinfo is None:
                        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                    if now >= exp_dt:
                        # Clean up user queues index for remaining users
                        queue = await self.get_queue(subject)
                        for uid in queue.values():
                            await self.remove_user_from_index(uid, subject)
                        await self.clear(subject)
                        deleted.append(subject)
                except Exception as e:
                    logger.warning(f"Error checking expiration for {subject}: {e}")
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

        await self.r.lpush(key, entry)
        await self.r.ltrim(key, 0, MAX_HISTORY_ITEMS - 1)
        meta_ttl = await self.r.ttl(self._meta_key(subject))
        ttl = meta_ttl if (meta_ttl and meta_ttl > 0) else TWO_WEEKS_SECONDS
        await self.r.expire(key, ttl)

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
