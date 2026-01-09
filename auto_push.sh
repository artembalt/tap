#!/bin/bash
cd /home/telegram-ads-platform

# Проверяем есть ли изменения
if [[ -n $(git status --porcelain) ]]; then
    git add -A
    git commit -m "Auto-sync $(date '+%Y-%m-%d %H:%M')"
    git push origin main
    echo "$(date): Changes pushed" >> /home/telegram-ads-platform/logs/git_sync.log
fi
