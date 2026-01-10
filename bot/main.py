# bot/main.py
"""ДИАГНОСТИЧЕСКАЯ ВЕРСИЯ - логирует ВСЕ callback'и"""

import asyncio
import logging
import sys
from pathlib import Path
from aiohttp import web, ClientTimeout
from typing import Any, Awaitable, Callable, Dict

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from redis.asyncio import Redis

sys.path.append(str(Path(__file__).parent.parent))

from bot.config import settings
from bot.database.connection import init_db
from bot.handlers import (
    start, ad_creation, ad_management,
    search, profile, admin, payment
)
from bot.utils.commands import set_bot_commands

# Настройка логирования - УРОВЕНЬ DEBUG!
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Отключаем спам от aiohttp и aiogram
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.getLogger('aiogram').setLevel(logging.INFO)

WEBHOOK_PATH = "/webhook/bot"
DOMAIN = getattr(settings, 'DOMAIN', 'prodaybot.ru')
WEBHOOK_URL = f"https://{DOMAIN}{WEBHOOK_PATH}"
WEB_SERVER_HOST = "127.0.0.1"
WEB_SERVER_PORT = 8080


class DiagnosticMiddleware(BaseMiddleware):
    """Middleware для диагностики - логирует ВСЕ события"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Логируем ДО обработки
        if isinstance(event, CallbackQuery):
            logger.info(f">>> CALLBACK ПОЛУЧЕН: data='{event.data}', user={event.from_user.id}")
        elif isinstance(event, Message):
            text = event.text or event.caption or "[media]"
            logger.info(f">>> MESSAGE ПОЛУЧЕН: '{text[:50]}', user={event.from_user.id}")
        
        try:
            # Вызываем handler
            result = await handler(event, data)
            
            # Логируем ПОСЛЕ успешной обработки
            if isinstance(event, CallbackQuery):
                logger.info(f"<<< CALLBACK ОБРАБОТАН: data='{event.data}'")
            
            return result
            
        except Exception as e:
            # Логируем ошибку
            logger.error(f"!!! ОШИБКА в handler: {type(e).__name__}: {e}", exc_info=True)
            raise


async def on_startup(bot: Bot):
    """Действия при запуске бота"""
    logger.info("=" * 50)
    logger.info("ЗАПУСК ДИАГНОСТИЧЕСКОЙ ВЕРСИИ БОТА")
    logger.info("=" * 50)
    
    await init_db()
    await set_bot_commands(bot)
    
    try:
        me = await bot.get_me()
        logger.info(f"Бот: @{me.username}")
    except Exception as e:
        logger.error(f"Ошибка get_me: {e}")
    
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    logger.info(f"Webhook: {WEBHOOK_URL}")


async def on_shutdown(bot: Bot):
    logger.info("Остановка бота...")
    await bot.delete_webhook()


async def main():
    # Redis
    redis = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
        decode_responses=True
    )
    
    # Проверка Redis
    try:
        await redis.ping()
        logger.info("Redis: OK")
    except Exception as e:
        logger.error(f"Redis ОШИБКА: {e}")
    
    storage = RedisStorage(redis=redis)
    
    # Таймауты
    timeout = ClientTimeout(total=30, connect=10, sock_read=20, sock_connect=10)
    session = AiohttpSession(timeout=timeout)
    
    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher(storage=storage)
    
    # ТОЛЬКО DiagnosticMiddleware - без других!
    dp.message.middleware(DiagnosticMiddleware())
    dp.callback_query.middleware(DiagnosticMiddleware())
    
    # Регистрация роутеров с логированием
    logger.info("Регистрация роутеров:")
    
    dp.include_router(start.router)
    logger.info(f"  - start.router: {len(start.router.callback_query.handlers)} callback handlers")
    
    dp.include_router(ad_creation.router)
    logger.info(f"  - ad_creation.router: {len(ad_creation.router.callback_query.handlers)} callback handlers")
    
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
