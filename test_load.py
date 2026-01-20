#!/usr/bin/env python3
"""Тест производительности локальной модерации"""
import asyncio
import time
import sys
sys.path.insert(0, '/home/telegram-ads-platform')

from bot.services.local_moderation import moderate_image, is_available

# Загружаем реальное тестовое изображение
with open('/tmp/test_image.jpg', 'rb') as f:
    TEST_IMAGE = f.read()
print(f"Размер тестового изображения: {len(TEST_IMAGE)} байт")

async def test_single():
    """Тест одного фото"""
    start = time.time()
    result = await moderate_image(TEST_IMAGE, check_nsfw=True, check_text=True)
    elapsed = time.time() - start
    return elapsed, result

async def test_concurrent(n):
    """Тест N одновременных запросов"""
    print(f"\n=== Тест: {n} одновременных запросов ===")
    start = time.time()
    tasks = [test_single() for _ in range(n)]
    results = await asyncio.gather(*tasks)
    total = time.time() - start
    times = [r[0] for r in results]
    avg = sum(times) / len(times)
    print(f"Общее время: {total:.1f} сек")
    print(f"Среднее на фото: {avg:.1f} сек")
    print(f"Мин/Макс: {min(times):.1f} / {max(times):.1f} сек")
    print(f"Пропускная способность: {n/total:.2f} фото/сек")
    return total

async def main():
    print("Проверка доступности:", "OK" if is_available() else "НЕТ")
    
    # Прогрев моделей
    print("\nПрогрев моделей (первый запуск загружает ~500MB в память)...")
    warmup_start = time.time()
    elapsed, result = await test_single()
    print(f"Прогрев завершён за {time.time() - warmup_start:.1f} сек")
    print(f"Результат: is_safe={result.is_safe}, text='{result.recognized_text[:50] if result.recognized_text else ''}'")
    
    # Тесты
    await test_concurrent(1)
    await test_concurrent(5)
    await test_concurrent(10)
    
    print("\n=== Вывод ===")
    print("При 100 одновременных пользователях с 2 CPU ядрами:")
    print("- ThreadPool=2 воркера = очередь из 100 задач")
    print("- Если 1 фото = 5 сек, то 100 фото ≈ 250 сек (4+ мин)")

if __name__ == "__main__":
    asyncio.run(main())
