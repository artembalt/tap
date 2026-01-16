# bot/utils/llm_moderation.py
"""
LLM-модерация объявлений с использованием Claude API.
Второй уровень проверки после rule-based фильтра.
"""

import logging
import json
import httpx
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


# Circuit breaker настройки
CIRCUIT_BREAKER_THRESHOLD = 3  # Количество ошибок для срабатывания
CIRCUIT_BREAKER_TIMEOUT = 300  # Секунд до повторной попытки (5 минут)


class ModerationCategory(str, Enum):
    """Категории нарушений"""
    SAFE = "safe"
    SPAM = "spam"
    SCAM = "scam"
    PROFANITY = "profanity"
    THREATS = "threats"
    HATE_SPEECH = "hate_speech"
    ADULT_CONTENT = "adult_content"
    DRUGS = "drugs"
    TERRORISM = "terrorism"
    FRAUD = "fraud"
    PERSONAL_DATA = "personal_data"  # телефоны, ссылки в обход


@dataclass
class LLMModerationResult:
    """Результат LLM-модерации"""
    is_safe: bool
    category: ModerationCategory
    confidence: float  # 0.0 - 1.0
    reason: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


# Системный промпт для модерации
MODERATION_SYSTEM_PROMPT = """Ты — модератор объявлений на торговой площадке. Твоя задача — проверять объявления на соответствие правилам.

ЗАПРЕЩЕНО:
1. Спам и реклама сторонних сервисов
2. Мошенничество (пирамиды, "лёгкий заработок", фейковые схемы)
3. Нецензурная лексика и оскорбления
4. Угрозы и призывы к насилию
5. Разжигание ненависти (расизм, ксенофобия, дискриминация)
6. Контент для взрослых (порно, эскорт)
7. Наркотики и запрещённые вещества
8. Терроризм и экстремизм
9. Контактные данные в обход платформы (телефоны, ссылки, @username)

РАЗРЕШЕНО:
- Обычные объявления о продаже товаров и услуг
- Описание товаров с характеристиками
- Упоминание брендов и моделей
- Указание цен и условий

ВАЖНО — УЧИТЫВАЙ КАТЕГОРИЮ ОБЪЯВЛЕНИЯ:
- В категории "Растения/Сад" слова: трава, газон, семена, рассада — РАЗРЕШЕНЫ
- В категории "Животные" слова: корм, питомник, вязка — РАЗРЕШЕНЫ
- В категории "Авто" слова: тонировка, глушитель, обвес — РАЗРЕШЕНЫ
- В категории "Красота/Здоровье" слова: массаж, уход за телом — РАЗРЕШЕНЫ
- Оценивай слова В КОНТЕКСТЕ категории, не блокируй легитимные товары

Отвечай СТРОГО в JSON формате:
{
  "is_safe": true/false,
  "category": "safe|spam|scam|profanity|threats|hate_speech|adult_content|drugs|terrorism|fraud|personal_data",
  "confidence": 0.0-1.0,
  "reason": "краткое объяснение на русском (1-2 предложения)"
}"""


class ClaudeModerator:
    """Модератор на базе Claude API"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
        threshold: float = 0.7
    ):
        self.api_key = api_key
        self.model = model
        self.threshold = threshold
        self.api_url = "https://api.anthropic.com/v1/messages"

        # Circuit breaker state
        self._error_count = 0
        self._circuit_open_until = 0.0
        self._last_error_logged = 0.0

    async def moderate(
        self,
        text: str,
        ad_category: str = None,
        ad_subcategory: str = None,
        content_type: str = None
    ) -> LLMModerationResult:
        """
        Модерация текста объявления.

        Args:
            text: Текст для проверки (заголовок + описание)
            ad_category: Категория объявления (для контекста)
            ad_subcategory: Рубрика объявления (для контекста)
            content_type: Тип контента (link_title, link_url, title, description)

        Returns:
            LLMModerationResult с результатом модерации
        """
        if not self.api_key:
            logger.warning("[LLM] Claude API key не настроен, пропускаем LLM-модерацию")
            return LLMModerationResult(
                is_safe=True,
                category=ModerationCategory.SAFE,
                confidence=0.0,
                reason="LLM-модерация отключена (нет API ключа)"
            )

        if not text or len(text.strip()) < 3:
            return LLMModerationResult(
                is_safe=True,
                category=ModerationCategory.SAFE,
                confidence=1.0,
                reason="Текст слишком короткий для анализа"
            )

        try:
            result = await self._call_claude(text, ad_category, ad_subcategory, content_type)
            return result
        except Exception as e:
            logger.error(f"[LLM] Ошибка модерации: {e}")
            # При ошибке пропускаем (fail-open) — rule-based уже проверил
            return LLMModerationResult(
                is_safe=True,
                category=ModerationCategory.SAFE,
                confidence=0.0,
                reason=f"Ошибка LLM: {str(e)[:50]}"
            )

    async def _call_claude(
        self,
        text: str,
        ad_category: str = None,
        ad_subcategory: str = None,
        content_type: str = None
    ) -> LLMModerationResult:
        """Вызов Claude API"""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }

        # Формируем запрос с категорией и рубрикой для контекста
        context_parts = []
        if ad_category:
            context_parts.append(f"Категория: {ad_category}")
        if ad_subcategory:
            context_parts.append(f"Рубрика: {ad_subcategory}")

        # Добавляем контекст типа контента
        content_type_context = ""
        if content_type == "link_title":
            content_type_context = (
                "\n\nВАЖНО: Это НАЗВАНИЕ ССЫЛКИ (заголовок кнопки), а не рекламный текст! "
                "Названия типа 'Мой канал', 'Мой сайт', 'Геопозиция', 'Подробнее', 'Ссылка на товар' — "
                "это НОРМАЛЬНЫЕ названия для кнопки-ссылки. Блокируй только явный мат, угрозы или спам."
            )
        elif content_type == "link_url":
            content_type_context = (
                "\n\nВАЖНО: Это URL ссылки, которую пользователь прикрепляет к объявлению. "
                "Проверь, не ведёт ли ссылка на запрещённый контент (порно, наркотики, мошенничество). "
                "Обычные ссылки на соцсети, магазины, карты — РАЗРЕШЕНЫ."
            )

        if context_parts:
            context = "\n".join(context_parts)
            user_content = f"{context}{content_type_context}\n\nТекст для проверки:\n{text[:2000]}"
        else:
            user_content = f"Проверь это:{content_type_context}\n\n{text[:2000]}"

        payload = {
            "model": self.model,
            "max_tokens": 256,
            "system": MODERATION_SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": user_content
                }
            ]
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                self.api_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()

        # Парсим ответ
        content = data.get("content", [{}])[0].get("text", "")
        return self._parse_response(content, data)

    def _parse_response(self, content: str, raw: Dict) -> LLMModerationResult:
        """Парсинг JSON ответа от Claude"""
        try:
            # Извлекаем JSON из ответа
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                result = json.loads(json_str)
            else:
                raise ValueError("JSON не найден в ответе")

            category_str = result.get("category", "safe").lower()
            try:
                category = ModerationCategory(category_str)
            except ValueError:
                category = ModerationCategory.SAFE

            confidence = float(result.get("confidence", 0.5))
            is_safe = result.get("is_safe", True)

            # Применяем порог уверенности
            if not is_safe and confidence < self.threshold:
                logger.info(
                    f"[LLM] Низкая уверенность ({confidence:.2f} < {self.threshold}), "
                    f"пропускаем объявление"
                )
                is_safe = True

            return LLMModerationResult(
                is_safe=is_safe,
                category=category,
                confidence=confidence,
                reason=result.get("reason"),
                raw_response=raw
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"[LLM] Ошибка парсинга ответа: {e}, content: {content[:200]}")
            return LLMModerationResult(
                is_safe=True,
                category=ModerationCategory.SAFE,
                confidence=0.0,
                reason="Ошибка парсинга ответа LLM"
            )


# Глобальный экземпляр модератора (инициализируется при первом использовании)
_moderator: Optional[ClaudeModerator] = None


def get_moderator() -> Optional[ClaudeModerator]:
    """Получить экземпляр модератора"""
    global _moderator
    if _moderator is None:
        try:
            from bot.config import settings
            if settings.CLAUDE_API_KEY and settings.LLM_MODERATION_ENABLED:
                _moderator = ClaudeModerator(
                    api_key=settings.CLAUDE_API_KEY,
                    model=settings.CLAUDE_MODEL,
                    threshold=settings.LLM_MODERATION_THRESHOLD
                )
                logger.info(f"[LLM] Claude модератор инициализирован (model={settings.CLAUDE_MODEL})")
            else:
                logger.info("[LLM] LLM-модерация отключена")
        except Exception as e:
            logger.error(f"[LLM] Ошибка инициализации модератора: {e}")
    return _moderator


async def moderate_with_llm(
    text: str,
    ad_category: str = None,
    ad_subcategory: str = None,
    content_type: str = None
) -> LLMModerationResult:
    """
    Удобная функция для модерации текста.

    Args:
        text: Текст для проверки
        ad_category: Категория объявления
        ad_subcategory: Рубрика объявления
        content_type: Тип контента (link_title, link_url, title, description)

    Использование:
        result = await moderate_with_llm("Продам семена", ad_category="Растения", ad_subcategory="Рассада и семена")
        if not result.is_safe:
            print(f"Отклонено: {result.reason}")
    """
    moderator = get_moderator()
    if moderator is None:
        return LLMModerationResult(
            is_safe=True,
            category=ModerationCategory.SAFE,
            confidence=0.0,
            reason="LLM-модерация не настроена"
        )
    return await moderator.moderate(text, ad_category, ad_subcategory, content_type)


# Маппинг категорий на русские названия
CATEGORY_NAMES = {
    ModerationCategory.SAFE: "Безопасно",
    ModerationCategory.SPAM: "Спам",
    ModerationCategory.SCAM: "Мошенничество",
    ModerationCategory.PROFANITY: "Нецензурная лексика",
    ModerationCategory.THREATS: "Угрозы",
    ModerationCategory.HATE_SPEECH: "Разжигание ненависти",
    ModerationCategory.ADULT_CONTENT: "Контент 18+",
    ModerationCategory.DRUGS: "Наркотики",
    ModerationCategory.TERRORISM: "Терроризм",
    ModerationCategory.FRAUD: "Финансовое мошенничество",
    ModerationCategory.PERSONAL_DATA: "Контактные данные в обход",
}


def get_rejection_message(result: LLMModerationResult) -> str:
    """Получить сообщение для пользователя при отклонении"""
    category_name = CATEGORY_NAMES.get(result.category, "Нарушение правил")
    reason = result.reason or "Контент не соответствует правилам площадки"

    return (
        f"❌ <b>Объявление отклонено</b>\n\n"
        f"<b>Причина:</b> {category_name}\n"
        f"<b>Подробности:</b> {reason}\n\n"
        f"Пожалуйста, исправьте объявление и попробуйте снова."
    )
