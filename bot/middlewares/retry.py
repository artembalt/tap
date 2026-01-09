# bot/middlewares/retry.py
"""Middleware для автоматического повтора при сетевых ошибках Telegram API"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

logger = logging.getLogger(__name__)


class RetryMiddleware(BaseMiddleware):
    """
    Middleware для автоматического повтора обработки при сетевых ошибках.
    
    Перехватывает TelegramNetworkError и повторяет обработку до 3 раз
    с экспоненциальной задержкой.
    """
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return await handler(event, data)
            
            except TelegramRetryAfter as e:
                # Telegram просит подождать
                logger.warning(f"Telegram rate limit, ждём {e.retry_after} сек...")
                await asyncio.sleep(e.retry_after)
                # Пробуем ещё раз (не считаем как попытку)
                continue
                
            except TelegramNetworkError as e:
                last_exception = e
                delay = self.base_delay * (2 ** attempt)  # 1, 2, 4 сек
                
                if attempt < self.max_retries - 1:
                    # Получаем информацию о событии для лога
                    event_info = self._get_event_info(event)
                    logger.warning(
                        f"Сетевая ошибка ({event_info}), "
                        f"попытка {attempt + 1}/{self.max_retries}, "
                        f"повтор через {delay:.1f}с: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Все {self.max_retries} попытки исчерпаны: {e}"
                    )
        
        # Все попытки исчерпаны
        if last_exception:
            raise last_exception
    
    def _get_event_info(self, event: TelegramObject) -> str:
        """Получить информацию о событии для логирования"""
        if isinstance(event, Message):
            text = event.text or event.caption or "[media]"
            return f"Message: {text[:30]}..."
        elif isinstance(event, CallbackQuery):
            return f"Callback: {event.data}"
        else:
            return f"{type(event).__name__}"
