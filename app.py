"""
Voice Caddy Pro — Root Launcher & Streamlit Cloud Entry Point
Inoltra l'esecuzione all'applicazione completa in voice_caddy/app.py
garantendo la piena compatibilità sia in locale che sul cloud.
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
VC_DIR = ROOT_DIR / "voice_caddy"

# Inserisce voice_caddy nei path di sistema per consentire tutti gli import (core, data, golf_strategy_ai)
if str(VC_DIR) not in sys.path:
    sys.path.insert(0, str(VC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(1, str(ROOT_DIR))

# Imposta la cartella di lavoro su voice_caddy per preservare i percorsi relativi del database e dei profili SafeVault
try:
    os.chdir(str(VC_DIR))
except Exception:
    pass

# Esegue l'applicazione principale con namespace corretto
app_file = VC_DIR / "app.py"
with open(app_file, "r", encoding="utf-8") as f:
    code = f.read()

app_globals = dict(globals())
app_globals["__file__"] = str(app_file)
exec(compile(code, str(app_file), "exec"), app_globals)
