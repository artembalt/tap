# bot/database/models.py
"""SQLAlchemy модели для базы данных"""

from datetime import datetime
from typing import Optional, List
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, 
    ForeignKey, Index, JSON, ARRAY, UUID, BigInteger, Table
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

Base = declarative_base()

# Enum классы
class UserRole(str, Enum):
    USER = "user"
    VERIFIED = "verified"
    BUSINESS = "business"
    MODERATOR = "moderator"
    ADMIN = "admin"

class AdStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    DELETED = "deleted"
    BANNED = "banned"

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
    
    # Подписки и платежи
    is_premium = Column(Boolean, default=False)
    premium_until = Column(DateTime, nullable=True)
    balance = Column(Float, default=0.0)
    total_spent = Column(Float, default=0.0)
    
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
    reports_sent = relationship("Report", foreign_keys="Report.reporter_id", back_populates="reporter")
    reviews_given = relationship("Review", foreign_keys="Review.reviewer_id", back_populates="reviewer")
    reviews_received = relationship("Review", foreign_keys="Review.reviewed_user_id", back_populates="reviewed_user")
    
    __table_args__ = (
        Index('idx_user_role', 'role'),
        Index('idx_user_created', 'created_at'),
        Index('idx_user_email', 'email'),
        Index('idx_user_phone', 'phone'),
        Index('idx_user_banned', 'is_banned'),
        Index('idx_user_premium', 'is_premium'),
        Index('idx_user_last_activity', 'last_activity'),
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
    __tablename__ = 'payments'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(BigInteger, ForeignKey('users.telegram_id'), nullable=False)
    
    # Информация о платеже
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default='RUB')
    status = Column(String(20), default=PaymentStatus.PENDING.value)
    
    # Детали платежа
    service_type = Column(String(50), nullable=False)  # Тип услуги из PAID_SERVICES
    service_details = Column(JSONB, default={})  # Дополнительные параметры
    ad_id = Column(UUID(as_uuid=True), ForeignKey('ads.id'), nullable=True)
    
    # Платежная система
    payment_system = Column(String(50), default='yoomoney')
    payment_id = Column(String(255), nullable=True)  # ID в платежной системе
    payment_url = Column(Text, nullable=True)  # Ссылка на оплату
    
    # Временные метки
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    
    # Отношения
    user = relationship("User", back_populates="payments")
    
    __table_args__ = (
        Index('idx_payment_user_status', 'user_id', 'status'),
        Index('idx_payment_created', 'created_at'),
        Index('idx_payment_expires', 'expires_at'),
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