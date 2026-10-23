FROM python:3.11-slim

# Системные пакеты, компиляторы и утилиты
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    curl \
    gcc \
    libffi-dev \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Часовой пояс по умолчанию (Москва)
ENV TZ=Europe/Moscow
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Установка зависимостей Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Гарантируем наличие файлов данных перед монтированием томов
RUN touch leads.db chats_list.txt

# Порт для Telegram Mini App
EXPOSE 8080

# Переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    MINI_APP_PORT=8080 \
    MINI_APP_HOST=0.0.0.0

# Проверка здоровья контейнера
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/logo.png || exit 1

# Запуск единого демона (Aiogram Bot + Telethon Parser + Aiohttp Mini App)
CMD ["python", "main.py"]
