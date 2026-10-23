"""
run_bot.py — Запуск только Telegram-бота (без парсера чатов).
Работает со 100% стабильностью через принудительный IPv4 (без таймаутов Windows).
"""

import sys
import socket
import asyncio
import logging

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

import config
import db
import bot as bot_module

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("BotOnly")


class IPv4AiohttpSession(AiohttpSession):
    """Сессия с принудительным IPv4 для предотвращения сетевых таймаутов в Windows."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connector_init["family"] = socket.AF_INET


async def main():
    await db.init_db()

    session = IPv4AiohttpSession()
    bot_instance = Bot(
        token=config.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()
    dp.include_router(bot_module.router)

    bot_info = await bot_instance.get_me()
    print("=" * 60)
    print(f"🚀 БОТ УСПЕШНО РАБОТАЕТ!")
    print(f"Ссылка на бота: https://t.me/{bot_info.username}")
    print(f"Откройте Telegram, найдите @{bot_info.username} и нажмите /start")
    print("=" * 60)

    await bot_instance.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot_instance)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен.")
