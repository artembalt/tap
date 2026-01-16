# Инструкции для Claude Code

Этот файл содержит инструкции и контекст для работы с проектом.

## Проект

**Telegram Ads Platform** — бот для размещения объявлений (@proday_main_bot)

### Структура
```
bot/
├── handlers/        # Обработчики команд и сообщений
├── database/        # Модели и подключение к БД
├── utils/           # Утилиты (фильтры, модерация)
├── middlewares/     # Middleware (antiflood и др.)
└── config.py        # Конфигурация
logs/                # Логи приложения
alembic/             # Миграции БД
```

### Ключевые файлы
- `bot/main.py` — точка входа
- `bot/utils/content_filter.py` — rule-based фильтрация контента
- `bot/utils/llm_moderation.py` — LLM-модерация через Claude API
- `bot/handlers/ad_creation.py` — создание объявлений

### Управление
```bash
supervisorctl status telegram_bot    # Статус
supervisorctl restart telegram_bot   # Перезапуск
tail -f logs/bot.log                 # Логи
```

---

## Обязательные действия

### После каждого изменения кода:

1. **Обновить CHANGELOG.md**
   - Добавить запись о сделанных изменениях
   - Формат: дата → категория (Добавлено/Изменено/Исправлено) → описание
   - Указать затронутые файлы

2. **Перезапустить бота** (если изменения в коде)
   ```bash
   supervisorctl restart telegram_bot
   ```

3. **Проверить логи** на ошибки после перезапуска
   ```bash
   tail -20 logs/bot.log
   ```

### При диагностике проблем:

1. Проверить статус: `supervisorctl status`
2. Проверить логи: `tail -100 logs/bot.err.log`
3. Проверить ресурсы: `df -h`, `free -h`
4. Проверить Redis: `redis-cli ping`

---

## Стиль кода

- Python 3.11+
- Асинхронный код (aiogram 3.x)
- Логирование через `logging` модуль
- Комментарии на русском языке
- Type hints где возможно

---

## Частые задачи

### Добавить новый хендлер
1. Создать файл в `bot/handlers/`
2. Зарегистрировать роутер в `bot/main.py`
3. Обновить CHANGELOG.md

### Изменить модель БД
1. Изменить `bot/database/models.py`
2. Создать миграцию: `alembic revision --autogenerate -m "описание"`
3. Применить: `alembic upgrade head`
4. Обновить CHANGELOG.md

### Добавить конфигурацию
1. Добавить в `.env`
2. Добавить в `bot/config.py` (класс Settings)
3. Обновить CHANGELOG.md
