# 🎯 LeadHunter — Telegram-парсер лидов и B2B заказчиков

Асинхронный сервис для поиска клиентов, заказов на фрилансе и B2B компаний без сайта с официальным Telegram-ботом и Mini App терминалом на **Python 3.11+**, **aiogram 3.x**, **Telethon** и **aiohttp**.

---

## ⚡️ Быстрый старт на сервере (VPS)

Для полного автоматического развертывания на любом Linux-сервере (Ubuntu/Debian):

```bash
git clone <URL_РЕПОЗИТОРИЯ> /opt/leadhunter
cd /opt/leadhunter
cp .env.example .env
nano .env  # Заполните BOT_TOKEN, API_ID, API_HASH
bash deploy.sh
```

Подробное руководство со скриншотами, привязкой своего домена и SSL-сертификатами Let's Encrypt:
👉 **[Инструкция по деплою (DEPLOY.md)](DEPLOY.md)**

---

## 📁 Архитектура и структура проекта

* `main.py` — единая точка входа. Одновременно запускает SQLite, Telegram-бота `aiogram 3.x`, клиент `Telethon` и веб-сервер Mini App `aiohttp`.
* `miniapp/` — ядро Telegram Mini App:
  * `server.py` — асинхронный HTTP/REST API сервер (Gzip сжатие, CORS, iframe CSP headers).
  * `rpc_handler.py` — диспетчер RPC протокола (дашборд «Сегодня», «Парсер», «База», «Сообщения»).
  * `places_search.py` — поисковый движок заведений без сайта (Google Places API + Nominatim/OSM).
  * `pitch_generator.py` — алгоритм генерации офферов и калькулятор упущенной выгоды (ROI).
  * `tunnel.py` — умный менеджер HTTPS туннеля с авто-восстановлением.
  * `static/index.html` — адаптивный мобильный интерфейс терминала (Liquid Glass, Cyber Obsidian).
* `bot.py` — логика клиентского Telegram-бота на `aiogram 3.x`:
  * Запуск Mini App через веб-кнопку и меню Telegram
  * 🎯 Готовые фильтры (35+ сфер бизнеса)
  * Управление ключевыми и минус-словами
  * Тарифы подписки PRO и монетизация
  * Личный кабинет фрилансера и статистика
* `parser.py` — фоновый перехватчик горячих заказов из Telegram-чатов на `Telethon`.
* `db.py` — асинхронная база данных SQLite (`aiosqlite`) с индексами и CRM-воронкой.
* `deploy.sh` — скрипт 1-клик деплоя и настройки службы `systemd`.
* `deploy_check.py` — автоматический тестовый стенд (51 проверка готовности перед деплоем).
* `Dockerfile` и `docker-compose.yml` — контейнеризация для Docker.
* `nginx-leadhunter.conf` и `Caddyfile` — готовые конфигурации веб-сервера с поддержкой SSL.

---

## 🛠 Полезные команды на сервере

```bash
# Статус службы
sudo systemctl status leadhunter

# Живой просмотр логов
sudo journalctl -u leadhunter -f

# Перезапуск службы
sudo systemctl restart leadhunter

# Комплексный тест всех компонентов
python deploy_check.py
```
