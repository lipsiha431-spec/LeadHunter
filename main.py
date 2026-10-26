"""
main.py — Главная точка входа в Telegram SaaS-парсер лидов и заказов.
Бот (aiogram 3.x) и парсер Telethon работают параллельно в одном цикле asyncio.
"""

import sys
import os
import socket
import asyncio
import logging

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from telethon import TelegramClient
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

import config
import db
import bot as bot_module
import parser as parser_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("MainRunner")


class IPv4AiohttpSession(AiohttpSession):
    """Сессия с принудительным IPv4 для предотвращения сетевых таймаутов в Windows."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connector_init["family"] = socket.AF_INET


async def main() -> None:
    logger.info("Запуск Telegram SaaS-сервиса...")

    # 1. Инициализация базы данных
    await db.init_db()
    logger.info("База данных SQLite подключена.")

    # 2. Инициализация бота aiogram 3.x
    if sys.platform == "win32":
        session = IPv4AiohttpSession()
    else:
        session = AiohttpSession()
    bot_instance = Bot(
        token=config.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    dp.include_router(bot_module.router)

    # 3. Настройка прокси для Telethon при необходимости
    proxy_settings = None
    if config.USE_PROXY:
        try:
            # Автоматическая проверка доступности порта прокси
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(1.0)
            is_proxy_open = False
            try:
                test_sock.connect((config.PROXY_HOST, config.PROXY_PORT))
                is_proxy_open = True
            except Exception:
                pass
            finally:
                test_sock.close()

            # Если порт закрыт, запускаем встроенный автономный xray-прокси
            if not is_proxy_open:
                xray_exe = r"C:\Program Files\FlyFrogLLC\Happ\core\xray.exe"
                xray_cfg = os.path.join(os.path.dirname(__file__), "xray_proxy.json")
                if os.path.exists(xray_exe) and os.path.exists(xray_cfg):
                    import subprocess
                    subprocess.Popen([xray_exe, "-config", xray_cfg], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    await asyncio.sleep(2.0)
                    logger.info("Автоматически запущен локальный прокси-сервер.")

            import socks
            p_type = socks.SOCKS5 if config.PROXY_TYPE == "socks5" else socks.HTTP
            proxy_settings = (p_type, config.PROXY_HOST, config.PROXY_PORT)
            logger.info("Включен прокси %s://%s:%s", config.PROXY_TYPE, config.PROXY_HOST, config.PROXY_PORT)
        except Exception as proxy_err:
            logger.warning("Не удалось настроить прокси: %s", proxy_err)

    # 4. Инициализация Telethon (парсинг чатов)
    client = None
    if config.API_ID and config.API_HASH:
        try:
            from telethon.sessions import StringSession
            session_target = None

            # 1. Проверяем строковую сессию из переменных окружения
            str_session_val = (config.TELEGRAM_STRING_SESSION or "").strip()
            if str_session_val:
                session_target = StringSession(str_session_val)
                logger.info("[Telethon] Загружена сессия из TELEGRAM_STRING_SESSION")

            # 2. Проверяем защищенную сессию session.enc (расшифровывается через BOT_TOKEN)
            if not session_target:
                enc_file = os.path.join(os.path.dirname(__file__), "session.enc")
                if os.path.exists(enc_file):
                    try:
                        import base64, hashlib
                        from cryptography.fernet import Fernet
                        clean_token = (config.BOT_TOKEN or "").strip()
                        keys_to_try = [b"dCdiW2S1arZNtddc3IYbABNTYZBgZ7HOL2LmlFgv-qY="]
                        if clean_token:
                            keys_to_try.insert(0, base64.urlsafe_b64encode(hashlib.sha256(clean_token.encode()).digest()))
                        
                        with open(enc_file, "rb") as ef:
                            enc_data = ef.read().strip()
                        
                        dec_str = None
                        for k in keys_to_try:
                            try:
                                dec_str = Fernet(k).decrypt(enc_data).decode("utf-8").strip()
                                if dec_str:
                                    break
                            except Exception:
                                continue
                        
                        if dec_str:
                            session_target = StringSession(dec_str)
                            logger.info("[Telethon] Успешно расшифрована и загружена сессия из session.enc")
                    except Exception as dec_err:
                        logger.warning("[Telethon] Ошибка расшифровки session.enc: %s", dec_err)

            # 3. Проверяем локальный файл .session_string
            if not session_target:
                local_str_file = os.path.join(os.path.dirname(__file__), ".session_string")
                if os.path.exists(local_str_file):
                    try:
                        with open(local_str_file, "r", encoding="utf-8") as sf:
                            s_data = sf.read().strip()
                        if s_data:
                            session_target = StringSession(s_data)
                            logger.info("[Telethon] Загружена сессия из .session_string")
                    except Exception as sf_err:
                        logger.warning("Ошибка чтения .session_string: %s", sf_err)

            # 4. Файловая сессия по умолчанию
            if not session_target:
                session_target = config.SESSION_NAME

            client = TelegramClient(
                session=session_target,
                api_id=config.API_ID,
                api_hash=config.API_HASH,
                proxy=proxy_settings,
                connection_retries=5,
                retry_delay=5,
                auto_reconnect=True,
            )
            client.flood_sleep_threshold = 60
            parser_module.setup_parser(client=client, bot=bot_instance)
            bot_module.set_telethon_client(client)
        except Exception as tel_init_err:
            logger.warning("Ошибка инициализации Telethon: %s", tel_init_err)
    else:
        logger.warning("[!] Telethon не инициализирован: API_ID или API_HASH не заданы.")

    # Функция запуска Telegram-бота с авто-восстановлением при сетевых сбоях
    async def run_bot():
        while True:
            try:
                bot_info = await bot_instance.get_me()
                logger.info("[OK] Бот @%s запущен. Ссылка: https://t.me/%s", bot_info.username, bot_info.username)
                await bot_module.setup_bot_commands(bot_instance)
                await bot_instance.delete_webhook(drop_pending_updates=True)
                await dp.start_polling(bot_instance)
            except Exception as e:
                logger.warning("Сетевая пауза в Telegram-боте: %s. Авто-переподключение через 5 сек...", e)
                await asyncio.sleep(5.0)

    # Фоновый воркер безопасного вступления в проверенные чаты
    async def background_chat_joiner(client_inst):
        """Фоновое безопасное вступление в проверенные чаты фриланса с вечным Mute."""
        await asyncio.sleep(25)  # Небольшая пауза после старта
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
            from telethon.tl.functions.account import UpdateNotifySettingsRequest
            from telethon.tl.types import InputNotifyPeer, InputPeerNotifySettings
            from telethon.errors import FloodWaitError, UserAlreadyParticipantError
            import chat_manager

            candidates = chat_manager.get_all_chats()
            if not candidates:
                return

            dialogs = await client_inst.get_dialogs(limit=350)
            existing_keys = set()
            for d in dialogs:
                u = getattr(d.entity, "username", None)
                if u:
                    existing_keys.add(u.lower())

            to_join = []
            for c in candidates:
                clean = chat_manager.extract_username_or_link(c)
                if clean and clean.lower() not in existing_keys and not clean.startswith("http"):
                    to_join.append(clean)

            if not to_join:
                logger.info("🎯 [AutoJoiner] Telethon уже состоит во всех проверенных чатах (%d шт.)", len(existing_keys))
                return

            logger.info("🎯 [AutoJoiner] Найдено %d новых проверенных чатов. Запуск плавного вступления...", len(to_join))
            joined = 0
            for target in to_join:
                try:
                    entity = await client_inst.get_entity(target)
                    await client_inst(JoinChannelRequest(entity))
                    try:
                        inp_peer = await client_inst.get_input_entity(entity)
                        await client_inst(UpdateNotifySettingsRequest(
                            peer=InputNotifyPeer(inp_peer),
                            settings=InputPeerNotifySettings(mute_until=2147483647, silent=True)
                        ))
                    except Exception:
                        pass
                    joined += 1
                    logger.info("✅ [AutoJoiner] Вступили в чат @%s (всего новых: %d)", target, joined)
                    # Безопасная пауза 40 секунд между вступлениями во избежание FloodWait
                    await asyncio.sleep(40)
                except FloodWaitError as fwe:
                    logger.warning("⏳ [AutoJoiner] FloodWait от Telegram: пауза %d сек.", fwe.seconds)
                    await asyncio.sleep(fwe.seconds + 5)
                except UserAlreadyParticipantError:
                    pass
                except Exception as join_err:
                    logger.debug("Пропуск чата @%s: %s", target, join_err)
                    await asyncio.sleep(5)
        except Exception as bg_err:
            logger.warning("Ошибка в фоновом авто-джойнере: %s", bg_err)

    # Функция запуска парсера Telethon с защитой от быстрого реконнекта
    async def run_telethon():
        if not client:
            return
        
        from telethon.sessions import StringSession
        is_string_session = isinstance(client.session, StringSession)
        if not is_string_session:
            session_file = f"{config.SESSION_NAME}.session"
            if not os.path.exists(session_file):
                logger.warning(
                    "[!] Файл сессии Telethon (%s) не найден и TELEGRAM_STRING_SESSION не задан. "
                    "Парсер чатов ожидает сессию. Задайте TELEGRAM_STRING_SESSION в Bothost.",
                    session_file
                )
                while True:
                    await asyncio.sleep(60)

        while True:
            try:
                logger.info("Подключение Telethon к чатам Telegram...")
                await client.connect()
                if not await client.is_user_authorized():
                    logger.warning("[!] Telethon: сессия не авторизована. Требуется auth_session.py")
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    await asyncio.sleep(120)
                    continue
                
                try:
                    me = await client.get_me()
                    username_str = f"@{me.username}" if getattr(me, "username", None) else f"ID {getattr(me, 'id', '')}"
                    dialogs = await client.get_dialogs(limit=300)
                    active_chats = [d for d in dialogs if d.is_channel or d.is_group]
                    logger.info(
                        "[OK] Telethon подключен к чатам как %s (%s). Каналов/групп в мониторинге: %d",
                        username_str,
                        getattr(me, "first_name", ""),
                        len(active_chats),
                    )
                except Exception as me_err:
                    logger.info("[OK] Telethon подключен к чатам (%s)", me_err)
                
                # Запускаем фоновое плавное вступление в чаты базы
                asyncio.create_task(background_chat_joiner(client))
                    
                await client.run_until_disconnected()
            except Exception as e:
                logger.warning("[!] Telethon сетевая пауза: %s (повтор через 20 сек)", e)
                try:
                    await client.disconnect()
                except Exception:
                    pass
                await asyncio.sleep(20)

    # Функция запуска веб-сервера Telegram Mini App (B2B Лидогенератор)
    async def run_miniapp():
        try:
            from miniapp.server import create_app
            from miniapp.tunnel import start_tunnel
            from aiogram.types import MenuButtonWebApp, WebAppInfo
            from aiohttp import web

            app = create_app()
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host=config.MINI_APP_HOST, port=config.MINI_APP_PORT)
            await site.start()
            logger.info("[OK] Telegram Mini App запущен на http://%s:%s", config.MINI_APP_HOST, config.MINI_APP_PORT)

            # Обработчик нового URL туннеля
            async def apply_tunnel_url(new_url: str):
                config.MINI_APP_URL = new_url
                try:
                    await bot_instance.set_chat_menu_button(
                        menu_button=MenuButtonWebApp(text="Mini App", web_app=WebAppInfo(url=new_url))
                    )
                    if config.ADMIN_ID:
                        try:
                            await bot_instance.set_chat_menu_button(
                                chat_id=config.ADMIN_ID,
                                menu_button=MenuButtonWebApp(text="Mini App", web_app=WebAppInfo(url=new_url))
                            )
                        except Exception:
                            pass
                    logger.info("Кнопка [Mini App] активирована в Telegram меню: %s", new_url)
                except Exception as btn_err:
                    logger.warning("Не удалось установить chat menu button: %s", btn_err)

            # Синхронная обертка для передачи из туннеля
            def on_url_ready(url: str):
                asyncio.create_task(apply_tunnel_url(url))

            # Если в конфигурации уже задан постоянный продакшн HTTPS URL (домен сервера)
            is_tunnel_domain = any(dom in (config.MINI_APP_URL or "") for dom in ["lhr.life", "serveousercontent.com", "trycloudflare.com", "pinggy.link"])
            has_prod_url = (
                config.MINI_APP_URL
                and config.MINI_APP_URL.startswith("https://")
                and not is_tunnel_domain
            )

            if has_prod_url:
                try:
                    await bot_instance.set_chat_menu_button(
                        menu_button=MenuButtonWebApp(text="🚀 LeadHunter App", web_app=WebAppInfo(url=config.MINI_APP_URL))
                    )
                    if config.ADMIN_ID:
                        try:
                            await bot_instance.set_chat_menu_button(
                                chat_id=config.ADMIN_ID,
                                menu_button=MenuButtonWebApp(text="🚀 LeadHunter App", web_app=WebAppInfo(url=config.MINI_APP_URL))
                            )
                        except Exception:
                            pass
                    logger.info("Используется постоянный URL Mini App: %s", config.MINI_APP_URL)
                except Exception as btn_err:
                    logger.warning("Не удалось установить chat menu button: %s", btn_err)
            else:
                # Запуск автоматического HTTPS туннеля для разработки / прямого доступа
                async def auto_tunnel():
                    try:
                        tunnel_url = await start_tunnel(config.MINI_APP_PORT, on_url_found=on_url_ready)
                        if tunnel_url:
                            await apply_tunnel_url(tunnel_url)
                    except Exception as t_err:
                        logger.warning("Ошибка запуска туннеля: %s", t_err)

                asyncio.create_task(auto_tunnel())

            while True:
                await asyncio.sleep(3600)
        except Exception as e:
            logger.error("Ошибка при работе Mini App сервера: %s", e)

    try:
        await asyncio.gather(
            run_bot(),
            run_telethon(),
            run_miniapp(),
        )
    finally:
        await client.disconnect()
        await bot_instance.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПрограмма остановлена.")
