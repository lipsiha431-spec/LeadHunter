"""
auth_session.py — Однократная авторизация аккаунта Telethon в Telegram.
Запрашивает номер телефона и код подтверждения из Telegram (вводится один раз).
После этого сессия сохраняется в файл lead_parser_session.session навсегда.
"""

import sys
import os
import asyncio
from telethon import TelegramClient
import config

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

async def main():
    print("=" * 65)
    print("🔐 АВТОРИЗАЦИЯ TELEGRAM-АККАУНТА (TELETHON)")
    print("=" * 65)

    proxy_settings = None
    if config.USE_PROXY:
        try:
            import socks
            p_type = socks.SOCKS5 if config.PROXY_TYPE == "socks5" else socks.HTTP
            proxy_settings = (p_type, config.PROXY_HOST, config.PROXY_PORT)
            print(f"🛡 Используется локальный прокси: {config.PROXY_TYPE}://{config.PROXY_HOST}:{config.PROXY_PORT}")
        except Exception as e:
            print(f"⚠️ Ошибка прокси: {e}")

    client = TelegramClient(
        session=config.SESSION_NAME,
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        proxy=proxy_settings,
    )

    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"\n✅ Аккаунт УЖЕ успешно авторизован!")
        print(f"👤 Имя: {me.first_name} {me.last_name or ''}")
        print(f"📱 Username: @{me.username or 'без username'}")
        print(f"🆔 ID: {me.id}")
        print("Файл сессии готов к работе. Повторный вход не требуется!")
        await client.disconnect()
        return

    print("\n📲 Для первого входа введите номер телефона (в формате +79991234567):")
    await client.start()

    me = await client.get_me()
    print("\n" + "=" * 65)
    print(f"🎉 АВТОРИЗАЦИЯ УСПЕШНО ЗАВЕРШЕНА!")
    print(f"👤 Имя: {me.first_name} {me.last_name or ''}")
    print(f"📱 Username: @{me.username or 'без username'}")
    print(f"🆔 ID: {me.id}")
    print(f"💾 Сессия сохранена в {config.SESSION_NAME}.session")
    print("=" * 65)
    print("Теперь можно запускать join_chats.py и main.py без повторных подтверждений!\n")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
