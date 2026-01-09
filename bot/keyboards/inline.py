# bot/keyboards/inline.py
"""Inline клавиатуры бота"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота"""
    builder = InlineKeyboardBuilder()
    
    buttons = [
        ("📝 Подать объявление", "new_ad"),
        ("🔍 Поиск объявлений", "search"),
        ("📋 Мои объявления", "my_ads"),
        ("👤 Профиль", "profile"),
        ("ℹ️ Помощь", "help")
    ]
    
    for text, callback_data in buttons:
        builder.button(text=text, callback_data=callback_data)
    
    builder.adjust(2)
    return builder.as_markup()


def get_regions_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона"""
    from shared.regions_config import REGIONS
    
    builder = InlineKeyboardBuilder()
    
    for key, name in REGIONS.items():
        builder.button(text=name, callback_data=f"region_{key}")
    
    builder.button(text="❌ Отмена", callback_data="cancel_creation")
    builder.adjust(2)
    return builder.as_markup()


def get_categories_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора категории"""
    from shared.regions_config import CATEGORIES
    
    builder = InlineKeyboardBuilder()
    
    for key, name in CATEGORIES.items():
        builder.button(text=name, callback_data=f"category_{key}")
    
    builder.button(text="❌ Отмена", callback_data="cancel_creation")
    builder.adjust(2)
    return builder.as_markup()


def get_subcategories_keyboard(category: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора рубрики (подкатегории)"""
    from shared.regions_config import SUBCATEGORIES
    
    builder = InlineKeyboardBuilder()
    
    subcategories = SUBCATEGORIES.get(category, {})
    for key, name in subcategories.items():
        builder.button(text=name, callback_data=f"subcategory_{key}")
    
    builder.button(text="🔙 Назад", callback_data="back_to_category")
    builder.button(text="❌ Отмена", callback_data="cancel_creation")
    builder.adjust(2)
    return builder.as_markup()


def get_deal_types_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа сделки"""
    from shared.regions_config import DEAL_TYPES
    
    builder = InlineKeyboardBuilder()
    
    for key, name in DEAL_TYPES.items():
        builder.button(text=name, callback_data=f"deal_{key}")
    
    builder.button(text="🔙 Назад", callback_data="back_to_subcategory")
    builder.button(text="❌ Отмена", callback_data="cancel_creation")
    builder.adjust(2)
    return builder.as_markup()


def get_condition_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора состояния товара"""
    from shared.regions_config import CONDITION_TYPES
    
    builder = InlineKeyboardBuilder()
    
    for key, name in CONDITION_TYPES.items():
        builder.button(text=name, callback_data=f"condition_{key}")
    
    builder.button(text="❌ Отмена", callback_data="cancel_creation")
    builder.adjust(2)
    return builder.as_markup()


def get_delivery_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора способа доставки"""
    from shared.regions_config import DELIVERY_TYPES
    
    builder = InlineKeyboardBuilder()
    
    for key, name in DELIVERY_TYPES.items():
        builder.button(text=name, callback_data=f"delivery_{key}")
    
    builder.button(text="❌ Отмена", callback_data="cancel_creation")
    builder.adjust(2)
    return builder.as_markup()


def get_price_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для ввода цены"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Договорная", callback_data="negotiable")
    builder.button(text="❌ Отмена", callback_data="cancel_creation")
    builder.adjust(1)
    return builder.as_markup()


# ========== КЛАВИАТУРЫ ДЛЯ ЗАГРУЗКИ ФОТО ==========

def get_photo_skip_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура при первом запросе фото.
    Только кнопка Пропустить.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭️ Пропустить", callback_data="skip_photos")
    return builder.as_markup()


def get_photo_done_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура после загрузки фото.
    Только кнопка Далее.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Далее", callback_data="photos_done")
    return builder.as_markup()


# Для обратной совместимости
def get_skip_and_done_keyboard() -> InlineKeyboardMarkup:
    """Только Пропустить (для первого запроса фото)"""
    return get_photo_skip_keyboard()


def get_photo_done_only_keyboard() -> InlineKeyboardMarkup:
    """Только Далее (после загрузки фото)"""
    return get_photo_done_keyboard()


# ========== КЛАВИАТУРЫ ДЛЯ ВИДЕО ==========

def get_skip_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой Пропустить (для видео)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭️ Пропустить", callback_data="skip_video")
    builder.button(text="❌ Отмена", callback_data="cancel_creation")
    builder.adjust(1)
    return builder.as_markup()


# ========== КЛАВИАТУРЫ ПОДТВЕРЖДЕНИЯ ==========

def get_confirm_with_edit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения с возможностью редактирования"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Опубликовать", callback_data="confirm_publish")
    builder.button(text="✏️ Редактировать", callback_data="edit_ad")
    builder.button(text="❌ Отменить", callback_data="cancel_ad")
    builder.adjust(1)
    return builder.as_markup()


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Простая клавиатура подтверждения"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def get_confirm_delete_keyboard(ad_id: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"confirm_delete_{ad_id}")
    builder.button(text="❌ Отмена", callback_data="cancel_delete")
    builder.adjust(1)
    return builder.as_markup()


# ========== КЛАВИАТУРЫ ДЛЯ ОБЪЯВЛЕНИЙ ==========

def get_ad_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа объявления"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Продаю", callback_data="type_sell")
    builder.button(text="🔍 Куплю", callback_data="type_buy")
    builder.adjust(2)
    return builder.as_markup()


def get_phone_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек телефона"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Показывать номер", callback_data="phone_show")
    builder.button(text="🔒 Скрыть номер", callback_data="phone_hide")
    builder.adjust(1)
    return builder.as_markup()


def get_user_ads_keyboard(ads: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком объявлений пользователя"""
    builder = InlineKeyboardBuilder()
    
    for ad in ads[:10]:
        title = ad.title[:30] + "..." if len(ad.title) > 30 else ad.title
        builder.button(text=f"📌 {title}", callback_data=f"view_my_ad_{ad.id}")
    
    builder.button(text="🔙 Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def get_ad_actions_keyboard(ad_id: str, is_owner: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура действий с объявлением"""
    builder = InlineKeyboardBuilder()
    
    if is_owner:
        builder.button(text="✏️ Редактировать", callback_data=f"edit_ad_{ad_id}")
        builder.button(text="📦 В архив", callback_data=f"deactivate_ad_{ad_id}")
        builder.button(text="🗑 Удалить", callback_data=f"delete_ad_{ad_id}")
        builder.button(text="📊 Статистика", callback_data=f"stats_ad_{ad_id}")
        builder.adjust(2, 2)
    else:
        builder.button(text="💬 Написать", callback_data=f"contact_{ad_id}")
        builder.button(text="⭐ В избранное", callback_data=f"favorite_{ad_id}")
        builder.button(text="👤 Профиль", callback_data=f"profile_{ad_id}")
        builder.button(text="⚠️ Пожаловаться", callback_data=f"report_{ad_id}")
        builder.adjust(2, 2)
    
    builder.button(text="🔙 Назад", callback_data="my_ads")
    return builder.as_markup()


def get_edit_options_keyboard(ad_id: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора что редактировать"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📝 Заголовок", callback_data=f"edit_title_{ad_id}")
    builder.button(text="📄 Описание", callback_data=f"edit_description_{ad_id}")
    builder.button(text="💰 Цену", callback_data=f"edit_price_{ad_id}")
    builder.button(text="📸 Фото", callback_data=f"edit_photos_{ad_id}")
    builder.button(text="🔙 Назад", callback_data=f"view_my_ad_{ad_id}")
    
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def get_edit_preview_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура редактирования полей превью"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Заголовок", callback_data="edit_title")
    builder.button(text="📄 Описание", callback_data="edit_description")
    builder.button(text="💰 Цена", callback_data="edit_price")
    builder.button(text="📸 Фото", callback_data="edit_photos")
    builder.button(text="🎥 Видео", callback_data="edit_video")
    builder.button(text="🔙 Назад к превью", callback_data="back_to_preview")
    builder.adjust(2)
    return builder.as_markup()


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад в главное меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Главное меню", callback_data="back_to_menu")
    return builder.as_markup()


def get_photo_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для загрузки фото (устаревшая, для совместимости)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово", callback_data="photos_done")
    builder.button(text="❌ Отмена", callback_data="cancel_creation")
    return builder.as_markup()
