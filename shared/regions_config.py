# shared/regions_config.py
"""Конфигурация регионов и каналов для публикации объявлений"""

from typing import Dict, List, Optional
from dataclasses import dataclass

# Список доступных регионов
REGIONS = {
    "kaliningrad": "Калининград",
    "spb": "Санкт-Петербург", 
    "lenoblast": "Ленинградская область",
    "karelia": "Карелия",
    "komi": "Коми",
    "arkhangelsk": "Архангельск",
    "nenets": "Ненецкий АО",
    "vologda": "Вологда",
    "murmansk": "Мурманск",
    "novgorod": "Новгород",
    "pskov": "Псков",
    "test": "Тестовый регион"
    
}

# Список доступных категорий товаров
CATEGORIES = {
    "realty": "🏠 Недвижимость",
    "auto": "🚗 Автомобили",
    "smartphones": "📱 Смартфоны и техника",
    "building": "🔨 Стройматериалы",
    "jobs": "💼 Работа",
    "services": "🛠 Услуги",
    "clothes": "👕 Одежда и обувь",
    "furniture": "🪑 Мебель",
    "electronics": "💻 Электроника",
    "pets": "🐕 Животные",
    "hobbies": "🎨 Хобби и отдых",
    "kids": "👶 Детские товары"
}

# Рубрики для каждой категории (подкатегории)
SUBCATEGORIES = {
    "realty": {
        "apartments": "Квартиры",
        "rooms": "Комнаты",
        "houses": "Дома, дачи",
        "land": "Земельные участки",
        "garage": "Гаражи",
        "commercial": "Коммерческая недвижимость"
    },
    "auto": {
        "cars": "Легковые автомобили",
        "trucks": "Грузовые автомобили",
        "moto": "Мотоциклы и мототехника",
        "water": "Водный транспорт",
        "special": "Спецтехника",
        "parts": "Запчасти и аксессуары"
    },
    "smartphones": {
        "phones": "Мобильные телефоны",
        "tablets": "Планшеты",
        "laptops": "Ноутбуки",
        "computers": "Компьютеры",
        "accessories": "Аксессуары",
        "photo": "Фото и видео техника"
    },
    "building": {
        "materials": "Стройматериалы",
        "tools": "Инструменты",
        "plumbing": "Сантехника",
        "electrical": "Электрика",
        "doors": "Двери и окна",
        "other": "Прочее"
    },
    "jobs": {
        "vacancies": "Вакансии",
        "resume": "Резюме"
    },
    "services": {
        "repair": "Ремонт и строительство",
        "transport": "Грузоперевозки",
        "beauty": "Красота и здоровье",
        "education": "Образование",
        "cleaning": "Уборка",
        "other": "Другие услуги"
    },
    "clothes": {
        "men": "Мужская одежда",
        "women": "Женская одежда",
        "shoes": "Обувь",
        "accessories": "Аксессуары"
    },
    "furniture": {
        "living": "Мебель для гостиной",
        "bedroom": "Мебель для спальни",
        "kitchen": "Кухонная мебель",
        "office": "Офисная мебель",
        "other": "Прочая мебель"
    },
    "electronics": {
        "tv": "Телевизоры",
        "audio": "Аудиотехника",
        "appliances": "Бытовая техника",
        "games": "Игровые приставки",
        "other": "Прочее"
    },
    "pets": {
        "dogs": "Собаки",
        "cats": "Кошки",
        "birds": "Птицы",
        "fish": "Рыбки",
        "other": "Другие животные",
        "goods": "Товары для животных"
    },
    "hobbies": {
        "sport": "Спорт и отдых",
        "books": "Книги",
        "music": "Музыкальные инструменты",
        "collectibles": "Коллекционирование",
        "other": "Прочее"
    },
    "kids": {
        "clothes": "Детская одежда",
        "toys": "Игрушки",
        "furniture": "Детская мебель",
        "transport": "Детский транспорт",
        "other": "Прочее"
    }
}

# Типы сделок
DEAL_TYPES = {
    "sell": "💰 Продаю",
    "buy": "🔍 Куплю",
    "search": "🔎 Ищу",
    "exchange": "🔄 Обмен",
    "service": "🛠 Услуга"
}

# Состояние товара
CONDITION_TYPES = {
    "new": "✨ Новый",
    "used": "📦 Не новый"
}

# Типы доставки
DELIVERY_TYPES = {
    "pickup": "🏪 Самовывоз",
    "city": "🏙 По городу",
    "region": "🗺 По региону",
    "russia": "🇷🇺 По России"
}

# Рубрики которые требуют выбора доставки
CATEGORIES_WITH_DELIVERY = [
    "smartphones", "building", "clothes", "furniture", 
    "electronics", "hobbies", "kids"
]

# Типы сделок которые требуют указания состояния
DEAL_TYPES_WITH_CONDITION = ["sell", "buy", "search", "exchange"]

# Конфигурация каналов для публикации объявлений
CHANNELS_CONFIG = {
    "test": {
        "main": "@prodaytest",  # Главный канал для всех объявлений
        "menu": "@prodaytest_menu",      # Канал с меню категорий
        "categories": {
            "realty": "@prodaytest_realty",
            "auto": "@prodaytest_avto",
            "smartphones": "@prodaytest_smartphones"
        }
    },

    # Остальные регионы (пока не настроены)
    "kaliningrad": {"main": "", "menu": "", "categories": {}},
    "spb": {"main": "", "menu": "", "categories": {}},
    "lenoblast": {"main": "", "menu": "", "categories": {}},
    "karelia": {"main": "", "menu": "", "categories": {}},
    "komi": {"main": "", "menu": "", "categories": {}},
    "arkhangelsk": {"main": "", "menu": "", "categories": {}},
    "nenets": {"main": "", "menu": "", "categories": {}},
    "vologda": {"main": "", "menu": "", "categories": {}},
    "murmansk": {"main": "", "menu": "", "categories": {}},
    "novgorod": {"main": "", "menu": "", "categories": {}},
    "pskov": {"main": "", "menu": "", "categories": {}}
}

# Платные услуги и их стоимость
PAID_SERVICES = {
    "contact_buttons": {
        "name": "Кнопки связи",
        "description": "Добавить кнопки Позвонить/Написать под объявлением",
        "price": 50,
        "duration_days": 30
    },
    "pin_channel": {
        "name": "Закрепление в канале",
        "description": "Закрепить объявление в канале на 24 часа",
        "price_range": (100, 5000),  # Зависит от региона
        "duration_hours": 24
    },
    "main_channel": {
        "name": "Публикация в главном канале",
        "description": "Разместить в главном канале региона",
        "price": 200,
        "duration_days": 7
    },
    "multi_region": {
        "name": "Мультирегион",
        "description": "Публикация сразу в нескольких регионах",
        "price_per_region": 100
    },
    "stories": {
        "name": "Сториз канала",
        "description": "Попадание в историю канала",
        "price": 150,
        "duration_hours": 24
    },
    "business_account": {
        "name": "Бизнес-аккаунт",
        "description": "Снятие лимитов, верификация, аналитика",
        "price": 1000,
        "period": "month"
    },
    "premium_category": {
        "name": "Премиум категория",
        "description": "Размещение в премиум категории",
        "price": 300,
        "duration_days": 30
    }
}

# Лимиты для пользователей
USER_LIMITS = {
    "free": {
        "ads_per_day": 3,
        "ads_per_hour": 1,
        "photos_per_ad": 5,
        "video_per_ad": 0,
        "description_length": 1000,
        "active_ads": 10
    },
    "verified": {
        "ads_per_day": 10,
        "ads_per_hour": 3,
        "photos_per_ad": 10,
        "video_per_ad": 1,
        "description_length": 2000,
        "active_ads": 30
    },
    "business": {
        "ads_per_day": 100,
        "ads_per_hour": 20,
        "photos_per_ad": 10,
        "video_per_ad": 1,
        "description_length": 5000,
        "active_ads": 1000
    }
}

# Антиспам настройки
ANTISPAM_CONFIG = {
    "min_interval_seconds": 30,  # Минимальный интервал между сообщениями
    "max_similar_ads": 3,        # Максимум похожих объявлений
    "ban_duration_hours": 24,    # Длительность бана
    "reports_for_autoban": 3,    # Количество жалоб для автобана
    "suspicious_words": [
        "крипта", "криптовалюта", "заработок", "пассивный доход",
        "млм", "сетевой маркетинг", "быстрые деньги"
    ]
}

@dataclass
class RegionConfig:
    """Класс для работы с конфигурацией региона"""
    code: str
    name: str
    main_channel: str
    menu_channel: str
    categories: Dict[str, str]
    
    @classmethod
    def get_region(cls, region_code: str) -> Optional['RegionConfig']:
        """Получить конфигурацию региона по коду"""
        if region_code not in REGIONS:
            return None
            
        config = CHANNELS_CONFIG.get(region_code, {})
        return cls(
            code=region_code,
            name=REGIONS[region_code],
            main_channel=config.get("main", ""),
            menu_channel=config.get("menu", ""),
            categories=config.get("categories", {})
        )
    
    def get_channel_for_category(self, category: str) -> Optional[str]:
        """Получить канал для категории"""
        return self.categories.get(category)
    
    def is_configured(self) -> bool:
        """Проверить, настроен ли регион"""
        return bool(self.main_channel and self.categories)

def get_price_for_service(service: str, region: str = None) -> int:
    """Получить цену услуги для региона"""
    service_config = PAID_SERVICES.get(service, {})
    
    if "price_range" in service_config and region:
        # Логика определения цены по региону
        # Можно добавить коэффициенты для разных регионов
        min_price, max_price = service_config["price_range"]
        region_coefficients = {
            "spb": 1.0,
            "kaliningrad": 0.7,
            "pskov": 0.5,
            # и т.д.
        }
        coef = region_coefficients.get(region, 0.6)
        return int(min_price + (max_price - min_price) * coef)
    
    return service_config.get("price", 0)