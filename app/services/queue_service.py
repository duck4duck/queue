from datetime import datetime, timezone
from app.repositories.queue_repository import QueueRepository
from app.repositories.swap_request_repository import SwapRequestRepository
from app.repositories.subject_repository import SubjectRepository
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.core.config import settings
from app.core.datetime_utils import parse_utc_datetime
from app.core.logger import logger
from app.schemas.exception import (
    UserAlreadyInQueue,
    UserNotInQueue,
    PositionTaken,
    PositionEmpty,
    UserNotFound,
    InvalidPosition,
    Forbidden,
    QueueAlreadyExists,
    QueueNotFound,
    QueuePaused,
    SubjectNotFound,
)
from app.schemas.queue import (
    QueueUserInfo,
    QueueResponse,
    QueueMetaInfo,
    QueueListResponse,
    MyPositionResponse,
    SwapCandidate,
    QueueStatsResponse,
)

AVERAGE_MINUTES_PER_SUBMISSION = 8


class QueueService:
    def __init__(self, db: AsyncSession, r: Redis):
        self.user_service = UserService(db)
        self.subject_repo = SubjectRepository(db)
        self.queue_repo = QueueRepository(r)
        self.swap_repo = SwapRequestRepository(r)
        self.max_positions = settings.default_max_positions

    @staticmethod
    def _parse_auto_delete_ttl(auto_delete_at: str | None) -> tuple[str | None, int | None]:
        """Parse expiration datetime and calculate TTL seconds."""
        if not auto_delete_at:
            return None, None
        exp_dt = parse_utc_datetime(auto_delete_at)
        if exp_dt is None:
            logger.warning(f"Invalid auto_delete_at format '{auto_delete_at}'")
            return None, None
        diff = int((exp_dt - datetime.now(timezone.utc)).total_seconds())
        ttl_seconds = diff if diff > 0 else 30
        return auto_delete_at, ttl_seconds

    def _build_meta_info(
        self,
        subject: str,
        meta: dict | None,
        creator_name: str | None = None,
        taken_positions: int = 0,
        my_position: int | None = None,
        is_paused: bool | None = None,
    ) -> QueueMetaInfo:
        """Construct a standardized QueueMetaInfo schema from raw metadata."""
        if not meta:
            meta = {}
        paused = is_paused if is_paused is not None else (meta.get("is_paused") == "true")
        created_by_tg_id = int(meta.get("created_by_tg_id", 0))

        return QueueMetaInfo(
            subject=subject,
            subject_name=meta.get("subject_name", subject),
            queue_type=meta.get("queue_type", ""),
            created_by_tg_id=created_by_tg_id,
            created_by_name=creator_name,
            created_at=meta.get("created_at", datetime.now(timezone.utc).isoformat()),
            auto_delete_at=meta.get("auto_delete_at"),
            taken_positions=taken_positions,
            total_positions=self.max_positions,
            is_paused=paused,
            my_position=my_position,
        )

    async def get_first_in_line(self, subject: str) -> tuple[int, int] | None:
        """Get the participant currently at the head of the queue."""
        return await self.queue_repo.get_first_in_line(subject)

    # ──────────────────── Queue Lifecycle ────────────────────

    async def create_queue(
        self,
        subject_name: str,
        queue_type: str,
        created_by_tg_id: int,
        auto_delete_at: str | None = None,
    ) -> QueueMetaInfo:
        """Create a new named queue for a subject (e.g. 'Math:Lab 1') with optional auto-deletion time."""
        creator = await self.user_service.get_user_by_tg_id(created_by_tg_id)
        if creator is None:
            raise UserNotFound("Пользователь не найден!")

        db_subject = await self.subject_repo.get_by_name(subject_name)
        if db_subject is None:
            raise SubjectNotFound(
                f"Предмет '{subject_name}' не найден в каталоге! Сначала создайте предмет."
            )

        subject_key = f"{subject_name}:{queue_type}"

        if await self.queue_repo.meta_exists(subject_key):
            raise QueueAlreadyExists(f"Очередь '{subject_key}' уже создана!")

        auto_delete_at, ttl_seconds = self._parse_auto_delete_ttl(auto_delete_at)

        await self.queue_repo.create_queue_meta(
            subject=subject_key,
            subject_name=subject_name,
            queue_type=queue_type,
            created_by_tg_id=created_by_tg_id,
            auto_delete_at=auto_delete_at,
            ttl_seconds=ttl_seconds,
        )

        await self.queue_repo.log_event(
            subject_key,
            "create",
            f"Очередь создана пользователем {creator.name}",
        )
        logger.info(
            f"Queue created: '{subject_key}' by {creator.name} (tg_id={created_by_tg_id}), "
            f"auto_delete_at={auto_delete_at}"
        )

        meta = await self.queue_repo.get_queue_meta(subject_key)
        return self._build_meta_info(
            subject=subject_key,
            meta=meta,
            creator_name=creator.name,
            taken_positions=0,
            is_paused=False,
        )

    async def _check_creator(self, subject: str, user_tg_id: int):
        user = await self.user_service.get_user_by_tg_id(user_tg_id)
        if user is None:
            raise UserNotFound("Пользователь не найден!")
        meta = await self.queue_repo.get_queue_meta(subject)
        if meta is None:
            raise QueueNotFound("Очередь не найдена!")
        created_by = int(meta.get("created_by_tg_id", 0))
        if created_by != user_tg_id:
            raise Forbidden("Только создатель очереди имеет доступ к этому действию!")
        return meta, user

    async def delete_queue(self, subject: str, creator_tg_id: int) -> None:
        """Only the creator can delete the entire queue."""
        meta, user = await self._check_creator(subject, creator_tg_id)

        queue = await self.queue_repo.get_queue(subject)
        for uid in queue.values():
            await self.swap_repo.cancel_all_for_user_in_queue(subject, uid)
            await self.queue_repo.remove_user_from_index(uid, subject)

        await self.queue_repo.clear(subject)
        logger.info(f"Queue deleted: '{subject}' by creator {user.name} (tg_id={creator_tg_id})")

    async def clear_queue(self, subject: str, creator_tg_id: int) -> QueueResponse:
        """Only the creator can clear all students from the queue."""
        meta, user = await self._check_creator(subject, creator_tg_id)

        queue = await self.queue_repo.get_queue(subject)
        for uid in queue.values():
            await self.swap_repo.cancel_all_for_user_in_queue(subject, uid)
            await self.queue_repo.remove_user_from_index(uid, subject)

        await self.queue_repo.clear_participants(subject)
        await self.queue_repo.log_event(subject, "clear", f"Очередь очищена создателем {user.name}")
        logger.info(f"Queue '{subject}' cleared by creator {user.name}")

        return await self.get_queue(subject)

    async def pause_queue(
        self, subject: str, creator_tg_id: int, paused: bool
    ) -> QueueMetaInfo:
        """Only the creator can pause or resume queue."""
        meta, user = await self._check_creator(subject, creator_tg_id)

        await self.queue_repo.set_queue_pause(subject, paused)
        status_text = "Очередь приостановлена" if paused else "Очередь возобновлена"
        await self.queue_repo.log_event(
            subject, "pause" if paused else "resume", f"{status_text} создателем {user.name}"
        )
        logger.info(f"Queue '{subject}' pause={paused} by creator {user.name}")

        meta = await self.queue_repo.get_queue_meta(subject)
        taken = await self.queue_repo.size(subject)
        my_pos = await self.queue_repo.get_position(subject, creator_tg_id)

        return self._build_meta_info(
            subject=subject,
            meta=meta,
            taken_positions=taken,
            my_position=my_pos,
            is_paused=paused,
        )

    async def update_auto_delete(
        self, subject: str, creator_tg_id: int, auto_delete_at: str | None
    ) -> QueueMetaInfo:
        """Only the creator can change or clear the queue's auto-deletion time."""
        meta, user = await self._check_creator(subject, creator_tg_id)

        auto_delete_at, ttl_seconds = self._parse_auto_delete_ttl(auto_delete_at)
        await self.queue_repo.update_auto_delete(subject, auto_delete_at, ttl_seconds)

        event_text = (
            f"Автоудаление очереди установлено на {auto_delete_at}"
            if auto_delete_at
            else "Автоудаление очереди отключено"
        )
        await self.queue_repo.log_event(subject, "update_auto_delete", f"{event_text} создателем {user.name}")
        logger.info(f"Queue '{subject}' auto_delete_at updated to {auto_delete_at} by creator {user.name}")

        meta = await self.queue_repo.get_queue_meta(subject)
        taken = await self.queue_repo.size(subject)
        my_pos = await self.queue_repo.get_position(subject, creator_tg_id)

        return self._build_meta_info(
            subject=subject,
            meta=meta,
            taken_positions=taken,
            my_position=my_pos,
        )

    async def list_queues(
        self,
        search: str | None = None,
        subject_name: str | None = None,
        is_paused: bool | None = None,
    ) -> QueueListResponse:
        """List active queues with optional filtering and search."""
        keys = await self.queue_repo.get_all_active_queue_keys()
        queues = []
        now = datetime.now(timezone.utc)
        for subject in keys:
            meta = await self.queue_repo.get_queue_meta(subject)
            if meta is None:
                continue

            auto_del = meta.get("auto_delete_at")
            if auto_del:
                exp_dt = parse_utc_datetime(auto_del)
                if exp_dt and now >= exp_dt:
                    await self.queue_repo.clear(subject)
                    continue

            subj_name = meta.get("subject_name", "")
            q_type = meta.get("queue_type", "")
            paused = meta.get("is_paused") == "true"

            # Apply filters
            if subject_name and subj_name.lower() != subject_name.lower():
                continue
            if is_paused is not None and paused != is_paused:
                continue
            if search:
                query = search.lower()
                if query not in subject.lower() and query not in subj_name.lower() and query not in q_type.lower():
                    continue

            taken = await self.queue_repo.size(subject)
            created_by_tg_id = int(meta.get("created_by_tg_id", 0))
            creator = await self.user_service.get_user_by_tg_id(created_by_tg_id)

            queues.append(
                self._build_meta_info(
                    subject=subject,
                    meta=meta,
                    creator_name=creator.name if creator else None,
                    taken_positions=taken,
                    is_paused=paused,
                )
            )

        return QueueListResponse(queues=queues, total=len(queues))

    async def list_queues_by_subject(self, subject_name: str) -> QueueListResponse:
        return await self.list_queues(subject_name=subject_name)

    # ──────────────────── Participation (Join / Leave) ────────────────────

    async def join(self, subject: str, user_id: int, position: int) -> QueueResponse:
        if await self.queue_repo.is_queue_paused(subject):
            raise QueuePaused("Очередь приостановлена! Запись временно закрыта.")

        user = await self.user_service.get_user_by_tg_id(user_id)
        if user is None:
            raise UserNotFound("Пользователь не найден!")

        if position < 1 or position > self.max_positions:
            raise InvalidPosition(f"Некорректный номер позиции. Число должно быть от 1 до {self.max_positions}!")

        if await self.queue_repo.is_user_in_queue(subject, user_id):
            raise UserAlreadyInQueue("Вы уже находитесь в этой очереди!")

        acquired = await self.queue_repo.add(subject, user_id, position)
        if not acquired:
            raise PositionTaken(f"Позиция {position} уже занята другим участником!")

        await self.queue_repo.add_user_to_index(user_id, subject)
        await self.queue_repo.log_event(subject, "join", f"{user.name} занял(а) место #{position}")
        logger.info(f"User {user.name} (tg_id={user_id}) joined '{subject}' at pos #{position}")

        return await self.get_queue(subject)

    async def leave(self, subject: str, user_id: int, position: int | None = None) -> QueueResponse:
        user = await self.user_service.get_user_by_tg_id(user_id)
        if user is None:
            raise UserNotFound("Пользователь не найден!")

        if not await self.queue_repo.is_user_in_queue(subject, user_id):
            raise UserNotInQueue("Вы не состоите в этой очереди!")

        await self.swap_repo.cancel_all_for_user_in_queue(subject, user_id)
        freed_pos = await self.queue_repo.remove_by_user(subject, user_id)
        await self.queue_repo.remove_user_from_index(user_id, subject)

        await self.queue_repo.log_event(subject, "leave", f"{user.name} освободил(а) место #{freed_pos}")
        logger.info(f"User {user.name} (tg_id={user_id}) left '{subject}' (was pos #{freed_pos})")

        return await self.get_queue(subject)

    # ──────────────────── Curator Actions: Kick & Advance ────────────────────

    async def kick(
        self, subject: str, creator_tg_id: int, target_tg_id: int
    ) -> QueueResponse:
        meta, user = await self._check_creator(subject, creator_tg_id)

        target = await self.user_service.get_user_by_tg_id(target_tg_id)
        target_name = target.name if target else f"ID {target_tg_id}"

        if not await self.queue_repo.is_user_in_queue(subject, target_tg_id):
            raise UserNotInQueue("Целевой пользователь не состоит в этой очереди!")

        await self.swap_repo.cancel_all_for_user_in_queue(subject, target_tg_id)
        freed_pos = await self.queue_repo.remove_by_user(subject, target_tg_id)
        await self.queue_repo.remove_user_from_index(target_tg_id, subject)

        await self.queue_repo.log_event(
            subject,
            "kick",
            f"{target_name} (место #{freed_pos}) исключен(а) создателем {user.name}",
        )
        logger.info(f"Target {target_name} kicked from '{subject}' by creator {user.name}")

        return await self.get_queue(subject)

    async def advance_queue(
        self, subject: str, creator_tg_id: int
    ) -> tuple[int, QueueResponse]:
        meta, user = await self._check_creator(subject, creator_tg_id)

        first_in_line = await self.queue_repo.get_first_in_line(subject)
        if first_in_line is None:
            raise PositionEmpty("В очереди никого нет!")

        pos, user_id = first_in_line
        completed_user = await self.user_service.get_user_by_tg_id(user_id)
        user_name = completed_user.name if completed_user else f"ID {user_id}"

        await self.swap_repo.cancel_all_for_user_in_queue(subject, user_id)
        await self.queue_repo.remove_by_user(subject, user_id)
        await self.queue_repo.remove_user_from_index(user_id, subject)

        await self.queue_repo.log_event(
            subject,
            "advance",
            f"Сдача завершена: {user_name} сдал(а) работу! Очередь сдвинута.",
        )
        logger.info(f"Queue '{subject}' advanced: {user_name} (tg_id={user_id}) completed by creator {user.name}")

        updated_queue = await self.get_queue(subject)
        return user_id, updated_queue

    # ──────────────────── Queue State Inspection ────────────────────

    async def get_queue(self, subject: str) -> QueueResponse:
        meta = await self.queue_repo.get_queue_meta(subject)
        if meta and meta.get("auto_delete_at"):
            exp_dt = parse_utc_datetime(meta["auto_delete_at"])
            if exp_dt and datetime.now(timezone.utc) >= exp_dt:
                await self.queue_repo.clear(subject)
                raise QueueNotFound("Очередь была автоматически удалена по истечении срока действия!")

        queue = await self.queue_repo.get_queue(subject)
        is_paused = await self.queue_repo.is_queue_paused(subject)

        if not queue:
            positions = [
                QueueUserInfo(position=pos, is_free=True)
                for pos in range(1, self.max_positions + 1)
            ]
            return QueueResponse(
                subject=subject,
                queue=positions,
                total_positions=self.max_positions,
                taken_positions=0,
                is_paused=is_paused,
            )

        ids = list(queue.values())
        users = await self.user_service.get_by_tg_ids(ids) if ids else []
        user_map = {u.tg_id: u for u in users}

        positions = []
        for position in range(1, self.max_positions + 1):
            uid = queue.get(position)
            if uid:
                user = user_map.get(uid)
                name = user.name if user else f"Участник #{uid}"
                photo_url = user.photo_url if user else None
                positions.append(
                    QueueUserInfo(
                        position=position,
                        tg_id=uid,
                        name=name,
                        photo_url=photo_url,
                        is_free=False,
                    )
                )
            else:
                positions.append(QueueUserInfo(position=position, is_free=True))

        return QueueResponse(
            queue=positions,
            taken_positions=len(queue),
            subject=subject,
            total_positions=self.max_positions,
            is_paused=is_paused,
        )

    async def get_user_queues(self, tg_id: int) -> list[QueueMetaInfo]:
        subjects = await self.queue_repo.get_user_queues(tg_id)
        result = []
        now = datetime.now(timezone.utc)
        for subject in subjects:
            meta = await self.queue_repo.get_queue_meta(subject)
            if not meta:
                continue

            auto_del = meta.get("auto_delete_at")
            if auto_del:
                exp_dt = parse_utc_datetime(auto_del)
                if exp_dt and now >= exp_dt:
                    await self.queue_repo.clear(subject)
                    continue

            taken = await self.queue_repo.size(subject)
            is_paused = (meta.get("is_paused") == "true") if meta else False
            my_pos = await self.queue_repo.get_position(subject, tg_id)
            result.append(
                self._build_meta_info(
                    subject=subject,
                    meta=meta,
                    taken_positions=taken,
                    is_paused=is_paused,
                    my_position=my_pos,
                )
            )
        return result

    # ──────────────────── Student Helper: My Position ────────────────────

    async def get_my_position(self, subject: str, tg_id: int) -> MyPositionResponse:
        """Calculate how many people are in front of the student and estimate wait time."""
        queue = await self.queue_repo.get_queue(subject)
        my_pos = await self.queue_repo.get_position(subject, tg_id)

        if my_pos is None:
            return MyPositionResponse(in_queue=False, subject=subject)

        # Count occupied slots ahead of me
        people_ahead = sum(1 for pos in queue.keys() if pos < my_pos)
        is_next = people_ahead == 0
        est_wait = people_ahead * AVERAGE_MINUTES_PER_SUBMISSION

        return MyPositionResponse(
            in_queue=True,
            subject=subject,
            position=my_pos,
            people_ahead=people_ahead,
            is_next=is_next,
            estimated_wait_minutes=est_wait,
        )

    # ──────────────────── Swap Candidates ────────────────────

    async def get_swap_candidates(self, subject: str, tg_id: int) -> list[SwapCandidate]:
        """Get all participants available for swapping (both ahead and behind)."""
        my_pos = await self.queue_repo.get_position(subject, tg_id)
        if my_pos is None:
            raise UserNotInQueue("Вы не состоите в этой очереди!")

        queue = await self.queue_repo.get_queue(subject)
        candidates_positions = {pos: uid for pos, uid in queue.items() if pos != my_pos}

        if not candidates_positions:
            return []

        ids = list(candidates_positions.values())
        users = await self.user_service.get_by_tg_ids(ids)
        user_map = {u.tg_id: u for u in users}

        candidates = []
        for pos in sorted(candidates_positions.keys()):
            uid = candidates_positions[pos]
            user = user_map.get(uid)
            name = user.name if user else f"Участник #{uid}"
            photo_url = user.photo_url if user else None

            candidates.append(
                SwapCandidate(
                    position=pos,
                    tg_id=uid,
                    name=name,
                    photo_url=photo_url,
                    slots_difference=my_pos - pos,
                )
            )

        return candidates

    # ──────────────────── Queue Statistics ────────────────────

    async def get_stats(self, subject: str) -> QueueStatsResponse:
        """Get comprehensive real-time statistics for the queue."""
        queue = await self.queue_repo.get_queue(subject)
        is_paused = await self.queue_repo.is_queue_paused(subject)
        active_swaps = await self.swap_repo.count_active_for_queue(subject)

        taken = len(queue)
        free = self.max_positions - taken
        pct = round((taken / self.max_positions) * 100, 1)

        return QueueStatsResponse(
            subject=subject,
            total_positions=self.max_positions,
            taken_positions=taken,
            free_positions=free,
            occupancy_percent=pct,
            is_paused=is_paused,
            active_swap_requests=active_swaps,
        )

    async def get_history(self, subject: str, limit: int = 20) -> list[dict]:
        return await self.queue_repo.get_history(subject, limit)

    # ──────────────────── Direct Swap (Legacy) ────────────────────

    async def swap(self, pos1: int, pos2: int, subject: str) -> QueueResponse:
        if await self.queue_repo.is_queue_paused(subject):
            raise QueuePaused("Очередь приостановлена! Обмен временно закрыт.")

        if pos1 == pos2:
            raise InvalidPosition("Нельзя обменяться с самим собой!")

        if (
            pos1 < 1
            or pos1 > self.max_positions
            or pos2 < 1
            or pos2 > self.max_positions
        ):
            raise InvalidPosition("Некорректный номер позиции!")

        if not await self.queue_repo.is_position_taken(subject, pos1):
            raise UserNotInQueue(f"На позиции {pos1} никого нет!")

        if not await self.queue_repo.is_position_taken(subject, pos2):
            raise UserNotInQueue(f"На позиции {pos2} никого нет!")

        await self.queue_repo.swap(subject, pos1, pos2)
        await self.queue_repo.log_event(subject, "swap", f"Обмен местами: #{pos1} ↔ #{pos2}")
        logger.info(f"Direct swap in '{subject}': #{pos1} ↔ #{pos2}")

        return await self.get_queue(subject)
