# =====================================================
# setup.sh - Скрипт установки на Ubuntu 24.04
#!/bin/bash

set -e  # Остановка при ошибке

echo "========================================="
echo "Установка Telegram Ads Platform"
echo "========================================="

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для вывода сообщений
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Проверка прав
if [[ $EUID -ne 0 ]]; then
   log_error "Этот скрипт должен быть запущен с правами root (sudo)"
   exit 1
fi

# 1. Обновление системы
log_info "Обновление системы..."
apt update && apt upgrade -y

# 2. Установка системных пакетов
log_info "Установка системных пакетов..."
apt install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    redis-server \
    nginx \
    supervisor \
    git \
    curl \
    wget \
    build-essential \
    libpq-dev \
    python3.12-dev \
    libssl-dev \
    libffi-dev \
    ufw

# 3. Настройка PostgreSQL
log_info "Настройка PostgreSQL..."

# Генерация пароля для БД
DB_PASSWORD=$(openssl rand -base64 32)
echo "DB_PASSWORD=$DB_PASSWORD" >> /root/.env.backup

# Создание пользователя и базы данных
sudo -u postgres psql <<EOF
CREATE USER telegram_ads WITH PASSWORD '$DB_PASSWORD';
CREATE DATABASE telegram_ads OWNER telegram_ads;
GRANT ALL PRIVILEGES ON DATABASE telegram_ads TO telegram_ads;
ALTER USER telegram_ads CREATEDB;
EOF

# Настройка PostgreSQL для принятия подключений
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = 'localhost'/" /etc/postgresql/16/main/postgresql.conf
echo "host    telegram_ads    telegram_ads    127.0.0.1/32    md5" >> /etc/postgresql/16/main/pg_hba.conf

# Перезапуск PostgreSQL
systemctl restart postgresql
systemctl enable postgresql

# 4. Настройка Redis
log_info "Настройка Redis..."

# Включение персистентности
sed -i 's/# save 900 1/save 900 1/' /etc/redis/redis.conf
sed -i 's/# save 300 10/save 300 10/' /etc/redis/redis.conf
sed -i 's/# save 60 10000/save 60 10000/' /etc/redis/redis.conf

# Установка пароля для Redis (опционально)
REDIS_PASSWORD=$(openssl rand -base64 32)
echo "requirepass $REDIS_PASSWORD" >> /etc/redis/redis.conf
echo "REDIS_PASSWORD=$REDIS_PASSWORD" >> /root/.env.backup

# Перезапуск Redis
systemctl restart redis-server
systemctl enable redis-server

# 5. Создание пользователя для приложения
log_info "Создание пользователя приложения..."
useradd -m -s /bin/bash telegram_ads || log_warning "Пользователь уже существует"

# 6. Клонирование репозитория (или создание структуры)
log_info "Создание структуры проекта..."
cd /home/telegram_ads

# Создание директорий
mkdir -p telegram-ads-platform/{bot,backend,parser,web,shared,migrations,logs,uploads,scripts,tests}

# Копирование файлов (если у вас есть git репозиторий)
# git clone https://github.com/yourusername/telegram-ads-platform.git
# cd telegram-ads-platform

# 7. Создание виртуального окружения Python
log_info "Создание виртуального окружения Python..."
cd /home/telegram_ads/telegram-ads-platform
python3.12 -m venv venv
source venv/bin/activate

# 8. Установка Python зависимостей
log_info "Установка Python зависимостей..."
pip install --upgrade pip
pip install wheel setuptools
pip install -r requirements.txt

# 9. Создание .env файла
log_info "Создание файла конфигурации..."
cat > .env <<EOF
# Telegram Bot
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
BOT_USERNAME=proday_bot

# Telegram API (for parser)
API_ID=YOUR_API_ID
API_HASH=YOUR_API_HASH
PHONE_NUMBER=YOUR_PHONE

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=telegram_ads
DB_USER=telegram_ads
DB_PASSWORD=$DB_PASSWORD

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=$REDIS_PASSWORD

# Payment System
YOOMONEY_TOKEN=
YOOMONEY_WALLET=
YOOMONEY_SECRET=

# Admins (comma separated telegram IDs)
ADMIN_IDS=

# Web
BACKEND_URL=http://localhost:8000
WEB_DOMAIN=your-domain.ru

# Security
BACKEND_SECRET=$(openssl rand -base64 32)

# Debug
DEBUG=False
LOG_LEVEL=INFO
EOF

log_warning "Не забудьте заполнить BOT_TOKEN и другие параметры в файле .env!"

# 10. Инициализация базы данных
log_info "Инициализация базы данных..."
cd /home/telegram_ads/telegram-ads-platform
alembic init migrations || log_warning "Alembic уже инициализирован"

# Создание первой миграции
cat > alembic.ini <<EOF
[alembic]
script_location = migrations
prepend_sys_path = .
sqlalchemy.url = postgresql://telegram_ads:$DB_PASSWORD@localhost/telegram_ads

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
EOF

# 11. Настройка Supervisor для автозапуска
log_info "Настройка Supervisor..."

cat > /etc/supervisor/conf.d/telegram_bot.conf <<EOF
[program:telegram_bot]
command=/home/telegram_ads/telegram-ads-platform/venv/bin/python /home/telegram_ads/telegram-ads-platform/bot/main.py
directory=/home/telegram_ads/telegram-ads-platform
user=telegram_ads
autostart=true
autorestart=true
stderr_logfile=/home/telegram_ads/telegram-ads-platform/logs/bot.err.log
stdout_logfile=/home/telegram_ads/telegram-ads-platform/logs/bot.out.log
environment=PATH="/home/telegram_ads/telegram-ads-platform/venv/bin"
EOF

cat > /etc/supervisor/conf.d/backend.conf <<EOF
[program:backend]
command=/home/telegram_ads/telegram-ads-platform/venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
directory=/home/telegram_ads/telegram-ads-platform
user=telegram_ads
autostart=true
autorestart=true
stderr_logfile=/home/telegram_ads/telegram-ads-platform/logs/backend.err.log
stdout_logfile=/home/telegram_ads/telegram-ads-platform/logs/backend.out.log
environment=PATH="/home/telegram_ads/telegram-ads-platform/venv/bin"
EOF

# 12. Настройка Nginx
log_info "Настройка Nginx..."

cat > /etc/nginx/sites-available/telegram-ads <<EOF
server {
    listen 80;
    server_name _;
    
    client_max_body_size 50M;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    location /static {
        alias /home/telegram_ads/telegram-ads-platform/web/static;
    }
    
    location /uploads {
        alias /home/telegram_ads/telegram-ads-platform/uploads;
    }
}
EOF

ln -s /etc/nginx/sites-available/telegram-ads /etc/nginx/sites-enabled/ || log_warning "Ссылка уже существует"
rm /etc/nginx/sites-enabled/default || log_warning "Default site уже удален"

# Тест конфигурации Nginx
nginx -t

# 13. Настройка файрвола
log_info "Настройка файрвола..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 14. Установка прав
log_info "Установка прав доступа..."
chown -R telegram_ads:telegram_ads /home/telegram_ads/telegram-ads-platform
chmod 755 /home/telegram_ads/telegram-ads-platform
chmod 600 /home/telegram_ads/telegram-ads-platform/.env

# 15. Запуск сервисов
log_info "Запуск сервисов..."
systemctl restart nginx
supervisorctl reread
supervisorctl update

# 16. Создание скрипта для бэкапа
log_info "Создание скрипта резервного копирования..."

cat > /home/telegram_ads/telegram-ads-platform/scripts/backup.sh <<EOF
#!/bin/bash
BACKUP_DIR="/home/telegram_ads/backups"
DATE=\$(date +%Y%m%d_%H%M%S)
mkdir -p \$BACKUP_DIR

# Backup database
pg_dump -U telegram_ads telegram_ads | gzip > \$BACKUP_DIR/db_\$DATE.sql.gz

# Backup uploads
tar -czf \$BACKUP_DIR/uploads_\$DATE.tar.gz /home/telegram_ads/telegram-ads-platform/uploads

# Keep only last 7 days of backups
find \$BACKUP_DIR -type f -mtime +7 -delete

echo "Backup completed: \$DATE"
EOF

chmod +x /home/telegram_ads/telegram-ads-platform/scripts/backup.sh

# Добавление в cron
(crontab -l 2>/dev/null; echo "0 3 * * * /home/telegram_ads/telegram-ads-platform/scripts/backup.sh") | crontab -

# 17. Вывод информации об установке
log_info "========================================="
log_info "Установка завершена!"
log_info "========================================="
echo ""
echo "Важная информация сохранена в /root/.env.backup"
echo ""
echo "Дальнейшие шаги:"
echo "1. Отредактируйте файл /home/telegram_ads/telegram-ads-platform/.env"
echo "2. Добавьте BOT_TOKEN от @BotFather"
echo "3. Добавьте API_ID и API_HASH от https://my.telegram.org"
echo "4. Запустите миграции: cd /home/telegram_ads/telegram-ads-platform && alembic upgrade head"
echo "5. Перезапустите сервисы: supervisorctl restart all"
echo ""
echo "Проверка статуса:"
echo "- PostgreSQL: systemctl status postgresql"
echo "- Redis: systemctl status redis-server"
echo "- Nginx: systemctl status nginx"
echo "- Bot: supervisorctl status telegram_bot"
echo "- Backend: supervisorctl status backend"
echo ""
echo "Логи:"
echo "- Bot: tail -f /home/telegram_ads/telegram-ads-platform/logs/bot.out.log"
echo "- Backend: tail -f /home/telegram_ads/telegram-ads-platform/logs/backend.out.log"