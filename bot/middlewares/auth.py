# bot/middlewares/auth.py
"""Middleware для авторизации и регистрации пользователей"""

import logging
from typing import Dict, Any, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot.database.queries import UserQueries

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """
    Middleware для:
    - Автоматической регистрации новых пользователей
    - Проверки бана
    - Обновления last_activity
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события с проверкой авторизации"""

        user = event.from_user
        if not user:
            return await handler(event, data)

        try:
            # Получаем или создаём пользователя
            db_user = await UserQueries.get_or_create_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )

            # Проверяем бан
            if db_user and db_user.is_banned:
                logger.warning(f"Заблокированный пользователь {user.id} попытался отправить сообщение")

                if isinstance(event, Message):
                    await event.answer(
                        "❌ Ваш аккаунт заблокирован.\n"
                        f"Причина: {db_user.ban_reason or 'не указана'}"
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        "❌ Ваш аккаунт заблокирован",
                        show_alert=True
                    )
                return None  # Не обрабатываем запрос

            # Обновляем last_activity (в фоне, не ждём)
            if db_user:
                await UserQueries.update_last_activity(user.id)

            # Добавляем пользователя в data для хендлеров
            data["db_user"] = db_user

        except Exception as e:
            logger.error(f"AuthMiddleware error: {e}")
            # При ошибке пропускаем - не блокируем пользователя

        return await handler(event, data)
