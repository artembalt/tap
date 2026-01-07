#!/bin/bash

echo "=== Проверка статуса бота ==="
echo ""

# Проверка процесса
if pgrep -f "python.*bot/main.py" > /dev/null; then
    echo "✅ Процесс бота: РАБОТАЕТ"
    echo "   PID: $(pgrep -f 'python.*bot/main.py')"
else
    echo "❌ Процесс бота: НЕ РАБОТАЕТ"
fi

# Проверка Supervisor
echo ""
echo "Статус Supervisor:"
supervisorctl status telegram_bot

# Проверка БД
echo ""
echo "Проверка PostgreSQL:"
sudo -u postgres psql -d telegram_ads -c "SELECT COUNT(*) as users_count FROM users;" 2>/dev/null || echo "❌ Ошибка подключения к БД"

# Проверка Redis
echo ""
echo "Проверка Redis:"
redis-cli ping > /dev/null 2>&1 && echo "✅ Redis: РАБОТАЕТ" || echo "❌ Redis: НЕ РАБОТАЕТ"

# Последние логи
echo ""
echo "=== Последние записи в логах ==="
tail -5 /home/telegram-ads-platform/logs/bot.out.log

# Ошибки
if [ -f /home/telegram-ads-platform/logs/bot.err.log ]; then
    errors=$(tail -5 /home/telegram-ads-platform/logs/bot.err.log)
    if [ ! -z "$errors" ]; then
        echo ""
        echo "=== Последние ошибки ==="
        echo "$errors"
    fi
fi

echo ""
echo "=== Использование ресурсов ==="
echo "RAM: $(free -h | grep Mem | awk '{print $3"/"$2}')"
echo "Disk: $(df -h / | tail -1 | awk '{print $3"/"$2" ("$5")"}')"
