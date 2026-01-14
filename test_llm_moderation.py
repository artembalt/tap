#!/usr/bin/env python3
"""Тест LLM-модерации объявлений"""

import asyncio
import sys
sys.path.insert(0, '/home/telegram-ads-platform')

from dotenv import load_dotenv
load_dotenv('/home/telegram-ads-platform/.env')

from bot.utils.llm_moderation import moderate_with_llm, get_rejection_message, CATEGORY_NAMES


async def test_moderation():
    """Тестируем разные типы объявлений"""

    test_cases = [
        # Нормальные объявления (должны пройти)
        ("Продам iPhone 15 Pro Max 256GB", "Отличное состояние, полный комплект, на гарантии. Покупал в М.Видео."),
        ("Сдам квартиру в центре", "2-комнатная, 55 кв.м, свежий ремонт, вся мебель и техника."),

        # Подозрительные (должны блокироваться)
        ("Заработок без вложений", "Пассивный доход от 100к в месяц! Пиши в личку, расскажу схему!"),
        ("Продам курс по крипте", "Научу зарабатывать на бинарных опционах! 1000% прибыли гарантирую!"),

        # Контактные данные в обход
        ("Продам ноутбук", "Пиши в телегу @spamer123, там дешевле договоримся"),
    ]

    print("=" * 60)
    print("ТЕСТ LLM-МОДЕРАЦИИ ОБЪЯВЛЕНИЙ")
    print("=" * 60)

    for i, (title, description) in enumerate(test_cases, 1):
        full_text = f"{title}\n\n{description}"

        print(f"\n--- Тест #{i} ---")
        print(f"Заголовок: {title}")
        print(f"Описание: {description[:50]}...")

        result = await moderate_with_llm(full_text)

        status = "✅ ПРОПУЩЕНО" if result.is_safe else "❌ ЗАБЛОКИРОВАНО"
        category = CATEGORY_NAMES.get(result.category, result.category.value)

        print(f"Результат: {status}")
        print(f"Категория: {category}")
        print(f"Уверенность: {result.confidence:.0%}")
        if result.reason:
            print(f"Причина: {result.reason}")

    print("\n" + "=" * 60)
    print("ТЕСТ ЗАВЕРШЁН")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_moderation())
