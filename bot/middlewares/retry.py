# bot/middlewares/retry.py
"""Middleware для автоматического повтора при сетевых ошибках"""

import asyncio
import logging
from typing import Dict, Any, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Update
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

logger = logging.getLogger(__name__)


class RetryMiddleware(BaseMiddleware):
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await handler(event, data)
                
            except TelegramRetryAfter as e:
                logger.warning(f"Rate limit, ждём {e.retry_after} сек...")
                await asyncio.sleep(e.retry_after)
                continue
                
            except TelegramNetworkError as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(
                        f"Сетевая ошибка (попытка {attempt + 1}/{self.max_retries + 1}): {e}"
                    )
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.error(f"Сетевая ошибка после {self.max_retries + 1} попыток: {e}")
                    
            except Exception:
                raise
        
        if last_exception:
            raise last_exception