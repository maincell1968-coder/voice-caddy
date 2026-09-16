@echo off
chcp 65001 >nul
title Voice Caddy Pro — Telegram Bot Server
color 0A

echo ======================================================================
echo          ⛳ VOICE CADDY PRO — TELEGRAM BOT SERVER
echo ======================================================================
echo.
echo Avvio in corso del Bot di ascolto Telegram per Voice Caddy...
echo I giocatori possono inviare note vocali o messaggi durante la partita.
echo.

cd /d "%~dp0voice_caddy"

python -m core.telegram_bot

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ATTENZIONE] Il bot si è arrestato con codice %ERRORLEVEL%.
    pause
)
