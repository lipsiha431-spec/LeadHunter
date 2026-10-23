"""
miniapp/tunnel.py — Высокоскоростной отказоустойчивый HTTPS туннель для Telegram Mini App.
Использует Serveo (<0.8с отклик) с автоматическим резервным переключением на localhost.run
и непрерывным сторожевым мониторингом (watchdog) через легковесный эндпоинт /ping.
"""

import os
import re
import sys
import asyncio
import logging
from typing import Optional, Callable, List, Dict, Any
import urllib.request

logger = logging.getLogger("PublicTunnel")

_tunnel_proc: Optional[asyncio.subprocess.Process] = None
_current_url: str = ""
_url_ready_event = asyncio.Event()

# Провайдеры туннелей в порядке приоритета:
# 1. Serveo — глобальная сеть, моментальный CDN отклик (<0.8с)
# 2. localhost.run — проверенный резервный SSH провайдер
TUNNEL_PROVIDERS: List[Dict[str, Any]] = [
    {
        "name": "Serveo (High-Speed)",
        "cmd": lambda port: [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "TCPKeepAlive=yes",
            "-R", f"80:127.0.0.1:{port}",
            "serveo.net",
        ],
        "pattern": re.compile(r"https://[a-zA-Z0-9-]+\.serveousercontent\.com"),
    },
    {
        "name": "LocalhostRun (Fallback)",
        "cmd": lambda port: [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "TCPKeepAlive=yes",
            "-R", f"80:127.0.0.1:{port}",
            "nokey@localhost.run",
        ],
        "pattern": re.compile(r"https://[a-zA-Z0-9-]+\.lhr\.life"),
    },
]


def get_current_tunnel_url() -> str:
    return _current_url


async def _check_url_alive(url: str) -> bool:
    """Ультрабыстрая проверка доступности туннеля через /ping (не нагружает сеть)."""
    try:
        loop = asyncio.get_running_loop()
        def _req():
            try:
                check_target = url.rstrip("/") + "/ping"
                req = urllib.request.Request(
                    check_target,
                    headers={"User-Agent": "LeadHunter-HealthCheck/1.0"}
                )
                with urllib.request.urlopen(req, timeout=12.0) as resp:
                    return resp.status in (200, 301, 302, 304)
            except Exception:
                return False
        return await loop.run_in_executor(None, _req)
    except Exception:
        return False


async def _tunnel_watchdog():
    """Следит за здоровьем активного URL и перезапускает туннель только при реальном падении."""
    global _tunnel_proc, _current_url
    fail_count = 0

    while True:
        await asyncio.sleep(25.0)
        if _current_url and _tunnel_proc and _tunnel_proc.returncode is None:
            alive = await _check_url_alive(_current_url)
            if alive:
                fail_count = 0
            else:
                fail_count += 1
                logger.warning(
                    "[!] Публичный туннель %s не ответил на /ping (попытка %s/4)...",
                    _current_url, fail_count
                )
                if fail_count >= 4:
                    logger.warning("[!] Туннель подтвержденно недоступен 4 раза подряд. Перезапуск...")
                    try:
                        _tunnel_proc.terminate()
                    except Exception:
                        pass
                    fail_count = 0


async def _monitor_tunnel_loop(port: int, on_url_found: Optional[Callable[[str], None]] = None):
    """
    Основной цикл поддержания соединения:
    Перебирает провайдеры (Serveo -> LocalhostRun) для обеспечения 100% аптайма.
    """
    global _tunnel_proc, _current_url
    provider_idx = 0

    while True:
        provider = TUNNEL_PROVIDERS[provider_idx % len(TUNNEL_PROVIDERS)]
        provider_name = provider["name"]
        cmd = provider["cmd"](port)
        pattern = provider["pattern"]

        try:
            logger.info("Запуск туннеля [%s] для локального порта %s...", provider_name, port)
            _tunnel_proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            consecutive_lines = 0
            found_for_this_proc = False

            while _tunnel_proc.returncode is None:
                line_bytes = await _tunnel_proc.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="ignore").strip()
                consecutive_lines += 1

                # Поиск публичного HTTPS URL
                match = pattern.search(line)
                if match:
                    new_url = match.group(0)
                    found_for_this_proc = True
                    if new_url != _current_url:
                        _current_url = new_url
                        logger.info("[OK] Публичный HTTPS URL [%s] готов: %s", provider_name, _current_url)
                        _url_ready_event.set()
                        if on_url_found:
                            try:
                                on_url_found(_current_url)
                            except Exception as e:
                                logger.warning("Ошибка в callback on_url_found: %s", e)

            # Если процесс завершился, не успев отдать URL — переключаемся на резервного провайдера
            if not found_for_this_proc:
                logger.warning("Провайдер [%s] не предоставил URL. Переключение на резервный...", provider_name)
                provider_idx += 1
            else:
                logger.warning("Процесс туннеля [%s] завершился. Авто-восстановление через 3 сек...", provider_name)

        except Exception as err:
            logger.warning("Ошибка в туннеле [%s]: %s. Переключение через 3 сек...", provider_name, err)
            provider_idx += 1

        await asyncio.sleep(3.0)


async def start_tunnel(port: int = 8080, on_url_found: Optional[Callable[[str], None]] = None) -> str:
    """
    Запускает туннель и ожидает готовности HTTPS URL.
    """
    global _current_url
    _url_ready_event.clear()
    _current_url = ""

    asyncio.create_task(_monitor_tunnel_loop(port, on_url_found))
    asyncio.create_task(_tunnel_watchdog())

    try:
        await asyncio.wait_for(_url_ready_event.wait(), timeout=20.0)
    except asyncio.TimeoutError:
        logger.warning("Таймаут ожидания первичного URL туннеля (20с)")

    return _current_url
