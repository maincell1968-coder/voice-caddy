"""
Admin Inbox Manager (Voice Caddy Pro)
====================================
Gestisce l'invio, la ricezione, la memorizzazione persistente e la notifica
dei messaggi inviati dagli utenti all'Amministratore di Sistema (Stefano Pirani).
"""

from __future__ import annotations

import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MESSAGES_FILE = DATA_DIR / "admin_messages.json"


class AdminMessage(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:8]}")
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%d/%m/%Y %H:%M"))
    sender_user_id: str
    sender_name: str
    sender_contact: str = ""  # Email o recapito telefonico
    category: str = "Assistenza / Supporto Tecnico"
    subject: str
    body: str
    is_read: bool = False


class AdminInboxManager:
    """
    Gestore della casella messaggi dell'Amministratore di Sistema.
    Memorizza i messaggi su JSON dedicato e invia alert in tempo reale su Telegram.
    """

    def __init__(self, data_file: Path = MESSAGES_FILE):
        self.data_file = Path(data_file)
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file()

    def _ensure_file(self):
        if not self.data_file.exists():
            try:
                with open(self.data_file, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=4, ensure_ascii=False)
            except Exception:
                pass

    def _load_messages(self) -> List[Dict[str, Any]]:
        self._ensure_file()
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_messages(self, messages: List[Dict[str, Any]]) -> bool:
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(messages, f, indent=4, ensure_ascii=False)
            return True
        except Exception:
            return False

    def send_message(
        self,
        sender_user_id: str,
        sender_name: str,
        sender_contact: str,
        subject: str,
        body: str,
        category: str = "Assistenza / Supporto Tecnico"
    ) -> Tuple[bool, str]:
        """
        Invia e salva un messaggio per l'amministratore, inviando una notifica Telegram in tempo reale.
        """
        if not subject.strip() or not body.strip():
            return False, "Oggetto e testo del messaggio sono obbligatori."

        msg = AdminMessage(
            sender_user_id=sender_user_id,
            sender_name=sender_name,
            sender_contact=sender_contact.strip(),
            category=category.strip(),
            subject=subject.strip(),
            body=body.strip(),
            is_read=False
        )

        messages = self._load_messages()
        messages.insert(0, msg.model_dump())
        saved = self._save_messages(messages)

        if not saved:
            return False, "Impossibile salvare il messaggio nell'archivio."

        # Invia notifica Telegram all'amministratore (Stefano Pirani)
        try:
            from core.telegram_config import TelegramConfigManager
            tg_mgr = TelegramConfigManager()
            alert_text = (
                f"📬 <b>Nuovo Messaggio da {sender_name}!</b>\n\n"
                f"🏷️ <b>Categoria:</b> {category}\n"
                f"📌 <b>Oggetto:</b> {subject}\n"
                f"📞 <b>Recapito:</b> {sender_contact or 'Nessun recapito indicato'}\n\n"
                f"📝 <b>Messaggio:</b>\n{body}\n\n"
                f"<i>Visualizzabile nella Casella Amministratore su Voice Caddy Pro.</i>"
            )
            tg_mgr.notify_admin(alert_text)
        except Exception:
            pass

        return True, "Messaggio recapitato con successo all'Amministratore!"

    def get_messages(self, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Ritorna l'elenco dei messaggi, opzionalmente solo i non letti."""
        messages = self._load_messages()
        if unread_only:
            return [m for m in messages if not m.get("is_read", False)]
        return messages

    def get_unread_count(self) -> int:
        """Ritorna il conteggio dei messaggi non letti."""
        messages = self._load_messages()
        return sum(1 for m in messages if not m.get("is_read", False))

    def mark_as_read(self, message_id: str) -> bool:
        """Contrassegna un messaggio come letto."""
        messages = self._load_messages()
        found = False
        for m in messages:
            if m.get("id") == message_id:
                m["is_read"] = True
                found = True
                break
        if found:
            return self._save_messages(messages)
        return False

    def mark_all_as_read(self) -> bool:
        """Contrassegna tutti i messaggi come letti."""
        messages = self._load_messages()
        for m in messages:
            m["is_read"] = True
        return self._save_messages(messages)

    def delete_message(self, message_id: str) -> bool:
        """Elimina un messaggio dall'archivio."""
        messages = self._load_messages()
        new_list = [m for m in messages if m.get("id") != message_id]
        if len(new_list) != len(messages):
            return self._save_messages(new_list)
        return False
