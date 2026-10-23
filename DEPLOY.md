# 🚀 Руководство по развертыванию LeadHunter B2B на сервере (VPS/VDS)

Данное руководство описывает пошаговый процесс деплоя Telegram-бота и Mini App **LeadHunter** на облачный сервер (Ubuntu 22.04 / 24.04 или Debian 11/12).

---

## 📋 1. Требования к серверу (VPS)

- **ОС:** Ubuntu 22.04 LTS или Ubuntu 24.04 LTS (рекомендуется) / Debian 12
- **Процессор:** 1 vCPU
- **Оперативная память (RAM):** 1 ГБ (минимум 512 МБ со swap)
- **Диск:** 10–15 ГБ SSD/NVMe
- **Хостинг-провайдеры:** Timeweb Cloud, Aeza, Selectel, Beget, Hetzner, VDSina.

---

## ⚡️ 2. Быстрый запуск в 1 команду (Systemd)

### Шаг 1: Подключитесь к серверу по SSH
```bash
ssh root@YOUR_SERVER_IP
```

### Шаг 2: Загрузите проект на сервер
Если проект выгружен в GitHub/GitLab:
```bash
git clone https://github.com/YOUR_USERNAME/TGBOT.git /opt/leadhunter
cd /opt/leadhunter
```
*(Или скопируйте файлы через SFTP/FileZilla в папку `/opt/leadhunter`)*.

### Шаг 3: Настройте переменные окружения (.env)
Создайте `.env` из примера:
```bash
cp .env.example .env
nano .env
```
Укажите ваши актуальные данные:
- `BOT_TOKEN` — токен бота от @BotFather.
- `ADMIN_ID` — ваш Telegram ID (узнать в @userinfobot).
- `API_ID` и `API_HASH` — с сайта [my.telegram.org](https://my.telegram.org) (для Telethon).
- `MINI_APP_URL` — адрес вашего домена (например, `https://app.yourdomain.com`).  
  *(Если домена пока нет, оставьте пустым — бот автоматически запустит бесплатный защищенный HTTPS-туннель).*

Сохраните файл (`Ctrl+O`, затем `Enter`, для выхода `Ctrl+X`).

### Шаг 4: Запустите автоматический установщик
```bash
bash deploy.sh
```
Скрипт автоматически:
1. Установит необходимые пакеты Linux (Python 3, Pip, Venv, OpenSSH, компиляторы).
2. Развернет виртуальное окружение `venv` и установит зависимости.
3. Проведет автоматическое 51-пунктное тестирование всех систем (`deploy_check.py`).
4. Настроит и запустит фоновую службу **systemd** с автозапуском при перезагрузке сервера.

---

## 🔑 3. Авторизация Telethon (для парсинга чатов)

Для того чтобы Telethon мог перехватывать заявки из Telegram-чатов и каналов, необходимо один раз войти в рабочий аккаунт:

```bash
cd /opt/leadhunter
./venv/bin/python auth_session.py
```
- Введите номер телефона привязанного Telegram-аккаунта.
- Введите код подтверждения из Telegram (и облачный пароль 2FA, если включен).
- После сообщения `[УСПЕХ] Сессия сохранена` служба автоматически продолжит работу в фоне.

---

## 🌐 4. Подключение своего домена и SSL (Nginx + Certbot)

Telegram Mini App **обязательно требует действительный HTTPS-сертификат**.

### Шаг 1: Направьте домен на IP сервера
В панели управления вашим доменом (Reg.ru, Beget, Cloudflare и др.) добавьте **A-запись**:
- Имя: `app` (или `@` для основного домена)
- Значение: `IP_ВАШЕГО_СЕРВЕРА`

### Шаг 2: Установите Nginx и Certbot
```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

### Шаг 3: Настройте конфигурацию Nginx
Скопируйте готовый шаблон из проекта:
```bash
sudo cp nginx-leadhunter.conf /etc/nginx/sites-available/leadhunter.conf
sudo nano /etc/nginx/sites-available/leadhunter.conf
```
Замените `your-domain.com` на ваш реальный домен (например, `app.leadhunter.ru`), затем сохраните файл.

Активируйте сайт и проверьте конфигурацию:
```bash
sudo ln -s /etc/nginx/sites-available/leadhunter.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Шаг 4: Выпустите бесплатный SSL-сертификат Let's Encrypt
```bash
sudo certbot --nginx -d app.leadhunter.ru
```
*(Следуйте подсказкам на экране: укажите email и выберите автоматический редирект на HTTPS).*

### Шаг 5: Пропишите домен в .env
Откройте `.env`:
```bash
nano .env
```
Установите:
```env
MINI_APP_URL=https://app.leadhunter.ru
```
И перезапустите службу:
```bash
sudo systemctl restart leadhunter
```
Бот мгновенно обновит кнопку в Telegram на ваш постоянный защищенный домен!

---

## 🐳 5. Альтернативный запуск через Docker Compose

Если вы предпочитаете использовать Docker:

```bash
# 1. Установка Docker и Docker Compose (если не установлены)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 2. Создание файлов базы и сессий
touch leads.db chats_list.txt lead_parser_session.session

# 3. Сборка и запуск контейнера в фоне
docker compose up -d --build

# 4. Просмотр логов
docker compose logs -f
```

---

## 🛠 6. Управление и полезные команды

| Задача | Команда |
|---|---|
| **Проверить статус работы** | `sudo systemctl status leadhunter` |
| **Смотреть живые логи** | `sudo journalctl -u leadhunter -f` |
| **Перезапустить бота** | `sudo systemctl restart leadhunter` |
| **Остановить сервис** | `sudo systemctl stop leadhunter` |
| **Запустить самопроверку** | `./venv/bin/python deploy_check.py` |
| **Обновить код из Git** | `git pull && sudo systemctl restart leadhunter` |

---

## 🔒 7. Безопасность
- База данных SQLite (`leads.db`) хранится локально на сервере и не требует открытия портов наружу.
- Файлы сессий (`*.session`) защищены и не попадают в систему контроля версий благодаря `.gitignore`.
- Веб-сервер Mini App отдаёт данные с автоматическим сжатием Gzip и строгими заголовками `Content-Security-Policy: frame-ancestors` для корректной работы внутри Telegram Web и Mobile.
