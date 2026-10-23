"""
miniapp/tunnel.py — Чистый HTTPS туннель для Telegram Mini App без сторонних предупреждений.
Использует SSH localhost.run (отдает контент напрямую БЕЗ экранов-предупреждений 'Browser Warning')
с легковесным watchdog-мониторингом через /ping и авто-восстановлением.
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
    """Ультралегкая проверка доступности туннеля через /ping (50 байт, не нагружает канал)."""
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
    """Следит за здоровьем публичного URL и перезапускает SSH только если туннель реально умер 6 раз подряд."""
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
                    "[!] Туннель %s не ответил на /ping (%s/6)...",
                    _current_url, fail_count
                )
                if fail_count >= 6:
                    logger.warning("[!] Туннель недоступен 6 проверок подряд. Перезапуск соединения...")
                    try:
                        _tunnel_proc.terminate()
                    except Exception:
                        pass
                    fail_count = 0


async def _monitor_ssh_tunnel(port: int, on_url_found: Optional[Callable[[str], None]] = None):
    """
    Фоновый цикл поддержания соединения через localhost.run.
    Прямой туннель: никаких предупреждений 'Browser Warning' и заглушек.
    """
    global _tunnel_proc, _current_url
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.lhr\.life")

    while True:
        try:
            logger.info("Запуск чистого туннеля для порта %s через localhost.run...", port)
            _tunnel_proc = await asyncio.create_subprocess_exec(
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=15",
                "-o", "ServerAliveCountMax=4",
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
                    logger.info("[OK] Публичный чистый HTTPS URL для Mini App готов: %s", _current_url)
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

    asyncio.create_task(_monitor_ssh_tunnel(port, on_url_found))
    asyncio.create_task(_tunnel_watchdog())

    try:
        await asyncio.wait_for(_url_ready_event.wait(), timeout=25.0)
    except asyncio.TimeoutError:
        logger.warning("Таймаут ожидания первичного URL туннеля")

    return _current_url
