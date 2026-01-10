# bot/middlewares/retry.py
"""Middleware для автоматического повтора при сетевых ошибках Telegram API"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramAPIError

logger = logging.getLogger(__name__)


class RetryMiddleware(BaseMiddleware):
    """
    Middleware для автоматического повтора обработки при сетевых ошибках.
    
    Перехватывает TelegramNetworkError и повторяет обработку до max_retries раз
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
        
        for attempt in range(self.max_retries + 1):
            try:
                return await handler(event, data)
            
            except TelegramRetryAfter as e:
                # Telegram просит подождать - ждём и повторяем
                wait_time = min(e.retry_after, 60)  # Максимум 60 сек
                logger.warning(f"Telegram rate limit, ждём {wait_time} сек...")
                await asyncio.sleep(wait_time)
                # Пробуем ещё раз (не считаем как попытку)
                continue
                
            except TelegramNetworkError as e:
                last_exception = e
                delay = self.base_delay * (2 ** attempt)  # 1, 2, 4, 8 сек
                
                if attempt < self.max_retries:
                    event_info = self._get_event_info(event)
                    logger.warning(
                        f"Сетевая ошибка ({event_info}), "
                        f"попытка {attempt + 1}/{self.max_retries + 1}, "
                        f"повтор через {delay:.1f}с: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Все {self.max_retries + 1} попытки исчерпаны: {e}"
                    )
                    # Отправляем пользователю сообщение об ошибке (если возможно)
                    await self._notify_user_about_error(event, data)
            
            except TelegramAPIError as e:
                # Другие ошибки API (не сетевые) - не повторяем
                logger.error(f"Ошибка Telegram API: {e}")
                raise
            
            except Exception as e:
                # Неожиданные ошибки - логируем и пробрасываем
                logger.error(f"Неожиданная ошибка в handler: {e}", exc_info=True)
                raise
        
        # Все попытки исчерпаны - возвращаем None вместо исключения
        # чтобы бот не падал
        return None
    
    def _get_event_info(self, event: TelegramObject) -> str:
        """Получить информацию о событии для логирования"""
        if isinstance(event, Message):
            text = event.text or event.caption or "[media]"
            return f"Message: {text[:30]}..."
        elif isinstance(event, CallbackQuery):
            return f"Callback: {event.data}"
        else:
            return f"{type(event).__name__}"
    
    async def _notify_user_about_error(self, event: TelegramObject, data: Dict[str, Any]):
        """Попытаться уведомить пользователя об ошибке"""
        try:
            bot = data.get('bot')
            if not bot:
                return
            
            chat_id = None
            if isinstance(event, Message):
                chat_id = event.chat.id
            elif isinstance(event, CallbackQuery):
                chat_id = event.message.chat.id if event.message else None
            
            if chat_id:
                # Простое сообщение без retry
                await bot.send_message(
                    chat_id,
                    "⚠️ Произошла сетевая ошибка. Пожалуйста, попробуйте ещё раз через несколько секунд."
                )
        except Exception:
            # Игнорируем ошибки при отправке уведомления
            pass
