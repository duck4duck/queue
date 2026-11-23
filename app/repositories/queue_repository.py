import json
from datetime import datetime, timezone
from uuid import uuid4
from redis.asyncio import Redis
from redis.exceptions import WatchError
from app.core.config import settings
from app.core.datetime_utils import parse_utc_datetime

DEFAULT_TTL_SECONDS = settings.queue_ttl_days * 24 * 60 * 60
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

    @staticmethod
    def get_revision(meta: dict) -> str:
        return meta.get("revision") or meta.get("created_at", "")

    # ──────────────────── Queue State ────────────────────

    async def add(self, subject: str, user_id: int, position: int) -> int:
        """Atomically add a user to a free slot and update their queue index.

        Returns 1 on success, 0 if the slot is taken, -1 if the user is
        already in the queue, -2 if the queue does not exist, and -3 if paused.
        """
        script = """
        local queue_key = KEYS[1]
        local meta_key = KEYS[2]
        local user_index_key = KEYS[3]
        local position = ARGV[1]
        local user_id = ARGV[2]
        local default_ttl = tonumber(ARGV[3])

        if redis.call('EXISTS', meta_key) == 0 then
            return -2
        end
        if redis.call('HGET', meta_key, 'is_paused') == 'true' then
            return -3
        end

        local users = redis.call('HGETALL', queue_key)
        for i = 1, #users, 2 do
            if users[i + 1] == user_id then
                return -1
            end
        end

        if redis.call('HEXISTS', queue_key, position) == 1 then
            return 0
        end

        redis.call('HSET', queue_key, position, user_id)
        redis.call('SADD', user_index_key, ARGV[4])

        local deadline = redis.call('PEXPIRETIME', meta_key)
        if deadline > 0 then
            redis.call('PEXPIREAT', queue_key, deadline)
        else
            redis.call('EXPIRE', queue_key, default_ttl)
        end
        return 1
        """
        result = await self.r.eval(
            script,
            3,
            self._queue_key(subject),
            self._meta_key(subject),
            f"user_queues:{user_id}",
            str(position),
            str(user_id),
            str(DEFAULT_TTL_SECONDS),
            subject,
        )
        return int(result)

    async def remove_by_user(
        self,
        subject: str,
        user_id: int,
        *,
        revision: str = "",
        expected_head: int | None = None,
    ) -> int | None:
        """Remove a user and their index entry atomically."""
        script = """
        local revision = redis.call('HGET', KEYS[3], 'revision') or redis.call('HGET', KEYS[3], 'created_at')
        if ARGV[3] ~= '' and revision ~= ARGV[3] then
            return
        end
        local users = redis.call('HGETALL', KEYS[1])
        local expected_head = tonumber(ARGV[4])
        local position
        for i = 1, #users, 2 do
            if expected_head and tonumber(users[i]) < expected_head then
                return
            end
            if users[i + 1] == ARGV[1] then
                position = users[i]
            end
        end
        if expected_head and tonumber(position) ~= expected_head then
            return
        end
        redis.call('SREM', KEYS[2], ARGV[2])
        if position then
            redis.call('HDEL', KEYS[1], position)
            return tonumber(position)
        end
        """
        return await self.r.eval(
            script, 3, self._queue_key(subject), f"user_queues:{user_id}", self._meta_key(subject),
            str(user_id), subject, revision, str(expected_head) if expected_head is not None else "",
        )

    async def is_position_taken(self, subject: str, position: int) -> bool:
        return await self.r.hexists(self._queue_key(subject), str(position))

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

    async def move_user(self, subject: str, user_id: int, new_position: int) -> int:
        """
        Atomically move user to new_position in Redis via Lua script.
        Returns:
            > 0: old position (successful move)
            0: user already at new_position
            -1: new_position already taken
            -2: user not in queue
            -3: queue not found
            -4: queue paused
        """
        script = """
        local queue_key = KEYS[1]
        local user_id = ARGV[1]
        local new_pos = ARGV[2]
        if redis.call('EXISTS', KEYS[2]) == 0 then
            return -3
        end
        if redis.call('HGET', KEYS[2], 'is_paused') == 'true' then
            return -4
        end

        local all = redis.call('hgetall', queue_key)
        local old_pos = nil
        for i = 1, #all, 2 do
            if all[i+1] == user_id then
                old_pos = all[i]
                break
            end
        end

        if not old_pos then
            return -2
        end

        if old_pos == new_pos then
            return 0
        end

        if redis.call('hexists', queue_key, new_pos) == 1 then
            return -1
        end

        redis.call('hset', queue_key, new_pos, user_id)
        redis.call('hdel', queue_key, old_pos)
        return tonumber(old_pos)
        """
        res = await self.r.eval(
            script, 2, self._queue_key(subject), self._meta_key(subject),
            str(user_id), str(new_position),
        )
        return int(res)

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

    async def swap(self, subject: str, pos1: int, pos2: int, *, revision: str) -> bool:
        """Atomically exchange two occupied positions if their contents are unchanged."""
        key = self._queue_key(subject)
        script = """
        local revision = redis.call('HGET', KEYS[2], 'revision') or redis.call('HGET', KEYS[2], 'created_at')
        if revision ~= ARGV[5] or redis.call('HGET', KEYS[2], 'is_paused') == 'true' then
            return 0
        end
        local first = redis.call('HGET', KEYS[1], ARGV[1])
        local second = redis.call('HGET', KEYS[1], ARGV[2])
        if not first or not second or first ~= ARGV[3] or second ~= ARGV[4] then
            return 0
        end
        redis.call('HSET', KEYS[1], ARGV[1], second, ARGV[2], first)
        return 1
        """
        first, second = await self.r.hmget(key, str(pos1), str(pos2))
        if not first or not second:
            return False
        return bool(await self.r.eval(
            script, 2, key, self._meta_key(subject), str(pos1), str(pos2), first, second, revision,
        ))

    async def clear(self, subject: str, revision: str, *, delete_queue: bool) -> bool:
        """Clear a specific queue revision and invalidate its outstanding swaps."""
        meta_key = self._meta_key(subject)
        queue_key = self._queue_key(subject)
        async with self.r.pipeline() as pipe:
            while True:
                try:
                    await pipe.watch(meta_key, queue_key)
                    if self.get_revision(await pipe.hgetall(meta_key)) != revision:
                        return False
                    users = await pipe.hvals(queue_key)
                    pipe.multi()
                    for uid in users:
                        pipe.srem(f"user_queues:{uid}", subject)
                    pipe.delete(queue_key)
                    if delete_queue:
                        pipe.delete(meta_key, self._history_key(subject))
                        pipe.srem("active_queues", subject)
                    else:
                        pipe.hset(meta_key, "revision", uuid4().hex)
                    await pipe.execute()
                    return True
                except WatchError:
                    continue

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
        queue_date: str | None = None,
    ) -> dict | None:
        key = self._meta_key(subject)
        now = datetime.now(timezone.utc).isoformat()
        ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL_SECONDS
        mapping = {
            "subject": subject,
            "subject_name": subject_name,
            "queue_type": queue_type,
            "created_by_tg_id": str(created_by_tg_id),
            "created_at": now,
            "revision": uuid4().hex,
            "is_paused": "false",
        }
        if auto_delete_at:
            mapping["auto_delete_at"] = auto_delete_at
        if queue_date:
            mapping["queue_date"] = queue_date

        queue_key = self._queue_key(subject)
        async with self.r.pipeline() as pipe:
            while True:
                try:
                    await pipe.watch(key, queue_key)
                    if await pipe.exists(key):
                        return None
                    old_users = await pipe.hvals(queue_key)
                    pipe.multi()
                    for uid in old_users:
                        pipe.srem(f"user_queues:{uid}", subject)
                    pipe.delete(queue_key, self._history_key(subject))
                    pipe.hset(key, mapping=mapping)
                    pipe.expire(key, ttl)
                    pipe.sadd("active_queues", subject)
                    await pipe.execute()
                    return mapping
                except WatchError:
                    continue

    async def update_queue_details(
        self, subject: str, queue_type: str, queue_date: str | None, *, revision: str,
    ) -> bool:
        script = """
        local revision = redis.call('HGET', KEYS[1], 'revision') or redis.call('HGET', KEYS[1], 'created_at')
        if revision ~= ARGV[3] then
            return 0
        end
        redis.call('HSET', KEYS[1], 'queue_type', ARGV[1])
        if ARGV[2] == '' then
            redis.call('HDEL', KEYS[1], 'queue_date')
        else
            redis.call('HSET', KEYS[1], 'queue_date', ARGV[2])
        end
        return 1
        """
        return bool(await self.r.eval(
            script, 1, self._meta_key(subject), queue_type, queue_date or "", revision,
        ))

    async def update_auto_delete(
        self,
        subject: str,
        auto_delete_at: str | None,
        ttl_seconds: int | None = None,
        *,
        revision: str,
    ) -> bool:
        key = self._meta_key(subject)
        queue_key = self._queue_key(subject)
        history_key = self._history_key(subject)
        ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL_SECONDS
        script = """
        local revision = redis.call('HGET', KEYS[1], 'revision') or redis.call('HGET', KEYS[1], 'created_at')
        if revision ~= ARGV[3] then
            return 0
        end
        if ARGV[1] == '' then
            redis.call('HDEL', KEYS[1], 'auto_delete_at')
        else
            redis.call('HSET', KEYS[1], 'auto_delete_at', ARGV[1])
        end
        for i = 1, #KEYS do
            redis.call('EXPIRE', KEYS[i], ARGV[2])
        end
        return 1
        """
        return bool(await self.r.eval(
            script, 3, key, queue_key, history_key, auto_delete_at or "", str(ttl), revision,
        ))

    async def get_queue_meta(self, subject: str) -> dict | None:
        key = self._meta_key(subject)
        data = await self.r.hgetall(key)
        return data if data else None

    async def set_queue_pause(self, subject: str, paused: bool, *, revision: str) -> bool:
        script = """
        local revision = redis.call('HGET', KEYS[1], 'revision') or redis.call('HGET', KEYS[1], 'created_at')
        if revision ~= ARGV[2] then
            return 0
        end
        redis.call('HSET', KEYS[1], 'is_paused', ARGV[1])
        return 1
        """
        return bool(await self.r.eval(
            script, 1, self._meta_key(subject), "true" if paused else "false", revision,
        ))

    async def is_queue_paused(self, subject: str) -> bool:
        key = self._meta_key(subject)
        val = await self.r.hget(key, "is_paused")
        return val == "true"

    async def get_all_active_queue_keys(self) -> list[str]:
        return list(await self.r.smembers("active_queues"))

    async def cleanup_expired_queues(self) -> list[str]:
        """Checks all active queues for expiration, deletes expired ones, and returns their keys."""
        members = await self.r.smembers("active_queues")
        deleted = []
        for subject in members:
            meta_key = self._meta_key(subject)
            queue_key = self._queue_key(subject)
            async with self.r.pipeline() as pipe:
                try:
                    await pipe.watch(meta_key, queue_key, "active_queues")
                    if not await pipe.sismember("active_queues", subject):
                        continue
                    meta = await pipe.hgetall(meta_key)
                    deadline = parse_utc_datetime(meta.get("auto_delete_at"))
                    if meta.get("created_at") and (deadline is None or deadline > datetime.now(timezone.utc)):
                        continue
                    users = await pipe.hvals(queue_key)
                    pipe.multi()
                    for uid in users:
                        pipe.srem(f"user_queues:{uid}", subject)
                    pipe.delete(meta_key, queue_key, self._history_key(subject))
                    pipe.srem("active_queues", subject)
                    await pipe.execute()
                    deleted.append(subject)
                except WatchError:
                    continue
        return deleted

    # ──────────────────── User Participation Index ────────────────────

    async def get_user_queues(self, user_id: int) -> list[str]:
        user_key = f"user_queues:{user_id}"
        members = await self.r.smembers(user_key)
        active = []
        for subject in members:
            script = """
            if redis.call('EXISTS', KEYS[2]) == 1 then
                local users = redis.call('HVALS', KEYS[1])
                for i = 1, #users do
                    if users[i] == ARGV[1] then
                        return 1
                    end
                end
            end
            redis.call('SREM', KEYS[3], ARGV[2])
            return 0
            """
            if await self.r.eval(
                script, 3, self._queue_key(subject), self._meta_key(subject), user_key,
                str(user_id), subject,
            ):
                active.append(subject)
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

        script = """
        local deadline = redis.call('PEXPIRETIME', KEYS[2])
        if deadline == -2 then
            return
        end
        redis.call('LPUSH', KEYS[1], ARGV[1])
        redis.call('LTRIM', KEYS[1], 0, ARGV[2])
        if deadline > 0 then
            redis.call('PEXPIREAT', KEYS[1], deadline)
        else
            redis.call('EXPIRE', KEYS[1], ARGV[3])
        end
        """
        await self.r.eval(
            script, 2, key, self._meta_key(subject), entry,
            str(MAX_HISTORY_ITEMS - 1), str(DEFAULT_TTL_SECONDS),
        )

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
