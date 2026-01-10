# bot/utils/network.py
"""Утилиты для работы с сетью - retry для отдельных операций"""

import asyncio
import logging
from typing import TypeVar, Callable, Awaitable
from aiogram.exceptions import TelegramNetworkError

logger = logging.getLogger(__name__)

T = TypeVar('T')


async def safe_send(
    coro: Awaitable[T],
    retries: int = 2,
    delay: float = 0.5
) -> T | None:
    """
    Безопасная отправка с retry для отдельной операции.
    
    Использование:
        await safe_send(message.answer("Привет"))
        await safe_send(bot.send_photo(chat_id, photo))
    
    Args:
        coro: Корутина для выполнения
        retries: Количество повторов при ошибке
        delay: Задержка между попытками
    
    Returns:
        Результат или None при ошибке
    """
    for attempt in range(retries + 1):
        try:
            return await coro
        except TelegramNetworkError as e:
            if attempt < retries:
                logger.warning(f"Сетевая ошибка, повтор {attempt + 1}/{retries}: {e}")
                await asyncio.sleep(delay * (attempt + 1))
            else:
                logger.error(f"Не удалось отправить после {retries} попыток: {e}")
                return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return None
    return None
