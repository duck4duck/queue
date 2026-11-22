import asyncio
import json
import logging
from base64 import urlsafe_b64encode
from random import choice

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.markdown import bold
from aiogram.utils.text_decorations import markdown_decoration
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError

from bot.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=settings.telegram_bot_token)
dispatcher = Dispatcher()

QUEUE_EMOJIS = ("📋", "✨", "📚", "🎯", "🚀", "🎉")
SWAP_EMOJIS = ("🔄", "🔁", "🤝", "🔀", "↔️", "🔃")


def queue_button(subject: str) -> InlineKeyboardMarkup:
    encoded_subject = urlsafe_b64encode(subject.encode("utf-8")).decode("ascii").rstrip("=")
    url = settings.queue_share_url_template.format(subject=f"b_{encoded_subject}")
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть очередь", url=url)]]
    )


def queue_title(event: dict) -> str:
    subject_name = event.get("subject_name")
    queue_type = event.get("queue_type")
    if subject_name and queue_type:
        return f"{subject_name} • {queue_type}"
    return event["subject"].replace(":", " • ", 1)


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
    sender = " ".join((event.get("from_name") or "").split()) or "Другой участник"
    positions = (
        f"Вы будете на месте #{event['from_position']}\n"
        f"{sender} станет #{event['to_position']}"
    )
    quote = markdown_decoration.blockquote(markdown_decoration.quote(positions))
    text = (
        f"{choice(SWAP_EMOJIS)} *Запрос на обмен*\n"
        f"{bold(queue_title(event))}\n\n"
        f"{quote}"
    )
    note = (event.get("message") or "").strip()
    if note:
        text += f"\n\n💬 *Комментарий*\n{markdown_decoration.quote(note)}"
    try:
        await bot.send_message(
            event["to_tg_id"],
            text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=queue_button(event["subject"]),
        )
    except Exception:
        logger.exception("Could not deliver private swap notification")


async def notify_groups(event: dict, redis: Redis) -> None:
    text = f"{bold('Новая очередь!')}\n{bold(queue_title(event))}"
    markup = queue_button(event["subject"])
    group_ids = await redis.smembers("telegram_bot_groups")
    group_ids.update(map(str, settings.group_ids))
    for group_id in group_ids:
        try:
            await bot.send_message(
                group_id,
                f"{choice(QUEUE_EMOJIS)} {text}",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=markup,
            )
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
