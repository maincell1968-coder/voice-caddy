from __future__ import annotations

import os
import json
import urllib.request
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_FILE = DATA_DIR / "telegram_config.json"
USERS_MAP_FILE = DATA_DIR / "telegram_users.json"
ENV_FILE = PROJECT_ROOT / ".env"


class TelegramConfigManager:
    """
    Gestore della configurazione del Bot Telegram e dell'abbinamento chat_id -> user_id.
    Supporta prioritariamente file JSON locale, file .env e variabili d'ambiente di sistema.
    """

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.data_dir / "telegram_config.json"
        self.users_map_file = self.data_dir / "telegram_users.json"

    def get_token(self) -> str:
        """
        Recupera il token Telegram in ordine di priorità:
        1. File telegram_config.json
        2. File .env
        3. Variabile d'ambiente TELEGRAM_BOT_TOKEN
        """
        # 1. telegram_config.json
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    token = data.get("bot_token", "").strip()
                    if token:
                        return token
            except Exception:
                pass

        # 2. .env file
        if ENV_FILE.exists():
            try:
                with open(ENV_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("TELEGRAM_BOT_TOKEN="):
                            token = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if token:
                                return token
            except Exception:
                pass

        # 3. Ambiente di sistema
        return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    def set_token(self, token: str):
        """Salva il token Telegram in formato persistente."""
        token = token.strip()
        data = {}
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data["bot_token"] = token
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def test_token(self, token: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Interroga Telegram API (getMe) per verificare la validità del token.
        Ritorna: (successo, messaggio_o_errore, username_bot)
        """
        bot_token = token or self.get_token()
        if not bot_token:
            return False, "Nessun Token Telegram configurato.", None

        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VoiceCaddy/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("ok"):
                    bot_info = res["result"]
                    username = bot_info.get("username", "")
                    first_name = bot_info.get("first_name", "Bot")
                    return True, f"Connessione riuscita! Bot: @{username} ({first_name})", username
                else:
                    return False, f"Telegram API error: {res.get('description', 'Sconosciuto')}", None
        except Exception as e:
            return False, f"Impossibile contattare Telegram: {e}", None

    # ---------------------------------------------------------
    # Mapping chat_id <-> Voice Caddy user_id
    # ---------------------------------------------------------
    def load_users_map(self) -> Dict[str, Dict[str, Any]]:
        """Carica la mappa chat_id -> {user_id, group_name, first_name, active_course}."""
        if not self.users_map_file.exists():
            return {}
        try:
            with open(self.users_map_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def link_chat_user(
        self,
        chat_id: int | str,
        user_id: str,
        group_name: str,
        first_name: str,
        active_course_name: Optional[str] = "Conero Golf Club"
    ):
        """Associa una chat Telegram a un utente Voice Caddy."""
        mapping = self.load_users_map()
        mapping[str(chat_id)] = {
            "user_id": user_id,
            "group_name": group_name,
            "first_name": first_name,
            "active_course_name": active_course_name or "Conero Golf Club"
        }
        with open(self.users_map_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=4, ensure_ascii=False)

    def get_linked_user(self, chat_id: int | str) -> Optional[Dict[str, Any]]:
        """Ritorna i dati dell'utente associato al chat_id, o None."""
        mapping = self.load_users_map()
        return mapping.get(str(chat_id))

    def set_active_course(self, chat_id: int | str, course_name: str):
        """Aggiorna il campo da golf attivo per la chat."""
        mapping = self.load_users_map()
        cid = str(chat_id)
        if cid in mapping:
            mapping[cid]["active_course_name"] = course_name
        else:
            mapping[cid] = {
                "user_id": "strafatti_stefano_pirani",
                "group_name": "strafatti",
                "first_name": "Stefano",
                "active_course_name": course_name
            }
        with open(self.users_map_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=4, ensure_ascii=False)
