@echo off
chcp 65001 >nul
title Voice Caddy Pro — Backup SafeVault
color 0A

echo ======================================================================
echo          ⛳ VOICE CADDY PRO — PROCEDURA DI BACKUP SICURO
echo ======================================================================
echo.

cd /d "%~dp0"
python backup_voice_caddy.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRORE] Il backup ha riscontrato un problema.
    pause
) else (
    echo.
    echo Backup terminato con successo.
    pause
)
