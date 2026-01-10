# bot/main_debug.py - ДИАГНОСТИКА: логируем ВСЕ update'ы

import asyncio
import logging
import sys
import json
from pathlib import Path
from aiohttp import web, ClientTimeout

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Update, TelegramObject, Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from redis.asyncio import Redis
from typing import Any, Awaitable, Callable, Dict

sys.path.append(str(Path(__file__).parent.parent))

from bot.config import settings
from bot.database.connection import init_db
from bot.handlers import start, ad_creation, ad_management, search, profile, admin, payment
from bot.middlewares.antiflood import AntiFloodMiddleware
from bot.middlewares.auth import AuthMiddleware
from bot.utils.commands import set_bot_commands

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('logs/bot.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/webhook/bot"
WEBHOOK_URL = f"https://prodaybot.ru{WEBHOOK_PATH}"


class RawUpdateLogger(BaseMiddleware):
    """Логирует КАЖДЫЙ update ДО любой обработки"""
    async def __call__(self, handler: Callable, event: TelegramObject, data: Dict[str, Any]) -> Any:
        if isinstance(event, CallbackQuery):
            logger.info(f"!!! RAW CALLBACK: data='{event.data}' from_user={event.from_user.id}")
        elif isinstance(event, Message):
            logger.info(f"!!! RAW MESSAGE: text='{event.text}' from_user={event.from_user.id}")
        return await handler(event, data)


async def on_startup(bot: Bot):
    logger.info("=" * 60)
    logger.info("ЗАПУСК ДИАГНОСТИЧЕСКОГО БОТА")
    logger.info("=" * 60)
    await init_db()
    await set_bot_commands(bot)
    me = await bot.get_me()
    logger.info(f"Бот: @{me.username}")
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True, allowed_updates=["message", "callback_query"])
    logger.info(f"Webhook: {WEBHOOK_URL}")
    
    # Логируем все зарегистрированные handlers
    logger.info("=== ЗАРЕГИСТРИРОВАННЫЕ CALLBACK HANDLERS ===")
    for router in [start.router, ad_creation.router, ad_management.router]:
        logger.info(f"Router '{router.name}': {len(router.callback_query.handlers)} callbacks")
        for h in router.callback_query.handlers[:5]:
            logger.info(f"  - {h.callback} filters: {h.filters}")


async def on_shutdown(bot: Bot):
    await bot.delete_webhook()


async def main():
    redis = Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB,
                  password=settings.REDIS_PASSWORD or None, decode_responses=False)
    storage = RedisStorage(redis=redis)
    
    timeout = ClientTimeout(total=120, connect=30, sock_read=60, sock_connect=30)
    session = AiohttpSession(timeout=timeout)
    bot = Bot(token=settings.BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    dp = Dispatcher(storage=storage)
    
    # ПЕРВЫМ ставим RawUpdateLogger - он логирует ВСЁ
    dp.callback_query.outer_middleware(RawUpdateLogger())
    dp.message.outer_middleware(RawUpdateLogger())
    
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
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8080)
    
    try:
        await site.start()
        logger.info("Сервер запущен на 127.0.0.1:8080")
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot.session.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())