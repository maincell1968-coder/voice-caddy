@echo off
chcp 65001 >nul
title Voice Caddy Pro — Web Dashboard
color 0B

echo ======================================================================
echo          ⛳ VOICE CADDY PRO — APPLICAZIONE LOCALE
echo ======================================================================
echo.
cd /d "%~dp0"
python -m streamlit run app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ATTENZIONE] Si è verificato un errore durante l'avvio.
    pause
)
