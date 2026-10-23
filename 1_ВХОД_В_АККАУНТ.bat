@echo off
cd /d "%~dp0"
chcp 65001 > nul
title 1. Авторизация в Telegram (Telethon)
echo ========================================================
echo   1. ПЕРВИЧНЫЙ ВХОД В TELEGRAM-АККАУНТ
echo ========================================================
echo.
python auth_session.py
echo.
pause
