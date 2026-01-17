# bot/config/settings.py
"""Конфигурация бота и переменные окружения"""

import os
from typing import List
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения
# Path: bot/config/settings.py -> bot/config -> bot -> project_root -> .env
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(env_path)

class Settings:
    """Класс с настройками приложения"""
    
    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "proday_bot")
    
    # Telegram API для парсера (Telethon)
    API_ID: int = int(os.getenv("API_ID", "0"))
    API_HASH: str = os.getenv("API_HASH", "")
    PHONE_NUMBER: str = os.getenv("PHONE_NUMBER", "")
    
    # База данных PostgreSQL
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "telegram_ads")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    
    # Redis
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    
    # Платежная система YooMoney
    YOOMONEY_TOKEN: str = os.getenv("YOOMONEY_TOKEN", "")
    YOOMONEY_WALLET: str = os.getenv("YOOMONEY_WALLET", "")
    YOOMONEY_SECRET: str = os.getenv("YOOMONEY_SECRET", "")

    # Robokassa
    ROBOKASSA_MERCHANT_LOGIN: str = os.getenv("ROBOKASSA_MERCHANT_LOGIN", "")
    ROBOKASSA_PASSWORD1: str = os.getenv("ROBOKASSA_PASSWORD1", "")
    ROBOKASSA_PASSWORD2: str = os.getenv("ROBOKASSA_PASSWORD2", "")
    ROBOKASSA_TEST_MODE: bool = os.getenv("ROBOKASSA_TEST_MODE", "False").lower() == "true"
    
    # Администраторы
    ADMIN_IDS: List[int] = [
        int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id
    ]
    
    # Модераторы
    MODERATOR_IDS: List[int] = [
        int(id) for id in os.getenv("MODERATOR_IDS", "").split(",") if id
    ]
    
    # Web Backend
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    BACKEND_SECRET: str = os.getenv("BACKEND_SECRET", "secret_key")
    
    # Веб-интерфейс
    WEB_DOMAIN: str = os.getenv("WEB_DOMAIN", "proday39.ru")
    WEB_URL: str = f"https://{WEB_DOMAIN}"

    # Webhook конфигурация
    WEBHOOK_DOMAIN: str = os.getenv("WEBHOOK_DOMAIN", "prodaybot.ru")
    WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "/webhook/bot")
    WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "127.0.0.1")
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8080"))

    @property
    def webhook_url(self) -> str:
        """Получить полный URL вебхука"""
        return f"https://{self.WEBHOOK_DOMAIN}{self.WEBHOOK_PATH}"
    
    # Файлы и медиа
    UPLOAD_DIR: Path = Path("uploads")
    MAX_PHOTO_SIZE: int = 10 * 1024 * 1024  # 10 MB
    MAX_VIDEO_SIZE: int = 50 * 1024 * 1024  # 50 MB
    ALLOWED_PHOTO_FORMATS: List[str] = ["jpg", "jpeg", "png", "webp"]
    ALLOWED_VIDEO_FORMATS: List[str] = ["mp4", "avi", "mov"]
    
    # Антиспам и лимиты
    ANTIFLOOD_RATE: int = 3  # Сообщений в секунду
    ANTIFLOOD_BURST: int = 5  # Максимальный всплеск
    MIN_MESSAGE_INTERVAL: int = 1  # Минимальный интервал между сообщениями (сек)
    
    # Кэширование
    CACHE_TTL: int = 3600  # Время жизни кэша (сек)
    
    # Логирование
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = "logs/bot.log"
    
    # Режим разработки
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # API ключи для внешних сервисов
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

    # Claude API для LLM-модерации
    CLAUDE_API_KEY: str = os.getenv("CLAUDE_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-3-haiku-20240307")  # haiku для скорости/дешевизны
    LLM_MODERATION_ENABLED: bool = os.getenv("LLM_MODERATION_ENABLED", "True").lower() == "true"
    LLM_MODERATION_THRESHOLD: float = float(os.getenv("LLM_MODERATION_THRESHOLD", "0.7"))  # 0-1
    
    @property
    def database_url(self) -> str:
        """Получить URL для подключения к БД"""
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
    
    @property
    def redis_url(self) -> str:
        """Получить URL для подключения к Redis"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    def is_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        return user_id in self.ADMIN_IDS
    
    def is_moderator(self, user_id: int) -> bool:
        """Проверить, является ли пользователь модератором"""
        return user_id in self.MODERATOR_IDS or self.is_admin(user_id)

# Создание экземпляра настроек
settings = Settings()

# Создание директорий, если их нет
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
Path("logs").mkdir(parents=True, exist_ok=True)

# Проверка обязательных переменных
if not settings.BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

if not settings.DB_PASSWORD and not settings.DEBUG:
    raise ValueError("DB_PASSWORD не установлен в переменных окружения")