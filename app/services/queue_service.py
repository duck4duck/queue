from app.repositories.queue_repository import QueueRepository
from app.repositories.swap_request_repository import SwapRequestRepository
from app.repositories.subject_repository import SubjectRepository
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.core.config import settings
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
        self.r = QueueRepository(r)
        self.swap_repo = SwapRequestRepository(r)
        self.max_positions = settings.default_max_positions

    # ──────────────────── Queue Lifecycle ────────────────────

    async def create_queue(
        self, subject_name: str, queue_type: str, created_by_tg_id: int
    ) -> QueueMetaInfo:
        """Create a new named queue for a subject (e.g. 'Math:Lab 1')."""
        creator = await self.user_service.get_user_by_tg_id(created_by_tg_id)
        if creator is None:
            raise UserNotFound("Пользователь не найден!")

        db_subject = await self.subject_repo.get_by_name(subject_name)
        if db_subject is None:
            raise SubjectNotFound(
                f"Предмет '{subject_name}' не найден в каталоге! Сначала создайте предмет."
            )

        subject_key = f"{subject_name}:{queue_type}"

        if await self.r.meta_exists(subject_key):
            raise QueueAlreadyExists(f"Очередь '{subject_key}' уже создана!")

        await self.r.create_queue_meta(
            subject=subject_key,
            subject_name=subject_name,
            queue_type=queue_type,
            created_by_tg_id=created_by_tg_id,
        )

        await self.r.log_event(
            subject_key,
            "create",
            f"Очередь создана пользователем {creator.name}",
        )
        logger.info(f"Queue created: '{subject_key}' by {creator.name} (tg_id={created_by_tg_id})")

        meta = await self.r.get_queue_meta(subject_key)
        return QueueMetaInfo(
            subject=subject_key,
            subject_name=subject_name,
            queue_type=queue_type,
            created_by_tg_id=created_by_tg_id,
            created_by_name=creator.name,
            created_at=meta["created_at"],
            taken_positions=0,
            total_positions=self.max_positions,
            is_paused=False,
        )

    async def delete_queue(self, subject: str, curator_tg_id: int) -> None:
        """Curator deletes an entire queue."""
        curator = await self.user_service.get_user_by_tg_id(curator_tg_id)
        if curator is None:
            raise UserNotFound("Пользователь не найден!")
        if curator.role != "curator":
            raise Forbidden("Только курирующий может удалить очередь!")

        await self.r.clear(subject)
        logger.info(f"Queue deleted: '{subject}' by curator {curator.name} (tg_id={curator_tg_id})")

    async def clear_queue(self, subject: str, curator_tg_id: int) -> QueueResponse:
        """Curator clears all students from the queue, preserving metadata and settings."""
        curator = await self.user_service.get_user_by_tg_id(curator_tg_id)
        if curator is None:
            raise UserNotFound("Пользователь не найден!")
        if curator.role != "curator":
            raise Forbidden("Только курирующий может очистить очередь!")

        queue = await self.r.get_queue(subject)
        for uid in queue.values():
            await self.swap_repo.cancel_all_for_user_in_queue(subject, uid)
            await self.r.remove_user_from_index(uid, subject)

        await self.r.clear_participants(subject)
        await self.r.log_event(subject, "clear", f"Очередь полностью очищена куратором {curator.name}")
        logger.info(f"Queue '{subject}' cleared by curator {curator.name}")

        return await self.get_queue(subject)

    async def pause_queue(
        self, subject: str, curator_tg_id: int, paused: bool
    ) -> QueueMetaInfo:
        """Curator pauses or resumes queue."""
        curator = await self.user_service.get_user_by_tg_id(curator_tg_id)
        if curator is None:
            raise UserNotFound("Пользователь не найден!")
        if curator.role != "curator":
            raise Forbidden("Только курирующий может изменить статус очереди!")

        await self.r.set_queue_pause(subject, paused)
        status_text = "Очередь приостановлена" if paused else "Очередь возобновлена"
        await self.r.log_event(subject, "pause" if paused else "resume", f"{status_text} куратором {curator.name}")
        logger.info(f"Queue '{subject}' pause={paused} by curator {curator.name}")

        meta = await self.r.get_queue_meta(subject)
        taken = await self.r.size(subject)

        return QueueMetaInfo(
            subject=subject,
            subject_name=meta.get("subject_name", subject) if meta else subject,
            queue_type=meta.get("queue_type", "") if meta else "",
            created_by_tg_id=int(meta.get("created_by_tg_id", 0)) if meta else 0,
            created_at=meta.get("created_at", "") if meta else "",
            taken_positions=taken,
            total_positions=self.max_positions,
            is_paused=paused,
        )

    async def list_queues(
        self,
        search: str | None = None,
        subject_name: str | None = None,
        is_paused: bool | None = None,
    ) -> QueueListResponse:
        """List active queues with optional filtering and search."""
        keys = await self.r.get_all_active_queue_keys()
        queues = []
        for subject in keys:
            meta = await self.r.get_queue_meta(subject)
            if meta is None:
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

            taken = await self.r.size(subject)
            created_by_tg_id = int(meta.get("created_by_tg_id", 0))
            creator = await self.user_service.get_user_by_tg_id(created_by_tg_id)

            queues.append(
                QueueMetaInfo(
                    subject=subject,
                    subject_name=subj_name,
                    queue_type=q_type,
                    created_by_tg_id=created_by_tg_id,
                    created_by_name=creator.name if creator else None,
                    created_at=meta.get("created_at", ""),
                    taken_positions=taken,
                    total_positions=self.max_positions,
                    is_paused=paused,
                )
            )

        return QueueListResponse(queues=queues, total=len(queues))

    async def list_queues_by_subject(self, subject_name: str) -> QueueListResponse:
        return await self.list_queues(subject_name=subject_name)

    # ──────────────────── Participation (Join / Leave) ────────────────────

    async def join(self, subject: str, user_id: int, position: int) -> QueueResponse:
        if await self.r.is_queue_paused(subject):
            raise QueuePaused("Очередь приостановлена! Запись временно закрыта.")

        user = await self.user_service.get_user_by_tg_id(user_id)
        if user is None:
            raise UserNotFound("Пользователь не найден!")

        if position < 1 or position > self.max_positions:
            raise InvalidPosition(f"Некорректный номер позиции. Число должно быть от 1 до {self.max_positions}!")

        if await self.r.is_user_in_queue(subject, user_id):
            raise UserAlreadyInQueue("Вы уже находитесь в этой очереди!")

        # Atomic slot reservation via HSETNX to prevent race conditions
        acquired = await self.r.add(subject, user_id, position)
        if not acquired:
            raise PositionTaken(f"Позиция {position} уже занята другим участником!")

        await self.r.add_user_to_index(user_id, subject)
        await self.r.log_event(subject, "join", f"{user.name} занял(а) место #{position}")
        logger.info(f"User {user.name} (tg_id={user_id}) joined '{subject}' at pos #{position}")

        return await self.get_queue(subject)

    async def leave(self, subject: str, user_id: int, position: int | None = None) -> QueueResponse:
        user = await self.user_service.get_user_by_tg_id(user_id)
        if user is None:
            raise UserNotFound("Пользователь не найден!")

        if not await self.r.is_user_in_queue(subject, user_id):
            raise UserNotInQueue("Пользователь не состоит в очереди!")

        await self.swap_repo.cancel_all_for_user_in_queue(subject, user_id)
        freed_pos = await self.r.remove_by_user(subject, user_id)
        await self.r.remove_user_from_index(user_id, subject)

        await self.r.log_event(subject, "leave", f"{user.name} освободил(а) место #{freed_pos}")
        logger.info(f"User {user.name} (tg_id={user_id}) left '{subject}' (freed #{freed_pos})")

        return await self.get_queue(subject)

    # ──────────────────── Curator Actions: Kick & Advance ────────────────────

    async def kick(
        self, subject: str, curator_tg_id: int, target_tg_id: int
    ) -> QueueResponse:
        curator = await self.user_service.get_user_by_tg_id(curator_tg_id)
        if curator is None:
            raise UserNotFound("Курирующий не найден!")
        if curator.role != "curator":
            raise Forbidden("Только курирующий может удалять пользователей из очереди!")

        target = await self.user_service.get_user_by_tg_id(target_tg_id)
        target_name = target.name if target else f"ID {target_tg_id}"

        if not await self.r.is_user_in_queue(subject, target_tg_id):
            raise UserNotInQueue("Целевой пользователь не состоит в этой очереди!")

        await self.swap_repo.cancel_all_for_user_in_queue(subject, target_tg_id)
        freed_pos = await self.r.remove_by_user(subject, target_tg_id)
        await self.r.remove_user_from_index(target_tg_id, subject)

        await self.r.log_event(
            subject,
            "kick",
            f"{target_name} (место #{freed_pos}) исключен(а) куратором {curator.name}",
        )
        logger.info(f"Target {target_name} kicked from '{subject}' by curator {curator.name}")

        return await self.get_queue(subject)

    async def advance_queue(
        self, subject: str, curator_tg_id: int
    ) -> tuple[int, QueueResponse]:
        curator = await self.user_service.get_user_by_tg_id(curator_tg_id)
        if curator is None:
            raise UserNotFound("Курирующий не найден!")
        if curator.role != "curator":
            raise Forbidden("Только курирующий может продвигать очередь!")

        first_in_line = await self.r.get_first_in_line(subject)
        if first_in_line is None:
            raise PositionEmpty("В очереди никого нет!")

        pos, user_id = first_in_line
        completed_user = await self.user_service.get_user_by_tg_id(user_id)
        user_name = completed_user.name if completed_user else f"ID {user_id}"

        await self.swap_repo.cancel_all_for_user_in_queue(subject, user_id)
        await self.r.remove_by_user(subject, user_id)
        await self.r.remove_user_from_index(user_id, subject)

        await self.r.log_event(
            subject,
            "advance",
            f"Сдача завершена: {user_name} сдал(а) работу! Очередь сдвинута.",
        )
        logger.info(f"Queue '{subject}' advanced: {user_name} (tg_id={user_id}) completed by curator {curator.name}")

        updated_queue = await self.get_queue(subject)
        return user_id, updated_queue

    # ──────────────────── Queue State Inspection ────────────────────

    async def get_queue(self, subject: str) -> QueueResponse:
        queue = await self.r.get_queue(subject)
        is_paused = await self.r.is_queue_paused(subject)

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
                # Fix phantom slot bug: always marked occupied with proper name
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
        subjects = await self.r.get_user_queues(tg_id)
        result = []
        for subject in subjects:
            meta = await self.r.get_queue_meta(subject)
            taken = await self.r.size(subject)
            is_paused = (meta.get("is_paused") == "true") if meta else False
            result.append(
                QueueMetaInfo(
                    subject=subject,
                    subject_name=meta.get("subject_name", subject) if meta else subject,
                    queue_type=meta.get("queue_type", "") if meta else "",
                    created_by_tg_id=int(meta.get("created_by_tg_id", 0)) if meta else 0,
                    created_at=meta.get("created_at", "") if meta else "",
                    taken_positions=taken,
                    total_positions=self.max_positions,
                    is_paused=is_paused,
                )
            )
        return result

    # ──────────────────── Student Helper: My Position ────────────────────

    async def get_my_position(self, subject: str, tg_id: int) -> MyPositionResponse:
        """Calculate how many people are in front of the student and estimate wait time."""
        queue = await self.r.get_queue(subject)
        my_pos = await self.r.get_position(subject, tg_id)

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
        """Get all participants who are ahead of the current user in line."""
        my_pos = await self.r.get_position(subject, tg_id)
        if my_pos is None:
            raise UserNotInQueue("Вы не состоите в этой очереди!")

        queue = await self.r.get_queue(subject)
        # Find all occupied positions ahead of me
        candidates_positions = {pos: uid for pos, uid in queue.items() if pos < my_pos}

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
        queue = await self.r.get_queue(subject)
        is_paused = await self.r.is_queue_paused(subject)
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
        return await self.r.get_history(subject, limit)

    # ──────────────────── Direct Swap (Legacy) ────────────────────

    async def swap(self, pos1: int, pos2: int, subject: str) -> QueueResponse:
        if await self.r.is_queue_paused(subject):
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

        if not await self.r.is_position_taken(subject, pos1):
            raise UserNotInQueue(f"На позиции {pos1} никого нет!")

        if not await self.r.is_position_taken(subject, pos2):
            raise UserNotInQueue(f"На позиции {pos2} никого нет!")

        await self.r.swap(subject, pos1, pos2)
        await self.r.log_event(subject, "swap", f"Обмен местами: #{pos1} ↔ #{pos2}")
        logger.info(f"Direct swap in '{subject}': #{pos1} ↔ #{pos2}")

        return await self.get_queue(subject)
