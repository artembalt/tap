from typing import Dict, Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

class AntiFloodMiddleware(BaseMiddleware):
    """Middleware для защиты от флуда"""
    
    def __init__(self, rate_limit: int = 3):
        self.rate_limit = rate_limit
        self.user_messages = {}
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        # Пока просто пропускаем все сообщения
        return await handler(event, data)
