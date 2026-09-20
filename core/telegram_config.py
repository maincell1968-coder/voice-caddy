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


DEFAULT_BOT_TOKEN = "8855332306:AAHd_SH6ei4jv8cY3OzrB2GDWdoV8tHzcRI"
DEFAULT_BOT_USERNAME = "VoiceCaddyGolf_bot"
DEFAULT_ADMIN_CHAT_ID = "7133743757"


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
        3. Streamlit secrets
        4. Variabile d'ambiente TELEGRAM_BOT_TOKEN
        5. Token di default del bot di produzione
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

        # 3. Streamlit secrets
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "TELEGRAM_BOT_TOKEN" in st.secrets:
                tok = str(st.secrets["TELEGRAM_BOT_TOKEN"]).strip()
                if tok:
                    return tok
        except Exception:
            pass

        # 4. Ambiente di sistema
        env_tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if env_tok:
            return env_tok

        # 5. Token predefinito
        return DEFAULT_BOT_TOKEN

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

    def get_bot_username(self) -> str:
        """Recupera l'username del bot se salvato in cache o interrogando Telegram."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("bot_username"):
                        return data["bot_username"]
            except Exception:
                pass
        tok = self.get_token()
        if tok and tok != DEFAULT_BOT_TOKEN:
            ok, _, uname = self.test_token(tok)
            if ok and uname:
                return uname
        return DEFAULT_BOT_USERNAME

    def save_bot_username(self, username: str):
        """Salva l'username del bot nel file config."""
        data = {}
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["bot_username"] = username
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
                    if username:
                        self.save_bot_username(username)
                    return True, f"Connessione riuscita! Bot: @{username} ({first_name})", username
                else:
                    return False, f"Telegram API error: {res.get('description', 'Sconosciuto')}", None
        except Exception as e:
            return False, f"Impossibile contattare Telegram: {e}", None

    # ---------------------------------------------------------
    # Mapping chat_id <-> Voice Caddy user_id
    # ---------------------------------------------------------
    def load_users_map(self) -> Dict[str, Dict[str, Any]]:
        """Carica la mappa chat_id -> {user_id, group_name, first_name, active_course} con persistenza dual-layer e fallback."""
        mapping: Dict[str, Dict[str, Any]] = {}

        # 1. Prova a caricare dal database SQLite (solo in ambiente di produzione)
        if self.data_dir == DATA_DIR:
            try:
                from core.db import PROJECT_ROOT
                import sqlite3
                db_path = PROJECT_ROOT / "voice_caddy.db"
                if db_path.exists():
                    with sqlite3.connect(db_path) as conn:
                        cur = conn.cursor()
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS telegram_user_mappings (
                                chat_id TEXT PRIMARY KEY,
                                user_id TEXT,
                                group_name TEXT,
                                first_name TEXT,
                                active_course_name TEXT,
                                mode TEXT DEFAULT 'training'
                            )
                        """)
                        for row in cur.execute("SELECT chat_id, user_id, group_name, first_name, active_course_name, mode FROM telegram_user_mappings").fetchall():
                            mapping[str(row[0])] = {
                                "user_id": row[1],
                                "group_name": row[2],
                                "first_name": row[3],
                                "active_course_name": row[4],
                                "mode": row[5] or "training"
                            }
            except Exception:
                pass

        # 2. Prova a caricare dal file JSON
        if self.users_map_file.exists():
            try:
                with open(self.users_map_file, "r", encoding="utf-8") as f:
                    file_map = json.load(f)
                    mapping.update(file_map)
            except Exception:
                pass

        # 3. Assicurati che Stefano Pirani (Amministratore) sia associato nel file di produzione
        if self.data_dir == DATA_DIR and not mapping and self.users_map_file == USERS_MAP_FILE:
            mapping[DEFAULT_ADMIN_CHAT_ID] = {
                "user_id": "strafatti_stefano_pirani",
                "group_name": "strafatti",
                "first_name": "Stefano",
                "active_course_name": "Conero Golf Club",
                "mode": "training"
            }
            try:
                with open(self.users_map_file, "w", encoding="utf-8") as f:
                    json.dump(mapping, f, indent=4, ensure_ascii=False)
            except Exception:
                pass

        return mapping

    def link_chat_user(
        self,
        chat_id: int | str,
        user_id: str,
        group_name: str,
        first_name: str,
        active_course_name: Optional[str] = "Conero Golf Club"
    ):
        """Associa una chat Telegram a un utente Voice Caddy sia su file JSON che in SQLite."""
        cid_str = str(chat_id)
        entry = {
            "user_id": user_id,
            "group_name": group_name,
            "first_name": first_name,
            "active_course_name": active_course_name or "Conero Golf Club"
        }
        mapping = self.load_users_map()
        mapping[cid_str] = entry
        try:
            with open(self.users_map_file, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

        # Salva anche in SQLite per persistenza dual-layer (solo in produzione)
        if self.data_dir == DATA_DIR:
            try:
                from core.db import PROJECT_ROOT
                import sqlite3
                db_path = PROJECT_ROOT / "voice_caddy.db"
                with sqlite3.connect(db_path) as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS telegram_user_mappings (
                            chat_id TEXT PRIMARY KEY,
                            user_id TEXT,
                            group_name TEXT,
                            first_name TEXT,
                            active_course_name TEXT,
                            mode TEXT DEFAULT 'training'
                        )
                    """)
                    cur.execute("""
                        INSERT OR REPLACE INTO telegram_user_mappings (chat_id, user_id, group_name, first_name, active_course_name)
                        VALUES (?, ?, ?, ?, ?)
                    """, (cid_str, user_id, group_name, first_name, active_course_name or "Conero Golf Club"))
                    conn.commit()
            except Exception:
                pass

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

    # ---------------------------------------------------------
    # Player Mode (Gara vs Training)
    # ---------------------------------------------------------
    def get_user_mode(self, chat_id: int | str) -> str:
        """
        Ritorna la modalità del giocatore per questa chat:
        'gara' (Regola 4.3 R&A, solo distanze, no consiglio mazza) oppure 'training' (distanza + bastone).
        Default: 'training'.
        """
        mapping = self.load_users_map()
        return mapping.get(str(chat_id), {}).get("mode", "training")

    def set_user_mode(self, chat_id: int | str, mode: str):
        """Imposta la modalità per la chat: 'training' o 'gara' in modo persistente."""
        clean_mode = "gara" if "gara" in str(mode).lower() else "training"
        mapping = self.load_users_map()
        cid = str(chat_id)
        if cid in mapping:
            mapping[cid]["mode"] = clean_mode
        else:
            mapping[cid] = {
                "user_id": "strafatti_stefano_pirani",
                "group_name": "strafatti",
                "first_name": "Stefano",
                "active_course_name": "Conero Golf Club",
                "mode": clean_mode
            }
        with open(self.users_map_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=4, ensure_ascii=False)

    # ---------------------------------------------------------
    # Admin Notifications (Stefano Pirani)
    # ---------------------------------------------------------
    def get_admin_chat_id(self) -> str:
        """
        Recupera il chat_id dell'amministratore (Stefano Pirani):
        1. Da telegram_config.json ("admin_chat_id")
        2. Dalla mappa telegram_users.json (chat associata a Stefano)
        3. Da variabile d'ambiente TELEGRAM_ADMIN_CHAT_ID
        4. Fallback costante DEFAULT_ADMIN_CHAT_ID
        """
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    admin_id = data.get("admin_chat_id")
                    if admin_id:
                        return str(admin_id)
            except Exception:
                pass

        # Cerca nella mappa utenti telegram
        mapping = self.load_users_map()
        for cid, uinfo in mapping.items():
            u_id = uinfo.get("user_id", "")
            if u_id == "strafatti_stefano_pirani" or uinfo.get("first_name", "").lower() == "stefano":
                return str(cid)

        # Variabile d'ambiente
        env_admin = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
        if env_admin:
            return env_admin
        return DEFAULT_ADMIN_CHAT_ID

    def set_admin_chat_id(self, chat_id: int | str):
        """Salva il chat_id dell'amministratore in telegram_config.json."""
        data = {}
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["admin_chat_id"] = str(chat_id)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_chat_id_for_user(self, user_id: str, first_name: Optional[str] = None) -> Optional[str]:
        """Trova il chat_id associato a un determinato user_id (es. 'strafatti_stefano_pirani' o 'Stefano')."""
        mapping = self.load_users_map()
        matches = []
        clean_target = str(user_id or "").strip().lower()
        clean_fn = str(first_name or "").strip().lower()
        for cid, data in mapping.items():
            u_id = str(data.get("user_id", "")).strip().lower()
            fn = str(data.get("first_name", "")).strip().lower()
            if (
                (clean_target and u_id == clean_target)
                or (clean_target and clean_target in u_id)
                or (clean_fn and fn == clean_fn)
                or (clean_target and fn == clean_target)
            ):
                matches.append(str(cid))
        if not matches:
            return None
        # Preferisci sempre l'ID reale di Telegram (numerico a 8+ cifre) o l'ultimo registrato
        for cid in reversed(matches):
            if cid.isdigit() and len(cid) >= 8:
                return cid
        return matches[-1]

    def unlink_user(self, user_id: str) -> bool:
        """Rimuove l'associazione Telegram per un determinato user_id."""
        mapping = self.load_users_map()
        to_remove = [cid for cid, data in mapping.items() if data.get("user_id") == user_id]
        if to_remove:
            for cid in to_remove:
                del mapping[cid]
            with open(self.users_map_file, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=4, ensure_ascii=False)
            if self.data_dir == DATA_DIR:
                try:
                    from core.db import PROJECT_ROOT
                    import sqlite3
                    db_path = PROJECT_ROOT / "voice_caddy.db"
                    with sqlite3.connect(db_path) as conn:
                        cur = conn.cursor()
                        cur.execute("DELETE FROM telegram_user_mappings WHERE user_id = ?", (user_id,))
                        conn.commit()
                except Exception:
                    pass
            return True
        return False

    def send_direct_message(self, chat_id: int | str, text: str) -> Tuple[bool, str]:
        """Invia un messaggio diretto a una specifica chat Telegram."""
        bot_token = self.get_token()
        if not bot_token:
            return False, "Nessun token Telegram configurato."
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": "HTML"
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "VoiceCaddy/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("ok"):
                    return True, "Messaggio inviato con successo allo smartphone!"
                return False, f"Errore Telegram: {res.get('description', 'Sconosciuto')}"
        except Exception as e:
            return False, f"Impossibile inviare messaggio a Telegram: {e}"

    def notify_admin(self, message: str) -> bool:
        """
        Invia una notifica Telegram all'Amministratore (Stefano Pirani).
        Silenzioso e sicuro: non solleva mai eccezioni né blocca l'applicazione se Telegram è offline.
        """
        admin_chat_id = self.get_admin_chat_id()
        if not admin_chat_id:
            return False
        ok, _ = self.send_direct_message(admin_chat_id, message)
        return ok
