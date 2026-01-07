
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
    builder = InlineKeyboardBuilder()
    builder.button(text="Тестовый регион", callback_data="region_test")
    builder.button(text="Санкт-Петербург", callback_data="region_spb")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()

def get_categories_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора категории"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Недвижимость", callback_data="category_realty")
    builder.button(text="🚗 Автомобили", callback_data="category_auto")
    builder.button(text="📱 Смартфоны", callback_data="category_smartphones")
    builder.button(text="❌ Отмена", callback_data="category_cancel")
    builder.adjust(2)
    return builder.as_markup()

def get_ad_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа объявления"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Продаю", callback_data="type_sell")
    builder.button(text="🔍 Куплю", callback_data="type_buy")
    builder.adjust(2)
    return builder.as_markup()

def get_skip_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для пропуска шага"""
    builder = InlineKeyboardBuilder()
    builder.button(text="➡️ Пропустить", callback_data="skip")
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()

def get_photo_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для загрузки фото"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Готово", callback_data="skip")
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()

def get_subcategories_keyboard(category: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора рубрики (подкатегории)"""
    from shared.regions_config import SUBCATEGORIES
    
    builder = InlineKeyboardBuilder()
    
    subcategories = SUBCATEGORIES.get(category, {})
    for key, name in subcategories.items():
        builder.button(text=name, callback_data=f"subcategory_{key}")
    
    builder.button(text="🔙 Назад", callback_data="back_to_category")
    builder.adjust(2)
    return builder.as_markup()

def get_deal_types_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа сделки"""
    from shared.regions_config import DEAL_TYPES
    
    builder = InlineKeyboardBuilder()
    
    for key, name in DEAL_TYPES.items():
        builder.button(text=name, callback_data=f"deal_{key}")
    
    builder.button(text="🔙 Назад", callback_data="back_to_subcategory")
    builder.adjust(2)
    return builder.as_markup()

def get_condition_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора состояния"""
    from shared.regions_config import CONDITION_TYPES
    
    builder = InlineKeyboardBuilder()
    
    for key, name in CONDITION_TYPES.items():
        builder.button(text=name, callback_data=f"condition_{key}")
    
    builder.adjust(2)
    return builder.as_markup()

def get_price_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для цены"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Договорная", callback_data="negotiable")
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()

def get_delivery_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора доставки"""
    from shared.regions_config import DELIVERY_TYPES
    
    builder = InlineKeyboardBuilder()
    
    for key, name in DELIVERY_TYPES.items():
        builder.button(text=name, callback_data=f"delivery_{key}")
    
    builder.adjust(2)
    return builder.as_markup()

def get_confirm_with_edit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения с редактированием"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Опубликовать", callback_data="confirm_publish")
    builder.button(text="✏️ Редактировать", callback_data="edit_ad")
    builder.button(text="❌ Отменить", callback_data="cancel_ad")
    builder.adjust(1)
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

def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Опубликовать", callback_data="confirm")
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()

def get_phone_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек телефона"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Показывать номер", callback_data="phone_show")
    builder.button(text="🔒 Скрыть номер", callback_data="phone_hide")
    return builder.as_markup()

def get_user_ads_keyboard(ads: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком объявлений пользователя"""
    builder = InlineKeyboardBuilder()
    
    for ad in ads[:10]:  # Показываем максимум 10
        # Обрезаем заголовок если длинный
        title = ad.title[:30] + "..." if len(ad.title) > 30 else ad.title
        builder.button(text=f"📌 {title}", callback_data=f"view_my_ad_{ad.id}")
    
    builder.button(text="🔙 Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_ad_actions_keyboard(ad_id: str, is_owner: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура действий с объявлением"""
    builder = InlineKeyboardBuilder()
    
    if is_owner:
        # Кнопки для владельца объявления
        builder.button(text="✏️ Редактировать", callback_data=f"edit_ad_{ad_id}")
        builder.button(text="📦 В архив", callback_data=f"deactivate_ad_{ad_id}")
        builder.button(text="🗑 Удалить", callback_data=f"delete_ad_{ad_id}")
        builder.button(text="📊 Статистика", callback_data=f"stats_ad_{ad_id}")
        builder.adjust(2, 2)
    else:
        # Кнопки для других пользователей
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

def get_confirm_delete_keyboard(ad_id: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="✅ Да, удалить", callback_data=f"confirm_delete_{ad_id}")
    builder.button(text="❌ Отмена", callback_data="cancel_delete")
    
    builder.adjust(1)
    return builder.as_markup()

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Главное меню", callback_data="back_to_menu")
    return builder.as_markup()
