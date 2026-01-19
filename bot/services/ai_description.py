# bot/services/ai_description.py
"""
Сервис улучшения описаний объявлений с помощью Claude AI.
Использует официальный Anthropic SDK.
"""

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AIDescriptionResult:
    """Результат улучшения описания"""
    success: bool
    improved_text: Optional[str] = None
    error: Optional[str] = None


# Системный промпт для улучшения описаний
IMPROVE_DESCRIPTION_PROMPT = """Ты — помощник для написания объявлений о продаже на торговой площадке.

Твоя задача — улучшить описание объявления, сохранив всю информацию от пользователя.

Правила:
1. Сохрани ВСЮ фактическую информацию из оригинала
2. Исправь орфографию и пунктуацию
3. Сделай текст более читаемым и структурированным
4. Добавь эмодзи где уместно (не больше 2-3)
5. Длина: 2-5 предложений (не больше 500 символов)
6. Тон: дружелюбный, но деловой
7. НЕ добавляй информацию, которой нет в оригинале
8. НЕ добавляй цену, контакты, призывы "звоните/пишите"
9. Пиши на русском языке

Верни ТОЛЬКО улучшенный текст описания, без пояснений."""


class AIDescriptionService:
    """Сервис улучшения описаний через Claude API (официальный SDK)"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
    ):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        """Ленивая инициализация клиента"""
        if self._client is None:
            import anthropic
            import httpx
            # Явно создаём httpx клиент чтобы избежать конфликтов с aiogram
            http_client = httpx.AsyncClient(timeout=30.0)
            self._client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                http_client=http_client
            )
        return self._client

    async def improve_description(
        self,
        original_text: str,
        title: str = None,
        category: str = None,
        subcategory: str = None,
    ) -> AIDescriptionResult:
        """
        Улучшить описание объявления.
        """
        if not self.api_key:
            logger.warning("[AI_DESC] API ключ не настроен")
            return AIDescriptionResult(
                success=False,
                error="Функция временно недоступна"
            )

        if not original_text or len(original_text.strip()) < 5:
            return AIDescriptionResult(
                success=False,
                error="Описание слишком короткое"
            )

        try:
            result = await self._call_claude(original_text, title, category, subcategory)
            return result
        except Exception as e:
            logger.error(f"[AI_DESC] Ошибка: {type(e).__name__}: {e}")
            return AIDescriptionResult(
                success=False,
                error="Сервис временно недоступен, попробуйте позже"
            )

    async def _call_claude(
        self,
        original_text: str,
        title: str = None,
        category: str = None,
        subcategory: str = None,
    ) -> AIDescriptionResult:
        """Вызов Claude API через официальный SDK"""

        # Формируем контекст
        context_parts = []
        if title:
            context_parts.append(f"Заголовок: {title}")
        if category:
            context_parts.append(f"Категория: {category}")
        if subcategory:
            context_parts.append(f"Рубрика: {subcategory}")

        context = "\n".join(context_parts) if context_parts else ""

        user_message = f"""{context}

Оригинальное описание от пользователя:
{original_text[:1000]}

Улучши это описание:"""

        client = self._get_client()

        message = await client.messages.create(
            model=self.model,
            max_tokens=512,
            system=IMPROVE_DESCRIPTION_PROMPT,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        # Извлекаем текст из ответа
        content = message.content[0].text.strip() if message.content else ""

        if not content:
            return AIDescriptionResult(
                success=False,
                error="Не удалось улучшить описание"
            )

        # Обрезаем если слишком длинное
        if len(content) > 1000:
            content = content[:997] + "..."

        logger.info(f"[AI_DESC] Успешно улучшено: {len(original_text)} -> {len(content)} символов")

        return AIDescriptionResult(
            success=True,
            improved_text=content
        )


# Глобальный экземпляр сервиса
_service: Optional[AIDescriptionService] = None


def get_ai_description_service() -> Optional[AIDescriptionService]:
    """Получить экземпляр сервиса"""
    global _service
    if _service is None:
        try:
            from bot.config import settings
            if settings.CLAUDE_API_KEY and settings.AI_DESCRIPTION_ENABLED:
                _service = AIDescriptionService(
                    api_key=settings.CLAUDE_API_KEY,
                    model=settings.CLAUDE_MODEL,
                )
                logger.info(f"[AI_DESC] Сервис инициализирован (model={settings.CLAUDE_MODEL})")
            else:
                logger.info("[AI_DESC] Сервис отключен")
        except Exception as e:
            logger.error(f"[AI_DESC] Ошибка инициализации: {e}")
    return _service


async def improve_description(
    original_text: str,
    title: str = None,
    category: str = None,
    subcategory: str = None,
) -> AIDescriptionResult:
    """
    Удобная функция для улучшения описания.

    Использование:
        result = await improve_description("телефон норм сост", title="iPhone 15")
        if result.success:
            print(result.improved_text)
    """
    service = get_ai_description_service()
    if service is None:
        return AIDescriptionResult(
            success=False,
            error="Функция временно недоступна"
        )
    return await service.improve_description(original_text, title, category, subcategory)
