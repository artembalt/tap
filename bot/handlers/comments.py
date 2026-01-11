# bot/handlers/comments.py
"""Мониторинг комментариев к объявлениям и уведомления продавцам"""

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select

from bot.database.connection import get_db_session
from bot.database.models import Ad, User

router = Router(name='comments')
logger = logging.getLogger(__name__)


@router.message(F.chat.type.in_(["group", "supergroup"]))
async def handle_group_message(message: Message, bot: Bot):
    """
    Обработка сообщений в группах обсуждений.
    Если это комментарий к посту канала — уведомляем продавца.
    """
    # Проверяем что это ответ на сообщение (комментарий к посту)
    if not message.reply_to_message:
        return

    reply = message.reply_to_message

    # Проверяем что это пересланный пост из канала
    # В группах обсуждений reply_to_message содержит копию поста канала
    if not reply.forward_from_chat and not reply.sender_chat:
        return

    # Получаем ID канала и ID сообщения
    if reply.forward_from_chat:
        channel_id = reply.forward_from_chat.id
        channel_message_id = reply.forward_from_message_id
    elif reply.sender_chat:
        # Для linked channels
        channel_id = reply.sender_chat.id
        channel_message_id = reply.message_id
    else:
        return

    logger.info(
        f"[COMMENT] Комментарий в группе {message.chat.id} "
        f"к посту канала {channel_id}/{channel_message_id} "
        f"от {message.from_user.id}"
    )

    # Ищем объявление по channel_message_id
    ad = await find_ad_by_channel_message(channel_id, channel_message_id)

    if not ad:
        logger.debug(f"[COMMENT] Объявление не найдено для поста {channel_id}/{channel_message_id}")
        return

    # Не уведомляем если продавец сам комментирует
    if message.from_user.id == ad.user_id:
        logger.debug(f"[COMMENT] Продавец сам комментирует, пропускаем")
        return

    # Отправляем уведомление продавцу
    await notify_seller(bot, ad, message)


async def find_ad_by_channel_message(channel_id: int, message_id: int):
    """Найти объявление по ID сообщения в канале"""
    try:
        async with get_db_session() as session:
            # channel_message_ids хранит {"@channel_name": message_id}
            # Нужно искать по message_id в JSON
            result = await session.execute(select(Ad))
            ads = result.scalars().all()

            for ad in ads:
                channel_msgs = ad.channel_message_ids or {}
                for channel, msg_id in channel_msgs.items():
                    if msg_id == message_id:
                        return ad

            return None
    except Exception as e:
        logger.error(f"[COMMENT] Ошибка поиска объявления: {e}")
        return None


async def notify_seller(bot: Bot, ad: Ad, comment: Message):
    """Отправить уведомление продавцу о новом комментарии"""
    try:
        # Формируем текст уведомления
        commenter_name = comment.from_user.first_name or "Пользователь"
        if comment.from_user.username:
            commenter_link = f"<a href=\"https://t.me/{comment.from_user.username}\">{commenter_name}</a>"
        else:
            commenter_link = f"<a href=\"tg://user?id={comment.from_user.id}\">{commenter_name}</a>"

        # Обрезаем текст комментария если длинный
        comment_text = comment.text or comment.caption or "[медиа]"
        if len(comment_text) > 200:
            comment_text = comment_text[:200] + "..."

        # Получаем ссылку на объявление в канале
        ad_link = None
        channel_msgs = ad.channel_message_ids or {}
        for channel, msg_id in channel_msgs.items():
            if channel.startswith("@"):
                channel_clean = channel.lstrip("@")
                ad_link = f"https://t.me/{channel_clean}/{msg_id}?comment={comment.message_id}"
                break

        # Формируем сообщение
        title_short = ad.title[:50] + "..." if len(ad.title) > 50 else ad.title

        notification_text = f"""💬 <b>Новый комментарий</b>

📢 К объявлению: <b>{title_short}</b>
👤 От: {commenter_link}

<i>«{comment_text}»</i>"""

        if ad_link:
            notification_text += f"\n\n<a href=\"{ad_link}\">Открыть объявление</a>"

        # Отправляем уведомление продавцу
        await bot.send_message(
            chat_id=ad.user_id,
            text=notification_text,
            disable_web_page_preview=True
        )

        logger.info(f"[COMMENT] Уведомление отправлено продавцу {ad.user_id}")

    except TelegramAPIError as e:
        # Пользователь заблокировал бота или другая ошибка
        logger.warning(f"[COMMENT] Не удалось отправить уведомление {ad.user_id}: {e}")
    except Exception as e:
        logger.error(f"[COMMENT] Ошибка отправки уведомления: {e}")
