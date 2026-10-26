FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Europe/Moscow
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV MINI_APP_PORT=8080
ENV MINI_APP_HOST=0.0.0.0

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN touch leads.db chats_list.txt

EXPOSE 8080

CMD ["python", "main.py"]
