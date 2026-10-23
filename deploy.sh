#!/usr/bin/env bash
# ==============================================================================
# deploy.sh — Скрипт автоматического 1-клик деплоя LeadHunter на Linux VPS
# Поддерживает: Ubuntu 20.04+, Debian 11+, AlmaLinux 9, Rocky Linux
# ==============================================================================
set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}=============================================================="
echo -e "   ⚡️ LEADHUNTER B2B — АВТОМАТИЧЕСКИЙ ДЕПЛОЙ НА СЕРВЕР ⚡️"
echo -e "==============================================================${NC}"

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$CURRENT_DIR"

# 1. Проверка прав root / sudo
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
else
    SUDO=""
fi

# 2. Установка системных зависимостей (Python 3.10+, pip, venv, curl, ssh)
echo -e "\n${CYAN}[1/6] Проверка системных пакетов...${NC}"
if command -v apt-get &> /dev/null; then
    $SUDO apt-get update -y
    $SUDO apt-get install -y python3 python3-venv python3-pip python3-dev build-essential openssh-client curl git tzdata
elif command -v dnf &> /dev/null; then
    $SUDO dnf install -y python3 python3-pip python3-devel gcc openssh-clients curl git tzdata
fi

# 3. Подготовка структуры данных и предотвращение ошибок монтирования
echo -e "\n${CYAN}[2/6] Подготовка файлов базы данных и сессий...${NC}"
touch "$CURRENT_DIR/leads.db"
touch "$CURRENT_DIR/chats_list.txt"
touch "$CURRENT_DIR/lead_parser_session.session"

# 4. Проверка и настройка конфигурации .env
echo -e "\n${CYAN}[3/6] Проверка конфигурации (.env)...${NC}"
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}[!] Файл .env создан из .env.example.${NC}"
        echo -e "${YELLOW}[!] ВНИМАНИЕ: Откройте .env (nano .env) и укажите ваши BOT_TOKEN, API_ID, API_HASH!${NC}"
    else
        echo -e "${RED}[ОШИБКА] Не найден файл .env или .env.example!${NC}"
        exit 1
    fi
fi

# 5. Создание виртуального окружения и установка библиотек Python
echo -e "\n${CYAN}[4/6] Установка Python-зависимостей в venv...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 6. Запуск тестов готовности системы
echo -e "\n${CYAN}[5/6] Запуск комплексного теста готовности...${NC}"
./venv/bin/python deploy_check.py

# 7. Настройка и запуск системного сервиса systemd
echo -e "\n${CYAN}[6/6] Настройка службы systemd (автозапуск и перезапуск)...${NC}"
SERVICE_FILE="/etc/systemd/system/leadhunter.service"

$SUDO bash -c "cat << 'EOF' > $SERVICE_FILE
[Unit]
Description=LeadHunter B2B — Telegram Bot & Mini App
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$CURRENT_DIR
ExecStart=$CURRENT_DIR/venv/bin/python main.py
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=15
LimitNOFILE=65535
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
EOF"

$SUDO systemctl daemon-reload
$SUDO systemctl enable leadhunter
$SUDO systemctl restart leadhunter

echo -e "\n${GREEN}=============================================================="
echo -e "   [УСПЕХ] LeadHunter успешно развернут и запущен в фоне!   "
echo -e "==============================================================${NC}"
echo -e "Полезные команды для управления на сервере:"
echo -e "  • Статус сервиса:       ${CYAN}$SUDO systemctl status leadhunter${NC}"
echo -e "  • Логи в реальном времени: ${CYAN}$SUDO journalctl -u leadhunter -f${NC}"
echo -e "  • Перезапуск сервиса:    ${CYAN}$SUDO systemctl restart leadhunter${NC}"
echo -e "  • Остановка:             ${CYAN}$SUDO systemctl stop leadhunter${NC}"
echo -e "\nЕсли у вас есть домен, настройте Nginx по файлу: ${CYAN}nginx-leadhunter.conf${NC}"
