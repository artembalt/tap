# bot/main.py
"""Telegram бот - webhook режим с retry"""

import asyncio
import logging
import sys
from pathlib import Path
from aiohttp import web, ClientTimeout

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Update, TelegramObject, Message, CallbackQuery
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
from bot.handlers import start, ad_creation, ad_management, search, profile, admin, payment
from bot.middlewares.antiflood import AntiFloodMiddleware
from bot.middlewares.auth import AuthMiddleware
from bot.utils.commands import set_bot_commands

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('logs/bot.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/webhook/bot"
DOMAIN = "prodaybot.ru"
WEBHOOK_URL = f"https://{DOMAIN}{WEBHOOK_PATH}"
WEB_SERVER_HOST = "127.0.0.1"
WEB_SERVER_PORT = 8080


class RetryMiddleware(BaseMiddleware):
    """Middleware для обработки rate limit (retry только для TelegramRetryAfter)"""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        max_retries = 3

        for attempt in range(max_retries):
            try:
                return await handler(event, data)
            except TelegramRetryAfter as e:
                logger.warning(f"Rate limit, ждём {e.retry_after}с")
                await asyncio.sleep(e.retry_after)
            except TelegramNetworkError as e:
                # НЕ повторяем весь handler при сетевой ошибке -
                # это вызывает дублирование сообщений и зависание
                logger.error(f"Сетевая ошибка: {e}")
                raise


class RawUpdateLogger(BaseMiddleware):
    """Логирование входящих update"""
    
    async def __call__(self, handler, event: Update, data: dict):
        if hasattr(event, 'message') and event.message:
            logger.info(f"!!! RAW MESSAGE: text='{event.message.text}' from_user={event.message.from_user.id}")
        elif hasattr(event, 'callback_query') and event.callback_query:
            logger.info(f"!!! RAW CALLBACK: data='{event.callback_query.data}' from_user={event.callback_query.from_user.id}")
        return await handler(event, data)


async def keepalive_task(bot: Bot):
    """Фоновая задача для поддержания соединения с Telegram API"""
    while True:
        await asyncio.sleep(15)  # Каждые 15 секунд - держим соединение горячим
        try:
            await bot.get_me()
        except Exception:
            pass  # Игнорируем ошибки - главное держать соединение активным


async def on_startup(bot: Bot):
    logger.info("=" * 60)
    logger.info("ЗАПУСК БОТА")
    logger.info("=" * 60)

    await init_db()
    await set_bot_commands(bot)

    try:
        me = await bot.get_me()
        logger.info(f"Бот: @{me.username}")
    except Exception as e:
        logger.warning(f"Прогрев: {e}")

    await bot.set_webhook(
        url=WEBHOOK_URL,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )
    logger.info(f"Webhook: {WEBHOOK_URL}")

    # Запускаем фоновую задачу для поддержания соединения
    asyncio.create_task(keepalive_task(bot))


async def on_shutdown(bot: Bot):
    logger.info("Остановка бота...")
    await bot.delete_webhook()


async def main():
    redis = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
        decode_responses=True
    )
    storage = RedisStorage(redis=redis)
    
    # Очень короткие таймауты для быстрого retry при cold start
    timeout = ClientTimeout(
        total=8,
        connect=2,
        sock_read=3,
        sock_connect=2
    )

    session = AiohttpSession(timeout=timeout)
    # Настраиваем connector для избежания "протухших" соединений
    session._connector_init.update({
        'keepalive_timeout': 10,
        'enable_cleanup_closed': True,
    })
    bot = Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher(storage=storage)
    
    # Middleware
    dp.update.outer_middleware(RawUpdateLogger())
    dp.message.outer_middleware(RetryMiddleware())
    dp.callback_query.outer_middleware(RetryMiddleware())
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