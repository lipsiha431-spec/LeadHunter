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

    # 2. Инициализация бота aiogram 3.x с IPv4
    session = IPv4AiohttpSession()
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

    # 4. Инициализация Telethon
    client = TelegramClient(
        session=config.SESSION_NAME,
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        proxy=proxy_settings,
        connection_retries=3,
        retry_delay=5,
        auto_reconnect=False,
    )
    parser_module.setup_parser(client=client, bot=bot_instance)
    bot_module.set_telethon_client(client)

    # Функция запуска Telegram-бота
    async def run_bot():
        try:
            bot_info = await bot_instance.get_me()
            logger.info("[OK] Бот @%s запущен. Ссылка: https://t.me/%s", bot_info.username, bot_info.username)
            await bot_module.setup_bot_commands(bot_instance)
            await bot_instance.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot_instance)
        except Exception as e:
            logger.error("Ошибка при работе бота: %s", e)

    # Функция запуска парсера Telethon с защитой от быстрого реконнекта
    async def run_telethon():
        while True:
            try:
                logger.info("Подключение Telethon к чатам Telegram...")
                await client.connect()
                if not await client.is_user_authorized():
                    logger.warning("[!] Telethon: сессия не авторизована. Требуется auth_session.py")
                    await asyncio.sleep(30)
                    continue
                logger.info("[OK] Telethon подключен к чатам.")
                await client.run_until_disconnected()
            except Exception as e:
                logger.warning("[!] Telethon ожидает стабильной связи: %s (повтор через 15 сек)", e)
                try:
                    await client.disconnect()
                except Exception:
                    pass
                await asyncio.sleep(15)

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
            has_prod_url = (
                config.MINI_APP_URL
                and config.MINI_APP_URL.startswith("https://")
                and "lhr.life" not in config.MINI_APP_URL
            )

            if has_prod_url:
                try:
                    await bot_instance.set_chat_menu_button(
                        menu_button=MenuButtonWebApp(text="[▸] Mini App", web_app=WebAppInfo(url=config.MINI_APP_URL))
                    )
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
