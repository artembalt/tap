# bot/middlewares/antiflood.py
"""Middleware для защиты от флуда с использованием Redis"""

import logging
from typing import Dict, Any, Callable, Awaitable, Optional

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.fsm.context import FSMContext
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# FSM состояния, которые исключены из проверки лимитов (создание объявления)
EXCLUDED_FSM_STATES = (
    "AdCreation:",  # Все состояния создания объявления
)

# Системные user_id Telegram — исключаем из антифлуда
SYSTEM_USER_IDS = {
    777000,      # Telegram (пересылка сообщений в каналы)
    136817688,   # Channel Bot
    1087968824,  # Group Anonymous Bot
}


class AntiFloodMiddleware(BaseMiddleware):
    """
    Middleware для защиты от флуда.
    Использует Redis для хранения счетчиков сообщений.
    Исключает из проверки шаги создания объявления.
    """

    def __init__(
        self,
        rate_limit: int = 5,          # Максимум сообщений за период
        period: int = 10,             # Период в секундах
        block_duration: int = 30,     # Время блокировки при превышении
        redis: Optional[Redis] = None
    ):
        self.rate_limit = rate_limit
        self.period = period
        self.block_duration = block_duration
        self._redis = redis
        self._warned_users: set = set()  # Для in-memory fallback

    def set_redis(self, redis: Redis) -> None:
        """Установить Redis соединение"""
        self._redis = redis

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события с проверкой rate limit"""

        # Получаем user_id
        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return await handler(event, data)

        # Исключаем системные аккаунты Telegram
        if user_id in SYSTEM_USER_IDS:
            return await handler(event, data)

        # Проверяем FSM состояние - исключаем шаги создания объявления
        state: FSMContext = data.get("state")
        if state:
            current_state = await state.get_state()
            if current_state and any(current_state.startswith(exc) for exc in EXCLUDED_FSM_STATES):
                # Пользователь в процессе создания объявления - пропускаем лимит
                return await handler(event, data)

        # Проверяем блокировку и rate limit
        is_blocked = await self._check_rate_limit(user_id)

        if is_blocked:
            logger.warning(f"AntiFlood: пользователь {user_id} превысил лимит")

            # Уведомляем пользователя один раз
            if user_id not in self._warned_users:
                self._warned_users.add(user_id)
                try:
                    if isinstance(event, Message):
                        await event.answer(
                            "⚠️ Слишком много запросов. Подождите немного.",
                            show_alert=False
                        )
                    elif isinstance(event, CallbackQuery):
                        await event.answer(
                            "⚠️ Слишком быстро! Подождите.",
                            show_alert=True
                        )
                except Exception as e:
                    logger.debug(f"Не удалось отправить предупреждение: {e}")

            return None  # Не обрабатываем событие

        # Очищаем warned status при успешном запросе
        self._warned_users.discard(user_id)

        return await handler(event, data)

    async def _check_rate_limit(self, user_id: int) -> bool:
        """
        Проверяет rate limit для пользователя.
        Возвращает True если пользователь заблокирован.
        """
        if not self._redis:
            # Без Redis - пропускаем (fallback)
            return False

        try:
            # Ключи в Redis
            count_key = f"antiflood:count:{user_id}"
            block_key = f"antiflood:block:{user_id}"

            # Проверяем блокировку
            if await self._redis.exists(block_key):
                return True

            # Инкрементируем счетчик
            count = await self._redis.incr(count_key)

            # Устанавливаем TTL при первом сообщении
            if count == 1:
                await self._redis.expire(count_key, self.period)

            # Проверяем превышение лимита
            if count > self.rate_limit:
                # Блокируем пользователя
                await self._redis.setex(
                    block_key,
                    self.block_duration,
                    "1"
                )
                logger.info(
                    f"AntiFlood: блокировка user={user_id} на {self.block_duration}с "
                    f"(превышен лимит: {count}/{self.rate_limit})"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"AntiFlood Redis error: {e}")
            return False  # При ошибке пропускаем
