"""
miniapp/tunnel.py — Автоматический HTTPS туннель для Telegram Mini App.
Использует SSH localhost.run (работает без блокировок 22/80/443, в отличие от Cloudflare 1033)
с непрерывным watchdog-мониторингом здоровья туннеля и мгновенным авто-восстановлением.
"""

import os
import re
import sys
import asyncio
import logging
from typing import Optional, Callable
import urllib.request

logger = logging.getLogger("PublicTunnel")

_tunnel_proc: Optional[asyncio.subprocess.Process] = None
_current_url: str = ""
_url_ready_event = asyncio.Event()


def get_current_tunnel_url() -> str:
    return _current_url


async def _check_url_alive(url: str) -> bool:
    """Быстрая проверка доступности туннеля через легкий запрос к logo.png."""
    try:
        loop = asyncio.get_running_loop()
        def _req():
            try:
                check_target = url.rstrip("/") + "/logo.png"
                req = urllib.request.Request(
                    check_target,
                    headers={"User-Agent": "LeadHunter-HealthCheck/1.0"}
                )
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    return resp.status in (200, 301, 302, 304)
            except Exception:
                return False
        return await loop.run_in_executor(None, _req)
    except Exception:
        return False


async def _tunnel_watchdog():
    """Следит за здоровьем публичного URL и перезапускает SSH, если туннель упал."""
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
                    "[!] Публичный туннель %s не отвечает (проверка %s/4)...",
                    _current_url, fail_count
                )
                if fail_count >= 4:
                    logger.warning("[!] Туннель действительно упал после 4 проверок. Перезапуск SSH...")
                    try:
                        _tunnel_proc.terminate()
                    except Exception:
                        pass
                    fail_count = 0


async def _monitor_ssh_tunnel(port: int, on_url_found: Optional[Callable[[str], None]] = None):
    """Фоновый цикл поддержания SSH соединения."""
    global _tunnel_proc, _current_url
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.lhr\.life")

    while True:
        try:
            logger.info("Запуск SSH туннеля для порта %s через localhost.run...", port)
            _tunnel_proc = await asyncio.create_subprocess_exec(
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=15",
                "-o", "ServerAliveCountMax=2",
                "-o", "ExitOnForwardFailure=yes",
                "-o", "TCPKeepAlive=yes",
                "-R", f"80:127.0.0.1:{port}",
                "nokey@localhost.run",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            while _tunnel_proc.returncode is None:
                line_bytes = await _tunnel_proc.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="ignore").strip()

                # Поиск HTTPS URL
                match = url_pattern.search(line)
                if match and match.group(0) != _current_url:
                    _current_url = match.group(0)
                    logger.info("[OK] Публичный HTTPS URL для Mini App готов: %s", _current_url)
                    _url_ready_event.set()
                    if on_url_found:
                        try:
                            on_url_found(_current_url)
                        except Exception as e:
                            logger.warning("Ошибка в on_url_found: %s", e)

            logger.warning("SSH процесс туннеля завершился. Перезапуск через 3 сек...")
        except Exception as err:
            logger.warning("Ошибка SSH туннеля: %s. Повтор через 5 сек...", err)

        await asyncio.sleep(3.0)


async def start_tunnel(port: int = 8080, on_url_found: Optional[Callable[[str], None]] = None) -> str:
    """
    Запускает SSH туннель и возвращает сгенерированный URL.
    """
    global _current_url
    _url_ready_event.clear()
    _current_url = ""

    # Запускаем SSH монитор и сторожевой таймер
    asyncio.create_task(_monitor_ssh_tunnel(port, on_url_found))
    asyncio.create_task(_tunnel_watchdog())

    try:
        await asyncio.wait_for(_url_ready_event.wait(), timeout=20.0)
    except asyncio.TimeoutError:
        logger.warning("Таймаут ожидания URL туннеля")

    return _current_url
