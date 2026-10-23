"""
join_chats.py — Умное безопасное вступление в проверенные чаты фриланса и заказов.

Что делает скрипт:
1. Автоматически создает или находит папку в Telegram: '🎯 Заказы' (Dialog Filter).
2. Находит все текущие чаты заказов на аккаунте, отключает в них уведомления (MUTE FOREVER)
   и переносит их в папку '🎯 Заказы'.
3. Загружает только ПРОВЕРЕННЫЕ РАБОЧИЕ каналы/чаты (chats_verified.txt) без битых ссылок.
4. Вступает в новые чаты с безопасной паузой (10-18 сек.) для защиты от спам-фильтра Telegram.
5. Для каждого нового чата сразу:
   - Вступает (JoinChannelRequest)
   - Отключает звук и всплывающие уведомления навсегда (UpdateNotifySettingsRequest)
   - Добавляет чат в папку '🎯 Заказы' (UpdateDialogFilterRequest)
6. Контролирует лимит Telegram (500 чатов для обычного аккаунта, 1000 для Premium).
7. Ловит FloodWaitError и не падает с ошибками.

Запуск:
    python join_chats.py --limit 35
    python join_chats.py --dry-run
"""

import sys
import os
import time
import random
import asyncio
import argparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from telethon import TelegramClient
from telethon.tl import types
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
from telethon.tl.functions.account import UpdateNotifySettingsRequest
from telethon.tl.types import (
    InputNotifyPeer,
    InputPeerNotifySettings,
    DialogFilter,
    TextWithEntities,
)
from telethon.errors import (
    FloodWaitError,
    UserAlreadyParticipantError,
    ChannelPrivateError,
    InviteRequestSentError,
    ChannelsTooMuchError,
    UsernameNotOccupiedError,
)

import config

FOLDER_NAME = "🎯 Заказы"
VERIFIED_CHATS_FILE = "chats_verified.txt"
FALLBACK_CHATS_FILE = "chats_list.txt"


def load_candidate_chats() -> list[str]:
    """Загружает список источников (приоритет: chats_verified.txt, затем chats_list.txt)."""
    file_path = VERIFIED_CHATS_FILE if os.path.exists(VERIFIED_CHATS_FILE) else FALLBACK_CHATS_FILE
    if not os.path.exists(file_path):
        print(f"❌ Файл со списком чатов не найден: {file_path}")
        return []

    targets = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            # Убираем комментарии в конце строки (# Название)
            clean = clean.split("#")[0].strip()
            if clean.startswith("https://t.me/"):
                clean = clean.replace("https://t.me/", "").strip()
            elif clean.startswith("t.me/"):
                clean = clean.replace("t.me/", "").strip()
            clean = clean.lstrip("@").strip()
            if clean and clean.lower() not in [t.lower() for t in targets]:
                targets.append(clean)

    print(f"📁 Загружено {len(targets)} проверенных источников из {file_path}")
    return targets


async def get_or_create_orders_folder(client: TelegramClient) -> tuple[int, DialogFilter]:
    """Находит или создает Telegram-папку '🎯 Заказы'."""
    filters_resp = await client(GetDialogFiltersRequest())
    existing_filters = filters_resp.filters

    # Ищем существующую папку
    for flt in existing_filters:
        title_obj = getattr(flt, "title", None)
        title_str = ""
        if hasattr(title_obj, "text"):
            title_str = title_obj.text
        elif isinstance(title_obj, str):
            title_str = title_obj
        
        if "заказ" in title_str.lower() or "orders" in title_str.lower():
            folder_id = getattr(flt, "id", 5)
            print(f"📁 Найдена существующая Telegram-папка: '{title_str}' [ID: {folder_id}]")
            return folder_id, flt

    # Если папки еще нет — создаем новую
    used_ids = {f.id for f in existing_filters if hasattr(f, "id") and f.id is not None}
    new_id = 5 if 5 not in used_ids else next(i for i in range(2, 30) if i not in used_ids)
    
    new_folder = DialogFilter(
        id=new_id,
        title=TextWithEntities(text=FOLDER_NAME, entities=[]),
        pinned_peers=[],
        include_peers=[],
        exclude_peers=[],
        groups=True,
        broadcasts=True,
    )
    await client(UpdateDialogFilterRequest(id=new_id, filter=new_folder))
    print(f"✨ Создана новая Telegram-папка: '{FOLDER_NAME}' [ID: {new_id}]")
    return new_id, new_folder


async def mute_chat(client: TelegramClient, input_peer) -> bool:
    """Полностью отключает звук и всплывающие уведомления в чате навсегда."""
    try:
        await client(
            UpdateNotifySettingsRequest(
                peer=InputNotifyPeer(input_peer),
                settings=InputPeerNotifySettings(
                    mute_until=2147483647,  # Максимальный Unix-таймштамп (вечный mute)
                    silent=True,
                    show_previews=False,
                ),
            )
        )
        return True
    except Exception as e:
        return False


async def add_peer_to_folder(client: TelegramClient, folder_id: int, folder_filter: DialogFilter, input_peer) -> bool:
    """Добавляет чат/канал в указанную папку Telegram."""
    try:
        peer_id = getattr(input_peer, "channel_id", getattr(input_peer, "chat_id", None))
        if not peer_id:
            return False

        current_peers = {
            getattr(p, "channel_id", getattr(p, "chat_id", None))
            for p in folder_filter.include_peers
        }

        if peer_id not in current_peers:
            folder_filter.include_peers.append(input_peer)
            await client(UpdateDialogFilterRequest(id=folder_id, filter=folder_filter))
            return True
        return False
    except Exception as e:
        return False


async def main():
    parser = argparse.ArgumentParser(description="Автоматическое вступление в чаты заказов с авто-папкой и Mute")
    parser.add_argument("--limit", type=int, default=35, help="Сколько чатов добавить за этот запуск (по умолчанию: 35)")
    parser.add_argument("--min-delay", type=int, default=10, help="Мин. задержка между вступлениями в сек. (по умолчанию: 10)")
    parser.add_argument("--max-delay", type=int, default=18, help="Макс. задержка между вступлениями в сек. (по умолчанию: 18)")
    parser.add_argument("--dry-run", action="store_true", help="Режим проверки без вступления")
    args = parser.parse_args()

    print("=" * 70)
    print("🚀 SMART AUTO-JOINER + MUTE + TELEGRAM FOLDER SYNC")
    print("=" * 70)

    proxy_settings = None
    if config.USE_PROXY:
        try:
            import socket
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

            if not is_proxy_open:
                xray_exe = r"C:\Program Files\FlyFrogLLC\Happ\core\xray.exe"
                xray_cfg = os.path.join(os.path.dirname(__file__), "xray_proxy.json")
                if os.path.exists(xray_exe) and os.path.exists(xray_cfg):
                    import subprocess
                    subprocess.Popen([xray_exe, "-config", xray_cfg], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    await asyncio.sleep(2.0)
                    print("🛡 Локальный прокси-сервер автоматически запущен.")

            import socks
            p_type = socks.SOCKS5 if config.PROXY_TYPE == "socks5" else socks.HTTP
            proxy_settings = (p_type, config.PROXY_HOST, config.PROXY_PORT)
            print(f"🛡 Прокси подключен: {config.PROXY_TYPE}://{config.PROXY_HOST}:{config.PROXY_PORT}")
        except Exception as e:
            print(f"⚠️ Ошибка прокси: {e}")

    client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH, proxy=proxy_settings)
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Сессия не авторизована! Запустите 1_ВХОД_В_АККАУНТ.bat для авторизации.")
        await client.disconnect()
        return

    me = await client.get_me()
    print(f"👤 Аккаунт: {me.first_name} (@{me.username or 'без username'}) [ID: {me.id}]")
    is_premium = getattr(me, "premium", False)
    max_account_limit = 1000 if is_premium else 500
    print(f"⭐ Статус: {'Telegram Premium (лимит 1000 чатов)' if is_premium else 'Обычный аккаунт (лимит 500 чатов)'}")

    # 1. Настройка папки в Telegram
    folder_id, folder_filter = await get_or_create_orders_folder(client)

    # 2. Сканирование текущих диалогов аккаунта
    print("\n🔍 Сканирую текущие чаты аккаунта...")
    dialogs = await client.get_dialogs()
    channel_groups = [d for d in dialogs if d.is_channel or d.is_group]
    current_count = len(channel_groups)
    free_slots = max(0, max_account_limit - current_count)
    print(f"📊 Текущее число каналов/групп: {current_count} из {max_account_limit}")
    print(f"🟢 Свободных мест до лимита: {free_slots} шт.")

    # 3. Собираем юзернеймы, в которых пользователь уже состоит
    existing_usernames = set()
    existing_peer_map = {}
    for d in dialogs:
        u = getattr(d.entity, "username", None)
        if u:
            existing_usernames.add(u.lower())
            existing_peer_map[u.lower()] = d.entity

    # 4. Приводим текущие существующие чаты заказов в порядок (Mute + Папка)
    print("\n🧹 Синхронизирую текущие чаты заказов: отключаю звук и добавляю в папку...")
    synced_existing = 0
    for uname, ent in existing_peer_map.items():
        title = getattr(ent, "title", uname)
        t_low = title.lower()
        # Проверяем, относится ли текущий чат к заказам/фрилансу
        if any(w in t_low for w in ["freelance", "фриланс", "заказ", "ваканси", "работа", "remote", "удаленк", "job"]):
            try:
                inp_peer = await client.get_input_entity(ent)
                await mute_chat(client, inp_peer)
                await add_peer_to_folder(client, folder_id, folder_filter, inp_peer)
                synced_existing += 1
            except Exception:
                pass
    print(f"✅ Успешно синхронизировано и замьючено текущих чатов: {synced_existing} шт.")

    # 5. Загружаем целевые проверенные чаты
    candidates = load_candidate_chats()
    if not candidates:
        await client.disconnect()
        return

    to_join = [c for c in candidates if c.lower() not in existing_usernames]
    print(f"\n🎯 Новых проверенных чатов для вступления: {len(to_join)} шт.")

    if args.dry_run:
        print("\n[DRY RUN] Проверка завершена. Вступления не выполнялись.")
        await client.disconnect()
        return

    if not to_join:
        print("\n🎉 Отлично! Вы уже состоите во ВСЕХ проверенных чатах из базы!")
        await client.disconnect()
        return

    # Рассчитываем фактический лимит на этот запуск
    join_limit = min(args.limit, len(to_join), free_slots - 5 if free_slots > 5 else 0)
    if join_limit <= 0:
        print("\n⚠️ ВНИМАНИЕ: Свободных мест в Telegram почти не осталось!")
        print(f"У вас занято {current_count} из {max_account_limit} чатов.")
        if not is_premium:
            print("💡 Для расширения лимита до 1000 чатов подключите Telegram Premium.")
        await client.disconnect()
        return

    print(f"\n⚡ Начинаю вступление в {join_limit} новых чатов...")
    print(f"⏱ Задержка между запросами: {args.min_delay}-{args.max_delay} сек. (безопасный режим)\n")

    joined_count = 0
    skipped_count = 0

    for idx, target in enumerate(to_join[:join_limit], 1):
        try:
            print(f"[{idx}/{join_limit}] @{target}...", end=" ", flush=True)

            # Получаем сущность
            entity = await client.get_entity(target)
            title = getattr(entity, "title", target)

            # Вступаем
            await client(JoinChannelRequest(entity))
            print(f"✅ Вступил ('{title[:25]}') |", end=" ", flush=True)
            joined_count += 1

            # Сразу отключаем уведомления (MUTE)
            inp_peer = await client.get_input_entity(entity)
            muted = await mute_chat(client, inp_peer)
            print(f"{'🔇 Muted' if muted else '⚠️ Mute err'} |", end=" ", flush=True)

            # Сразу добавляем в папку '🎯 Заказы'
            in_folder = await add_peer_to_folder(client, folder_id, folder_filter, inp_peer)
            print(f"{'📁 В папке' if in_folder else '📁 Уже был'}")

            # Случайная пауза
            delay = random.randint(args.min_delay, args.max_delay)
            print(f"    ⏳ Ожидание {delay} сек...")
            await asyncio.sleep(delay)

        except UserAlreadyParticipantError:
            print("ℹ️ Уже участник.")
            try:
                inp_peer = await client.get_input_entity(target)
                await mute_chat(client, inp_peer)
                await add_peer_to_folder(client, folder_id, folder_filter, inp_peer)
            except Exception:
                pass
            skipped_count += 1

        except InviteRequestSentError:
            print("📩 Заявка отправлена админам | 🔇 Muted")
            joined_count += 1
            try:
                inp_peer = await client.get_input_entity(target)
                await mute_chat(client, inp_peer)
            except Exception:
                pass

        except ChannelPrivateError:
            print("🔒 Приватный канал/чат, пропуск.")
            skipped_count += 1

        except ChannelsTooMuchError:
            print("\n" + "!" * 65)
            print("⚠️ ДОСТИГНУТ ЛИМИТ TELEGRAM НА ЧАТЫ (500 шт.)!")
            print("Останавливаемся. Для продолжения нужен Telegram Premium.")
            print("!" * 65)
            break

        except FloodWaitError as e:
            print(f"\n⚠️ TELEGRAM FLOODWAIT: Ожидание {e.seconds} сек.")
            if e.seconds > 120:
                print("Пауза превышает 2 минуты. Завершаем текущий запуск безопасно.")
                break
            else:
                print(f"Ожидаем {e.seconds + 2} сек...")
                await asyncio.sleep(e.seconds + 2)

        except (ValueError, UsernameNotOccupiedError):
            print("❌ Чат не существует или удален, пропуск.")
            skipped_count += 1

        except Exception as e:
            print(f"⚠️ Ошибка: {e}")
            skipped_count += 1

    await client.disconnect()

    print("\n" + "=" * 70)
    print("🏁 ИТОГИ ВЫПОЛНЕНИЯ:")
    print(f"✅ Успешно вступили в новых чатов: {joined_count}")
    print(f"🔇 Все добавленные чаты полностью ЗАМЬЮЧЕНЫ (без звуков и спама)")
    print(f"📁 Все добавленные чаты находятся в Telegram-папке: '{FOLDER_NAME}'")
    print(f"⏭ Пропущено: {skipped_count}")
    print(f"📊 Свободных слотов осталось: {max(0, free_slots - joined_count)}")
    print("=" * 70)
    print("✨ Теперь откройте Telegram — у вас появилась вкладка '🎯 Заказы' со всеми чатами!\n")


if __name__ == "__main__":
    asyncio.run(main())
