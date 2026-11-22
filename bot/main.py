import asyncio
import json
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, ChatMemberUpdated
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError

from bot.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=settings.telegram_bot_token)
dispatcher = Dispatcher()


@dispatcher.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("Бот уведомлений очередей подключен. Разрешите личные сообщения, чтобы получать запросы обмена.")


@dispatcher.my_chat_member()
async def bot_added_to_group(update: ChatMemberUpdated) -> None:
    if update.new_chat_member.status in {"member", "administrator"}:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        await redis.sadd("telegram_bot_groups", str(update.chat.id))
        await redis.aclose()
        await bot.send_message(update.chat.id, "Бот подключен. Буду публиковать ссылки на новые очереди в этой группе.")


async def publish_events() -> None:
    async with Redis.from_url(settings.redis_url, decode_responses=True) as redis:
        while True:
            try:
                async with redis.pubsub() as pubsub:
                    await pubsub.subscribe("queue_events")
                    async for message in pubsub.listen():
                        if message.get("type") != "message":
                            continue
                        try:
                            event = json.loads(message["data"])
                            if event["type"] == "swap_request":
                                await notify_swap(event)
                            elif event["type"] == "queue_created":
                                await notify_groups(event, redis)
                        except Exception:
                            logger.exception("Failed to process queue event")
            except (ConnectionError, TimeoutError):
                logger.exception("Lost Redis event subscription. Reconnecting")
                await asyncio.sleep(2)


async def notify_swap(event: dict) -> None:
    try:
        await bot.send_message(
            event["to_tg_id"],
            f"{event['from_name']} предлагает обмен в очереди «{event['subject']}»: "
            f"место #{event['from_position']} ↔ #{event['to_position']}.",
        )
    except Exception:
        logger.exception("Could not deliver private swap notification")


async def notify_groups(event: dict, redis: Redis) -> None:
    link = settings.queue_share_url_template.format(subject=event["subject"])
    text = (
        f"Создана новая очередь по предмету «{event['subject_name']}»\n"
        f"Очередь: {event['queue_type']}\n{link}"
    )
    group_ids = await redis.smembers("telegram_bot_groups")
    group_ids.update(map(str, settings.group_ids))
    for group_id in group_ids:
        try:
            await bot.send_message(group_id, text)
        except Exception:
            logger.exception("Could not announce a queue to group %s", group_id)


async def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the bot")
    event_task = asyncio.create_task(publish_events())
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        event_task.cancel()
        await asyncio.gather(event_task, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
