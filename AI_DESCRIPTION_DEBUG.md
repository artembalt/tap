# Проблема: AI-улучшение описаний — 403 Forbidden

## Дата: 2026-01-19

## Суть проблемы
Добавили функцию "Улучшить описание с ИИ" в создание объявлений. Claude API возвращает **403 Forbidden** внутри бота, но **работает при тестах напрямую**.

## Что странно
- Тот же API ключ работает при запуске через `python -c "..."`
- Тот же API ключ работает через curl
- Внутри бота (aiogram) — всегда 403 "Request not allowed"
- Пробовали 2 разных API ключа — оба дают 403 в боте
- Пробовали: httpx напрямую, официальный anthropic SDK, subprocess — всё 403

## Что сделано

### Новые файлы:
- `bot/services/ai_description.py` — сервис улучшения описаний
- Добавлены настройки в `bot/config/settings.py`:
  - `AI_DESCRIPTION_ENABLED`
  - `AI_DESCRIPTION_DAILY_LIMIT`
  - `AI_DESCRIPTION_API_KEY` (отдельный ключ)

### Изменения в ad_creation.py:
- Новое состояние `AdCreation.description_ai_pending`
- После ввода описания показываются кнопки: [✅ Далее] [✨ Улучшить с ИИ]
- Callbacks: `desc_confirm_next`, `ai_improve_description`, `ai_desc_use`

### Изменения в keyboards/inline.py:
- `get_description_confirm_keyboard()`
- `get_ai_description_result_keyboard()`

### Исправления в content_filter.py:
- Убраны короткие корни `'еб'`, `'ёб'` (ложные срабатывания на "мебель")
- Убран `'анал'` (ложные срабатывания на "канал")

## Версии попыток решения 403:
1. Raw httpx — 403
2. Добавили User-Agent — 403
3. Официальный anthropic SDK — 403
4. anthropic SDK с явным httpx.AsyncClient — 403
5. Отдельный API ключ (AI_DESCRIPTION_API_KEY) — 403
6. Subprocess изоляция — 403

## Ключи в .env:
```
CLAUDE_API_KEY=sk-ant-api03-nZ... (108 символов) — для модерации, тоже 403
AI_DESCRIPTION_API_KEY=sk-ant-api03-jeoL... (108 символов) — для AI описаний
```

## Гипотезы для проверки:
1. Может aiogram/aiohttp устанавливает глобальный HTTP proxy?
2. Может проблема с event loop?
3. Может Anthropic блокирует запросы по какому-то паттерну (IP rate limit)?
4. Может нужно проверить network namespace/firewall?

## Логи ошибки:
```
HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 403 Forbidden"
PermissionDeniedError: Error code: 403 - {'error': {'type': 'forbidden', 'message': 'Request not allowed'}}
```

## Команды для диагностики:
```bash
# Тест ключа напрямую (работает):
/home/telegram-ads-platform/tramp/bin/python -c "
import anthropic
client = anthropic.Anthropic(api_key='sk-ant-api03-...')
msg = client.messages.create(model='claude-3-haiku-20240307', max_tokens=10, messages=[{'role': 'user', 'content': 'Hi'}])
print(msg.content[0].text)
"

# Логи бота:
tail -50 /home/telegram-ads-platform/logs/bot.log | grep -E "AI_DESC|403"
```

## TODO при продолжении:
1. Проверить сетевые настройки процесса бота
2. Попробовать запустить бота вручную (не через supervisor) и проверить
3. Проверить iptables/firewall rules
4. Возможно попробовать другую модель (claude-3-5-sonnet вместо haiku)
