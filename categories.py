"""
categories.py — Каталог готовых фильтров и направлений по сферам (IT, Дизайн, Маркетинг, WB/Ozon, Видео, Тексты и др.).
Создан по образцу ведущих сервисов поиска заказов (Shikari.do, @find_lead_bot, @golubin_bot).
Каждое направление содержит профессионально подобранный словарь ключевых слов и фраз заказчиков.
Поддерживает динамическое добавление и редактирование сфер, категорий и ключевых слов администратором.
"""

import os
import re
import json
import copy
from typing import Optional

CLUSTERS = [
    {
        "id": "it",
        "name": "IT, сайты и разработка",
        "emoji": "💻",
        "categories": [
            {
                "id": "it_web",
                "name": "🌐 Веб-сайты и лендинги",
                "short_name": "Сайты и лендинги",
                "keywords": [
                    "сделать сайт", "создать сайт", "разработка сайта", "разработать сайт",
                    "лендинг", "landing", "сайт под ключ", "доработка сайта", "редизайн сайта",
                    "tilda", "тильда", "тильде", "вебфлоу", "webflow", "верстка", "сверстать",
                    "сайта на tilda", "верстка сайта", "html css", "сайт визитка", "интернет магазин",
                ],
            },
            {
                "id": "it_bots",
                "name": "🤖 Telegram-боты и скрипты",
                "short_name": "Telegram-боты",
                "keywords": [
                    "телеграм бот", "телеграм бота", "телеграм боту", "тг бот", "тг бота",
                    "тг боту", "телеграм-бот", "телеграм-бота", "тг-бот", "тг-бота",
                    "разработка бота", "написать бота", "сделать бота", "создать бота", "создание бота", "создания бота",
                    "разработчик ботов", "разработчик бота", "чат бот", "чат-бот", "чатбота", "скрипт", "написать скрипт",
                    "парсер", "написать парсер", "автоматизация", "telegram bot", "aiogram", "telethon", "бота на python",
                ],
            },
            {
                "id": "it_backend",
                "name": "⚙️ Python, Backend и API",
                "short_name": "Python & Backend",
                "keywords": [
                    "python", "питон", "бэкенд", "backend", "fastapi", "django", "flask",
                    "написать бэкенд", "разработчик python", "api", "интеграция по api",
                    "база данных", "postgresql", "mysql", "sqlite", "node.js", "nodejs",
                ],
            },
            {
                "id": "it_frontend",
                "name": "🎨 Frontend-разработка",
                "short_name": "Frontend",
                "keywords": [
                    "фронтенд", "frontend", "react", "vue", "vue.js", "react.js",
                    "javascript", "typescript", "верстка макета", "next.js", "nextjs",
                    "фронтендер", "верстальщик",
                ],
            },
            {
                "id": "it_mobile",
                "name": "📱 Мобильные приложения",
                "short_name": "Мобильные прил.",
                "keywords": [
                    "мобильное приложение", "мобильного приложения", "разработка приложения",
                    "создать приложение", "приложение на ios", "приложение на android",
                    "flutter", "react native", "swift", "kotlin", "приложение под ключ",
                ],
            },
            {
                "id": "it_1c_crm",
                "name": "🏢 1C, CRM и интеграции",
                "short_name": "1C & CRM",
                "keywords": [
                    "1с", "1c", "программист 1с", "настройка 1с", "битрикс", "bitrix",
                    "bitrix24", "битрикс24", "amocrm", "амосрм", "амо срм", "настройка crm",
                    "внедрение crm", "интеграция crm",
                ],
            },
            {
                "id": "it_crypto",
                "name": "🪙 Web3, Крипта и блокчейн",
                "short_name": "Web3 & Крипта",
                "keywords": [
                    "web3", "смарт контракт", "smart contract", "solidity", "крипто бот",
                    "ton connect", "блокчейн", "solana", "dapp", "ton app", "mini app",
                ],
            },
            {
                "id": "it_gamedev",
                "name": "🎮 Разработка игр (Gamedev)",
                "short_name": "Геймдев",
                "keywords": [
                    "геймдев", "gamedev", "unity", "юнити", "unreal engine", "анриал",
                    "разработка игры", "сделать игру", "godot", "геймдизайнер", "игровой движок",
                ],
            },
            {
                "id": "it_nocode",
                "name": "🧩 No-Code и автоматизация",
                "short_name": "No-Code",
                "keywords": [
                    "nocode", "no-code", "нокод", "bubble", "баббл", "make.com", "integromat",
                    "n8n", "albato", "зерокодинг", "zerocode",
                ],
            },
        ],
    },
    {
        "id": "design",
        "name": "Дизайн и графика",
        "emoji": "🎨",
        "categories": [
            {
                "id": "design_wb",
                "name": "🛍 Карточки маркетплейсов (WB/Ozon)",
                "short_name": "Карточки WB/Ozon",
                "keywords": [
                    "карточки товара", "карточек товара", "дизайн карточек", "инфографика",
                    "инфографику", "карточки для вайлдберриз", "карточки для wildberries",
                    "карточки озон", "карточки ozon", "сделать инфографику", "оформление карточек",
                ],
            },
            {
                "id": "design_uiux",
                "name": "💻 UI/UX и Веб-дизайн (Figma)",
                "short_name": "UI/UX & Figma",
                "keywords": [
                    "дизайн сайта", "дизайнер сайтов", "веб дизайн", "веб-дизайн", "ui/ux",
                    "ux/ui", "дизайн лендинга", "макет в figma", "фигма", "figma",
                    "дизайн приложения", "редизайн сайта", "ux дизайн",
                ],
            },
            {
                "id": "design_logo",
                "name": "✨ Логотипы и брендинг",
                "short_name": "Логотипы и стиль",
                "keywords": [
                    "логотип", "сделать логотип", "разработка логотипа", "лого", "фирменный стиль",
                    "айдентика", "брендбук", "brandbook", "логотипа и фирменного",
                ],
            },
            {
                "id": "design_banners",
                "name": "🖼 Баннеры и рекламные креативы",
                "short_name": "Баннеры & Креативы",
                "keywords": [
                    "баннер", "сделать баннер", "рекламный баннер", "креативы", "креатив для рекламы",
                    "оформление группы", "оформление канала", "аватарка", "шапка профиля",
                    "визуал", "презентация", "сделать презентацию", "дизайн презентации",
                ],
            },
            {
                "id": "design_3d",
                "name": "🧊 3D моделирование и рендеры",
                "short_name": "3D & Моделирование",
                "keywords": [
                    "3d", "3д", "3d модель", "3d визуализация", "3d моделлер", "блендер",
                    "blender", "рендер", "визуализатор", "3д моделирование",
                ],
            },
            {
                "id": "design_print",
                "name": "📦 Полиграфия и упаковка",
                "short_name": "Полиграфия",
                "keywords": [
                    "полиграфия", "дизайн упаковки", "этикетка", "сделать этикетку", "визитки",
                    "листовка", "буклет", "дизайн каталога", "верстка каталога", "печать каталога",
                ],
            },
        ],
    },
    {
        "id": "marketing",
        "name": "Маркетинг, трафик и реклама",
        "emoji": "📢",
        "categories": [
            {
                "id": "mkt_target",
                "name": "🎯 Таргетированная реклама",
                "short_name": "Таргет",
                "keywords": [
                    "таргетолог", "таргет", "настроить таргет", "таргетированная реклама",
                    "таргет вк", "реклама вк", "target", "лиды из вк", "таргетинг",
                ],
            },
            {
                "id": "mkt_context",
                "name": "🔍 Контекстная реклама (Яндекс)",
                "short_name": "Яндекс.Директ",
                "keywords": [
                    "директолог", "яндекс директ", "яндекс.директ", "контекстная реклама",
                    "настройка директа", "настроить директ", "реклама в яндексе", "рся",
                ],
            },
            {
                "id": "mkt_smm",
                "name": "📱 SMM и ведение соцсетей",
                "short_name": "SMM & Ведение",
                "keywords": [
                    "смм", "smm", "сммщик", "smm-специалист", "ведение соцсетей",
                    "ведение аккаунта", "контент менеджер", "контент-план", "сторисмейкер",
                    "рилсмейкер", "reelsмейкер", "ведение группы",
                ],
            },
            {
                "id": "mkt_tg",
                "name": "✈️ Telegram-маркетинг и реклама",
                "short_name": "Telegram-реклама",
                "keywords": [
                    "закупка рекламы", "закупщик рекламы", "посевы", "посевы в тг",
                    "реклама в каналах", "telegram ads", "трафик в канал", "продвижение тг",
                    "продвижение канала", "ведение тг канала",
                ],
            },
            {
                "id": "mkt_seo",
                "name": "📈 SEO продвижение сайтов",
                "short_name": "SEO сайтов",
                "keywords": [
                    "сео", "seo", "seo специалист", "продвижение сайта", "сео оптимизация",
                    "семантическое ядро", "вывести сайт в топ", "аудит сайта",
                ],
            },
            {
                "id": "mkt_leadgen",
                "name": "🧲 Лидогенерация и автоворонки",
                "short_name": "Лидогенерация",
                "keywords": [
                    "лидогенерация", "лидген", "лиды", "автоворонка", "воронка продаж",
                    "настроить воронку", "привлечение клиентов", "трафик", "трафиколог",
                ],
            },
        ],
    },
    {
        "id": "marketplaces",
        "name": "Маркетплейсы (WB / Ozon)",
        "emoji": "🛍",
        "categories": [
            {
                "id": "mp_manager",
                "name": "📋 Менеджер маркетплейсов",
                "short_name": "Менеджер WB/Ozon",
                "keywords": [
                    "менеджер маркетплейсов", "менеджер вайлдберриз", "менеджер wildberries",
                    "менеджер ozon", "менеджер озон", "ведение личного кабинета", "селлер",
                    "помощник на маркетплейс", "создание карточек",
                ],
            },
            {
                "id": "mp_seo",
                "name": "🔍 SEO карточек товара",
                "short_name": "SEO карточек",
                "keywords": [
                    "seo карточки", "сео карточки", "сео для вб", "seo wildberries",
                    "ключевые слова для карточки", "описание для карточки", "seo ozon",
                ],
            },
            {
                "id": "mp_ads",
                "name": "📊 Реклама и продвижение на маркетплейсах",
                "short_name": "Реклама на WB/Ozon",
                "keywords": [
                    "реклама на вб", "реклама wildberries", "реклама ozon", "арк",
                    "автоматические кампании", "внутренняя реклама вб", "продвижение на маркетплейсах",
                ],
            },
        ],
    },
    {
        "id": "video",
        "name": "Видео, монтаж и озвучка",
        "emoji": "🎬",
        "categories": [
            {
                "id": "video_reels",
                "name": "🔥 Монтаж Reels, Shorts и TikTok",
                "short_name": "Reels / Shorts",
                "keywords": [
                    "монтаж reels", "монтаж рилс", "монтажер рилс", "монтаж shorts",
                    "монтаж шортс", "монтаж tiktok", "монтажер reels", "короткие видео",
                    "монтаж клипов", "субтитры для видео", "нарезать рилс",
                ],
            },
            {
                "id": "video_yt",
                "name": "🎥 Монтаж YouTube и длинных видео",
                "short_name": "Монтаж YouTube",
                "keywords": [
                    "видеомонтажер", "видеомонтаж", "монтаж видео", "монтажер на youtube",
                    "монтаж ютуб", "смонтировать видео", "монтаж подкаста", "видеограф",
                ],
            },
            {
                "id": "video_motion",
                "name": "✨ Моушн-дизайн и анимация",
                "short_name": "Моушн-дизайн",
                "keywords": [
                    "моушн", "motion", "моушн дизайн", "анимация", "анимировать",
                    "2d анимация", "after effects", "анимированный ролик", "заставка",
                ],
            },
            {
                "id": "audio_voice",
                "name": "🎙 Озвучка и работа со звуком",
                "short_name": "Озвучка & Звук",
                "keywords": [
                    "диктор", "озвучка", "озвучить ролик", "голос для видео", "звукорежиссер",
                    "обработка звука", "сведение аудио", "запись голоса",
                ],
            },
        ],
    },
    {
        "id": "texts",
        "name": "Тексты, копирайтинг и переводы",
        "emoji": "✍️",
        "categories": [
            {
                "id": "txt_copy",
                "name": "📝 Копирайтинг и статьи",
                "short_name": "Копирайтинг",
                "keywords": [
                    "копирайтер", "написать текст", "текст для сайта", "написать статью",
                    "копирайтинг", "продающий текст", "рерайт", "рерайтер", "статьи на сайт",
                ],
            },
            {
                "id": "txt_smm",
                "name": "📱 Посты для соцсетей и Telegram",
                "short_name": "Посты для соцсетей",
                "keywords": [
                    "посты для тг", "посты для канала", "написать пост", "автор постов",
                    "посты для группы", "контент для канала", "тексты для инстаграм",
                ],
            },
            {
                "id": "txt_scripts",
                "name": "🎬 Сценарии для рилс и видео",
                "short_name": "Сценарии",
                "keywords": [
                    "сценарист", "сценарий для reels", "сценарий рилс", "сценарий для ютуб",
                    "сценарий ролика", "написать сценарий", "сценарии для shorts",
                ],
            },
            {
                "id": "txt_trans",
                "name": "🌍 Переводчики и языки",
                "short_name": "Переводы",
                "keywords": [
                    "переводчик", "перевести текст", "перевод с английского", "перевод на английский",
                    "китайский язык", "перевод документов", "технический перевод",
                ],
            },
        ],
    },
    {
        "id": "business",
        "name": "Бизнес, ассистенты и продажи",
        "emoji": "💼",
        "categories": [
            {
                "id": "biz_assist",
                "name": "🤝 Бизнес-ассистент / Помощник",
                "short_name": "Бизнес-ассистент",
                "keywords": [
                    "ассистент", "бизнес ассистент", "личный помощник", "помощник руководителя",
                    "удаленный ассистент", "виртуальный ассистент",
                ],
            },
            {
                "id": "biz_sales",
                "name": "📞 Менеджер по продажам",
                "short_name": "Отдел продаж",
                "keywords": [
                    "менеджер по продажам", "продажник", "менеджер на переписки", "оператор",
                    "менеджер звонков", "обработка заявок", "менеджер по работе с клиентами",
                ],
            },
            {
                "id": "biz_buh",
                "name": "📊 Бухгалтерия и налоги",
                "short_name": "Бухгалтерия",
                "keywords": [
                    "бухгалтер", "бухгалтерские услуги", "сдать отчетность", "бухгалтерия для ип",
                    "налоговая отчетность", "бухучет", "восстановление учета",
                ],
            },
            {
                "id": "biz_law",
                "name": "⚖️ Юристы и договоры",
                "short_name": "Юристы",
                "keywords": [
                    "юрист", "юридические услуги", "составить договор", "проверить договор",
                    "юридическая консультация", "оферта", "договор оказания услуг",
                ],
            },
            {
                "id": "biz_hr",
                "name": "👥 HR и подбор персонала",
                "short_name": "HR & Рекрутинг",
                "keywords": [
                    "рекрутер", "подбор персонала", "найти сотрудника", "hr специалист",
                    "найм персонала", "поиск сотрудников",
                ],
            },
        ],
    },
    {
        "id": "infobiz",
        "name": "Инфобизнес и онлайн-школы",
        "emoji": "🚀",
        "categories": [
            {
                "id": "info_tech",
                "name": "🛠 Техспециалист (GetCourse и вебинары)",
                "short_name": "Техспец GetCourse",
                "keywords": [
                    "техспец", "технический специалист", "геткурс", "getcourse", "настройка getcourse",
                    "бизон", "bizon365", "вебинар", "модератор вебинара", "настройка вебинара",
                ],
            },
            {
                "id": "info_producer",
                "name": "🚀 Продюсирование и запуски",
                "short_name": "Продюсирование",
                "keywords": [
                    "продюсер", "запуск курса", "продюсирование", "запуск эксперта",
                    "прогрев", "методолог", "методология курса",
                ],
            },
            {
                "id": "info_curator",
                "name": "👩‍🏫 Кураторы курсов",
                "short_name": "Кураторы",
                "keywords": [
                    "куратор", "куратор курса", "куратор онлайн школы", "проверка домашних заданий",
                    "наставник",
                ],
            },
        ],
    },
    {
        "id": "services",
        "name": "Офлайн и бытовые услуги (Shikari style)",
        "emoji": "🛠",
        "categories": [
            {
                "id": "srv_photo",
                "name": "📸 Фотографы и видеографы",
                "short_name": "Фотографы",
                "keywords": [
                    "фотограф", "нужен фотограф", "фотосессия", "свадебный фотограф",
                    "предметный фотограф", "фотосъемка", "видеооператор",
                ],
            },
            {
                "id": "srv_repair",
                "name": "🔨 Ремонт квартир и отделка",
                "short_name": "Ремонт и стройка",
                "keywords": [
                    "ремонт квартир", "ремонт квартиры", "отделка", "мастер на час", "сантехник",
                    "электрик", "плиточник", "косметический ремонт",
                ],
            },
            {
                "id": "srv_cargo",
                "name": "🚚 Грузоперевозки и переезды",
                "short_name": "Грузоперевозки",
                "keywords": [
                    "грузоперевозки", "переезд", "грузчики", "перевезти мебель",
                    "газель", "грузовое такси",
                ],
            },
            {
                "id": "srv_realty",
                "name": "🏠 Недвижимость и риелторы",
                "short_name": "Недвижимость",
                "keywords": [
                    "снять квартиру", "аренда квартиры", "риелтор", "купить квартиру",
                    "посуточная аренда", "коммерческая недвижимость",
                ],
            },
            {
                "id": "srv_tutor",
                "name": "📚 Репетиторы и обучение",
                "short_name": "Репетиторы",
                "keywords": [
                    "репетитор", "репетитор по математике", "репетитор по английскому",
                    "подготовка к егэ", "подготовка к огэ", "учитель", "преподаватель",
                ],
            },
        ],
    },
    {
        "id": "ai",
        "name": "Нейросети, AI и ChatGPT",
        "emoji": "🤖",
        "categories": [
            {
                "id": "ai_prompts",
                "name": "🎨 Midjourney, Stable Diffusion и арты",
                "short_name": "AI-генерация артов",
                "keywords": [
                    "midjourney", "миджорни", "stable diffusion", "стейбл дифьюжн",
                    "сгенерировать картинку", "генерация изображений", "нейросеть фото",
                    "comfyui", "промпт", "промпты", "нейроарт",
                ],
            },
            {
                "id": "ai_text",
                "name": "✍️ ChatGPT, тексты и промпт-инжиниринг",
                "short_name": "ChatGPT & Тексты",
                "keywords": [
                    "chatgpt", "чатгпт", "чат гпт", "gpt-4", "написать промпт",
                    "промпт инжиниринг", "нейросети для текста", "написание текстов через нейросети",
                ],
            },
            {
                "id": "ai_dev",
                "name": "⚡ Внедрение AI, OpenAI API и LLM",
                "short_name": "AI-разработка",
                "keywords": [
                    "openai api", "внедрить ai", "внедрить нейросеть", "интеграция chatgpt",
                    "llm", "langchain", "llamaindex", "ai ассистент", "искусственный интеллект бот",
                    "обучение модели", "fine-tuning",
                ],
            },
        ],
    },
]

CUSTOM_CATEGORIES_FILE = os.path.join(os.path.dirname(__file__), "custom_categories.json")

# Базовая неизменяемая копия кластеров
BASE_CLUSTERS = copy.deepcopy(CLUSTERS)

# Быстрые индексы для O(1) поиска
ALL_CATEGORIES_DICT = {}
CLUSTER_BY_ID = {}
CATEGORY_TO_CLUSTER = {}
ALL_KEYWORDS_CACHE = []


def _load_custom_data() -> dict:
    if os.path.exists(CUSTOM_CATEGORIES_FILE):
        try:
            with open(CUSTOM_CATEGORIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"extra_clusters": [], "extra_categories": [], "extra_keywords": {}, "deleted_keywords": {}}


def _save_custom_data(data: dict) -> None:
    with open(CUSTOM_CATEGORIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def rebuild_indexes():
    """Пересобирает все категории и быстрые индексы с учетом изменений администратора."""
    global CLUSTERS, ALL_CATEGORIES_DICT, CLUSTER_BY_ID, CATEGORY_TO_CLUSTER, ALL_KEYWORDS_CACHE
    clusters_copy = copy.deepcopy(BASE_CLUSTERS)
    custom = _load_custom_data()

    # 1. Добавляем кастомные сферы (кластеры)
    for ec in custom.get("extra_clusters", []):
        if not any(c["id"] == ec["id"] for c in clusters_copy):
            clusters_copy.append({
                "id": ec["id"],
                "name": ec["name"],
                "emoji": ec.get("emoji", "🎯"),
                "categories": []
            })

    cluster_dict_temp = {c["id"]: c for c in clusters_copy}

    # 2. Добавляем кастомные категории
    for cat in custom.get("extra_categories", []):
        parent_cluster = cat.get("cluster_id")
        if parent_cluster in cluster_dict_temp:
            if not any(c["id"] == cat["id"] for c in cluster_dict_temp[parent_cluster]["categories"]):
                cluster_dict_temp[parent_cluster]["categories"].append({
                    "id": cat["id"],
                    "name": cat["name"],
                    "short_name": cat.get("short_name", cat["name"]),
                    "keywords": cat.get("keywords", [])
                })

    # 3. Модифицируем ключевые слова
    extra_kw = custom.get("extra_keywords", {})
    del_kw = custom.get("deleted_keywords", {})

    for c in clusters_copy:
        for cat in c["categories"]:
            cid = cat["id"]
            current_kws = list(cat.get("keywords", []))

            if cid in extra_kw:
                for kw in extra_kw[cid]:
                    if kw.lower() not in [k.lower() for k in current_kws]:
                        current_kws.append(kw)

            if cid in del_kw:
                to_del_lower = {d.lower() for d in del_kw[cid]}
                current_kws = [k for k in current_kws if k.lower() not in to_del_lower]

            cat["keywords"] = current_kws

    CLUSTERS = clusters_copy

    ALL_CATEGORIES_DICT.clear()
    CLUSTER_BY_ID.clear()
    CATEGORY_TO_CLUSTER.clear()

    for cluster in CLUSTERS:
        CLUSTER_BY_ID[cluster["id"]] = cluster
        for cat in cluster["categories"]:
            cat_id = cat["id"]
            ALL_CATEGORIES_DICT[cat_id] = cat
            CATEGORY_TO_CLUSTER[cat_id] = cluster["id"]

    seen = set()
    all_kws = []
    for cat in ALL_CATEGORIES_DICT.values():
        for kw in cat.get("keywords", []):
            kw_clean = kw.strip().lower()
            if kw_clean not in seen:
                seen.add(kw_clean)
                all_kws.append(kw_clean)
    ALL_KEYWORDS_CACHE = all_kws


# Инициализируем индексы
rebuild_indexes()


# --- Функции управления для администратора ---

def add_custom_cluster(cluster_id: str, name: str, emoji: str = "🎯") -> tuple[bool, str]:
    cluster_id = cluster_id.strip().lower().replace(" ", "_")
    if cluster_id in CLUSTER_BY_ID:
        return False, "Сфера с таким ID уже существует."
    custom = _load_custom_data()
    custom.setdefault("extra_clusters", []).append({
        "id": cluster_id,
        "name": name.strip(),
        "emoji": emoji.strip(),
    })
    _save_custom_data(custom)
    rebuild_indexes()
    return True, f"Сфера {emoji} <b>{name}</b> (ID: <code>{cluster_id}</code>) успешно создана!"


def add_custom_category(cluster_id: str, cat_id: str, name: str, short_name: str, keywords: list[str]) -> tuple[bool, str]:
    cluster_id = cluster_id.strip().lower()
    cat_id = cat_id.strip().lower().replace(" ", "_")
    if cluster_id not in CLUSTER_BY_ID:
        return False, f"Сфера <code>{cluster_id}</code> не найдена."
    if cat_id in ALL_CATEGORIES_DICT:
        return False, f"Категория с ID <code>{cat_id}</code> уже существует."

    clean_kws = [k.strip().lower() for k in keywords if k.strip()]
    custom = _load_custom_data()
    custom.setdefault("extra_categories", []).append({
        "cluster_id": cluster_id,
        "id": cat_id,
        "name": name.strip(),
        "short_name": short_name.strip() or name.strip(),
        "keywords": clean_kws
    })
    _save_custom_data(custom)
    rebuild_indexes()
    return True, f"Категория <b>{name}</b> ({len(clean_kws)} ключевых слов) добавлена в сферу {CLUSTER_BY_ID[cluster_id]['name']}!"


def add_keywords_to_category(cat_id: str, new_words: list[str]) -> tuple[bool, int, str]:
    cat_id = cat_id.strip().lower()
    if cat_id not in ALL_CATEGORIES_DICT:
        return False, 0, f"Категория <code>{cat_id}</code> не найдена."

    clean_words = [w.strip().lower() for w in new_words if w.strip()]
    if not clean_words:
        return False, 0, "Не указаны ключевые слова."

    custom = _load_custom_data()
    extra_kw = custom.setdefault("extra_keywords", {})
    existing = extra_kw.setdefault(cat_id, [])

    added = 0
    for w in clean_words:
        if w not in existing:
            existing.append(w)
            added += 1

    del_kw = custom.get("deleted_keywords", {}).get(cat_id, [])
    if del_kw:
        custom["deleted_keywords"][cat_id] = [d for d in del_kw if d.lower() not in clean_words]

    _save_custom_data(custom)
    rebuild_indexes()
    return True, added, f"✅ Добавлено <b>{added}</b> новых ключевых слов в «{ALL_CATEGORIES_DICT[cat_id]['name']}»!"


def remove_keyword_from_category(cat_id: str, word: str) -> tuple[bool, str]:
    cat_id = cat_id.strip().lower()
    if cat_id not in ALL_CATEGORIES_DICT:
        return False, f"Категория <code>{cat_id}</code> не найдена."

    word_clean = word.strip().lower()
    cat = ALL_CATEGORIES_DICT[cat_id]
    if word_clean not in [k.lower() for k in cat.get("keywords", [])]:
        return False, f"Слово «{word}» не найдено в этой категории."

    custom = _load_custom_data()
    if cat_id in custom.get("extra_keywords", {}):
        custom["extra_keywords"][cat_id] = [w for w in custom["extra_keywords"][cat_id] if w.lower() != word_clean]

    del_list = custom.setdefault("deleted_keywords", {}).setdefault(cat_id, [])
    if word_clean not in del_list:
        del_list.append(word_clean)

    _save_custom_data(custom)
    rebuild_indexes()
    return True, f"✅ Слово «{word}» удалено из категории «{cat['name']}»."


def get_cluster(cluster_id: str) -> Optional[dict]:
    """Возвращает информацию о сфере (кластере)."""
    return CLUSTER_BY_ID.get(cluster_id)


def get_category(category_id: str) -> Optional[dict]:
    """Возвращает данные по конкретной категории."""
    return ALL_CATEGORIES_DICT.get(category_id)


def get_keywords_for_categories(category_ids: set[str] | list[str]) -> list[str]:
    """Собирает список всех ключевых слов для набора выбранных категорий."""
    result = []
    seen = set()
    for cat_id in category_ids:
        cat = ALL_CATEGORIES_DICT.get(cat_id)
        if not cat:
            continue
        for kw in cat.get("keywords", []):
            kw_clean = kw.strip().lower()
            if kw_clean not in seen:
                seen.add(kw_clean)
                result.append(kw_clean)
    return result


def match_keyword_in_text(kw: str, text_lower: str) -> bool:
    """
    Проверяет вхождение ключевого слова с учетом границ слов и окончаний.
    Исключает ложные срабатывания (например 'бот' в 'разработка', 'арт' в 'партер').
    """
    kw_clean = kw.strip().lower()
    if not kw_clean:
        return False
    # Фразы из нескольких слов проверяются как подстрока
    if " " in kw_clean:
        return kw_clean in text_lower
    # Отдельные слова проверяются с учетом морфологических окончаний и границ слов
    pattern = r'(?:\b|\A)' + re.escape(kw_clean) + r'[а-яёa-z0-9]*(?:\b|\Z)'
    return bool(re.search(pattern, text_lower, re.IGNORECASE))


def find_matched_category_info(text_lower: str, active_cat_ids: set[str] | list[str]) -> Optional[tuple[str, str]]:
    """
    Проверяет, совпало ли сообщение с одной из активных категорий пользователя.
    Выбирает наиболее точную категорию по весу совпадения (длинные фразы имеют приоритет).
    Возвращает (название_категории, совпавшее_слово) или None.
    """
    best_cat = None
    best_kw = ""
    best_score = 0

    for cat_id in active_cat_ids:
        cat = ALL_CATEGORIES_DICT.get(cat_id)
        if not cat:
            continue
        for kw in cat.get("keywords", []):
            if match_keyword_in_text(kw, text_lower):
                # Чем длиннее ключевая фраза, тем она специфичнее
                score = len(kw) + (10 if " " in kw else 0)
                if score > best_score:
                    best_score = score
                    best_cat = cat["name"]
                    best_kw = kw

    if best_cat:
        return (best_cat, best_kw)
    return None
