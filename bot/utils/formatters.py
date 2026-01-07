# bot/utils/formatters.py
"""Форматтеры для красивого отображения данных"""

from typing import Optional, Dict, Any
from datetime import datetime
from bot.database.models import Ad, User
from shared.regions_config import REGIONS, CATEGORIES

def format_price(price: Optional[float]) -> str:
    """Форматировать цену"""
    if price is None or price == 0:
        return "Договорная"
    return f"{int(price):,} ₽".replace(",", " ")

def format_date(date: datetime) -> str:
    """Форматировать дату"""
    if not date:
        return "Неизвестно"
    
    now = datetime.utcnow()
    delta = now - date
    
    if delta.days == 0:
        hours = delta.seconds // 3600
        if hours == 0:
            minutes = delta.seconds // 60
            return f"{minutes} мин. назад"
        return f"{hours} ч. назад"
    elif delta.days == 1:
        return "Вчера"
    elif delta.days < 7:
        return f"{delta.days} дн. назад"
    else:
        return date.strftime("%d.%m.%Y")

def format_ad_detail(ad: Ad) -> str:
    """
    Форматировать детальное отображение объявления
    
    Args:
        ad: Объект объявления
        
    Returns:
        Отформатированный текст объявления
    """
    
    # Статус объявления
    status_emoji = {
        "active": "✅",
        "pending": "⏳",
        "archived": "📦",
        "rejected": "❌",
        "deleted": "🗑"
    }.get(ad.status, "❓")
    
    status_text = {
        "active": "Активно",
        "pending": "На модерации",
        "archived": "В архиве",
        "rejected": "Отклонено",
        "deleted": "Удалено"
    }.get(ad.status, "Неизвестно")
    
    # Формируем текст
    text = f"<b>{ad.title}</b>\n\n"
    
    # Описание
    text += f"{ad.description}\n\n"
    
    # Цена
    text += f"💰 <b>Цена:</b> {format_price(ad.price)}\n"
    
    # Регион и категория
    region_name = REGIONS.get(ad.region, ad.region)
    category_name = CATEGORIES.get(ad.category, ad.category)
    text += f"📍 <b>Регион:</b> {region_name}\n"
    text += f"📂 <b>Категория:</b> {category_name}\n"
    
    # Статус
    text += f"📊 <b>Статус:</b> {status_emoji} {status_text}\n"
    
    # Статистика
    text += f"\n📈 <b>Статистика:</b>\n"
    text += f"   👁 Просмотров: {ad.views_count}\n"
    text += f"   ⭐ В избранном: {ad.favorites_count}\n"
    text += f"   💬 Контактов: {ad.contacts_count}\n"
    
    # Дата создания
    text += f"\n🕐 <b>Создано:</b> {format_date(ad.created_at)}\n"
    
    # ID объявления (для отладки и поддержки)
    text += f"\n🆔 <code>{ad.id}</code>"
    
    return text

def format_ad_list_item(ad: Ad, index: int = 0) -> str:
    """
    Форматировать объявление для списка
    
    Args:
        ad: Объект объявления
        index: Номер в списке
        
    Returns:
        Краткая строка для списка
    """
    
    status_emoji = {
        "active": "✅",
        "pending": "⏳",
        "archived": "📦",
        "rejected": "❌"
    }.get(ad.status, "❓")
    
    # Обрезаем заголовок если длинный
    title = ad.title[:40] + "..." if len(ad.title) > 40 else ad.title
    
    text = f"{index}. {status_emoji} <b>{title}</b>\n"
    text += f"   💰 {format_price(ad.price)} | "
    text += f"👁 {ad.views_count} | "
    text += f"📂 {CATEGORIES.get(ad.category, ad.category)}\n"
    
    return text

def format_user_profile(user: User, ad_count: int = 0) -> str:
    """
    Форматировать профиль пользователя
    
    Args:
        user: Объект пользователя
        ad_count: Количество активных объявлений
        
    Returns:
        Отформатированный профиль
    """
    
    text = f"👤 <b>Профиль пользователя</b>\n\n"
    
    # Имя
    name = user.first_name
    if user.last_name:
        name += f" {user.last_name}"
    text += f"<b>Имя:</b> {name}\n"
    
    # Username
    if user.username:
        text += f"<b>Username:</b> @{user.username}\n"
    
    # Статус
    if user.is_premium:
        text += f"<b>Статус:</b> ⭐ Premium\n"
    
    # Статистика
    text += f"\n📊 <b>Статистика:</b>\n"
    text += f"   📋 Всего объявлений: {user.total_ads}\n"
    text += f"   ✅ Активных: {ad_count}\n"
    text += f"   ⭐ Рейтинг: {user.rating:.1f}/5.0\n"
    text += f"   💬 Отзывов: {user.reviews_count}\n"
    
    # Дата регистрации
    text += f"\n📅 <b>На платформе с:</b> {format_date(user.created_at)}"
    
    return text

def format_search_results(ads: list, query: str = "") -> str:
    """
    Форматировать результаты поиска
    
    Args:
        ads: Список объявлений
        query: Поисковый запрос
        
    Returns:
        Отформатированный список результатов
    """
    
    if not ads:
        text = "🔍 <b>Результаты поиска</b>\n\n"
        if query:
            text += f"По запросу '<i>{query}</i>' ничего не найдено.\n\n"
        else:
            text += "Ничего не найдено.\n\n"
        text += "Попробуйте изменить параметры поиска."
        return text
    
    text = f"🔍 <b>Результаты поиска</b> ({len(ads)})\n"
    if query:
        text += f"По запросу: <i>{query}</i>\n"
    text += "\n"
    
    for i, ad in enumerate(ads, 1):
        text += format_ad_list_item(ad, i)
        text += "\n"
    
    return text

def truncate_text(text: str, max_length: int = 100) -> str:
    """
    Обрезать текст до указанной длины
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина
        
    Returns:
        Обрезанный текст с многоточием
    """
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

# Для обратной совместимости
def format_ad_preview(data: Dict[str, Any]) -> str:
    """Форматирование превью объявления перед публикацией"""
    from shared.regions_config import (
        REGIONS, CATEGORIES, SUBCATEGORIES, DEAL_TYPES, 
        CONDITION_TYPES, DELIVERY_TYPES
    )
    
    region = data.get('region', '')
    category = data.get('category', '')
    subcategory = data.get('subcategory', '')
    deal_type = data.get('deal_type', '')
    condition = data.get('condition')
    title = data.get('title', '')
    description = data.get('description', '')
    price = data.get('price', 'Не указана')
    delivery = data.get('delivery')
    photos_count = len(data.get('photos', []))
    has_video = bool(data.get('video'))
    
    # Формируем текст
    region_name = REGIONS.get(region, region)
    category_name = CATEGORIES.get(category, category)
    subcategory_name = SUBCATEGORIES.get(category, {}).get(subcategory, subcategory)
    deal_type_name = DEAL_TYPES.get(deal_type, '')
    condition_text = f" / {CONDITION_TYPES.get(condition, '')}" if condition else ""
    delivery_text = f" | {DELIVERY_TYPES.get(delivery, '')}" if delivery else ""
    
    title_text = f"<b>{title}</b>\n\n" if title else ""
    
    # ВАЖНО: Ограничиваем длину описания (Telegram caption лимит 1024 символа)
    # Оставляем запас на остальной текст
    max_description_length = 600
    if description:
        if len(description) > max_description_length:
            description_text = f"{description[:max_description_length]}...\n\n"
        else:
            description_text = f"{description}\n\n"
    else:
        description_text = ""
    
    media_info = []
    if photos_count > 0:
        media_info.append(f"📸 {photos_count} фото")
    if has_video:
        media_info.append("🎥 Видео")
    media_text = " | ".join(media_info) if media_info else "Без медиа"
    
    preview = f"""📢 <b>Превью вашего объявления</b>

📍 Регион: {region_name}
📂 Категория: {category_name}
📑 Рубрика: {subcategory_name}
💼 Тип: {deal_type_name}{condition_text}

{title_text}{description_text}💰 Цена: {price}{delivery_text}
{media_text}

<b>Всё верно?</b>"""
    
    return preview

async def format_ad_for_channel(ad) -> str:
    """Форматирование объявления для канала"""
    return f"{ad.title}\n\n{ad.description}\n\n💰 Цена: {ad.price or 'Договорная'} ₽"
