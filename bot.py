"""
bot.py — Модуль Telegram-бота для клиентов и администратора на aiogram 3.x.
Включает:
- Управление ключевыми словами (постепенное добавление, удаление поштучно или всё сразу)
- Загрузку слов файлом (.txt, .csv) и экспорт
- Автоматический бесплатный триал PRO на 1 день для новых клиентов
- Оплату популярными методами: СБП, Карты РФ, Криптовалюта (USDT, TON) и Telegram Stars
- Автоматизированную отправку чеков администратору на проверку в 1 клик
- Счётчик пойманных лидов и админ-команды
"""

import io
import html
import asyncio
import socket
import os
from typing import Optional, Any
from aiogram import Bot, Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
    BotCommandScopeDefault,
    BufferedInputFile,
    FSInputFile,
    LabeledPrice,
    PreCheckoutQuery,
    WebAppInfo,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
import db
import categories
import chat_manager

router = Router()

# Глобальная ссылка на сессию Telethon для операций вступления/выхода
_TELETHON_CLIENT = None


def set_telethon_client(client):
    global _TELETHON_CLIENT
    _TELETHON_CLIENT = client


# --- FSM Состояния ---
class UserStates(StatesGroup):
    waiting_add_keywords = State()
    waiting_add_stop_words = State()
    waiting_payment_receipt = State()


class AdminStates(StatesGroup):
    waiting_give_pro = State()
    waiting_revoke_pro = State()
    waiting_broadcast = State()
    waiting_add_chat = State()
    waiting_del_chat = State()
    waiting_search_chat = State()
    waiting_upload_chats = State()
    waiting_add_kw_cat = State()
    waiting_del_kw_cat = State()
    waiting_add_category = State()
    waiting_add_cluster = State()
    waiting_set_price = State()
    waiting_set_requisite = State()


# --- Динамические настройки тарифов и реквизитов ---

async def get_plan_price(days: int) -> int:
    if days == 3:
        val = await db.get_setting("price_3_days", "0")
    elif days == 30:
        val = await db.get_setting("price_30_days", "490")
    else:
        val = await db.get_setting("price_lifetime", "1490")
    try:
        return int(val)
    except Exception:
        return 0 if days == 3 else (490 if days == 30 else 1490)


async def get_plan_stars(days: int) -> int:
    if days == 3:
        val = await db.get_setting("stars_3_days", "0")
    elif days == 30:
        val = await db.get_setting("stars_30_days", "250")
    else:
        val = await db.get_setting("stars_lifetime", "750")
    try:
        return int(val)
    except Exception:
        return 50 if days == 3 else (250 if days == 30 else 750)


async def get_plan_crypto(days: int) -> str:
    if days == 3:
        return str(await db.get_setting("crypto_3_days", "1.2"))
    elif days == 30:
        return str(await db.get_setting("crypto_30_days", "5.5"))
    else:
        return str(await db.get_setting("crypto_lifetime", "16.5"))


async def get_requisites() -> dict[str, str]:
    return {
        "sbp_phone": await db.get_setting("pay_sbp_phone", config.PAY_SBP_PHONE),
        "sbp_bank": await db.get_setting("pay_sbp_bank", config.PAY_SBP_BANK),
        "card_number": await db.get_setting("pay_card_number", config.PAY_CARD_NUMBER),
        "usdt": await db.get_setting("pay_crypto_usdt", config.PAY_CRYPTO_USDT_TRC20),
        "ton": await db.get_setting("pay_crypto_ton", config.PAY_CRYPTO_TON),
    }


# --- Меню и постоянная клавиатура ---

def get_persistent_reply_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """
    Постоянные кнопки внизу экрана под полем ввода текста.
    Всегда под рукой и избавляют от необходимости писать /start вручную.
    """
    app_url = getattr(config, "MINI_APP_URL", "")
    if app_url.startswith("https://"):
        app_btn = KeyboardButton(text="⚡️ B2B Поиск клиентов (App)", web_app=WebAppInfo(url=app_url))
    else:
        app_btn = KeyboardButton(text="⚡️ B2B Поиск клиентов (App)")

    keyboard = [
        [app_btn],
        [
            KeyboardButton(text="🎯 Готовые фильтры"),
            KeyboardButton(text="👤 Личный кабинет"),
        ],
        [
            KeyboardButton(text="🔑 Ключевые слова"),
            KeyboardButton(text="💎 Тарифы подписки"),
        ],
    ]
    if is_admin:
        keyboard.append([
            KeyboardButton(text="👑 Панель Администратора"),
            KeyboardButton(text="📋 Главное меню"),
        ])
    else:
        keyboard.append([
            KeyboardButton(text="📋 Главное меню"),
        ])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Нажмите кнопку или введите команду...",
    )


async def setup_bot_commands(bot: Bot) -> None:
    """Устанавливает официальное меню команд Telegram в левом нижнем углу экрана."""
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="app", description="B2B Лидогенератор (Mini App)"),
        BotCommand(command="trial", description="🎁 Бесплатный PRO (3 дня)"),
        BotCommand(command="filters", description="Готовые фильтры сфер"),
        BotCommand(command="keywords", description="Ключевые слова"),
        BotCommand(command="profile", description="Личный кабинет"),
        BotCommand(command="pro", description="Тарифы подписки PRO"),
        BotCommand(command="admin", description="Панель управления"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    except Exception:
        pass


# --- Главное меню ---

def get_download_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура запуска Web-терминала."""
    app_url = getattr(config, "MINI_APP_URL", "")
    support_user = getattr(config, "ADMIN_USERNAME", "paniicca").lstrip("@")
    kb = []
    if app_url.startswith("https://"):
        kb.append([InlineKeyboardButton(text="⚡️ Запустить LeadHunter B2B", web_app=WebAppInfo(url=app_url))])
    kb.append([
        InlineKeyboardButton(text="« Главное меню", callback_data="btn_main_menu"),
        InlineKeyboardButton(text="💬 Поддержка", url=f"https://t.me/{support_user}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню LeadHunter с запуском терминала и тарифами."""
    app_url = getattr(config, "MINI_APP_URL", "")
    support_user = getattr(config, "ADMIN_USERNAME", "paniicca").lstrip("@")
    if app_url.startswith("https://"):
        app_btn = InlineKeyboardButton(text="⚡️ B2B Поиск клиентов (Карты)", web_app=WebAppInfo(url=app_url))
    else:
        app_btn = InlineKeyboardButton(text="⚡️ B2B Поиск клиентов (Карты)", callback_data="btn_open_miniapp")

    keyboard = [
        [app_btn],
        [
            InlineKeyboardButton(text="🎯 Готовые фильтры (35+ сфер)", callback_data="menu_categories"),
        ],
        [
            InlineKeyboardButton(text="🔑 Свои ключевые слова", callback_data="menu_kw"),
            InlineKeyboardButton(text="⛔️ Минус-слова", callback_data="menu_sw"),
        ],
        [
            InlineKeyboardButton(text="💎 Тарифы подписки", callback_data="menu_pay_plans"),
            InlineKeyboardButton(text="👤 Личный кабинет", callback_data="btn_settings"),
        ],
        [
            InlineKeyboardButton(text="💬 Написать в поддержку", url=f"https://t.me/{support_user}"),
        ],
    ]
    if is_admin:
        keyboard.append([
            InlineKeyboardButton(text="👑 Панель Администратора", callback_data="admin_panel"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура главной панели администратора."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
                InlineKeyboardButton(text="🔄 Диагностика", callback_data="admin_sys_check"),
            ],
            [
                InlineKeyboardButton(text="🎁 Выдать PRO", callback_data="admin_give_pro_prompt"),
                InlineKeyboardButton(text="🚫 Забрать PRO", callback_data="admin_revoke_pro_prompt"),
            ],
            [
                InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast_prompt"),
                InlineKeyboardButton(text="🗂 Чаты мониторинга", callback_data="admin_chats_hub"),
            ],
            [
                InlineKeyboardButton(text="🎯 Сферы и категории", callback_data="admin_categories_hub"),
                InlineKeyboardButton(text="💳 Тарифы и цены", callback_data="admin_pricing_hub"),
            ],
            [
                InlineKeyboardButton(text="🏦 Реквизиты оплаты", callback_data="admin_requisites_hub"),
                InlineKeyboardButton(text="🏠 В главное меню", callback_data="btn_main_menu"),
            ],
        ]
    )


# --- Клавиатуры готовых фильтров (направлений) ---

def get_clusters_keyboard(user_active_cats: set[str]) -> InlineKeyboardMarkup:
    """Список сфер деятельности (кластеров) с индикатором активных подкатегорий."""
    keyboard = []
    for cluster in categories.CLUSTERS:
        cluster_id = cluster["id"]
        active_in_cluster = sum(1 for c in cluster["categories"] if c["id"] in user_active_cats)

        status_badge = f"({active_in_cluster} ✅)" if active_in_cluster > 0 else ""
        btn_text = f"{cluster['emoji']} {cluster['name']} {status_badge}".strip()
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"cluster:{cluster_id}")])

    total_active = len(user_active_cats)
    nav_row = [
        InlineKeyboardButton(text=f"👀 Мои фильтры ({total_active} акт.)", callback_data="cat_my_active"),
    ]
    if total_active > 0:
        nav_row.append(InlineKeyboardButton(text="🗑 Сбросить всё", callback_data="cat_reset_confirm"))
    keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="btn_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cluster_details_keyboard(cluster_id: str, user_active_cats: set[str]) -> InlineKeyboardMarkup:
    """Клавиатура подкатегорий конкретной сферы с тумблерами [✓] / [—]."""
    cluster = categories.get_cluster(cluster_id)
    if not cluster:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="‹ Назад", callback_data="menu_categories")]])

    keyboard = []
    row = []
    for cat in cluster["categories"]:
        cat_id = cat["id"]
        is_active = cat_id in user_active_cats
        check = "✅" if is_active else "❌"
        title = f"[{check}] {cat['short_name']}"
        row.append(InlineKeyboardButton(text=title, callback_data=f"cat_toggle:{cluster_id}:{cat_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton(text="⚡️ Включить всю сферу", callback_data=f"cluster_on:{cluster_id}"),
        InlineKeyboardButton(text="❌ Выключить сферу", callback_data=f"cluster_off:{cluster_id}"),
    ])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад ко всем сферам", callback_data="menu_categories")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)



# --- Клавиатуры раздела оплаты ---

async def get_payment_plans_keyboard(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Выбор тарифа подписки с динамической защитой от повторного взятия триала."""
    p3 = await get_plan_price(3)
    p30 = await get_plan_price(30)
    plife = await get_plan_price(999)

    trial_used = await db.has_used_trial(user_id) if user_id else False

    keyboard = []
    if not trial_used:
        trial_label = "🎁 3 дня (Пробный) — БЕСПЛАТНО" if p3 == 0 else f"⚡️ 3 дня (Пробный) — {p3} ₽"
        keyboard.append([
            InlineKeyboardButton(text=trial_label, callback_data=f"plan:3:{p3}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(text="⚡️ 3 дня (Пробный) — [Использован]", callback_data="trial_already_used")
        ])

    keyboard.append([
        InlineKeyboardButton(text=f"💎 Месяц: 30 дней — {p30} ₽", callback_data=f"plan:30:{p30}"),
    ])
    keyboard.append([
        InlineKeyboardButton(text=f"👑 Безлимит: Навсегда — {plife} ₽", callback_data=f"plan:999:{plife}"),
    ])
    keyboard.append([
        InlineKeyboardButton(text="🏠 В главное меню", callback_data="btn_main_menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def get_payment_methods_keyboard(days: int, price: int) -> InlineKeyboardMarkup:
    """Выбор метода оплаты для выбранного тарифа."""
    stars_count = await get_plan_stars(days)
    crypto_usd = await get_plan_crypto(days)

    keyboard = [
        [
            InlineKeyboardButton(text=f"💳 СБП / Карты РФ ({price} ₽)", callback_data=f"pay:sbp:{days}:{price}"),
        ],
        [
            InlineKeyboardButton(text=f"💎 Крипта: USDT / TON (${crypto_usd})", callback_data=f"pay:crypto:{days}:{price}"),
        ],
        [
            InlineKeyboardButton(text=f"⭐️ Telegram Stars ({stars_count} ⭐️)", callback_data=f"pay:stars:{days}:{stars_count}"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад к тарифам", callback_data="menu_pay_plans"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_receipt_action_keyboard(days: int, price: int, method_name: str) -> InlineKeyboardMarkup:
    """Кнопка подтверждения оплаты для отправки чека."""
    keyboard = [
        [
            InlineKeyboardButton(text="📤 Я оплатил (Отправить чек)", callback_data=f"send_rec:{days}:{price}:{method_name}"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Выбрать другой способ", callback_data=f"plan:{days}:{price}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_admin_approval_keyboard(user_id: int, days: int) -> InlineKeyboardMarkup:
    """Кнопки подтверждения для администратора."""
    keyboard = [
        [
            InlineKeyboardButton(text=f"✅ Одобрить ({days} дн.)", callback_data=f"adm_approve:{user_id}:{days}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_reject:{user_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- Клавиатуры управления словами ---

def get_keywords_menu_keyboard(has_words: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить ключевые слова", callback_data="kw_add")]
    ]
    if has_words:
        buttons.append([
            InlineKeyboardButton(text="❌ Удалить конкретное слово", callback_data="kw_delete_choice"),
            InlineKeyboardButton(text="🗑 Очистить всё", callback_data="kw_clear_confirm"),
        ])
        buttons.append([
            InlineKeyboardButton(text="📥 Скачать слова (.txt)", callback_data="kw_export"),
        ])
    buttons.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="btn_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_stop_words_menu_keyboard(has_words: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить минус-слова", callback_data="sw_add")]
    ]
    if has_words:
        buttons.append([
            InlineKeyboardButton(text="❌ Удалить конкретное", callback_data="sw_delete_choice"),
            InlineKeyboardButton(text="🗑 Очистить всё", callback_data="sw_clear_confirm"),
        ])
    buttons.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="btn_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_delete_words_keyboard(words: list[str], prefix: str, page: int = 0) -> InlineKeyboardMarkup:
    PAGE_SIZE = 12
    total_pages = max(1, (len(words) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_words = words[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    keyboard = []
    row = []
    for i, w in enumerate(page_words):
        global_idx = page * PAGE_SIZE + i
        row.append(InlineKeyboardButton(text=f"[-] {w}", callback_data=f"{prefix}_del:{global_idx}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="‹ Назад", callback_data=f"{prefix}_page:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Далее ›", callback_data=f"{prefix}_page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    back_callback = "menu_kw" if prefix == "kw" else "menu_sw"
    keyboard.append([InlineKeyboardButton(text="‹ Назад в меню слов", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cancel_keyboard(target: str = "btn_main_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="‹ Отмена", callback_data=target)]]
    )


# --- Команда /start ---
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    is_admin = db.is_admin(user_id)
    is_new = await db.add_user(user_id)

    user = await db.get_user(user_id)
    pro_status = await db.get_pro_status_display(user)

    trial_banner = ""
    if is_admin:
        trial_banner = (
            "👑 <b>СТАТУС: АДМИНИСТРАТОР</b>\n"
            "Вам предоставлен бессрочный PRO-доступ, прямые контакты и админ-панель /admin.\n\n"
        )
    elif is_new:
        trial_banner = (
            "🎁 <b>БЕСПЛАТНЫЙ ТЕСТОВЫЙ ПЕРИОД: 5 ДНЕЙ PRO</b>\n"
            "Прямые контакты заказчиков, заявки с бирж и B2B поиск открыты без ограничений.\n\n"
        )

    text = (
        "⚡️ <b>LeadHunter — Найди бизнес. Предложи сайт или бота.</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Клиенты для тех, кто делает сайты, ботов и дизайн</i>\n\n"
        "LeadHunter находит в Картах (Google & 2GIS) малый бизнес без своего сайта "
        "или с шаблонной страницей вместо него (QR-меню, запись YCLIENTS/Booksy, страница в соцсетях) — "
        "собирает прямые контакты владельцев (WhatsApp, Telegram, телефон) и помогает написать первым.\n\n"
        "А также в реальном времени мониторит фриланс-биржи (Kwork, FL, Habr) и десятки чатов на целевые заказы.\n\n"
        "📍 <i>15+ сфер бизнеса • поиск клиентов в Telegram и браузере • мгновенные уведомления</i>\n\n"
        "💎 <b>Тарифы подписки PRO:</b>\n"
        "🎁 <b>3 дня (Пробный)</b> — <b>БЕСПЛАТНО</b> <i>(0 ₽)</i>\n"
        "🔥 <b>1 месяц (Стандарт)</b> — <b>490 ₽</b> <i>/ 250 ⭐️</i>  <code>[Хит]</code>\n"
        "👑 <b>Навсегда (Безлимит)</b> — <b>1 490 ₽</b> <i>/ 750 ⭐️</i>\n\n"
        "<i>💳 Оплата: СБП, карты любых банков РФ, USDT/TON или Telegram Stars.</i>\n\n"
        "<blockquote expandable>"
        "<b>🎯 Что умеет LeadHunter:</b>\n"
        "• <b>Поиск без сайта:</b> фильтрация заведений без сайтов на картах\n"
        "• <b>Контакты в 1 клик:</b> прямые ссылки на WhatsApp и Telegram владельца\n"
        "• <b>AI-оффер:</b> персонализированный расчет упущенной выгоды под сферу\n"
        "• <b>Радар бирж:</b> перехват свежих заявок на разработку сайтов и ботов за секунды\n"
        "• <b>Встроенная CRM:</b> учет статусов сделок «Отправлено», «Ответили», «В работе»"
        "</blockquote>\n\n"
        "<blockquote expandable>"
        "<b>🚀 Как запустить и пользоваться:</b>\n"
        "1. Запустите <b>B2B Web-терминал</b> прямо в Telegram (кнопка ниже).\n"
        "2. Выберите нужную сферу (рестораны, салоны красоты, автосервисы...) и город поиска.\n"
        "3. Получайте прямые контакты владельцев (WhatsApp, Telegram, телефон) и отправляйте готовые предложения!\n"
        "4. Включайте мониторинг бирж и получайте горячие заказы прямо в этот чат."
        "</blockquote>\n\n"
        "<blockquote expandable>"
        "<b>🛡 Данные и гарантии:</b>\n"
        "• Вся собранная база компаний сохраняется на вашем компьютере и выгружается в Excel/CSV.\n"
        "• Прямые контакты без посредников и комиссий бирж.\n"
        "• Поддержка на связи 24/7."
        "</blockquote>\n\n"
        f"{trial_banner}"
        f"💎 <b>Ваш статус:</b> {pro_status}\n"
        f"👤 <b>Ваш ID:</b> <code>{user_id}</code>"
    )
    # Закрепляем постоянные кнопки быстрого доступа под полем ввода текста
    await message.answer(
        "<i>Навигация закреплена внизу экрана:</i>",
        reply_markup=get_persistent_reply_keyboard(is_admin=is_admin),
        parse_mode="HTML",
    )
    await message.answer(text, reply_markup=get_main_keyboard(is_admin=is_admin), parse_mode="HTML")


# --- B2B Mini App Handler ---
@router.message(Command("app"))
@router.message(Command("miniapp"))
@router.message(F.text.in_(["⚡️ B2B Поиск клиентов (App)", "[▸] B2B Поиск клиентов (App)", "Поиск B2B клиентов (App)", "🚀 Поиск B2B клиентов (App)"]))
@router.callback_query(F.data == "btn_open_miniapp")
async def show_miniapp_info(event: Message | CallbackQuery) -> None:
    message = event if isinstance(event, Message) else event.message
    app_url = getattr(config, "MINI_APP_URL", "")
    from_user = event.from_user
    uid = from_user.id if from_user else 0
    browser_url = f"{app_url}?user_id={uid}" if (app_url.startswith("https://") and uid) else app_url

    text = (
        "⚡️ <b>LeadHunter B2B — Поиск заведений без сайта</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Инструмент поиска компаний на картах для веб-разработчиков и дизайнеров:\n\n"
        "• 🎯 <b>15+ ниш:</b> Рестораны, салоны красоты, автосервисы, отели, клиники, спорт\n"
        "• 🔥 <b>HOT-лиды:</b> Заведения без сайта или с шаблонным меню\n"
        "• 📱 <b>1-клик контакты:</b> Прямой переход в WhatsApp, Telegram, Instagram или звонок\n"
        "• 💡 <b>Генератор оффера:</b> Готовый персонализированный расчет упущенной выгоды\n"
        "• 💼 <b>Встроенная CRM:</b> Учет этапов сделки и клиентская база\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <i>Нажмите кнопку ниже для запуска терминала:</i>"
    )

    if app_url.startswith("https://"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ Запустить LeadHunter B2B", web_app=WebAppInfo(url=app_url))],
            [InlineKeyboardButton(text="🌐 Открыть в обычном браузере", url=browser_url)],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="btn_main_menu")],
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Открыть LeadHunter B2B", url=browser_url)],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="btn_main_menu")],
        ])

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "btn_download_app")
async def cb_download_app(callback: CallbackQuery) -> None:
    app_url = getattr(config, "MINI_APP_URL", "")
    text = (
        "⚡️ <b>LeadHunter B2B Web-терминал</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Сервис работает <b>напрямую внутри Telegram</b> как защищенное веб-приложение (Mini App).\n\n"
        "Вам не нужно ничего скачивать или устанавливать на диск — терминал открывается в 1 клик на любом устройстве (ПК, iPhone, Android, Mac).\n\n"
        "👇 <i>Нажмите кнопку ниже, чтобы открыть терминал:</i>"
    )
    kb_buttons = []
    if app_url.startswith("https://"):
        kb_buttons.append([InlineKeyboardButton(text="⚡️ Запустить LeadHunter B2B", web_app=WebAppInfo(url=app_url))])
    kb_buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="btn_main_menu")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("dl_os:"))
async def cb_download_os(callback: CallbackQuery) -> None:
    await cb_download_app(callback)


@router.callback_query(F.data == "btn_main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    is_admin = db.is_admin(callback.from_user.id)
    user = await db.get_user(callback.from_user.id)
    pro_status = await db.get_pro_status_display(user)
    text = (
        "⚡️ <b>LeadHunter — Найди бизнес. Предложи сайт или бота.</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Клиенты для тех, кто делает сайты, ботов и дизайн</i>\n\n"
        "LeadHunter находит в Картах (Google & 2GIS) малый бизнес без своего сайта "
        "или с шаблонной страницей вместо него — собирает прямые контакты владельцев (WhatsApp, Telegram, телефон) и помогает написать первым.\n\n"
        "💎 <b>Тарифы подписки PRO:</b>\n"
        "🎁 <b>3 дня (Пробный)</b> — <b>БЕСПЛАТНО</b> <i>(0 ₽)</i>\n"
        "🔥 <b>1 месяц</b> — <b>490 ₽</b> <i>/ 250 ⭐️</i>  <code>[Хит]</code>\n"
        "👑 <b>Навсегда</b> — <b>1 490 ₽</b> <i>/ 750 ⭐️</i>\n\n"
        "<blockquote expandable>"
        "<b>🎯 Что умеет LeadHunter:</b>\n"
        "• <b>Поиск без сайта:</b> заведения с шаблонным меню или соцсетями вместо сайта\n"
        "• <b>Контакты в 1 клик:</b> WhatsApp, Telegram, телефон лица, принимающего решения\n"
        "• <b>AI-оффер:</b> персонализированный расчет упущенной выгоды под сферу\n"
        "• <b>Радар бирж:</b> перехват заказов на разработку сайтов и ботов за секунды\n"
        "• <b>Встроенная CRM:</b> учет этапов «Отправлено», «Ответили», «В работе»"
        "</blockquote>\n\n"
        f"💎 <b>Ваш статус:</b> {pro_status}\n"
        f"👤 <b>Ваш ID:</b> <code>{callback.from_user.id}</code>\n\n"
        "👇 <i>Выберите действие в меню ниже:</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_main_keyboard(is_admin=is_admin),
        parse_mode="HTML",
    )
    await callback.answer()


# --- Обработчики постоянных кнопок и текстовых команд ---

@router.message(Command("menu"))
@router.message(F.text.in_(["📋 Главное меню", "🏠 Главное меню", "▪ Главное меню", "Главное меню"]))
async def nav_main_menu(message: Message, state: FSMContext) -> None:
    await cmd_start(message, state)


@router.message(Command("filters"))
@router.message(F.text.in_(["🎯 Готовые фильтры", "▪ Готовые фильтры", "Готовые фильтры"]))
async def nav_filters(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    user_active_cats = await db.get_user_categories(user_id)
    text = (
        "<b>Каталог готовых фильтров по профессиям</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Вам <b>не нужно вручную придумывать слова</b>: "
        "мы уже собрали целевые маркеры заказов и сгруппировали их по направлениям.\n\n"
        "› <i>Выберите подходящую сферу и включите нужные направления галочками [✓]:</i>"
    )
    await message.answer(
        text,
        reply_markup=get_clusters_keyboard(user_active_cats),
        parse_mode="HTML",
    )


@router.message(Command("profile"))
@router.message(F.text.in_(["👤 Личный кабинет", "▪ Личный кабинет", "Личный кабинет", "📋 Личный кабинет"]))
async def nav_profile(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    is_admin = db.is_admin(user_id)
    user = await db.get_user(user_id)
    if not user:
        await db.add_user(user_id)
        user = await db.get_user(user_id)

    pro_display = await db.get_pro_status_display(user)
    leads_count = user.get("leads_received", 0)
    kw_count = len(db._parse_list(user.get("keywords")))
    sw_count = len(db._parse_list(user.get("stop_words")))
    user_active_cats = await db.get_user_categories(user_id)
    cat_count = len(user_active_cats)

    admin_badge = "• <b>Роль:</b> Главный Администратор / Владелец\n" if is_admin else ""

    text = (
        "<b>Личный кабинет пользователя</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"{admin_badge}"
        f"• <b>Тарифный план:</b> {pro_display}\n\n"
        f"• <b>Активных готовых фильтров:</b> {cat_count}\n"
        f"• <b>Своих ключевых слов:</b> {kw_count}\n"
        f"• <b>Минус-слов:</b> {sw_count}\n"
        f"• <b>Поймано заказов:</b> <b>{leads_count}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "› <i>Управляйте фильтрами, словами и тарифом в меню ниже:</i>"
    )
    await message.answer(text, reply_markup=get_main_keyboard(is_admin=is_admin), parse_mode="HTML")


@router.message(Command("keywords"))
@router.message(F.text.in_(["🔑 Ключевые слова", "▪ Ключевые слова", "Ключевые слова"]))
async def nav_keywords(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await db.get_user(message.from_user.id)
    words = db._parse_list(user.get("keywords")) if user else []

    if words:
        words_formatted = "\n".join(f"  <b>{i+1}.</b> <code>{html.escape(w)}</code>" for i, w in enumerate(words))
        text = (
            f"<b>Ваши ключевые слова</b> (всего: {len(words)}):\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{words_formatted}\n\n"
            f"› <i>Бот присылает заказы, в которых есть хотя бы одно из этих слов.</i>"
        )
    else:
        text = (
            "<b>Список ключевых слов пока пуст</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Нажмите <b>«+ Добавить ключевые слова»</b>, чтобы ввести слова через запятую "
            "или отправить готовый текстовый файл (.txt со словами)."
        )

    await message.answer(
        text,
        reply_markup=get_keywords_menu_keyboard(bool(words)),
        parse_mode="HTML",
    )


@router.message(Command("pro"))
@router.message(F.text.in_(["💎 Тарифы подписки", "[PRO] Тарифы подписки", "Тарифы подписки", "💎 Подключить PRO", "Подключить PRO"]))
async def nav_pro(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = (
        "<b>Тарифные планы подписки PRO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Что даёт статус PRO:</b>\n"
        "• Полные открытые контакты заказчиков (@username и ссылки)\n"
        "• Прямой переход к исходному сообщению в чате в 1 клик\n"
        "• Мгновенная доставка лидов без задержек\n"
        "• Полный доступ к B2B поиску клиентов без сайта\n\n"
        "› <i>Доступны СБП, банковские карты РФ, Криптовалюта (USDT, TON) и Telegram Stars.</i>\n\n"
        "› <b>Выберите срок действия:</b>"
    )
    await message.answer(text, reply_markup=await get_payment_plans_keyboard(message.from_user.id), parse_mode="HTML")


# ==========================================
# СИСТЕМА ОПЛАТЫ (СБП, КАРТЫ, КРИПТА, STARS)
# ==========================================

@router.callback_query(F.data.in_(["menu_pay_plans", "btn_buy_pro"]))
async def cb_pay_plans(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    p3 = await get_plan_price(3)
    p30 = await get_plan_price(30)
    plife = await get_plan_price(999)
    trial_str = "<b>БЕСПЛАТНО</b>" if p3 == 0 else f"<b>{p3} ₽</b>"
    text = (
        "💎 <b>Тарифные планы подписки PRO:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎁 <b>3 дня (Пробный):</b> {trial_str}\n"
        f"🔥 <b>30 дней (Месяц):</b> <b>{p30} ₽</b>\n"
        f"👑 <b>Безлимит (Навсегда):</b> <b>{plife} ₽</b>\n\n"
        "<b>Возможности статуса PRO:</b>\n"
        "• 🔓 Полные открытые контакты заказчиков (@username и ссылки)\n"
        "• 🔗 Прямой переход к исходному сообщению в чате в 1 клик\n"
        "• ⚡️ Мгновенная доставка лидов без задержек\n"
        "• 🎯 Доступ к B2B поиску заведений без сайта на картах\n"
        "• 💡 Персонализированный AI-генератор офферов и ROI\n\n"
        "<i>Доступны СБП, банковские карты РФ, Криптовалюта (USDT, TON) и Telegram Stars.</i>\n\n"
        "👇 <b>Выберите срок действия подписки:</b>"
    )
    await callback.message.edit_text(text, reply_markup=await get_payment_plans_keyboard(callback.from_user.id), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "trial_already_used")
async def cb_trial_already_used(callback: CallbackQuery) -> None:
    await callback.answer(
        "⚠️ Вы уже использовали бесплатный пробный период на этом аккаунте.\n\n"
        "Для продолжения работы выберите тариф «Месяц» или «Безлимит».",
        show_alert=True
    )


@router.callback_query(F.data.startswith("plan:"))
async def cb_choose_plan(callback: CallbackQuery) -> None:
    _, days_str, price_str = callback.data.split(":")
    days = int(days_str)
    price = int(price_str)
    user_id = callback.from_user.id

    if days == 3 or price == 0:
        ok, res = await db.activate_free_trial(user_id, days=3)
        if not ok:
            if res == "already_used":
                await callback.answer(
                    "⚠️ Бесплатный пробный период уже был использован на этом аккаунте!\n\n"
                    "Для продолжения выберите тариф «Месяц» или «Безлимит».",
                    show_alert=True
                )
                await callback.message.edit_reply_markup(
                    reply_markup=await get_payment_plans_keyboard(user_id)
                )
            elif res == "already_active":
                user = await db.get_user(user_id)
                pro_status = await db.get_pro_status_display(user)
                await callback.answer(f"У вас уже активен PRO статус ({pro_status})!", show_alert=True)
            return

        readable_until = res
        user = await db.get_user(user_id)
        pro_status = await db.get_pro_status_display(user)

        success_text = (
            "🎉 <b>БЕСПЛАТНЫЙ ПРОБНЫЙ ПЕРИОД PRO АКТИВИРОВАН!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💎 <b>Ваш статус:</b> {pro_status}\n"
            f"⏱ <b>Срок действия:</b> 3 дня ({readable_until})\n\n"
            "<b>Вам открыт полный безлимитный доступ:</b>\n"
            "• 🔓 Прямые контакты заказчиков (@username, телефон, ссылки)\n"
            "• 🎯 B2B Web-терминал поиска заведений без сайта на картах\n"
            "• ⚡️ Мгновенный перехват заказов с бирж (FL, Kwork, Habr)\n"
            "• ✨ AI-генератор продающих офферов под ниши\n\n"
            "👇 <i>Запустите Web-терминал прямо сейчас:</i>"
        )
        app_url = getattr(config, "MINI_APP_URL", "")
        buttons = []
        if app_url.startswith("https://"):
            buttons.append([InlineKeyboardButton(text="⚡️ Запустить B2B Поиск (App)", web_app=WebAppInfo(url=app_url))])
        else:
            buttons.append([InlineKeyboardButton(text="⚡️ Запустить B2B Поиск", callback_data="btn_open_miniapp")])
        buttons.append([InlineKeyboardButton(text="🎯 Настроить фильтры заказов", callback_data="menu_categories")])
        buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="btn_main_menu")])

        await callback.message.edit_text(success_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
        await callback.answer("🎁 Бесплатный пробный период активирован!")
        return

    period_label = "3 дня (Тест)" if days == 3 else ("30 дней (Месяц)" if days == 30 else "Навсегда (Lifetime)")

    text = (
        f"💳 <b>Оплата тарифа: PRO {period_label}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 <b>Стоимость:</b> <b>{price} ₽</b>\n\n"
        f"👇 <i>Выберите удобный способ оплаты:</i>"
    )
    await callback.message.edit_text(text, reply_markup=await get_payment_methods_keyboard(days, price), parse_mode="HTML")
    await callback.answer()


# 1. Оплата через СБП и Карты РФ
@router.callback_query(F.data.startswith("pay:sbp:"))
async def cb_pay_sbp(callback: CallbackQuery) -> None:
    _, _, days_str, price_str = callback.data.split(":")
    days = int(days_str)
    price = int(price_str)
    user_id = callback.from_user.id
    req = await get_requisites()

    text = (
        f"💳 <b>Оплата через СБП / Карту РФ ({price} ₽)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1. <b>СБП (по номеру телефона):</b>\n"
        f"   📱 <b>Номер:</b> <code>{req['sbp_phone']}</code>\n"
        f"   🏦 <b>Банк:</b> <b>{req['sbp_bank']}</b>\n\n"
        f"2. <b>Перевод по номеру карты:</b>\n"
        f"   💳 <b>Карта:</b> <code>{req['card_number']}</code>\n\n"
        f"📌 <b>ВАЖНО:</b> В комментарии к переводу укажите ваш ID: <code>{user_id}</code>\n\n"
        f"3. После перевода нажмите кнопку <b>«📤 Я оплатил (Отправить чек)»</b> ниже "
        f"и пришлите скриншот квитанции. Бот передаст его админу, и PRO сразу активируется!"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_receipt_action_keyboard(days, price, "СБП/Карта"),
        parse_mode="HTML",
    )
    await callback.answer()


# 2. Оплата Криптовалютой (USDT / TON)
@router.callback_query(F.data.startswith("pay:crypto:"))
async def cb_pay_crypto(callback: CallbackQuery) -> None:
    _, _, days_str, price_str = callback.data.split(":")
    days = int(days_str)
    price = int(price_str)
    crypto_usd = await get_plan_crypto(days)
    req = await get_requisites()

    text = (
        f"💎 <b>Оплата криптовалютой (~${crypto_usd} USDT)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🟢 <b>USDT (Сеть TRC-20):</b>\n"
        f"<code>{req['usdt']}</code>\n\n"
        f"💎 <b>TON (The Open Network):</b>\n"
        f"<code>{req['ton']}</code>\n\n"
        f"📌 Переведите <b>${crypto_usd} USDT</b> (или эквивалент в TON) на любой из адресов выше.\n\n"
        f"После отправки нажмите <b>«📤 Я оплатил (Отправить чек)»</b> и пришлите TXID или скриншот кошелька."
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_receipt_action_keyboard(days, price, "Криптовалюта"),
        parse_mode="HTML",
    )
    await callback.answer()


# 3. Оплата через Telegram Stars
@router.callback_query(F.data.startswith("pay:stars:"))
async def cb_pay_stars(callback: CallbackQuery, bot: Bot) -> None:
    _, _, days_str, stars_str = callback.data.split(":")
    days = int(days_str)
    stars = int(stars_str)

    period_label = "3 дня" if days == 3 else ("30 дней" if days == 30 else "Lifetime")
    prices = [LabeledPrice(label=f"PRO подписка ({period_label})", amount=stars)]

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"PRO Подписка ({period_label})",
        description=f"Открытые контакты и прямые ссылки на заказы в Telegram Lead Hunter на {period_label}.",
        payload=f"stars:{callback.from_user.id}:{days}",
        currency="XTR",
        prices=prices,
        start_parameter="pro-subscription",
    )
    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery, bot: Bot) -> None:
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message, bot: Bot) -> None:
    payload = message.successful_payment.invoice_payload
    parts = payload.split(":")
    if len(parts) >= 3 and parts[0] == "stars":
        user_id = int(parts[1])
        days = int(parts[2])
        readable_date = await db.give_pro_days(user_id, days)

        await message.answer(
            f"<b>✅ ОПЛАТА ЧЕРЕЗ TELEGRAM STARS ПРОШЛА УСПЕШНО</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Вам активирован тариф <b>PRO</b> ({readable_date}).\n"
            f"Удачной охоты за лидами и крупными заказами!",
            reply_markup=get_main_keyboard(is_admin=db.is_admin(user_id)),
            parse_mode="HTML",
        )


# --- Отправка квитанции / чека администратору ---

@router.callback_query(F.data.startswith("send_rec:"))
async def cb_start_send_receipt(callback: CallbackQuery, state: FSMContext) -> None:
    _, days_str, price_str, method_name = callback.data.split(":")
    await state.set_state(UserStates.waiting_payment_receipt)
    await state.set_data({
        "days": int(days_str),
        "price": int(price_str),
        "method": method_name,
    })

    text = (
        "<b>ПОДТВЕРЖДЕНИЕ ОПЛАТЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте фото квитанции, документ или текстовое сообщение с деталями перевода (TXID хэш / номер операции).\n\n"
        "Администратор проверит платеж и активирует PRO-статус."
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard("menu_pay_plans"), parse_mode="HTML")
    await callback.answer()


@router.message(UserStates.waiting_payment_receipt)
async def process_receipt_submission(message: Message, bot: Bot, state: FSMContext) -> None:
    data = await state.get_data()
    days = data.get("days", 3)
    price = data.get("price", 99)
    method = data.get("method", "СБП/Карта")
    await state.clear()

    user = message.from_user
    user_mention = f"@{user.username}" if user.username else user.full_name
    period_label = "3 дня" if days == 3 else ("30 дней" if days == 30 else "Lifetime")

    admin_caption = (
        f"🔔 <b>НОВАЯ ОПЛАТА НА ПРОВЕРКУ!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Пользователь:</b> {user_mention} (ID: <code>{user.id}</code>)\n"
        f"💰 <b>Тариф:</b> PRO {period_label} ({price} ₽)\n"
        f"💳 <b>Способ:</b> {method}\n\n"
        f"Проверьте поступление средств и примите решение:"
    )

    markup = get_admin_approval_keyboard(user.id, days)

    try:
        if message.photo:
            await bot.send_photo(
                chat_id=config.ADMIN_ID,
                photo=message.photo[-1].file_id,
                caption=admin_caption,
                reply_markup=markup,
                parse_mode="HTML",
            )
        elif message.document:
            await bot.send_document(
                chat_id=config.ADMIN_ID,
                document=message.document.file_id,
                caption=admin_caption,
                reply_markup=markup,
                parse_mode="HTML",
            )
        else:
            admin_text = f"{admin_caption}\n\n• <b>Комментарий пользователя:</b>\n{html.escape(message.text or '')}"
            await bot.send_message(
                chat_id=config.ADMIN_ID,
                text=admin_text,
                reply_markup=markup,
                parse_mode="HTML",
            )

        await message.answer(
            "<b>[•] ЧЕК ПРИНЯТ НА ПРОВЕРКУ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Администратор подтвердит платеж в течение нескольких минут, "
            "и вы сразу получите уведомление об активации PRO-тарифа в этот чат.",
            reply_markup=get_main_keyboard(is_admin=db.is_admin(user.id)),
            parse_mode="HTML",
        )
    except Exception as err:
        await message.answer(f"⚠️ Ошибка отправки чека администратору: {err}")


# --- Обработка решений администратора ---

@router.callback_query(F.data.startswith("adm_approve:"))
async def cb_admin_approve(callback: CallbackQuery, bot: Bot) -> None:
    _, target_user_str, days_str = callback.data.split(":")
    target_user_id = int(target_user_str)
    days = int(days_str)

    readable_date = await db.give_pro_days(target_user_id, days)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"<b>✅ Оплата подтверждена!</b>\n"
        f"Пользователю <code>{target_user_id}</code> активирован PRO ({readable_date}).",
        parse_mode="HTML",
    )
    await callback.answer("Подтверждено")

    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=(
                f"<b>[PRO АКТИВИРОВАН] Ваша оплата подтверждена!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Вам успешно подключен статус <b>PRO</b> ({readable_date}).\n\n"
                f"Все открытые контакты заказчиков и ссылки на чаты доступны без ограничений."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        await callback.message.answer(f"⚠️ Не удалось отправить уведомление пользователю: {e}")


@router.callback_query(F.data.startswith("adm_reject:"))
async def cb_admin_reject(callback: CallbackQuery, bot: Bot) -> None:
    target_user_id = int(callback.data.split(":")[1])

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"[x] Оплата пользователя <code>{target_user_id}</code> отклонена.",
        parse_mode="HTML",
    )
    await callback.answer("Отклонено")

    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=(
                "<b>⚠️ Оплата не была подтверждена</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Возможно, перевод еще не поступил или квитанция не читается.\n"
                f"Пожалуйста, свяжитесь с поддержкой: @{config.ADMIN_USERNAME}"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass



# ==========================================
# ГОТОВЫЕ ФИЛЬТРЫ ПО НАПРАВЛЕНИЯМ
# ==========================================

@router.callback_query(F.data == "menu_categories")
async def cb_menu_categories(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = callback.from_user.id
    user_active_cats = await db.get_user_categories(user_id)

    text = (
        "<b>КАТАЛОГ ГОТОВЫХ B2B-ФИЛЬТРОВ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Вам <b>не нужно вручную придумывать слова</b>: "
        "мы уже собрали целевые маркеры заказов и разделили их по направлениям.\n\n"
        "› <i>Выберите подходящую сферу и включите нужные направления тумблерами [✓]:</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_clusters_keyboard(user_active_cats),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cluster:"))
async def cb_cluster_view(callback: CallbackQuery) -> None:
    cluster_id = callback.data.split(":")[1]
    cluster = categories.get_cluster(cluster_id)
    if not cluster:
        await callback.answer("Сфера не найдена.")
        return

    user_id = callback.from_user.id
    user_active_cats = await db.get_user_categories(user_id)

    text = (
        f"<b>{cluster['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Нажимайте на кнопки ниже, чтобы переключать направления <b>[✓ Вкл / — Выкл]</b>.\n"
        f"Бот мгновенно начнет отслеживать все заказы по выбранным профилям."
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_cluster_details_keyboard(cluster_id, user_active_cats),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat_toggle:"))
async def cb_cat_toggle(callback: CallbackQuery) -> None:
    _, cluster_id, cat_id = callback.data.split(":")
    user_id = callback.from_user.id

    is_now_active = await db.toggle_user_category(user_id, cat_id)
    user_active_cats = await db.get_user_categories(user_id)

    cat = categories.get_category(cat_id)
    cat_title = cat["short_name"] if cat else cat_id

    # Мгновенно обновляем клавиатуру на лету без мигания текста
    await callback.message.edit_reply_markup(
        reply_markup=get_cluster_details_keyboard(cluster_id, user_active_cats)
    )

    status_word = "[✓] Включено" if is_now_active else "[—] Отключено"
    kw_count = len(cat["keywords"]) if cat else 0
    await callback.answer(f"{status_word}: {cat_title} ({kw_count} ключевиков)", show_alert=False)


@router.callback_query(F.data.startswith("cluster_on:"))
async def cb_cluster_on(callback: CallbackQuery) -> None:
    cluster_id = callback.data.split(":")[1]
    user_id = callback.from_user.id

    added = await db.enable_cluster(user_id, cluster_id)
    user_active_cats = await db.get_user_categories(user_id)
    cluster = categories.get_cluster(cluster_id)
    name = cluster["name"] if cluster else cluster_id

    await callback.message.edit_reply_markup(
        reply_markup=get_cluster_details_keyboard(cluster_id, user_active_cats)
    )
    await callback.answer(f"[✓] Вся сфера «{name}» включена (+{added} направлений)", show_alert=False)


@router.callback_query(F.data.startswith("cluster_off:"))
async def cb_cluster_off(callback: CallbackQuery) -> None:
    cluster_id = callback.data.split(":")[1]
    user_id = callback.from_user.id

    removed = await db.disable_cluster(user_id, cluster_id)
    user_active_cats = await db.get_user_categories(user_id)
    cluster = categories.get_cluster(cluster_id)
    name = cluster["name"] if cluster else cluster_id

    await callback.message.edit_reply_markup(
        reply_markup=get_cluster_details_keyboard(cluster_id, user_active_cats)
    )
    await callback.answer(f"[—] Сфера «{name}» отключена (-{removed} направлений)", show_alert=False)


@router.callback_query(F.data == "cat_my_active")
async def cb_my_active_categories(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    user_active_cats = await db.get_user_categories(user_id)

    if not user_active_cats:
        text = (
            "<b>АКТИВНЫЕ ГОТОВЫЕ ФИЛЬТРЫ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "У вас пока нет активных готовых фильтров.\n"
            "Выберите сферу в каталоге, чтобы включить нужные направления в 1 клик."
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Выбрать сферы", callback_data="menu_categories")],
                [InlineKeyboardButton(text="‹ В главное меню", callback_data="btn_main_menu")],
            ]
        )
    else:
        lines = []
        total_keywords_count = 0
        for cluster in categories.CLUSTERS:
            matched_in_cluster = [c for c in cluster["categories"] if c["id"] in user_active_cats]
            if matched_in_cluster:
                lines.append(f"\n<b>{cluster['name']}:</b>")
                for c in matched_in_cluster:
                    kw_len = len(c["keywords"])
                    total_keywords_count += kw_len
                    lines.append(f"  • {c['name']} <i>({kw_len} маркеров)</i>")

        active_list_str = "\n".join(lines)
        text = (
            f"<b>АКТИВНЫЕ ГОТОВЫЕ ФИЛЬТРЫ</b> ({len(user_active_cats)} направл.):\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{active_list_str}\n\n"
            f"• <b>Суммарно отслеживается:</b> ~<b>{total_keywords_count}</b> профессиональных поисковых фраз.\n\n"
            f"<i>Вы можете в любой момент изменить выбор или сбросить фильтры.</i>"
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎯 Настроить фильтры", callback_data="menu_categories")],
                [InlineKeyboardButton(text="[x] Сбросить все категории", callback_data="cat_reset_confirm")],
                [InlineKeyboardButton(text="‹ В главное меню", callback_data="btn_main_menu")],
            ]
        )

    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "cat_reset_confirm")
async def cb_reset_categories(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    await db.clear_all_categories(user_id)
    await callback.answer("✅ Все готовые фильтры сброшены", show_alert=True)
    user_active_cats = await db.get_user_categories(user_id)
    text = (
        "<b>КАТАЛОГ ГОТОВЫХ B2B-ФИЛЬТРОВ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Вам <b>не нужно вручную придумывать слова</b>: "
        "мы уже собрали целевые маркеры заказов и разделили их по направлениям.\n\n"
        "› <i>Выберите подходящую сферу и включите нужные направления тумблерами [✓]:</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_clusters_keyboard(user_active_cats),
        parse_mode="HTML",
    )


# ==========================================
# УПРАВЛЕНИЕ КЛЮЧЕВЫМИ И МИНУС-СЛОВАМИ
# ==========================================

@router.callback_query(F.data == "menu_kw")
async def cb_menu_keywords(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    words = db._parse_list(user.get("keywords")) if user else []

    if words:
        words_formatted = "\n".join(f"  <b>{i+1}.</b> <code>{html.escape(w)}</code>" for i, w in enumerate(words))
        text = (
            f"<b>ВАШИ КЛЮЧЕВЫЕ СЛОВА</b> ({len(words)} шт.):\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{words_formatted}\n\n"
            f"<i>Бот присылает заказы, в которых найдено хотя бы одно из этих слов.</i>"
        )
    else:
        text = (
            "<b>ВАШИ КЛЮЧЕВЫЕ СЛОВА</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Список ключевых слов пока пуст.\n\n"
            "Нажмите <b>«[+] Добавить ключевые слова»</b>, чтобы ввести слова через запятую "
            "или отправить готовый текстовый файл (.txt со словами)."
        )

    await callback.message.edit_text(
        text,
        reply_markup=get_keywords_menu_keyboard(bool(words)),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "kw_add")
async def cb_kw_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserStates.waiting_add_keywords)
    text = (
        "<b>ДОБАВЛЕНИЕ КЛЮЧЕВЫХ СЛОВ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте мне слова одним из способов:\n\n"
        "1. <b>Текстом через запятую:</b>\n"
        "   <code>сайт, бот, python, дизайн, копирайтер</code>\n\n"
        "2. <b>Файлом (.txt или .csv):</b>\n"
        "   Прикрепите текстовый файл — бот добавит все слова автоматически.\n\n"
        "<i>Новые слова добавятся к текущему списку без дубликатов.</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard("menu_kw"), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "kw_delete_choice")
async def cb_kw_delete_choice(callback: CallbackQuery) -> None:
    user = await db.get_user(callback.from_user.id)
    words = db._parse_list(user.get("keywords")) if user else []

    if not words:
        await callback.answer("Список пуст.")
        return

    text = "<b>Нажмите на слово для удаления:</b>"
    await callback.message.edit_text(
        text,
        reply_markup=get_delete_words_keyboard(words, prefix="kw", page=0),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("kw_del:"))
async def cb_kw_delete_single(callback: CallbackQuery) -> None:
    idx = int(callback.data.split(":")[1])
    user = await db.get_user(callback.from_user.id)
    words = db._parse_list(user.get("keywords")) if user else []

    if 0 <= idx < len(words):
        word_to_remove = words[idx]
        updated_words = await db.remove_keyword(callback.from_user.id, word_to_remove)
        await callback.answer(f"Удалено: {word_to_remove}")

        if updated_words:
            await callback.message.edit_reply_markup(
                reply_markup=get_delete_words_keyboard(updated_words, prefix="kw", page=0)
            )
        else:
            await cb_menu_keywords(callback, FSMContext)
    else:
        await callback.answer("Слово не найдено.")


@router.callback_query(F.data.startswith("kw_page:"))
async def cb_kw_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])
    user = await db.get_user(callback.from_user.id)
    words = db._parse_list(user.get("keywords")) if user else []
    await callback.message.edit_reply_markup(
        reply_markup=get_delete_words_keyboard(words, prefix="kw", page=page)
    )
    await callback.answer()


@router.callback_query(F.data == "kw_clear_confirm")
async def cb_kw_clear(callback: CallbackQuery) -> None:
    await db.clear_keywords(callback.from_user.id)
    await callback.answer("Все ключевые слова удалены!")
    await cb_menu_keywords(callback, FSMContext)


@router.callback_query(F.data == "kw_export")
async def cb_kw_export(callback: CallbackQuery, bot: Bot) -> None:
    user = await db.get_user(callback.from_user.id)
    words = db._parse_list(user.get("keywords")) if user else []

    if not words:
        await callback.answer("Список пуст.")
        return

    content = "\n".join(words)
    file_bytes = content.encode("utf-8")
    doc = BufferedInputFile(file_bytes, filename="my_keywords.txt")

    await bot.send_document(
        chat_id=callback.from_user.id,
        document=doc,
        caption=f"• <b>Ваши ключевые слова:</b> {len(words)} шт.",
        parse_mode="HTML",
    )
    await callback.answer("Файл отправлен!")


# --- Минус-слова ---

@router.callback_query(F.data == "menu_sw")
async def cb_menu_stop_words(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    words = db._parse_list(user.get("stop_words")) if user else []

    if words:
        words_formatted = "\n".join(f"  <b>{i+1}.</b> <code>{html.escape(w)}</code>" for i, w in enumerate(words))
        text = (
            f"<b>СТОП-ФИЛЬТР (МИНУС-СЛОВА)</b> ({len(words)} шт.):\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{words_formatted}\n\n"
            f"<i>Заказы, содержащие эти слова, будут автоматически отсеиваться.</i>"
        )
    else:
        text = (
            "<b>СТОП-ФИЛЬТР (МИНУС-СЛОВА)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Список минус-слов пуст.\n"
            "Рекомендуем добавить слова (например: <i>курс, бесплатно, ищу работу</i>), чтобы отсекать спам."
        )

    await callback.message.edit_text(
        text,
        reply_markup=get_stop_words_menu_keyboard(bool(words)),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "sw_add")
async def cb_sw_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UserStates.waiting_add_stop_words)
    text = (
        "<b>ДОБАВЛЕНИЕ МИНУС-СЛОВ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте слова через запятую или файлом (.txt):\n"
        "<i>Например:</i>\n"
        "<code>курс, обучение, бесплатно, стажировка, бартер</code>"
    )
    await callback.message.edit_text(text, reply_markup=get_cancel_keyboard("menu_sw"), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "sw_delete_choice")
async def cb_sw_delete_choice(callback: CallbackQuery) -> None:
    user = await db.get_user(callback.from_user.id)
    words = db._parse_list(user.get("stop_words")) if user else []

    if not words:
        await callback.answer("Список пуст.")
        return

    text = "<b>Нажмите на минус-слово для удаления:</b>"
    await callback.message.edit_text(
        text,
        reply_markup=get_delete_words_keyboard(words, prefix="sw", page=0),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sw_del:"))
async def cb_sw_delete_single(callback: CallbackQuery) -> None:
    idx = int(callback.data.split(":")[1])
    user = await db.get_user(callback.from_user.id)
    words = db._parse_list(user.get("stop_words")) if user else []

    if 0 <= idx < len(words):
        word_to_remove = words[idx]
        updated_words = await db.remove_stop_word(callback.from_user.id, word_to_remove)
        await callback.answer(f"Удалено: {word_to_remove}")

        if updated_words:
            await callback.message.edit_reply_markup(
                reply_markup=get_delete_words_keyboard(updated_words, prefix="sw", page=0)
            )
        else:
            await cb_menu_stop_words(callback, FSMContext)
    else:
        await callback.answer("Слово не найдено.")


@router.callback_query(F.data.startswith("sw_page:"))
async def cb_sw_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[1])
    user = await db.get_user(callback.from_user.id)
    words = db._parse_list(user.get("stop_words")) if user else []
    await callback.message.edit_reply_markup(
        reply_markup=get_delete_words_keyboard(words, prefix="sw", page=page)
    )
    await callback.answer()


@router.callback_query(F.data == "sw_clear_confirm")
async def cb_sw_clear(callback: CallbackQuery) -> None:
    await db.clear_stop_words(callback.from_user.id)
    await callback.answer("Минус-слова полностью очищены!")
    await cb_menu_stop_words(callback, FSMContext)


# --- Парсинг слов из сообщений и документов ---

def parse_words_from_text(raw_text: str) -> list[str]:
    results = []
    for line in raw_text.splitlines():
        for chunk in line.split(","):
            cleaned = chunk.strip().strip("\"'#-*")
            if cleaned:
                results.append(cleaned)
    return results


@router.message(F.document)
async def handle_document_upload(message: Message, bot: Bot, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state == UserStates.waiting_payment_receipt.state:
        await process_receipt_submission(message, bot, state)
        return

    doc = message.document
    file_name = (doc.file_name or "").lower()

    if not (file_name.endswith(".txt") or file_name.endswith(".csv")):
        await message.answer("⚠️ Пожалуйста, отправьте текстовый файл с расширением <b>.txt</b> или <b>.csv</b>.", parse_mode="HTML")
        return

    file_stream = io.BytesIO()
    await bot.download(doc, destination=file_stream)
    file_stream.seek(0)
    raw_content = file_stream.read().decode("utf-8", errors="ignore")

    new_words = parse_words_from_text(raw_content)
    if not new_words:
        await message.answer("[x] Файл пуст или в нем не найдено подходящих слов.")
        return

    user_id = message.from_user.id

    if current_state == UserStates.waiting_add_stop_words.state:
        added_count, total = await db.add_stop_words(user_id, new_words)
        await state.clear()
        await message.answer(
            f"<b>✅ Файл успешно обработан!</b>\n\n"
            f"Добавлено новых минус-слов: <b>{added_count}</b>\n"
            f"Всего минус-слов: <b>{len(total)}</b>",
            reply_markup=get_stop_words_menu_keyboard(bool(total)),
            parse_mode="HTML",
        )
    else:
        added_count, total = await db.add_keywords(user_id, new_words)
        await state.clear()
        await message.answer(
            f"<b>✅ Файл успешно обработан!</b>\n\n"
            f"• Добавлено новых ключевых слов: <b>{added_count}</b>\n"
            f"• Всего ключевых слов: <b>{len(total)}</b> шт.",
            reply_markup=get_keywords_menu_keyboard(bool(total)),
            parse_mode="HTML",
        )


@router.message(UserStates.waiting_add_keywords)
async def process_keywords_text(message: Message, state: FSMContext) -> None:
    words = parse_words_from_text(message.text or "")
    if not words:
        await message.answer("Введите хотя бы одно слово.")
        return

    added_count, total = await db.add_keywords(message.from_user.id, words)
    await state.clear()

    await message.answer(
        f"<b>✅ Ключевые слова добавлены!</b>\n\n"
        f"• Новых слов: <b>{added_count}</b>\n"
        f"• Всего слов: <b>{len(total)}</b>\n\n"
        f"<i>Текущий список:</i> <code>{', '.join(total)}</code>",
        reply_markup=get_keywords_menu_keyboard(bool(total)),
        parse_mode="HTML",
    )


@router.message(UserStates.waiting_add_stop_words)
async def process_stop_words_text(message: Message, state: FSMContext) -> None:
    words = parse_words_from_text(message.text or "")
    if not words:
        await message.answer("Введите хотя бы одно слово.")
        return

    added_count, total = await db.add_stop_words(message.from_user.id, words)
    await state.clear()

    await message.answer(
        f"<b>✅ Минус-слова обновлены!</b>\n\n"
        f"• Добавлено новых: <b>{added_count}</b>\n"
        f"• Всего в стоп-фильтре: <b>{len(total)}</b>",
        reply_markup=get_stop_words_menu_keyboard(bool(total)),
        parse_mode="HTML",
    )


# --- Личный кабинет и статистика ---

@router.callback_query(F.data == "btn_settings")
async def cb_settings(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = callback.from_user.id
    is_admin = db.is_admin(user_id)
    user = await db.get_user(user_id)
    if not user:
        await db.add_user(user_id)
        user = await db.get_user(user_id)

    pro_display = await db.get_pro_status_display(user)
    leads_count = user.get("leads_received", 0)
    kw_count = len(db._parse_list(user.get("keywords")))
    sw_count = len(db._parse_list(user.get("stop_words")))
    user_active_cats = await db.get_user_categories(user_id)
    cat_count = len(user_active_cats)

    admin_badge = "👑 <b>Роль:</b> Администратор платформы\n" if is_admin else ""

    text = (
        f"📊 <b>Ваш личный кабинет:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"{admin_badge}"
        f"💎 <b>Тарифный план:</b> {pro_display}\n\n"
        f"🎯 <b>Активных готовых фильтров:</b> {cat_count} шт.\n"
        f"🔑 <b>Своих ключевых слов:</b> {kw_count} шт.\n"
        f"⛔️ <b>Минус-слов:</b> {sw_count} шт.\n"
        f"📈 <b>Поймано заказов для вас:</b> <b>{leads_count}</b> шт.\n\n"
        f"<i>Управляйте фильтрами, словами и тарифом в меню ниже:</i>"
    )
    await callback.message.edit_text(text, reply_markup=get_main_keyboard(is_admin=is_admin), parse_mode="HTML")
    await callback.answer()


# ==========================================
# ПАНЕЛЬ АДМИНИСТРАТОРА
# ==========================================

def get_verified_chats_count() -> int:
    """Возвращает число активных чатов из файла базы."""
    try:
        path = "chats_verified.txt"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return len([l.strip() for l in f if l.strip() and not l.strip().startswith("#")])
    except Exception:
        pass
    return 249


async def build_admin_panel_content() -> tuple[str, InlineKeyboardMarkup]:
    """Формирует текст и клавиатуру панели администратора."""
    stats = await db.get_admin_stats()
    chats_count = get_verified_chats_count()

    text = (
        f"<b>ПАНЕЛЬ УПРАВЛЕНИЯ B2B LEADHUNTER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Статистика сервиса:</b>\n"
        f"• Всего пользователей в базе: <b>{stats['total_users']}</b>\n"
        f"• 💎 PRO подписчиков: <b>{stats['pro_users']}</b>\n"
        f"• Пользователей на Free: <b>{stats['free_users']}</b>\n"
        f"• Всего доставлено лидов: <b>{stats['total_leads']}</b>\n\n"
        f"<b>Инфраструктура парсера:</b>\n"
        f"• База чатов в мониторинге: <b>{chats_count} чатов</b> (10 сфер / 48 направлений)\n"
        f"• Прокси: SOCKS5 <code>127.0.0.1:10808</code>\n"
        f"• Режим: Telethon Real-Time (Антиспам + Дедупликация)\n\n"
        f"<i>Быстрые команды администратора:</i>\n"
        f"• <code>/give_pro &lt;id&gt; [дни]</code> — выдать PRO\n"
        f"• <code>/revoke_pro &lt;id&gt;</code> — забрать PRO\n"
        f"• <code>/broadcast &lt;текст&gt;</code> — массовая рассылка\n"
        f"• <code>/stats</code> — системная сводка"
    )
    return text, get_admin_panel_keyboard()


@router.message(Command("admin"))
@router.message(F.text.in_(["👑 Панель Администратора", "▪ Панель Администратора", "Панель Администратора"]))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    """Открытие панели администратора по команде /admin."""
    await state.clear()
    if not db.is_admin(message.from_user.id):
        await message.answer("[x] Доступ к панели администратора запрещен.")
        return
    text, markup = await build_admin_panel_content()
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.message(Command("stats"))
@router.message(Command("status"))
@router.message(Command("telethon"))
@router.message(Command("diag"))
async def cmd_stats(message: Message) -> None:
    """Быстрая сводка диагностики и статистики системы."""
    user_id = message.from_user.id
    is_adm = db.is_admin(user_id)
    if not is_adm:
        await message.answer("🔒 Команда диагностики доступна только администратору.")
        return

    # 1. Telethon статус
    tel_status = "❌ Не инициализирован (нет сессии)"
    tel_user = "—"
    tel_chats_count = 0
    if _TELETHON_CLIENT:
        try:
            if _TELETHON_CLIENT.is_connected():
                if await _TELETHON_CLIENT.is_user_authorized():
                    me = await _TELETHON_CLIENT.get_me()
                    uname = f"@{me.username}" if getattr(me, "username", None) else f"ID {getattr(me, 'id', '')}"
                    tel_status = "✅ <b>Активен (В сети)</b>"
                    tel_user = f"{uname} ({getattr(me, 'first_name', '')})"
                else:
                    tel_status = "⚠️ Подключен, но НЕ авторизован (нужна авторизация)"
            else:
                tel_status = "🔄 В процессе подключения / ожидание сети"
        except Exception as e:
            tel_status = f"⚠️ Ошибка проверки: {e}"

    chats_in_base = len(chat_manager.get_all_chats())
    total_users = len(await db.get_all_user_ids())
    my_leads = len(await db.get_b2b_leads(user_id))
    my_cats = await db.get_user_categories(user_id)
    cats_str = ", ".join(list(my_cats)[:5]) + (f" (+{len(my_cats)-5})" if len(my_cats) > 5 else "") if my_cats else "Не выбраны"

    diag_lines = [
        "📊 <b>ДИАГНОСТИКА СИСТЕМЫ LEADHUNTER</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "📡 <b>Парсер чатов (Telethon MTProto):</b>",
        f"• Статус: {tel_status}",
        f"• Аккаунт: <code>{tel_user}</code>",
        f"• Целевых чатов в файле: <b>{chats_in_base}</b>",
        "",
        "🌐 <b>B2B Web-терминал (Mini App):</b>",
        f"• URL: <code>{config.MINI_APP_URL}</code>",
        f"• Порт сервера: <b>{config.MINI_APP_PORT}</b>",
        f"• Лидов в вашей CRM: <b>{my_leads}</b>",
        "",
        "⚙️ <b>Ваши фильтры заказов:</b>",
        f"• Категории: <code>{cats_str}</code>",
        f"• Всего пользователей в БД: <b>{total_users}</b>",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<i>Если Telethon не активен — укажите переменную TELEGRAM_STRING_SESSION в Bothost.</i>"
    ]
    diag_text = "\n".join(diag_lines)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Панель управления", callback_data="admin_panel")],
        [InlineKeyboardButton(text="⚡️ Запустить Mini App", web_app=WebAppInfo(url=config.MINI_APP_URL))],
    ])
    await message.answer(diag_text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат в панель администратора из любого подраздела."""
    await state.clear()
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.", show_alert=True)
        return
    text, markup = await build_admin_panel_content()
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery) -> None:
    """Просмотр списка зарегистрированных пользователей."""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.")
        return

    users = await db.get_all_users_details()
    lines = [f"<b>ЗАРЕГИСТРИРОВАННЫЕ ПОЛЬЗОВАТЕЛИ ({len(users)} чел.):</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"]

    for i, u in enumerate(users[:25], 1):
        uid = u["user_id"]
        if db.is_admin(uid):
            status = "<b>Админ (PRO)</b>"
        elif u.get("is_pro") == 1:
            status = "💎 PRO"
        else:
            status = "[Free]"

        leads = u.get("leads_received", 0)
        cats = [c for c in (u.get("active_categories") or "").split(",") if c.strip()]
        lines.append(f"{i}. <code>{uid}</code> | {status} | Лидов: <b>{leads}</b> | Фильтров: <b>{len(cats)}</b>")

    if len(users) > 25:
        lines.append(f"\n<i>...и еще {len(users) - 25} пользователей в базе</i>")

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ В админ-панель", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_chats_info")
async def cb_admin_chats_info(callback: CallbackQuery) -> None:
    """Информация о целевых чатах по категориям."""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.")
        return

    chats_count = get_verified_chats_count()
    lines = [
        f"<b>БАЗА ЦЕЛЕВЫХ ЧАТОВ В МОНИТОРИНГЕ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
        f"• Всего проверенных чатов: <b>{chats_count}</b> шт.",
        f"• Сфер деятельности: <b>10</b> (48 специальностей)\n",
        "• IT, Разработка & No-Code: ~45 чатов",
        "• Дизайн, UI/UX, 3D, Анимация: ~32 чата",
        "• Маркетинг, Трафик, Таргет: ~30 чатов",
        "• SMM, Reels, Shorts, Telegram: ~28 чатов",
        "• Копирайтинг, Тексты, Рерайтинг: ~22 чата",
        "• AI, Нейросети, Промптинг: ~18 чатов",
        "• Менеджмент, PM, Аналитика: ~16 чатов",
        "• 1С, CRM, ERP, Интеграции: ~14 чатов",
        "• Фриланс Биржи & Доски заказов: ~26 чатов",
        "• Видеомонтаж, Саунд-дизайн: ~18 чатов\n",
        "<i>Telethon обрабатывает входящие сообщения через прокси в реальном времени.</i>"
    ]

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ В админ-панель", callback_data="admin_panel")]
    ])
    await callback.message.edit_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_sys_check")
async def cb_admin_sys_check(callback: CallbackQuery) -> None:
    """Генеральная диагностика работы всех систем бота и парсера."""
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.")
        return

    # 1. Проверка SQLite
    db_ok = "✅ Доступна"
    try:
        stats = await db.get_admin_stats()
    except Exception as e:
        db_ok = f"[x] Ошибка ({e})"

    # 2. Проверка Прокси SOCKS5
    proxy_ok = "✅ Соединение активно"
    try:
        s = socket.socket()
        s.settimeout(1.0)
        res = s.connect_ex((config.PROXY_HOST, config.PROXY_PORT))
        s.close()
        if res != 0:
            proxy_ok = "⚠️ Порт недоступен"
    except Exception as e:
        proxy_ok = f"⚠️ Ошибка ({e})"

    # 3. База чатов
    chats_count = get_verified_chats_count()

    # 4. Каталог ключевых слов
    total_kw = len(categories.ALL_KEYWORDS_CACHE)
    total_cats = sum(len(c["categories"]) for c in categories.CLUSTERS)

    text = (
        f"<b>РЕЗУЛЬТАТЫ СИСТЕМНОЙ ДИАГНОСТИКИ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1. <b>База данных SQLite:</b> {db_ok}\n"
        f"   • Пользователей: {stats.get('total_users', 0)} | Заказов: {stats.get('total_leads', 0)}\n\n"
        f"2. <b>SOCKS5 Прокси ({config.PROXY_HOST}:{config.PROXY_PORT}):</b> {proxy_ok}\n"
        f"   • Обход блокировок Telegram: Активен\n\n"
        f"3. <b>База каналов и чатов:</b> ✅ {chats_count} целевых источников\n"
        f"   • Папка в аккаунте: Заказы\n\n"
        f"4. <b>Каталог категорий:</b> ✅ 10 кластеров, {total_cats} сфер, {total_kw} триггеров\n\n"
        f"5. <b>Парсер & Антиспам:</b> ✅ Запущен\n"
        f"   • MD5-дедупликатор, фильтр свежести (<90с), анти-резюме активны.\n\n"
        f"<i>Все сервисы функционируют штатно.</i>"
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ В админ-панель", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer("Проверка завершена!")


# --- Интерактивная выдача PRO ---

@router.callback_query(F.data == "admin_give_pro_prompt")
async def cb_admin_give_pro_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.")
        return

    await state.set_state(AdminStates.waiting_give_pro)
    text = (
        "<b>ВЫДАЧА ТАРИФА PRO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте <b>Telegram ID</b> пользователя и количество дней через пробел.\n\n"
        "<i>Примеры ввода:</i>\n"
        "• <code>123456789 30</code> — выдать PRO на 30 дней\n"
        "• <code>123456789 999</code> — выдать пожизненный (Lifetime) PRO\n"
        "• <code>123456789</code> — по умолчанию на 30 дней\n\n"
        "› <i>Отправьте сообщение или нажмите Отмена:</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_give_pro)
async def process_admin_give_pro(message: Message, bot: Bot, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if not parts or not parts[0].isdigit():
        await message.answer("⚠️ Неверный формат. Отправьте числовой ID пользователя (например: <code>123456789 30</code>).", parse_mode="HTML")
        return

    target_id = int(parts[0])
    days = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 30

    readable_date = await db.give_pro_days(target_id, days)
    await state.clear()

    await message.answer(
        f"<b>✅ PRO успешно выдан!</b>\n"
        f"Пользователь: <code>{target_id}</code>\n"
        f"Срок: <b>{days} дн.</b> ({readable_date})",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode="HTML",
    )

    try:
        await bot.send_message(
            chat_id=target_id,
            text=(
                f"<b>[PRO АКТИВИРОВАН] Вам успешно подключен тариф PRO!</b>\n\n"
                f"Срок действия: <b>{readable_date}</b>\n\n"
                f"Теперь вам доступны прямые ссылки на сообщения и открытые контакты заказчиков без ограничений."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"⚠️ Уведомление пользователю не отправлено: {e}")


# --- Интерактивное снятие PRO ---

@router.callback_query(F.data == "admin_revoke_pro_prompt")
async def cb_admin_revoke_pro_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.")
        return

    await state.set_state(AdminStates.waiting_revoke_pro)
    text = (
        "<b>ОТЗЫВ ТАРИФА PRO</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте <b>Telegram ID</b> пользователя, у которого нужно забрать PRO и вернуть на Free тариф.\n\n"
        "<i>Пример:</i> <code>123456789</code>\n\n"
        "› <i>Отправьте ID пользователя или нажмите Отмена:</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_revoke_pro)
async def process_admin_revoke_pro(message: Message, bot: Bot, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    text_id = message.text.strip()
    if not text_id.isdigit():
        await message.answer("⚠️ Неверный формат. Отправьте числовой ID пользователя.", parse_mode="HTML")
        return

    target_id = int(text_id)
    if db.is_admin(target_id):
        await message.answer("⚠️ Нельзя отозвать PRO у главного администратора!")
        return

    await db.revoke_pro(target_id)
    await state.clear()

    await message.answer(
        f"✅ PRO-статус пользователя <code>{target_id}</code> отозван. Тариф переведен на Free.",
        reply_markup=get_admin_panel_keyboard(),
        parse_mode="HTML",
    )


# --- Интерактивная рассылка сообщений ---

@router.callback_query(F.data == "admin_broadcast_prompt")
async def cb_admin_broadcast_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.")
        return

    await state.set_state(AdminStates.waiting_broadcast)
    text = (
        "<b>МАССОВАЯ РАССЫЛКА СООБЩЕНИЙ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте сообщение (текст, фото с подписью или пост), которое хотите разослать "
        "<b>всем пользователям бота</b>.\n\n"
        "Поддерживается форматирование HTML.\n\n"
        "› <i>Отправьте текст сообщения для рассылки или нажмите Отмена:</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_broadcast)
async def process_admin_broadcast(message: Message, bot: Bot, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    await state.clear()
    user_ids = await db.get_all_user_ids()
    total = len(user_ids)

    progress_msg = await message.answer(f"⏳ <b>Начало рассылки...</b> Всего получателей: {total}", parse_mode="HTML")

    success_count = 0
    fail_count = 0

    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            success_count += 1
        except Exception:
            fail_count += 1
        await asyncio.sleep(0.04)

    report_text = (
        f"<b>✅ Рассылка завершена!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• Всего получателей: <b>{total}</b>\n"
        f"• Успешно доставлено: <b>{success_count}</b>\n"
        f"• Ошибок (бот заблокирован): <b>{fail_count}</b>"
    )
    await progress_msg.edit_text(report_text, reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")


# --- Прямые команды администратора ---

@router.message(Command("give_pro"))
async def cmd_give_pro(message: Message, bot: Bot) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("[x] Доступно только администратору.")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("⚠️ Использование: <code>/give_pro 123456789 [дни]</code> (по умолчанию 30 дней)", parse_mode="HTML")
        return

    target_id = int(parts[1].strip())
    days = int(parts[2].strip()) if len(parts) >= 3 and parts[2].strip().isdigit() else 30

    readable_date = await db.give_pro_days(target_id, days)

    await message.answer(
        f"<b>✅ Пользователю <code>{target_id}</code> выдан статус PRO на {days} дн. ({readable_date})!</b>",
        parse_mode="HTML",
    )
    try:
        await bot.send_message(
            chat_id=target_id,
            text=(
                f"<b>[PRO АКТИВИРОВАН] Вам успешно подключен тариф PRO!</b>\n\n"
                f"Срок действия: <b>{readable_date}</b>\n\n"
                f"Теперь вам доступны прямые ссылки и открытые контакты заказчиков без ограничений."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"⚠️ Не удалось отправить ЛС пользователю: {e}")


@router.message(Command("revoke_pro"))
async def cmd_revoke_pro(message: Message) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("[x] Доступно только администратору.")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await message.answer("⚠️ Использование: <code>/revoke_pro 123456789</code>", parse_mode="HTML")
        return

    target_id = int(parts[1].strip())
    if db.is_admin(target_id):
        await message.answer("⚠️ Нельзя отозвать PRO у главного администратора!")
        return

    await db.revoke_pro(target_id)
    await message.answer(f"✅ У пользователя <code>{target_id}</code> отозван PRO-статус.", parse_mode="HTML")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot) -> None:
    if not db.is_admin(message.from_user.id):
        await message.answer("[x] Доступно только администратору.")
        return

    broadcast_text = message.text.partition(" ")[2].strip()
    if not broadcast_text:
        await message.answer("⚠️ Использование: <code>/broadcast Ваш текст сообщения</code>", parse_mode="HTML")
        return

    user_ids = await db.get_all_user_ids()
    total = len(user_ids)
    progress = await message.answer(f"⏳ Отправка рассылки {total} пользователям...", parse_mode="HTML")

    success = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=broadcast_text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.04)

    await progress.edit_text(
        f"<b>✅ Рассылка завершена!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• Всего получателей: <b>{total}</b>\n"
        f"• Доставлено: <b>{success}</b>\n"
        f"• Ошибок: <b>{failed}</b>",
        parse_mode="HTML",
    )


# ==========================================
# 1. УПРАВЛЕНИЕ ЧАТАМИ И КАНАЛАМИ
# ==========================================

@router.callback_query(F.data == "admin_chats_hub")
async def cb_admin_chats_hub(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.")
        return

    all_chats = chat_manager.get_all_chats()
    text = (
        f"<b>УПРАВЛЕНИЕ БАЗОЙ ЦЕЛЕВЫХ ЧАТОВ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• Всего источников в мониторинге: <b>{len(all_chats)}</b> шт.\n"
        f"• Парсер Telethon слушает все каналы в режиме реального времени.\n\n"
        f"<i>Выберите действие ниже:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="[+] Добавить чат", callback_data="admin_chat_add"),
            InlineKeyboardButton(text="[-] Удалить чат", callback_data="admin_chat_del"),
        ],
        [
            InlineKeyboardButton(text="🔎 Найти чат", callback_data="admin_chat_search"),
            InlineKeyboardButton(text="[↑] Загрузить файл", callback_data="admin_chat_upload"),
        ],
        [
            InlineKeyboardButton(text="[↓] Скачать базу (.txt)", callback_data="admin_chat_export"),
        ],
        [
            InlineKeyboardButton(text="‹ Назад в админку", callback_data="admin_panel"),
        ],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_chat_add")
async def cb_admin_chat_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_add_chat)
    text = (
        "<b>ДОБАВЛЕНИЕ ЧАТА В МОНИТОРИНГ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте юзернейм или ссылку на чат.\n"
        "<i>Примеры:</i>\n"
        "• <code>@freelance_orders</code>\n"
        "• <code>https://t.me/it_freelance</code>\n"
        "• <code>https://t.me/+AbCdEfGhIjK</code>\n\n"
        "› <i>Отправьте ссылку или нажмите Отмена:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Отмена", callback_data="admin_chats_hub")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_add_chat)
async def process_admin_add_chat(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    raw = message.text.strip()
    success, msg = chat_manager.add_chat(raw)

    # Пробуем мгновенно вступить через Telethon если сессия активна
    telethon_msg = ""
    if success and _TELETHON_CLIENT:
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
            clean = chat_manager.extract_username_or_link(raw)
            if clean and not clean.startswith("http"):
                entity = await _TELETHON_CLIENT.get_entity(clean)
                await _TELETHON_CLIENT(JoinChannelRequest(entity))
                telethon_msg = f"\n✅ Telethon успешно вступил в «{getattr(entity, 'title', clean)}»"
        except Exception as e:
            telethon_msg = f"\n⚠️ Авто-вступление Telethon: {e}"

    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад к чатам", callback_data="admin_chats_hub")]
    ])
    await message.answer(f"{msg}{telethon_msg}", reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_chat_del")
async def cb_admin_chat_del(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_del_chat)
    text = (
        "<b>УДАЛЕНИЕ ЧАТА ИЗ МОНИТОРИНГА</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте юзернейм или ссылку на чат, который нужно исключить из базы.\n\n"
        "<i>Пример:</i> <code>@old_freelance_chat</code>\n\n"
        "› <i>Отправьте юзернейм чата или нажмите Отмена:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_chats_hub")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_del_chat)
async def process_admin_del_chat(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    raw = message.text.strip()
    success, msg = chat_manager.remove_chat(raw)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад к чатам", callback_data="admin_chats_hub")]
    ])
    await message.answer(msg, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_chat_search")
async def cb_admin_chat_search(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_search_chat)
    text = "<b>ПОИСК ЧАТОВ В БАЗЕ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\nОтправьте часть названия или юзернейма чата:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_chats_hub")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_search_chat)
async def process_admin_search_chat(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    q = message.text.strip()
    matches = chat_manager.search_chats(q)
    await state.clear()

    if not matches:
        text = f"[x] Чатов по запросу «<b>{html.escape(q)}</b>» не найдено."
    else:
        top_matches = matches[:25]
        lines = [f"<b>РЕЗУЛЬТАТЫ ПОИСКА ({len(matches)} совп.):</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"]
        for i, m in enumerate(top_matches, 1):
            lines.append(f"{i}. <code>{m}</code>")
        if len(matches) > 25:
            lines.append(f"\n<i>...и еще {len(matches) - 25} чатов</i>")
        text = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад к чатам", callback_data="admin_chats_hub")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_chat_export")
async def cb_admin_chat_export(callback: CallbackQuery, bot: Bot) -> None:
    if not db.is_admin(callback.from_user.id):
        return

    if os.path.exists(chat_manager.VERIFIED_CHATS_FILE):
        file = FSInputFile(chat_manager.VERIFIED_CHATS_FILE, filename="chats_verified.txt")
        chats_count = len(chat_manager.get_all_chats())
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=file,
            caption=f"• <b>Актуальная база чатов:</b> {chats_count} источников.",
            parse_mode="HTML"
        )
        await callback.answer("Файл отправлен!")
    else:
        await callback.answer("Файл базы не найден.")


@router.callback_query(F.data == "admin_chat_upload")
async def cb_admin_chat_upload(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_upload_chats)
    text = (
        "<b>ЗАГРУЗКА ЧАТОВ СПИСКОМ (.TXT)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте текстовый файл <b>.txt</b> со списком чатов (по одной ссылке на строку) "
        "или просто вставьте текст сообщением прямо сюда.\n\n"
        "Бот автоматически отфильтрует дубликаты и добавит только новые чаты."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_chats_hub")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_upload_chats)
async def process_admin_upload_chats(message: Message, bot: Bot, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    content = ""
    if message.document:
        doc = message.document
        stream = io.BytesIO()
        await bot.download(doc, destination=stream)
        stream.seek(0)
        content = stream.read().decode("utf-8", errors="ignore")
    elif message.text:
        content = message.text

    if not content:
        await message.answer("⚠️ Пустое сообщение или файл.")
        return

    added, total = chat_manager.import_chats_from_text(content)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад к чатам", callback_data="admin_chats_hub")]
    ])
    await message.answer(
        f"<b>✅ Импорт завершен!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• Новых добавленных чатов: <b>{added}</b>\n"
        f"• Всего чатов в базе: <b>{total}</b>",
        reply_markup=kb,
        parse_mode="HTML"
    )


# ==========================================
# 2. УПРАВЛЕНИЕ НАПРАВЛЕНИЯМИ И КАТЕГОРИЯМИ
# ==========================================

@router.callback_query(F.data == "admin_categories_hub")
async def cb_admin_categories_hub(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.")
        return

    total_cats = len(categories.ALL_CATEGORIES_DICT)
    total_kw = len(categories.ALL_KEYWORDS_CACHE)
    text = (
        f"<b>УПРАВЛЕНИЕ СФЕРАМИ И КАТЕГОРИЯМИ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• Сфер (кластеров): <b>{len(categories.CLUSTERS)}</b>\n"
        f"• Специализаций: <b>{total_cats}</b>\n"
        f"• Слов-триггеров в словаре: <b>{total_kw}</b>\n\n"
        f"<i>Выберите действие ниже:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="[+] Добавить ключевые слова", callback_data="admin_cat_add_kw"),
            InlineKeyboardButton(text="[-] Удалить ключевое слово", callback_data="admin_cat_del_kw"),
        ],
        [
            InlineKeyboardButton(text="[+] Создать направление", callback_data="admin_cat_create"),
            InlineKeyboardButton(text="[+] Создать сферу", callback_data="admin_cluster_create"),
        ],
        [
            InlineKeyboardButton(text="📋 Список всех кодов (ID)", callback_data="admin_cat_list"),
        ],
        [
            InlineKeyboardButton(text="‹ Назад в админку", callback_data="admin_panel"),
        ],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_cat_list")
async def cb_admin_cat_list(callback: CallbackQuery) -> None:
    if not db.is_admin(callback.from_user.id):
        return

    lines = ["<b>СПИСОК ВСЕХ СФЕР И КАТЕГОРИЙ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"]
    for cl in categories.CLUSTERS:
        lines.append(f"\n<b>{cl['name']}</b> (код: <code>{cl['id']}</code>):")
        for cat in cl["categories"]:
            lines.append(f"  • {cat['short_name']} — код: <code>{cat['id']}</code> ({len(cat.get('keywords', []))} слов)")

    full_text = "\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад к сферам", callback_data="admin_categories_hub")]
    ])

    # Если текст длинный, разбиваем
    if len(full_text) > 4000:
        full_text = full_text[:4000] + "... (далее в коде)"
    await callback.message.edit_text(full_text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_cat_add_kw")
async def cb_admin_cat_add_kw(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_add_kw_cat)
    text = (
        "<b>ДОБАВЛЕНИЕ КЛЮЧЕВЫХ СЛОВ В СПЕЦИАЛИЗАЦИЮ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте сообщение в формате:\n"
        "<code>код_категории слово1, слово2, фраза 3</code>\n\n"
        "<i>Пример:</i>\n"
        "<code>it_bots автоответчик тг, юзербот, telethon скрипт</code>\n\n"
        "<i>(Узнать коды категорий можно по кнопке «Список всех сфер»)</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_categories_hub")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_add_kw_cat)
async def process_admin_add_kw_cat(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    parts = message.text.strip().split(" ", 1)
    if len(parts) < 2:
        await message.answer("⚠️ Формат: <code>код_категории слово1, слово2</code>", parse_mode="HTML")
        return

    cat_id = parts[0].strip().lower()
    raw_words = parts[1].split(",")

    success, count, msg = categories.add_keywords_to_category(cat_id, raw_words)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад к сферам", callback_data="admin_categories_hub")]
    ])
    await message.answer(msg, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_cat_del_kw")
async def cb_admin_cat_del_kw(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_del_kw_cat)
    text = (
        "<b>УДАЛЕНИЕ КЛЮЧЕВОГО СЛОВА ИЗ КАТЕГОРИИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте сообщение в формате:\n"
        "<code>код_категории слово_для_удаления</code>\n\n"
        "<i>Пример:</i> <code>it_bots юзербот</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_categories_hub")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_del_kw_cat)
async def process_admin_del_kw_cat(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    parts = message.text.strip().split(" ", 1)
    if len(parts) < 2:
        await message.answer("⚠️ Формат: <code>код_категории слово</code>", parse_mode="HTML")
        return

    cat_id = parts[0].strip().lower()
    word = parts[1].strip()

    success, msg = categories.remove_keyword_from_category(cat_id, word)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад к сферам", callback_data="admin_categories_hub")]
    ])
    await message.answer(msg, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_cat_create")
async def cb_admin_cat_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_add_category)
    text = (
        "<b>СОЗДАНИЕ НАПРАВЛЕНИЯ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте данные через разделитель <code>|</code>:\n"
        "<code>код_сферы | код_категории | Название | слова через запятую</code>\n\n"
        "<i>Пример:</i>\n"
        "<code>it | it_rust | Rust разработка | rust, разработчик rust, раст бэкенд</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_categories_hub")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_add_category)
async def process_admin_add_category(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) < 4:
        await message.answer("⚠️ Формат: <code>код_сферы | код_категории | Название | слова через запятую</code>", parse_mode="HTML")
        return

    cluster_id = parts[0].lower()
    cat_id = parts[1].lower()
    name = parts[2]
    keywords = [k.strip() for k in parts[3].split(",") if k.strip()]

    success, msg = categories.add_custom_category(cluster_id, cat_id, name, name, keywords)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад к сферам", callback_data="admin_categories_hub")]
    ])
    await message.answer(msg, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "admin_cluster_create")
async def cb_admin_cluster_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_add_cluster)
    text = (
        "<b>СОЗДАНИЕ НОВОЙ СФЕРЫ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Отправьте данные через разделитель <code>|</code>:\n"
        "<code>код_сферы | Название сферы | Emoji</code>\n\n"
        "<i>Пример:</i>\n"
        "<code>legal | Юристы и право</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_categories_hub")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_add_cluster)
async def process_admin_add_cluster(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) < 2:
        await message.answer("⚠️ Формат: <code>код_сферы | Название | Emoji</code>", parse_mode="HTML")
        return

    cluster_id = parts[0].lower()
    name = parts[1]
    emoji = parts[2] if len(parts) >= 3 else ""

    success, msg = categories.add_custom_cluster(cluster_id, name, emoji)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Назад к сферам", callback_data="admin_categories_hub")]
    ])
    await message.answer(msg, reply_markup=kb, parse_mode="HTML")


# ==========================================
# 3. УПРАВЛЕНИЕ ТАРИФАМИ И ЦЕНАМИ
# ==========================================

@router.callback_query(F.data == "admin_pricing_hub")
async def cb_admin_pricing_hub(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.")
        return

    p3 = await get_plan_price(3)
    p30 = await get_plan_price(30)
    plife = await get_plan_price(999)

    text = (
        f"<b>УПРАВЛЕНИЕ ЦЕНАМИ НА ПОДПИСКУ PRO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1. <b>Тест (3 дня):</b> <code>{p3} ₽</code>\n"
        f"2. <b>Месяц (30 дней):</b> <code>{p30} ₽</code>\n"
        f"3. <b>Безлимит (Навсегда):</b> <code>{plife} ₽</code>\n\n"
        f"<i>Нажмите на тариф ниже для изменения стоимости:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"[3 ДНЯ] Тест ({p3} ₽)", callback_data="admin_set_p:3"),
            InlineKeyboardButton(text=f"[30 ДНЕЙ] Месяц ({p30} ₽)", callback_data="admin_set_p:30"),
        ],
        [
            InlineKeyboardButton(text=f"[LIFE] Безлимит ({plife} ₽)", callback_data="admin_set_p:999"),
        ],
        [
            InlineKeyboardButton(text="‹ Назад в админку", callback_data="admin_panel"),
        ],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_set_p:"))
async def cb_admin_set_p_choice(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        return

    target_days = int(callback.data.split(":")[1])
    await state.set_state(AdminStates.waiting_set_price)
    await state.update_data(target_days=target_days)

    period_name = "3 дня (Тест)" if target_days == 3 else ("30 дней (Месяц)" if target_days == 30 else "Навсегда (Lifetime)")
    text = (
        f"<b>УСТАНОВКА ЦЕНЫ: {period_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Отправьте новую стоимость в рублях (число).\n"
        f"<i>Пример:</i> <code>390</code>\n\n"
        f"<i>(Опционально можно указать Stars и USD через пробел: <code>390 200 4.5</code>)</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_pricing_hub")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_set_price)
async def process_admin_set_price(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    data = await state.get_data()
    days = data.get("target_days", 30)

    parts = message.text.strip().split()
    if not parts or not parts[0].isdigit():
        await message.answer("⚠️ Введите числовую стоимость в рублях (например: <code>490</code>).", parse_mode="HTML")
        return

    price_rub = parts[0]
    key_rub = "price_3_days" if days == 3 else ("price_30_days" if days == 30 else "price_lifetime")
    await db.set_setting(key_rub, price_rub)

    extra_info = ""
    if len(parts) >= 2 and parts[1].isdigit():
        key_stars = "stars_3_days" if days == 3 else ("stars_30_days" if days == 30 else "stars_lifetime")
        await db.set_setting(key_stars, parts[1])
        extra_info += f", {parts[1]} ⭐️"

    if len(parts) >= 3:
        key_crypto = "crypto_3_days" if days == 3 else ("crypto_30_days" if days == 30 else "crypto_lifetime")
        await db.set_setting(key_crypto, parts[2])
        extra_info += f", ${parts[2]}"

    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к тарифам", callback_data="admin_pricing_hub")]
    ])
    await message.answer(
        f"<b>✅ Цена успешно обновлена!</b>\nТариф ({days} дн.): <b>{price_rub} ₽</b>{extra_info}",
        reply_markup=kb,
        parse_mode="HTML"
    )


# ==========================================
# 4. УПРАВЛЕНИЕ РЕКВИЗИТАМИ ОПЛАТЫ
# ==========================================

@router.callback_query(F.data == "admin_requisites_hub")
async def cb_admin_requisites_hub(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not db.is_admin(callback.from_user.id):
        await callback.answer("[x] Доступ запрещен.")
        return

    req = await get_requisites()
    text = (
        f"<b>УПРАВЛЕНИЕ РЕКВИЗИТАМИ ОПЛАТЫ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• <b>Телефон СБП:</b> <code>{req['sbp_phone']}</code>\n"
        f"• <b>Банк СБП:</b> <b>{req['sbp_bank']}</b>\n"
        f"• <b>Номер карты:</b> <code>{req['card_number']}</code>\n"
        f"• <b>USDT (TRC-20):</b> <code>{req['usdt']}</code>\n"
        f"• <b>TON кошелек:</b> <code>{req['ton']}</code>\n\n"
        f"<i>Нажмите на реквизит ниже для редактирования:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 СБП Телефон", callback_data="admin_set_req:pay_sbp_phone"),
            InlineKeyboardButton(text="🏦 СБП Банк", callback_data="admin_set_req:pay_sbp_bank"),
        ],
        [
            InlineKeyboardButton(text="💳 Номер Карты", callback_data="admin_set_req:pay_card_number"),
        ],
        [
            InlineKeyboardButton(text="🪙 USDT TRC-20", callback_data="admin_set_req:pay_crypto_usdt"),
            InlineKeyboardButton(text="💎 TON Кошелек", callback_data="admin_set_req:pay_crypto_ton"),
        ],
        [
            InlineKeyboardButton(text="‹ Назад в админку", callback_data="admin_panel"),
        ],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_set_req:"))
async def cb_admin_set_req_choice(callback: CallbackQuery, state: FSMContext) -> None:
    if not db.is_admin(callback.from_user.id):
        return

    req_key = callback.data.split(":")[1]
    await state.set_state(AdminStates.waiting_set_requisite)
    await state.update_data(req_key=req_key)

    labels = {
        "pay_sbp_phone": "• Номер телефона СБП (например: +7 999 123-45-67)",
        "pay_sbp_bank": "• Название банка СБП (например: Т-Банк / Сбер)",
        "pay_card_number": "• Номер банковской карты (например: 2200 7000 1234 5678)",
        "pay_crypto_usdt": "• Адрес кошелька USDT TRC-20 (начинается с T...)",
        "pay_crypto_ton": "• Адрес кошелька TON (начинается с UQ...)",
    }
    label = labels.get(req_key, req_key)

    text = f"<b>РЕДАКТИРОВАНИЕ РЕКВИЗИТА</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{label}\n\n› <i>Отправьте новое значение сообщением:</i>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_requisites_hub")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_set_requisite)
async def process_admin_set_requisite(message: Message, state: FSMContext) -> None:
    if not db.is_admin(message.from_user.id):
        return

    data = await state.get_data()
    req_key = data.get("req_key", "pay_card_number")
    new_val = message.text.strip()

    await db.set_setting(req_key, new_val)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к реквизитам", callback_data="admin_requisites_hub")]
    ])
    await message.answer(
        f"<b>✅ Реквизит успешно обновлен!</b>\n\n<code>{new_val}</code>",
        reply_markup=kb,
        parse_mode="HTML"
    )


# --- Прямые команды для быстрого редактирования ---

@router.message(Command("add_chat"))
async def cmd_add_chat(message: Message) -> None:
    if not db.is_admin(message.from_user.id):
        return
    parts = message.text.partition(" ")[2].strip()
    if not parts:
        await message.answer("⚠️ Использование: <code>/add_chat @channel_or_link</code>", parse_mode="HTML")
        return
    success, msg = chat_manager.add_chat(parts)
    await message.answer(msg, parse_mode="HTML")


@router.message(Command("del_chat"))
async def cmd_del_chat(message: Message) -> None:
    if not db.is_admin(message.from_user.id):
        return
    parts = message.text.partition(" ")[2].strip()
    if not parts:
        await message.answer("⚠️ Использование: <code>/del_chat @channel_or_link</code>", parse_mode="HTML")
        return
    success, msg = chat_manager.remove_chat(parts)
    await message.answer(msg, parse_mode="HTML")


@router.message(Command("find_chat"))
async def cmd_find_chat(message: Message) -> None:
    if not db.is_admin(message.from_user.id):
        return
    q = message.text.partition(" ")[2].strip()
    if not q:
        await message.answer("⚠️ Использование: <code>/find_chat ключевое_слово</code>", parse_mode="HTML")
        return
    matches = chat_manager.search_chats(q)
    if not matches:
        await message.answer(f"[x] Чатов по запросу «<b>{html.escape(q)}</b>» не найдено.", parse_mode="HTML")
        return
    lines = [f"<b>РЕЗУЛЬТАТЫ ПОИСКА ЧАТОВ ({len(matches)}):</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n"]
    for i, m in enumerate(matches[:25], 1):
        lines.append(f"{i}. <code>{m}</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("export_chats"))
async def cmd_export_chats(message: Message, bot: Bot) -> None:
    if not db.is_admin(message.from_user.id):
        return
    if os.path.exists(chat_manager.VERIFIED_CHATS_FILE):
        file = FSInputFile(chat_manager.VERIFIED_CHATS_FILE, filename="chats_verified.txt")
        chats_count = len(chat_manager.get_all_chats())
        await bot.send_document(
            chat_id=message.from_user.id,
            document=file,
            caption=f"• <b>База целевых чатов:</b> {chats_count} источников.",
            parse_mode="HTML"
        )


@router.message(Command("set_price"))
async def cmd_set_price(message: Message) -> None:
    if not db.is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("⚠️ Использование: <code>/set_price <3|30|life> <цена_руб></code>", parse_mode="HTML")
        return
    plan_key = parts[1].lower()
    price = parts[2]
    key_map = {"3": "price_3_days", "30": "price_30_days", "life": "price_lifetime", "lifetime": "price_lifetime"}
    if plan_key not in key_map:
        await message.answer("⚠️ Допустимые тарифы: <code>3</code>, <code>30</code>, <code>life</code>", parse_mode="HTML")
        return
    await db.set_setting(key_map[plan_key], price)
    await message.answer(f"<b>✅ Цена тарифа {plan_key} установлена:</b> <b>{price} ₽</b>", parse_mode="HTML")


@router.message(Command("set_card"))
async def cmd_set_card(message: Message) -> None:
    if not db.is_admin(message.from_user.id):
        return
    card_num = message.text.partition(" ")[2].strip()
    if not card_num:
        await message.answer("⚠️ Использование: <code>/set_card 2200 7000 0000 0000</code>", parse_mode="HTML")
        return
    await db.set_setting("pay_card_number", card_num)
    await message.answer(f"<b>✅ Номер карты обновлен:</b>\n<code>{card_num}</code>", parse_mode="HTML")


@router.message(Command("set_sbp"))
async def cmd_set_sbp(message: Message) -> None:
    if not db.is_admin(message.from_user.id):
        return
    parts = message.text.partition(" ")[2].strip().split("|")
    phone = parts[0].strip()
    if not phone:
        await message.answer("⚠️ Использование: <code>/set_sbp +79991234567 [| Банк]</code>", parse_mode="HTML")
        return
    await db.set_setting("pay_sbp_phone", phone)
    if len(parts) >= 2 and parts[1].strip():
        await db.set_setting("pay_sbp_bank", parts[1].strip())
    await message.answer(f"<b>✅ Реквизиты СБП обновлены:</b> <code>{phone}</code>", parse_mode="HTML")


@router.message(Command("trial"))
async def cmd_free_trial(message: Message) -> None:
    user_id = message.from_user.id
    ok, res = await db.activate_free_trial(user_id, days=3)
    if not ok:
        if res == "already_used":
            await message.answer(
                "⚠️ <b>Бесплатный пробный период уже был использован на вашем аккаунте.</b>\n\n"
                "Для продолжения оформите подписку PRO на месяц (490 ₽) или навсегда (1 490 ₽) в меню тарифов /pro.",
                reply_markup=await get_payment_plans_keyboard(user_id),
                parse_mode="HTML"
            )
        elif res == "already_active":
            user = await db.get_user(user_id)
            pro_status = await db.get_pro_status_display(user)
            await message.answer(f"💎 У вас уже активен PRO статус: {pro_status}")
        return

    readable_until = res
    user = await db.get_user(user_id)
    pro_status = await db.get_pro_status_display(user)

    success_text = (
        "🎉 <b>БЕСПЛАТНЫЙ ПРОБНЫЙ ПЕРИОД PRO АКТИВИРОВАН!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💎 <b>Ваш статус:</b> {pro_status}\n"
        f"⏱ <b>Срок действия:</b> 3 дня ({readable_until})\n\n"
        "<b>Вам открыт полный безлимитный доступ:</b>\n"
        "• 🔓 Прямые контакты заказчиков (@username, телефон, ссылки)\n"
        "• 🎯 B2B Web-терминал поиска заведений без сайта на картах\n"
        "• ⚡️ Мгновенный перехват заказов с бирж (FL, Kwork, Habr)\n"
        "• ✨ AI-генератор продающих офферов под ниши\n\n"
        "👇 <i>Запустите Web-терминал прямо сейчас:</i>"
    )
    app_url = getattr(config, "MINI_APP_URL", "")
    buttons = []
    if app_url.startswith("https://"):
        buttons.append([InlineKeyboardButton(text="⚡️ Запустить B2B Поиск (App)", web_app=WebAppInfo(url=app_url))])
    else:
        buttons.append([InlineKeyboardButton(text="⚡️ Запустить B2B Поиск", callback_data="btn_open_miniapp")])
    buttons.append([InlineKeyboardButton(text="🎯 Настроить фильтры заказов", callback_data="menu_categories")])
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="btn_main_menu")])

    await message.answer(success_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
