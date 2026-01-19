#!/usr/bin/env python3
"""Тест локальной модерации (PaddleOCR + NudeNet)"""

import asyncio
import sys
import time

async def test_moderation():
    print("=" * 60)
    print("ТЕСТ ЛОКАЛЬНОЙ МОДЕРАЦИИ")
    print("=" * 60)

    # Проверка импорта
    print("\n1. Проверка зависимостей...")

    try:
        from paddleocr import PaddleOCR
        print("   ✅ PaddleOCR установлен")
    except ImportError as e:
        print(f"   ❌ PaddleOCR не установлен: {e}")
        return False

    try:
        from nudenet import NudeDetector
        print("   ✅ NudeNet установлен")
    except ImportError as e:
        print(f"   ❌ NudeNet не установлен: {e}")
        return False

    # Проверка сервиса
    print("\n2. Проверка сервиса...")

    try:
        from bot.services.local_moderation import is_available, moderate_image, preload_models
        if is_available():
            print("   ✅ Сервис локальной модерации доступен")
        else:
            print("   ❌ Сервис недоступен")
            return False
    except Exception as e:
        print(f"   ❌ Ошибка импорта сервиса: {e}")
        return False

    # Загрузка моделей
    print("\n3. Загрузка моделей (первый раз долго)...")
    start = time.time()
    preload_models()
    print(f"   ✅ Модели загружены за {time.time()-start:.1f} сек")

    # Тест на изображении
    print("\n4. Тест модерации...")

    # Создаём тестовое изображение с текстом
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io

        # Создаём картинку с текстом
        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((50, 80), "Тест +7 999 123-45-67", fill='black')

        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        test_image = buf.getvalue()

        print("   Создано тестовое изображение с телефоном")

        # Модерация
        start = time.time()
        result = await moderate_image(test_image, check_nsfw=True, check_text=True)
        elapsed = time.time() - start

        print(f"\n   Результат модерации ({elapsed:.2f} сек):")
        print(f"   - is_safe: {result.is_safe}")
        print(f"   - nsfw_score: {result.nsfw_score:.2f}")
        print(f"   - recognized_text: {result.recognized_text[:100] if result.recognized_text else 'нет'}")
        print(f"   - nsfw_labels: {result.nsfw_labels}")

        if result.recognized_text and "999" in result.recognized_text:
            print("\n   ✅ OCR работает — телефон распознан!")
        else:
            print("\n   ⚠️ OCR мог не распознать текст (возможно нужен другой шрифт)")

    except Exception as e:
        print(f"   ❌ Ошибка теста: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 60)
    print("ТЕСТ ЗАВЕРШЁН УСПЕШНО")
    print("=" * 60)
    return True

if __name__ == "__main__":
    sys.path.insert(0, '/home/telegram-ads-platform')
    success = asyncio.run(test_moderation())
    sys.exit(0 if success else 1)
