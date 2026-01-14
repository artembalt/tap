# bot/utils/content_filter.py
"""
Модуль фильтрации контента для объявлений.
Проверяет на: ссылки, телефоны, мат, угрозы, экстремизм, порнографию.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Результат проверки контента"""
    is_valid: bool
    reason: Optional[str] = None
    matched_word: Optional[str] = None


# ============================================================================
# РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ
# ============================================================================

# URL паттерны
URL_PATTERNS = [
    r'https?://[^\s]+',                          # http:// https://
    r'www\.[^\s]+',                              # www.
    r't\.me/[^\s]+',                             # t.me/
    r'telegram\.me/[^\s]+',                      # telegram.me/
    r'@[a-zA-Z][a-zA-Z0-9_]{3,}',               # @username (4+ символов)
    r'[a-zA-Z0-9-]+\.(ru|com|net|org|info|biz|рф|su|me|io|co|cc|ws|top|xyz|online|site|club|shop|store|pro|space|tech|live|tv|link|click|pw|tk|ml|ga|cf|gq)[/\s]?',
]

# Телефонные паттерны
PHONE_PATTERNS = [
    r'\+7[\s\-\(]?\d{3}[\s\-\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # +7 (999) 123-45-67
    r'8[\s\-\(]?\d{3}[\s\-\)]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',    # 8 (999) 123-45-67
    r'\d{10,11}',                                                  # 89991234567
    r'\+\d{10,15}',                                                # международные
]

# ============================================================================
# БАЗЫ ЗАПРЕЩЁННЫХ СЛОВ
# ============================================================================

# Матерные слова и их производные (корни)
PROFANITY_ROOTS = {
    # Основные корни мата
    'хуй', 'хуя', 'хуе', 'хуи', 'хую', 'хуём',
    'пизд', 'пезд',
    'блят', 'бляд', 'блядь', 'блять',
    'ебат', 'ебан', 'ебну', 'ебёт', 'ебал', 'ебла', 'ебли', 'ебло', 'ебуч', 'ёб',
    'сука', 'суки', 'сучк', 'сучар',
    'мудак', 'мудил', 'мудо',
    'залуп',
    'гандон', 'гондон',
    'педик', 'педер', 'пидор', 'пидар', 'пидр',
    'жопа', 'жоп',
    'срать', 'срал', 'сран', 'насрал', 'обосрал', 'высрал', 'засран',
    'говно', 'говён', 'говн',
    'дерьмо', 'дерьм',
    'fuck', 'shit', 'bitch', 'asshole', 'dick', 'cock', 'pussy',
    # Эвфемизмы и замены
    'xyй', 'xуй', 'ху й', 'х у й', 'п1зд', 'п и з д', 'б л я',
    'п0рн', 'пopн',
}

# Слова-угрозы и насилие
THREAT_WORDS = {
    'убью', 'убить', 'убей', 'убийство', 'убийца',
    'зарежу', 'зарезать', 'порежу',
    'застрелю', 'застрелить', 'пристрелю',
    'задушу', 'задушить', 'удавлю',
    'сожгу', 'подожгу', 'спалю',
    'взорву', 'взорвать', 'взрыв',
    'отравлю', 'отравить',
    'покалечу', 'изувечу',
    'закопаю', 'закопать',
    'грохну', 'замочу', 'мочить',
    'башку оторву', 'голову оторву',
    'кровью умоешься', 'пожалеешь',
    'найду и', 'приеду и',
}

# Терроризм и экстремизм
TERRORISM_WORDS = {
    'террор', 'терракт', 'теракт',
    'джихад', 'шахид', 'смертник',
    'игил', 'игіл', 'isis', 'isil', 'даиш',
    'алькаид', 'аль-каид', 'al-qaeda',
    'талибан', 'талиб',
    'хезболла', 'хамас',
    'взрывчатк', 'бомба', 'бомбу',
    'захват заложник', 'заложник',
    'вербовк', 'вербую', 'завербую',
    'экстремизм', 'экстремист',
    'радикал',
}

# Расизм и межнациональная рознь
RACISM_WORDS = {
    'нигер', 'негр', 'ниггер', 'nigger', 'nigga',
    'чурк', 'чурбан', 'черномаз', 'черножоп',
    'хач', 'хачик',
    'жид', 'жидов', 'жиды',
    'узкоглаз', 'косоглаз', 'желтолиц',
    'чукч',
    'москал', 'кацап', 'хохол', 'хохл',
    'бандеровец', 'бандер',
    'нацист', 'нацизм', 'фашист', 'фашизм',
    'зиг хайл', 'зигхайл', 'sieg heil', 'heil hitler', 'хайль',
    '1488', '14/88',
    'свастик',
    'белая раса', 'чистота расы', 'расовая чистота',
    'геноцид',
    'холокост отрицаю', 'холокоста не было',
    'россия для русских', 'бей',
}

# Порнография и непристойности
PORN_WORDS = {
    'порно', 'порн', 'порнух', 'порев',
    'секс за деньги', 'интим услуг', 'интим-услуг',
    'проститу', 'шлюх', 'путан',
    'эскорт', 'эскортниц',
    'минет', 'миньет',
    'анал', 'аналь',
    'оргия', 'оргии',
    'групповух',
    'бдсм', 'bdsm',
    'фетиш',
    'стриптиз',
    'вебкам', 'webcam', 'онлифанс', 'onlyfans',
    'nudes', 'nude', 'xxx', 'xxх',
    'хентай', 'hentai',
    'лолит', 'loli',
    'cp ', 'цп ',
    'детск порн', 'child porn',
    'педофил',
    'зоофил',
    'инцест',
    'изнасилов', 'насилу',
}

# Наркотики и нелегальные вещества
DRUGS_WORDS = {
    'наркот', 'нарко',
    'героин', 'кокаин', 'метамфетамин', 'мет', 'амфетамин', 'амф',
    'марихуан', 'конопл', 'канабис', 'cannabis', 'marijuana',
    'гашиш', 'гаш',
    'экстази', 'mdma', 'мдма',
    'лсд', 'lsd',
    'спайс', 'соль', 'мефедрон', 'меф',
    'закладк', 'клад', 'закл',
    'купить траву', 'продам траву',
    'грибы псилоциб', 'псилоцибин',
}

# Мошенничество и спам
SCAM_WORDS = {
    'заработок без вложений',
    'легкие деньги', 'лёгкие деньги',
    'быстрый заработок',
    'пассивный доход гарантир',
    'схема заработка',
    'вложи и получи',
    'казино', 'casino',
    'ставки на спорт', 'букмекер',
    'бинарные опционы',
    'пирамид', 'млм', 'mlm',
    'криптовалют схем',
    'обнал', 'обналичивание',
    'дроп', 'дропов',
}


def _normalize_text(text: str) -> str:
    """Нормализация текста для проверки"""
    # Приводим к нижнему регистру
    text = text.lower()

    # Замена латиницы и цифр на похожие кириллические буквы
    # (для обхода фильтров типа "xyй", "пиzда", "6лять")
    replacements = {
        # Латиница → кириллица
        'a': 'а', 'b': 'в', 'c': 'с', 'e': 'е', 'h': 'н',
        'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о',
        'p': 'р', 'r': 'г', 's': 'с', 't': 'т', 'u': 'у',
        'x': 'х', 'y': 'у', 'z': 'з',
        # Цифры → буквы
        '0': 'о', '1': 'и', '3': 'з', '4': 'ч', '6': 'б',
        '7': 'т', '8': 'в', '9': 'д',
        # Спецсимволы
        '@': 'а', '$': 'с', '|': 'и', '○': 'о',
        'ё': 'е', 'і': 'и',
        # Убираем мусор
        '*': '', '_': '', '-': '', '.': '', ',': '', '!': '', '?': '',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Убираем повторяющиеся буквы (ххххууууйййй -> хуй)
    text = re.sub(r'(.)\1{2,}', r'\1', text)

    # Убираем пробелы между буквами (х у й -> хуй)
    text = re.sub(r'\s+', ' ', text)

    return text


def check_urls(text: str) -> FilterResult:
    """Проверка на ссылки"""
    for pattern in URL_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return FilterResult(
                is_valid=False,
                reason="Ссылки запрещены в объявлениях",
                matched_word=match.group()
            )
    return FilterResult(is_valid=True)


def check_phones(text: str) -> FilterResult:
    """Проверка на телефоны"""
    # Убираем пробелы и дефисы для проверки
    clean_text = re.sub(r'[\s\-\(\)]', '', text)

    for pattern in PHONE_PATTERNS:
        clean_pattern = pattern.replace(r'[\s\-\(]?', '').replace(r'[\s\-\)]?', '').replace(r'[\s\-]?', '')
        match = re.search(clean_pattern, clean_text)
        if match:
            return FilterResult(
                is_valid=False,
                reason="Телефоны запрещены в объявлениях. Покупатели свяжутся через бота.",
                matched_word=match.group()
            )

    # Проверяем оригинальный текст на паттерны с разделителями
    for pattern in PHONE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return FilterResult(
                is_valid=False,
                reason="Телефоны запрещены в объявлениях. Покупатели свяжутся через бота.",
                matched_word=match.group()
            )

    return FilterResult(is_valid=True)


def check_profanity(text: str) -> FilterResult:
    """Проверка на мат"""
    normalized = _normalize_text(text)

    for word in PROFANITY_ROOTS:
        if word in normalized:
            return FilterResult(
                is_valid=False,
                reason="Нецензурная лексика запрещена",
                matched_word=word
            )

    return FilterResult(is_valid=True)


def check_threats(text: str) -> FilterResult:
    """Проверка на угрозы"""
    normalized = _normalize_text(text)

    for word in THREAT_WORDS:
        if word in normalized:
            return FilterResult(
                is_valid=False,
                reason="Угрозы и призывы к насилию запрещены",
                matched_word=word
            )

    return FilterResult(is_valid=True)


def check_terrorism(text: str) -> FilterResult:
    """Проверка на терроризм и экстремизм"""
    normalized = _normalize_text(text)

    for word in TERRORISM_WORDS:
        if word in normalized:
            return FilterResult(
                is_valid=False,
                reason="Экстремистский контент запрещён",
                matched_word=word
            )

    return FilterResult(is_valid=True)


def check_racism(text: str) -> FilterResult:
    """Проверка на расизм и межнациональную рознь"""
    normalized = _normalize_text(text)

    for word in RACISM_WORDS:
        if word in normalized:
            return FilterResult(
                is_valid=False,
                reason="Разжигание межнациональной розни запрещено",
                matched_word=word
            )

    return FilterResult(is_valid=True)


def check_porn(text: str) -> FilterResult:
    """Проверка на порнографию и непристойности"""
    normalized = _normalize_text(text)

    for word in PORN_WORDS:
        if word in normalized:
            return FilterResult(
                is_valid=False,
                reason="Контент для взрослых запрещён",
                matched_word=word
            )

    return FilterResult(is_valid=True)


def check_drugs(text: str) -> FilterResult:
    """Проверка на наркотики"""
    normalized = _normalize_text(text)

    for word in DRUGS_WORDS:
        if word in normalized:
            return FilterResult(
                is_valid=False,
                reason="Реклама запрещённых веществ запрещена",
                matched_word=word
            )

    return FilterResult(is_valid=True)


def check_scam(text: str) -> FilterResult:
    """Проверка на мошенничество и спам"""
    normalized = _normalize_text(text)

    for word in SCAM_WORDS:
        if word in normalized:
            return FilterResult(
                is_valid=False,
                reason="Подозрительный контент (возможное мошенничество)",
                matched_word=word
            )

    return FilterResult(is_valid=True)


def validate_content(text: str) -> FilterResult:
    """
    Полная проверка контента.
    Возвращает FilterResult с результатом проверки.
    """
    if not text:
        return FilterResult(is_valid=True)

    # Порядок проверок (от критичных к менее критичным)
    checks = [
        check_urls,
        check_phones,
        check_terrorism,
        check_racism,
        check_porn,
        check_drugs,
        check_threats,
        check_profanity,
        check_scam,
    ]

    for check in checks:
        result = check(text)
        if not result.is_valid:
            logger.warning(
                f"[FILTER] Контент отклонён: {result.reason}, "
                f"matched='{result.matched_word}', text='{text[:50]}...'"
            )
            return result

    return FilterResult(is_valid=True)


def get_rejection_message(result: FilterResult) -> str:
    """Получить сообщение для пользователя при отклонении"""
    return f"❌ <b>Текст не прошёл проверку</b>\n\n{result.reason}\n\nПожалуйста, исправьте текст и попробуйте снова."


# ============================================================================
# LLM-МОДЕРАЦИЯ (второй уровень)
# ============================================================================

async def validate_content_with_llm(
    text: str,
    ad_category: str = None,
    ad_subcategory: str = None
) -> FilterResult:
    """
    Полная проверка контента с LLM.
    Гибридный подход: сначала быстрый rule-based, потом LLM для сложных случаев.

    Использование:
        result = await validate_content_with_llm("Продам траву", ad_category="Растения", ad_subcategory="Газоны")
        if not result.is_valid:
            await message.answer(get_rejection_message(result))
    """
    if not text:
        return FilterResult(is_valid=True)

    # Шаг 1: Быстрая rule-based проверка
    rule_result = validate_content(text)
    if not rule_result.is_valid:
        return rule_result

    # Шаг 2: LLM-проверка (если включена)
    try:
        from bot.utils.llm_moderation import moderate_with_llm, ModerationCategory

        llm_result = await moderate_with_llm(text, ad_category, ad_subcategory)

        if not llm_result.is_safe:
            logger.warning(
                f"[LLM-FILTER] Контент отклонён LLM: category={llm_result.category.value}, "
                f"confidence={llm_result.confidence:.2f}, reason='{llm_result.reason}', "
                f"text='{text[:50]}...'"
            )
            return FilterResult(
                is_valid=False,
                reason=llm_result.reason or "Контент не прошёл автоматическую модерацию",
                matched_word=f"[LLM:{llm_result.category.value}]"
            )

    except ImportError:
        logger.debug("[LLM-FILTER] Модуль LLM-модерации не установлен")
    except Exception as e:
        logger.error(f"[LLM-FILTER] Ошибка LLM-модерации: {e}")
        # Fail-open: если LLM недоступен, пропускаем (rule-based уже проверил)

    return FilterResult(is_valid=True)
