# bot/database/models.py
"""SQLAlchemy модели для базы данных"""

from datetime import datetime, date
from typing import Optional, List
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Index, JSON, ARRAY, UUID, BigInteger, Table, Date
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

Base = declarative_base()

# =============================================================================
# ENUM КЛАССЫ
# =============================================================================

class UserRole(str, Enum):
    USER = "user"
    VERIFIED = "verified"
    BUSINESS = "business"
    MODERATOR = "moderator"
    ADMIN = "admin"

class AccountType(str, Enum):
    """Тип аккаунта (подписки)"""
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"

class AdStatus(str, Enum):
    """
    Статусы объявлений:
    - DRAFT: черновик (не опубликовано)
    - PENDING: ожидает модерации
    - ACTIVE: активное (опубликовано, срок не истёк)
    - INACTIVE: не активное (срок публикации истёк)
    - NEEDS_EDIT: требует редактирования (отклонено модератором)
    - DELETED: удалено пользователем (хранится 6 месяцев)
    - ARCHIVED: в архиве (старые удалённые, старше 6 месяцев)
    - BANNED: заблокировано администратором
    """
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"      # Новый: срок публикации истёк
    NEEDS_EDIT = "needs_edit"  # Новый: требует редактирования после модерации
    DELETED = "deleted"
    ARCHIVED = "archived"
    BANNED = "banned"
    # Устаревший статус, оставлен для совместимости
    REJECTED = "rejected"

class AdType(str, Enum):
    SELL = "sell"
    BUY = "buy"
    SERVICE = "service"
    RENT = "rent"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"

class TransactionType(str, Enum):
    """Тип транзакции"""
    DEPOSIT = "deposit"          # Пополнение баланса
    PURCHASE = "purchase"        # Покупка услуги
    REFUND = "refund"            # Возврат
    BONUS = "bonus"              # Бонусное начисление
    SUBSCRIPTION = "subscription" # Оплата подписки

class PromocodeType(str, Enum):
    """Тип промокода"""
    FIXED_RUB = "fixed_rub"      # Фиксированная сумма в рублях
    PERCENT = "percent"          # Процент скидки
    BONUS_RUB = "bonus_rub"      # Бонус на баланс в рублях
    BONUS_STARS = "bonus_stars"  # Бонус на баланс в Stars
    FREE_SERVICE = "free_service" # Бесплатная услуга

class ReportReason(str, Enum):
    SPAM = "spam"
    SCAM = "scam"
    INAPPROPRIATE = "inappropriate"
    WRONG_CATEGORY = "wrong_category"
    OTHER = "other"

# Ассоциативные таблицы
ad_favorites = Table(
    'ad_favorites',
    Base.metadata,
    Column('user_id', BigInteger, ForeignKey('users.telegram_id')),
    Column('ad_id', UUID(as_uuid=True), ForeignKey('ads.id')),
    Column('created_at', DateTime, default=datetime.utcnow)
)

ad_views = Table(
    'ad_views',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', BigInteger, ForeignKey('users.telegram_id'), nullable=True),
    Column('ad_id', UUID(as_uuid=True), ForeignKey('ads.id')),
    Column('viewed_at', DateTime, default=datetime.utcnow),
    Column('ip_address', String(45)),
    Column('source', String(20))  # 'telegram', 'web', 'api'
)

# Основные модели
class User(Base):
    __tablename__ = 'users'
    
    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String(100), nullable=True, index=True)
    first_name = Column(String(100))
    last_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    role = Column(String(20), default=UserRole.USER.value)
    
    # Настройки пользователя
    allow_telegram_calls = Column(Boolean, default=False)
    show_phone = Column(Boolean, default=False)
    default_region = Column(String(50), nullable=True)
    notification_enabled = Column(Boolean, default=True)
    language = Column(String(10), default='ru')
    
    # Статистика
    total_ads = Column(Integer, default=0)
    active_ads = Column(Integer, default=0)
    completed_deals = Column(Integer, default=0)
    rating = Column(Float, default=0.0)
    reviews_count = Column(Integer, default=0)
    profile_views = Column(Integer, default=0)  # Просмотры профиля
    
    # Подписки и платежи (старые поля оставлены для совместимости)
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)
    balance = Column(Float, default=0.0)  # Deprecated: используйте balance_rub
    total_spent = Column(Float, default=0.0)  # Deprecated: используйте total_spent_rub

    # Новая система балансов
    balance_rub = Column(Float, default=0.0)       # Баланс в рублях
    balance_stars = Column(Integer, default=0)     # Баланс в Telegram Stars
    total_spent_rub = Column(Float, default=0.0)   # Всего потрачено в рублях
    total_spent_stars = Column(Integer, default=0) # Всего потрачено в Stars

    # Тип аккаунта / Подписка
    account_type = Column(String(20), default=AccountType.FREE.value)  # free, pro, business
    account_until = Column(DateTime, nullable=True)  # До какого числа активна подписка
    extra_ads_limit = Column(Integer, default=0)     # Докупленные объявления
    
    # Модерация
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(Text, nullable=True)
    banned_until = Column(DateTime, nullable=True)
    warnings_count = Column(Integer, default=0)
    
    # Временные метки
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    ads = relationship("Ad", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("Ad", secondary=ad_favorites, back_populates="favorited_by")
    payments = relationship("Payment", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    reports_sent = relationship("Report", foreign_keys="Report.reporter_id", back_populates="reporter")
    reviews_given = relationship("Review", foreign_keys="Review.reviewer_id", back_populates="reviewer")
    reviews_received = relationship("Review", foreign_keys="Review.reviewed_user_id", back_populates="reviewed_user")
    promocode_usages = relationship("PromocodeUsage", back_populates="user")

    __table_args__ = (
        Index('idx_user_role', 'role'),
        Index('idx_user_created', 'created_at'),
        Index('idx_user_email', 'email'),
        Index('idx_user_phone', 'phone'),
        Index('idx_user_banned', 'is_banned'),
        Index('idx_user_premium', 'is_premium'),
        Index('idx_user_last_activity', 'last_activity'),
        Index('idx_user_account_type', 'account_type'),
    )

class Ad(Base):
    __tablename__ = 'ads'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    
    # Основная информация
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Float, nullable=True)
    currency = Column(String(10), default='RUB')
    ad_type = Column(String(20), default=AdType.SELL.value)
    
    # Местоположение и категория
    region = Column(String(50), nullable=False, index=True)
    city = Column(String(100), nullable=True)
    category = Column(String(50), nullable=False, index=True)
    subcategory = Column(String(50), nullable=True)
    
    # Медиа
    photos = Column(ARRAY(String), default=[])  # Список file_id
    video = Column(String, nullable=True)  # file_id видео
    
    # Контакты
    contact_phone = Column(String(20), nullable=True)
    show_phone = Column(Boolean, default=False)
    allow_calls = Column(Boolean, default=False)
    
    # Хэштеги и поиск
    hashtags = Column(ARRAY(String), default=[])
    search_vector = Column(Text, nullable=True)  # Для полнотекстового поиска
    
    # Статус и модерация
    status = Column(String(20), default=AdStatus.PENDING.value, index=True)
    rejection_reason = Column(Text, nullable=True)
    moderated_at = Column(DateTime, nullable=True)
    moderated_by = Column(BigInteger, nullable=True)
    
    # Публикация в каналах
    channel_message_ids = Column(JSONB, default={})  # {"channel_id": message_id}
    published_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    
    # Внешние ссылки (до 4 штук)
    # Формат: [{"title": "Название", "url": "https://..."}, ...]
    links = Column(JSONB, default=[])

    # Платные услуги
    is_premium = Column(Boolean, default=False)
    premium_features = Column(JSONB, default={})  # {"contact_buttons": true, "pinned": true}
    pinned_until = Column(DateTime, nullable=True)
    in_stories_until = Column(DateTime, nullable=True)
    
    # Статистика
    views_count = Column(Integer, default=0)
    favorites_count = Column(Integer, default=0)
    contacts_count = Column(Integer, default=0)  # Сколько раз нажали "Связаться"
    
    # Временные метки
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)  # Когда удалено пользователем

    # Отношения
    user = relationship("User", back_populates="ads")
    favorited_by = relationship("User", secondary=ad_favorites, back_populates="favorites")
    reports = relationship("Report", back_populates="ad", cascade="all, delete-orphan")
    statistics = relationship("AdStatistics", back_populates="ad", uselist=False)
    
    __table_args__ = (
        Index('idx_ad_status_region_category', 'status', 'region', 'category'),
        Index('idx_ad_user_status', 'user_id', 'status'),
        Index('idx_ad_created', 'created_at'),
        Index('idx_ad_expires', 'expires_at'),
        Index('idx_ad_published', 'published_at'),
        Index('idx_ad_search', 'title', 'description'),  # Для поиска
    )

class Payment(Base):
    """Платежи (пополнение баланса)"""
    __tablename__ = 'payments'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)

    # Информация о платеже
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default='RUB')  # 'RUB' или 'XTR' (Stars)
    status = Column(String(20), default=PaymentStatus.PENDING.value)

    # Тип платежа
    payment_type = Column(String(20), default='deposit')  # 'deposit', 'service', 'subscription'

    # Детали платежа (опционально, для покупки услуги напрямую)
    service_type = Column(String(50), nullable=True)  # Код услуги из PAID_SERVICES
    service_details = Column(JSONB, default={})  # Дополнительные параметры
    ad_id = Column(UUID(as_uuid=True), ForeignKey('ads.id'), nullable=True)

    # Платежная система
    # Варианты: 'yookassa', 'robokassa', 'tinkoff', 'telegram_stars', 'manual', 'bonus'
    payment_system = Column(String(50), default='yookassa')
    payment_id = Column(String(255), nullable=True)  # ID в платежной системе
    payment_url = Column(Text, nullable=True)  # Ссылка на оплату

    # Для Telegram Stars
    telegram_payment_charge_id = Column(String(255), nullable=True)
    provider_payment_charge_id = Column(String(255), nullable=True)

    # Промокод (если применён)
    promocode_id = Column(Integer, ForeignKey('promocodes.id'), nullable=True)
    discount_amount = Column(Float, default=0.0)  # Сумма скидки

    # Временные метки
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Отношения
    user = relationship("User", back_populates="payments")
    promocode = relationship("Promocode", back_populates="payments")
    transaction = relationship("Transaction", back_populates="payment", uselist=False)

    __table_args__ = (
        Index('idx_payment_user_status', 'user_id', 'status'),
        Index('idx_payment_created', 'created_at'),
        Index('idx_payment_expires', 'expires_at'),
        Index('idx_payment_system', 'payment_system'),
    )

class Report(Base):
    __tablename__ = 'reports'
    
    id = Column(Integer, primary_key=True)
    ad_id = Column(UUID(as_uuid=True), ForeignKey('ads.id'), nullable=False)
    reporter_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    
    reason = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    
    # Модерация
    is_resolved = Column(Boolean, default=False)
    resolution = Column(Text, nullable=True)
    resolved_by = Column(BigInteger, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    ad = relationship("Ad", back_populates="reports")
    reporter = relationship("User", foreign_keys=[reporter_id], back_populates="reports_sent")
    
    __table_args__ = (
        Index('idx_report_ad', 'ad_id'),
        Index('idx_report_resolved', 'is_resolved'),
    )

class Review(Base):
    __tablename__ = 'reviews'
    
    id = Column(Integer, primary_key=True)
    reviewer_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    reviewed_user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    ad_id = Column(UUID(as_uuid=True), ForeignKey('ads.id'), nullable=True)
    
    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    reviewer = relationship("User", foreign_keys=[reviewer_id], back_populates="reviews_given")
    reviewed_user = relationship("User", foreign_keys=[reviewed_user_id], back_populates="reviews_received")

class AdStatistics(Base):
    __tablename__ = 'ad_statistics'
    
    ad_id = Column(UUID(as_uuid=True), ForeignKey('ads.id'), primary_key=True)
    
    # Статистика по дням
    daily_views = Column(JSONB, default={})  # {"2024-01-15": 150}
    daily_favorites = Column(JSONB, default={})
    daily_contacts = Column(JSONB, default={})
    
    # Источники трафика
    traffic_sources = Column(JSONB, default={})  # {"telegram": 100, "web": 50}
    
    # География
    views_by_region = Column(JSONB, default={})  # {"kaliningrad": 80, "spb": 20}
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Отношения
    ad = relationship("Ad", back_populates="statistics")

class SpamWord(Base):
    __tablename__ = 'spam_words'
    
    id = Column(Integer, primary_key=True)
    word = Column(String(255), unique=True, nullable=False)
    category = Column(String(50), nullable=True)  # 'scam', 'spam', 'inappropriate'
    severity = Column(Integer, default=1)  # 1-10, где 10 - самое серьезное
    action = Column(String(20), default='warn')  # 'warn', 'reject', 'ban'
    
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(BigInteger, nullable=True)
    
    __table_args__ = (
        Index('idx_spam_word', 'word'),
    )

class SystemSettings(Base):
    __tablename__ = 'system_settings'

    key = Column(String(100), primary_key=True)
    value = Column(JSONB, nullable=False)
    description = Column(Text, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(BigInteger, nullable=True)


# =============================================================================
# НОВЫЕ МОДЕЛИ ДЛЯ БИЛЛИНГА
# =============================================================================

class Transaction(Base):
    """История всех операций с балансом"""
    __tablename__ = 'transactions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)

    # Тип и валюта
    type = Column(String(20), nullable=False)  # deposit, purchase, refund, bonus, subscription
    currency = Column(String(10), nullable=False)  # 'RUB' или 'XTR'
    amount = Column(Float, nullable=False)  # Сумма (всегда положительная)

    # Балансы ПОСЛЕ операции (для аудита и сверки)
    balance_rub_after = Column(Float, nullable=False)
    balance_stars_after = Column(Integer, nullable=False)

    # Связи
    payment_id = Column(UUID(as_uuid=True), ForeignKey('payments.id'), nullable=True)
    ad_id = Column(UUID(as_uuid=True), ForeignKey('ads.id'), nullable=True)

    # Детали
    service_code = Column(String(50), nullable=True)  # Код услуги (если purchase)
    description = Column(String(255), nullable=False)  # "Пополнение баланса", "Закрепление в канале 24ч"

    created_at = Column(DateTime, default=datetime.utcnow)

    # Отношения
    user = relationship("User", back_populates="transactions")
    payment = relationship("Payment", back_populates="transaction")

    __table_args__ = (
        Index('idx_transaction_user', 'user_id'),
        Index('idx_transaction_type', 'type'),
        Index('idx_transaction_created', 'created_at'),
        Index('idx_transaction_user_created', 'user_id', 'created_at'),
    )


class ExchangeRate(Base):
    """Курсы валют (для расчёта стоимости Stars)"""
    __tablename__ = 'exchange_rates'

    id = Column(Integer, primary_key=True)
    rate_date = Column(Date, unique=True, nullable=False, index=True)

    # Курсы
    usd_rub = Column(Float, nullable=False)   # Курс ЦБ РФ USD/RUB
    star_rub = Column(Float, nullable=False)  # Рассчитанный курс Star/RUB

    # Формула: star_rub = usd_rub * 0.013 * 0.9, минимум 1.0

    source = Column(String(50), default='cbr')  # Источник курса: 'cbr', 'manual'
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_exchange_rate_date', 'rate_date'),
    )


class Promocode(Base):
    """Промокоды"""
    __tablename__ = 'promocodes'

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # "LAUNCH2026"

    # Тип и значение
    type = Column(String(20), nullable=False)  # fixed_rub, percent, bonus_rub, bonus_stars, free_service
    value = Column(Float, nullable=False)  # 100 (рублей), 20 (процентов), 50 (звёзд)
    service_code = Column(String(50), nullable=True)  # Для free_service - код услуги

    # Ограничения
    max_uses = Column(Integer, nullable=True)         # Всего использований (None = безлимит)
    max_uses_per_user = Column(Integer, default=1)    # На одного пользователя
    min_amount = Column(Float, nullable=True)         # Минимальная сумма заказа

    # Для каких услуг (None = для всех)
    allowed_services = Column(ARRAY(String), nullable=True)  # ['pin_channel_24h', 'boost_up']

    # Срок действия
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)

    # Статистика
    uses_count = Column(Integer, default=0)
    total_discount_given = Column(Float, default=0.0)  # Общая сумма скидок

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(BigInteger, nullable=True)

    # Отношения
    payments = relationship("Payment", back_populates="promocode")
    usages = relationship("PromocodeUsage", back_populates="promocode")

    __table_args__ = (
        Index('idx_promocode_code', 'code'),
        Index('idx_promocode_active', 'is_active'),
    )


class PromocodeUsage(Base):
    """История использования промокодов"""
    __tablename__ = 'promocode_usages'

    id = Column(Integer, primary_key=True)
    promocode_id = Column(Integer, ForeignKey('promocodes.id'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)

    discount_amount = Column(Float, nullable=False)  # Сколько сэкономил
    payment_id = Column(UUID(as_uuid=True), ForeignKey('payments.id'), nullable=True)

    used_at = Column(DateTime, default=datetime.utcnow)

    # Отношения
    promocode = relationship("Promocode", back_populates="usages")
    user = relationship("User", back_populates="promocode_usages")

    __table_args__ = (
        Index('idx_promocode_usage_user', 'user_id'),
        Index('idx_promocode_usage_promo', 'promocode_id'),
    )


class UserServicePurchase(Base):
    """Купленные пользователем услуги (активные)"""
    __tablename__ = 'user_service_purchases'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    ad_id = Column(UUID(as_uuid=True), ForeignKey('ads.id'), nullable=True)

    service_code = Column(String(50), nullable=False)  # Код услуги
    quantity = Column(Integer, default=1)  # Количество (для per_item услуг)

    # Срок действия (для временных услуг)
    activated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)

    # Связь с транзакцией
    transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.id'), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_user_service_user', 'user_id'),
        Index('idx_user_service_ad', 'ad_id'),
        Index('idx_user_service_active', 'is_active'),
        Index('idx_user_service_expires', 'expires_at'),
    )


class ArchivedAd(Base):
    """
    Архив удалённых объявлений.
    Сюда перемещаются объявления со статусом DELETED старше 6 месяцев.
    Хранятся бессрочно для истории и возможного восстановления.
    """
    __tablename__ = 'archived_ads'

    id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(BigInteger, nullable=False, index=True)

    # Основная информация (копия из Ad)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Float, nullable=True)
    currency = Column(String(10), default='RUB')
    ad_type = Column(String(20))

    # Местоположение и категория
    region = Column(String(50), nullable=False)
    city = Column(String(100), nullable=True)
    category = Column(String(50), nullable=False)
    subcategory = Column(String(50), nullable=True)

    # Медиа (file_id могут устареть, но храним для истории)
    photos = Column(ARRAY(String), default=[])
    video = Column(String, nullable=True)

    # Хэштеги
    hashtags = Column(ARRAY(String), default=[])

    # Статистика на момент архивации
    views_count = Column(Integer, default=0)
    favorites_count = Column(Integer, default=0)
    contacts_count = Column(Integer, default=0)

    # Временные метки
    created_at = Column(DateTime, nullable=False)      # Когда создано
    published_at = Column(DateTime, nullable=True)     # Когда опубликовано
    deleted_at = Column(DateTime, nullable=True)       # Когда удалено пользователем
    archived_at = Column(DateTime, default=datetime.utcnow)  # Когда перемещено в архив

    # Причина удаления/архивации
    archive_reason = Column(String(50), default='expired_deletion')  # expired_deletion, admin_cleanup

    __table_args__ = (
        Index('idx_archived_ad_user', 'user_id'),
        Index('idx_archived_ad_date', 'archived_at'),
    )