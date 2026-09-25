@echo off
chcp 65001 >nul
title Voice Caddy Pro — Ispettore di Progetto Zero Token
color 0A

echo ======================================================================
echo          ⛳ VOICE CADDY PRO — RESUME PROGETTO (ZERO TOKEN)
echo ======================================================================
echo.
echo Scansione deterministica dello stato del progetto in corso...
echo Verifica SafeVault, Database, Git, Dipendenze e Sintassi...
echo.

cd /d "%~dp0"
python -m voice_caddy.core.project_inspector resume

echo.
echo ======================================================================
echo  Report generato con successo! Puoi copiare il testo per qualsiasi IA.
echo ======================================================================
echo.
pause
