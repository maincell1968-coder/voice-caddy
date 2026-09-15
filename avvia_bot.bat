@echo off
chcp 65001 >nul
title Voice Caddy Pro — Telegram Bot Server
color 0A

echo ======================================================================
echo          ⛳ VOICE CADDY PRO — TELEGRAM BOT SERVER
echo ======================================================================
echo.
cd /d "%~dp0"

python -m core.telegram_bot

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ATTENZIONE] Il bot si è arrestato con codice %ERRORLEVEL%.
    pause
)
