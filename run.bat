@echo off
cd /d "%~dp0"
chcp 65001 > nul
title Telegram Lead and Order Hunter
echo ===================================================
echo   Telegram Lead and Order Hunter
echo ===================================================
echo.
python main.py
echo.
pause
