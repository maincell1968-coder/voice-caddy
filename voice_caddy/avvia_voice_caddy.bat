@echo off
chcp 65001 >nul
title Voice Caddy Pro — Web Dashboard
color 0B

echo ======================================================================
echo          ⛳ VOICE CADDY PRO — APPLICAZIONE LOCALE
echo ======================================================================
echo.
echo Avvio della Dashboard Web sul tuo PC...
echo In questo modo l'app si collegherà direttamente al tuo Ollama locale!
echo.

cd /d "%~dp0"
python -m streamlit run app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ATTENZIONE] Si è verificato un errore durante l'avvio.
    pause
)
