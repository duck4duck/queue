import asyncio
import json
import logging
from base64 import urlsafe_b64encode
from random import choice

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
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
MUTED_QUEUE_NOTIFICATIONS = "telegram_muted_queue_notifications"
NOTIFICATION_SETTINGS = "queue_notifications:settings"
NOTIFICATIONS_ON = "queue_notifications:on"
NOTIFICATIONS_OFF = "queue_notifications:off"


def mini_app_button(text: str, start_param: str) -> InlineKeyboardMarkup:
    url = settings.queue_share_url_template.format(subject=start_param)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]]
    )


def queue_button(subject: str) -> InlineKeyboardMarkup:
    encoded_subject = urlsafe_b64encode(subject.encode("utf-8")).decode("ascii").rstrip("=")
    return mini_app_button("Открыть очередь", f"b_{encoded_subject}")


def queue_title(event: dict) -> str:
    subject_name = event.get("subject_name")
    queue_type = event.get("queue_type")
    if subject_name and queue_type:
        return f"{subject_name} • {queue_type}"
    return event["subject"].replace(":", " • ", 1)


@dispatcher.message(CommandStart())
async def start(message: Message) -> None:
    text = "Бот уведомлений очередей подключен. Разрешите личные сообщения, чтобы получать запросы обмена."
    if message.chat.type == ChatType.PRIVATE:
        text += "\nНастройка уведомлений о новых очередях — /notifications."
    await message.answer(text)


def notification_settings_content(enabled: bool) -> tuple[str, InlineKeyboardMarkup]:
    status = "включены" if enabled else "отключены"
    button = InlineKeyboardButton(
        text="Отключить уведомления" if enabled else "Включить уведомления",
        callback_data=NOTIFICATIONS_OFF if enabled else NOTIFICATIONS_ON,
    )
    return f"Уведомления о новых очередях {status}.", InlineKeyboardMarkup(inline_keyboard=[[button]])


async def send_notification_settings(chat_id: int) -> None:
    async with Redis.from_url(settings.redis_url, decode_responses=True) as redis:
        muted = await redis.sismember(MUTED_QUEUE_NOTIFICATIONS, str(chat_id))
    text, markup = notification_settings_content(not muted)
    await bot.send_message(chat_id, text, reply_markup=markup)


@dispatcher.message(Command("notifications"), F.chat.type == ChatType.PRIVATE)
async def show_notification_settings(message: Message) -> None:
    await send_notification_settings(message.chat.id)


@dispatcher.callback_query(F.data == NOTIFICATION_SETTINGS, F.message.chat.type == ChatType.PRIVATE)
async def open_notification_settings(callback: CallbackQuery) -> None:
    await callback.answer()
    await send_notification_settings(callback.from_user.id)


@dispatcher.callback_query(F.data.in_({NOTIFICATIONS_ON, NOTIFICATIONS_OFF}), F.message.chat.type == ChatType.PRIVATE)
async def change_queue_notifications(callback: CallbackQuery) -> None:
    enabled = callback.data == NOTIFICATIONS_ON
    recipient = str(callback.from_user.id)
    async with Redis.from_url(settings.redis_url, decode_responses=True) as redis:
        if enabled:
            await redis.srem(MUTED_QUEUE_NOTIFICATIONS, recipient)
        else:
            await redis.sadd(MUTED_QUEUE_NOTIFICATIONS, recipient)
    text, markup = notification_settings_content(enabled)
    await callback.answer(text)
    message = callback.message
    if isinstance(message, Message) and (message.text != text or message.reply_markup != markup):
        try:
            await message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest as error:
            if "message is not modified" not in error.message.lower():
                raise


@dispatcher.my_chat_member(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}))
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
                                await notify_new_queue(event, redis)
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
            reply_markup=mini_app_button("Открыть обмены", "requests"),
        )
    except Exception:
        logger.exception("Could not deliver private swap notification")


async def notify_new_queue(event: dict, redis: Redis) -> None:
    text = f"{choice(QUEUE_EMOJIS)} {bold('Новая очередь!')}\n{bold(queue_title(event))}"
    group_markup = queue_button(event["subject"])
    private_markup = InlineKeyboardMarkup(inline_keyboard=[
        *group_markup.inline_keyboard,
        [InlineKeyboardButton(text="Настроить уведомления", callback_data=NOTIFICATION_SETTINGS)],
    ])
    group_ids = await redis.smembers("telegram_bot_groups")
    group_ids.update(map(str, settings.group_ids))
    # Older bot versions could store private chats in the group set.
    recipients = [int(chat_id) for chat_id in group_ids if chat_id.startswith("-")]
    recipients.extend(chat_id for chat_id in set(event.get("recipient_tg_ids", [])) if chat_id > 0)

    for chat_id in recipients:
        private = chat_id > 0
        for attempt in range(2):
            if private and await redis.sismember(MUTED_QUEUE_NOTIFICATIONS, str(chat_id)):
                break
            try:
                await bot.send_message(
                    chat_id,
                    text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=private_markup if private else group_markup,
                )
                break
            except TelegramRetryAfter as error:
                if attempt == 0:
                    await asyncio.sleep(error.retry_after)
                else:
                    logger.warning("Telegram rate limited the queue announcement for %s", chat_id)
            except TelegramForbiddenError:
                if not private:
                    logger.warning("Bot cannot post to group %s", chat_id)
                break
            except TelegramBadRequest as error:
                if not private or "chat not found" not in error.message.lower():
                    logger.exception("Could not announce a queue to chat %s", chat_id)
                break
            except Exception:
                logger.exception("Could not announce a queue to chat %s", chat_id)
                break


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
