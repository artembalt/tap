# bot/main.py
"""Telegram бот - webhook режим с RETRY и увеличенными таймаутами"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict
from aiohttp import web, ClientTimeout

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from redis.asyncio import Redis

sys.path.append(str(Path(__file__).parent.parent))

from bot.config import settings
from bot.database.connection import init_db
from bot.handlers import (
    start, ad_creation, ad_management,
    search, profile, admin, payment
)
from bot.middlewares.antiflood import AntiFloodMiddleware
from bot.middlewares.auth import AuthMiddleware
from bot.utils.commands import set_bot_commands

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Отключаем спам
logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

WEBHOOK_PATH = "/webhook/bot"
DOMAIN = getattr(settings, 'DOMAIN', 'prodaybot.ru')
WEBHOOK_URL = f"https://{DOMAIN}{WEBHOOK_PATH}"
WEB_SERVER_HOST = "127.0.0.1"
WEB_SERVER_PORT = 8080


class RetryMiddleware(BaseMiddleware):
    """
    Middleware для автоматического повтора при сетевых ошибках.
    НЕ теряет события - повторяет до успеха или исчерпания попыток.
    """
    
    def __init__(self, max_retries: int = 3, base_delay: float = 2.0):
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
        event_info = self._get_event_info(event)
        
        for attempt in range(self.max_retries + 1):
            try:
                return await handler(event, data)
            
            except TelegramRetryAfter as e:
                wait_time = min(e.retry_after, 30)
                logger.warning(f"[RETRY] Rate limit, ждём {wait_time}с...")
                await asyncio.sleep(wait_time)
                continue  # Не считаем как попытку
                
            except TelegramNetworkError as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)  # 2, 4, 8 сек
                    logger.warning(
                        f"[RETRY] Сетевая ошибка ({event_info}), "
                        f"попытка {attempt + 1}/{self.max_retries + 1}, "
                        f"повтор через {delay:.0f}с"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"[RETRY] Все попытки исчерпаны: {e}")
                    # Уведомляем пользователя
                    await self._notify_error(event, data)
            
            except Exception as e:
                # Другие ошибки - логируем и пробрасываем
                logger.error(f"[RETRY] Неожиданная ошибка: {e}", exc_info=True)
                raise
        
        # Все попытки исчерпаны - НЕ падаем, просто возвращаем None
        return None
    
    def _get_event_info(self, event: TelegramObject) -> str:
        if isinstance(event, CallbackQuery):
            return f"callback:{event.data}"
        elif isinstance(event, Message):
            text = event.text or "[media]"
            return f"message:{text[:20]}"
        return type(event).__name__
    
    async def _notify_error(self, event: TelegramObject, data: Dict[str, Any]):
        """Уведомить пользователя об ошибке"""
        try:
            bot = data.get('bot')
            if not bot:
                return
            
            chat_id = None
            if isinstance(event, Message):
                chat_id = event.chat.id
            elif isinstance(event, CallbackQuery):
                if event.message:
                    chat_id = event.message.chat.id
            
            if chat_id:
                await bot.send_message(
                    chat_id,
                    "⚠️ Сетевая ошибка. Попробуйте ещё раз."
                )
        except:
            pass  # Игнорируем ошибки уведомления


async def on_startup(bot: Bot):
    """Действия при запуске бота"""
    logger.info("=" * 50)
    logger.info("ЗАПУСК БОТА (webhook + retry)")
    logger.info("=" * 50)
    
    await init_db()
    await set_bot_commands(bot)
    
    # Прогрев с retry
    for attempt in range(5):
        try:
            me = await bot.get_me()
            logger.info(f"Бот: @{me.username}")
            break
        except TelegramNetworkError as e:
            logger.warning(f"Прогрев, попытка {attempt + 1}: {e}")
            await asyncio.sleep(3)
    
    # Webhook с retry
    for attempt in range(5):
        try:
            await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
            logger.info(f"Webhook: {WEBHOOK_URL}")
            break
        except TelegramNetworkError as e:
            logger.warning(f"Webhook, попытка {attempt + 1}: {e}")
            await asyncio.sleep(3)


async def on_shutdown(bot: Bot):
    logger.info("Остановка бота...")
    try:
        await bot.delete_webhook()
    except:
        pass


async def main():
    # Redis
    redis = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
        decode_responses=True
    )
    
    try:
        await redis.ping()
        logger.info("Redis: OK")
    except Exception as e:
        logger.error(f"Redis ОШИБКА: {e}")
    
    storage = RedisStorage(redis=redis)
    
    # УВЕЛИЧЕННЫЕ ТАЙМАУТЫ для нестабильной сети
    timeout = ClientTimeout(
        total=120,          # Общий таймаут 2 минуты
        connect=30,         # На установку соединения
        sock_read=60,       # На чтение (важно для media!)
        sock_connect=30     # На socket connect
    )
    
    session = AiohttpSession(timeout=timeout)
    
    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher(storage=storage)
    
    # Middleware - RetryMiddleware ПЕРВЫМ!
    dp.message.middleware(RetryMiddleware(max_retries=3, base_delay=2.0))
    dp.callback_query.middleware(RetryMiddleware(max_retries=3, base_delay=2.0))
    dp.message.middleware(AntiFloodMiddleware())
    dp.callback_query.middleware(AntiFloodMiddleware())
    dp.message.middleware(AuthMiddleware())
    
    # Роутеры
    dp.include_router(start.router)
    dp.include_router(ad_creation.router)
    dp.include_router(ad_management.router)
    dp.include_router(search.router)
    dp.include_router(profile.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    logger.info(f"Сервер: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    
    try:
        await site.start()
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot.session.close()
        await redis.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
