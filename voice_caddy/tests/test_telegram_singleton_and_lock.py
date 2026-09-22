import unittest
import sys
import threading
from unittest.mock import MagicMock, patch

from core.telegram_service import TelegramBotBackgroundService, get_telegram_service
from core.telegram_bot import VoiceCaddyTelegramBot


class TestTelegramSingletonAndLock(unittest.TestCase):
    def setUp(self):
        # Ripristina lo stato di sys prima di ogni test
        if hasattr(sys, "_voice_caddy_bot_service"):
            delattr(sys, "_voice_caddy_bot_service")
        if hasattr(sys, "_voice_caddy_bot_polling_active"):
            delattr(sys, "_voice_caddy_bot_polling_active")
        if hasattr(sys, "_voice_caddy_processed_updates"):
            delattr(sys, "_voice_caddy_processed_updates")

    def tearDown(self):
        if hasattr(sys, "_voice_caddy_bot_service"):
            srv = getattr(sys, "_voice_caddy_bot_service")
            srv.stop()
            delattr(sys, "_voice_caddy_bot_service")
        if hasattr(sys, "_voice_caddy_bot_polling_active"):
            delattr(sys, "_voice_caddy_bot_polling_active")
        if hasattr(sys, "_voice_caddy_processed_updates"):
            delattr(sys, "_voice_caddy_processed_updates")

    def test_singleton_persistence_in_sys(self):
        """Verifica che get_telegram_service() persista in sys._voice_caddy_bot_service e resista alle ri-istanziazioni."""
        srv1 = get_telegram_service()
        self.assertIsNotNone(srv1)
        self.assertIs(getattr(sys, "_voice_caddy_bot_service", None), srv1)

        # Nuova richiesta singleton deve restituire lo stesso oggetto
        srv2 = get_telegram_service()
        self.assertIs(srv1, srv2)

        # Chiamata diretta a get_instance sulla classe deve restituire lo stesso oggetto
        srv3 = TelegramBotBackgroundService.get_instance()
        self.assertIs(srv1, srv3)

    def test_socket_instance_lock_mutual_exclusion(self):
        """Verifica che due istanze non possano acquisire contemporaneamente il socket lock su 127.0.0.1:48199."""
        bot1 = VoiceCaddyTelegramBot(bot_token="123:DUMMY1", db=MagicMock(), auth_mgr=MagicMock())
        bot2 = VoiceCaddyTelegramBot(bot_token="123:DUMMY2", db=MagicMock(), auth_mgr=MagicMock())

        # Bot 1 acquisisce il lock
        acquired1 = bot1._acquire_instance_lock()
        self.assertTrue(acquired1, "Bot 1 deve acquisire il lock del socket")

        # Bot 2 tenta di acquisire il lock sulla stessa porta: deve fallire
        acquired2 = bot2._acquire_instance_lock()
        self.assertFalse(acquired2, "Bot 2 non deve poter acquisire il lock se Bot 1 è attivo")

        # Bot 1 rilascia il lock
        bot1._release_instance_lock()

        # Ora Bot 2 deve poter acquisire il lock
        acquired3 = bot2._acquire_instance_lock()
        self.assertTrue(acquired3, "Bot 2 deve poter acquisire il lock dopo il rilascio di Bot 1")
        bot2._release_instance_lock()

    def test_run_polling_exits_if_another_instance_active(self):
        """Verifica che run_polling() termini immediatamente senza ciclo se un'altra istanza ha il lock."""
        bot1 = VoiceCaddyTelegramBot(bot_token="123:DUMMY1", db=MagicMock(), auth_mgr=MagicMock())
        bot2 = VoiceCaddyTelegramBot(bot_token="123:DUMMY2", db=MagicMock(), auth_mgr=MagicMock())

        # Simula Bot 1 già attivo con lock acquisito
        bot1._acquire_instance_lock()

        try:
            bot2._api_request = MagicMock()
            bot2.run_polling()
            # Se è uscito subito, _api_request non deve essere mai stato chiamato
            bot2._api_request.assert_not_called()
            self.assertFalse(bot2.is_running)
        finally:
            bot1._release_instance_lock()

    def test_run_polling_in_process_guard(self):
        """Verifica che run_polling() non parta due volte nello stesso processo."""
        bot = VoiceCaddyTelegramBot(bot_token="123:DUMMY", db=MagicMock(), auth_mgr=MagicMock())
        setattr(sys, "_voice_caddy_bot_polling_active", True)

        bot._api_request = MagicMock()
        bot.run_polling()
        bot._api_request.assert_not_called()
        self.assertFalse(bot.is_running)


if __name__ == "__main__":
    unittest.main()
