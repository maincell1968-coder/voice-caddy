from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple, Dict, Any

from core.telegram_config import TelegramConfigManager
from core.telegram_bot import VoiceCaddyTelegramBot

import sys
logger = logging.getLogger(__name__)


class TelegramBotBackgroundService:
    """
    Gestore di servizio in background per il Bot Telegram di Voice Caddy Pro.
    Esegue il polling in un thread daemon dedicato, consentendo all'applicazione
    Streamlit di avviare, monitorare o riavviare il bot senza bloccare la UI
    e senza costringere l'utente a gestire manualmente finestre terminale separate.
    """

    _lock = threading.Lock()

    def __init__(self):
        self.config_mgr = TelegramConfigManager()
        self._thread: Optional[threading.Thread] = None
        self._bot: Optional[VoiceCaddyTelegramBot] = None
        self._is_active: bool = False
        self._last_error: Optional[str] = None
        self._start_time: Optional[float] = None
        self._bot_username: Optional[str] = None

    @classmethod
    def get_instance(cls) -> TelegramBotBackgroundService:
        with cls._lock:
            cached = getattr(sys, "_voice_caddy_bot_service", None)
            if cached is not None and isinstance(cached, cls):
                return cached
            instance = cls()
            setattr(sys, "_voice_caddy_bot_service", instance)
            return instance

    def is_alive(self) -> bool:
        """Verifica se il thread del bot è attualmente in esecuzione."""
        if self._thread and self._thread.is_alive() and self._is_active:
            return True
        # Verifica se esiste un thread worker attivo nel runtime (anche da reload precedenti)
        has_running_worker = any(
            t.name == "VoiceCaddy-TelegramBotThread" and t.is_alive()
            for t in threading.enumerate()
        )
        return has_running_worker and self._is_active

    def get_status_info(self) -> Dict[str, Any]:
        """Restituisce informazioni dettagliate sullo stato del server bot."""
        token = self.config_mgr.get_token()
        alive = self.is_alive()
        uname = self._bot_username or self.config_mgr.get_bot_username() or "VoiceCaddyGolf_bot"
        return {
            "is_alive": alive,
            "has_token": bool(token),
            "bot_username": uname,
            "last_error": self._last_error,
            "uptime_seconds": (time.time() - self._start_time) if (alive and self._start_time) else 0
        }

    def start(self, token: Optional[str] = None) -> Tuple[bool, str]:
        """
        Avvia il Bot Telegram in un thread daemon background.
        Ritorna: (successo, messaggio)
        """
        with self._lock:
            if self.is_alive():
                return True, f"Server Bot già attivo e in ascolto su @{self._bot_username or 'VoiceCaddyGolf_bot'}."

            bot_token = token or self.config_mgr.get_token()
            if not bot_token:
                self._last_error = "Nessun token Telegram configurato."
                return False, "Nessun token Telegram trovato. Inseriscilo nella configurazione."

            # Verifica preventiva del token su Telegram
            ok_test, msg_test, uname = self.config_mgr.test_token(bot_token)
            if not ok_test:
                self._last_error = msg_test
                return False, f"Verifica token fallita: {msg_test}"

            self._bot_username = uname or "VoiceCaddyGolf_bot"

            try:
                self._bot = VoiceCaddyTelegramBot(bot_token=bot_token)
                self._is_active = True
                self._last_error = None
                self._start_time = time.time()

                def _run_worker():
                    try:
                        logger.info("Avvio thread worker Telegram Bot...")
                        self._bot.run_polling()
                    except Exception as e:
                        logger.error(f"Errore fatale worker Telegram Bot: {e}")
                        self._last_error = str(e)
                    finally:
                        self._is_active = False
                        logger.info("Thread worker Telegram Bot terminato.")

                self._thread = threading.Thread(
                    target=_run_worker,
                    name="VoiceCaddy-TelegramBotThread",
                    daemon=True
                )
                self._thread.start()

                # Piccola attesa per verificare che il thread sia partito
                time.sleep(0.3)
                if self._thread.is_alive():
                    return True, f"Server Bot avviato con successo su @{self._bot_username}!"
                else:
                    return False, f"Impossibile avviare il server bot: {self._last_error or 'Arresto imprevisto'}"

            except Exception as e:
                self._is_active = False
                self._last_error = str(e)
                return False, f"Errore inizializzazione bot: {e}"

    def stop(self) -> Tuple[bool, str]:
        """Arresta il thread del Bot Telegram in modo pulito."""
        with self._lock:
            if not self.is_alive():
                return True, "Server Bot non attivo."

            try:
                if self._bot:
                    self._bot.stop()
                self._is_active = False
                self._start_time = None
                if self._thread:
                    self._thread.join(timeout=2.0)
                return True, "Server Bot arrestato con successo."
            except Exception as e:
                return False, f"Errore durante l'arresto del bot: {e}"

    def restart(self, token: Optional[str] = None) -> Tuple[bool, str]:
        """Riavvia il Bot Telegram."""
        self.stop()
        time.sleep(0.5)
        return self.start(token=token)


def get_telegram_service() -> TelegramBotBackgroundService:
    """Funzione helper per ottenere l'istanza singleton del servizio bot."""
    return TelegramBotBackgroundService.get_instance()
