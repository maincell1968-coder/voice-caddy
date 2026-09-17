@echo off
chcp 65001 >nul
title Voice Caddy — Rules Academy (Modulo Didattico)
color 0A

echo ======================================================================
echo       🎓 VOICE CADDY — RULES ACADEMY (REGOLE DEL GOLF R&A)
echo ======================================================================
echo.
echo Avvio del Modulo Didattico Standalone sul tuo browser...
echo.

cd /d "%~dp0"
python -m streamlit run golf_rules_module.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ATTENZIONE] Si e' verificato un errore durante l'avvio del modulo.
    pause
)
