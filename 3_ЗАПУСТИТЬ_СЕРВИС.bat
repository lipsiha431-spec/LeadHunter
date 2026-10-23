@echo off
cd /d "%~dp0"
chcp 65001 > nul
title 3. Запуск Telegram SaaS Lead & Order Hunter
echo ========================================================
echo   3. ЗАПУСК БОТА И ПАРСЕРА ЛИДОВ В РЕАЛЬНОМ ВРЕМЕНИ
echo ========================================================
echo.
python main.py
echo.
pause
