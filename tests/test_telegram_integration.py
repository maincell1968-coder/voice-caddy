import unittest
import os
import shutil
import tempfile
from pathlib import Path

from core.telegram_config import TelegramConfigManager
from core.telegram_bot import VoiceCaddyTelegramBot
from core.db import DatabaseManager
from core.demo_data import get_demo_golf_round
from core.auth import AuthManager


class TestTelegramIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.cfg_mgr = TelegramConfigManager(data_dir=self.test_dir)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_config_manager_token(self):
        test_tok = "123456789:TEST_ABC_TOKEN_XYZ"
        self.cfg_mgr.set_token(test_tok)
        self.assertEqual(self.cfg_mgr.get_token(), test_tok)

    def test_link_user_and_course(self):
        chat_id = 999888777
        self.cfg_mgr.link_chat_user(
            chat_id=chat_id,
            user_id="strafatti_stefano_pirani",
            group_name="strafatti",
            first_name="Stefano",
            active_course_name="Conero Golf Club"
        )
        linked = self.cfg_mgr.get_linked_user(chat_id)
        self.assertIsNotNone(linked)
        self.assertEqual(linked["user_id"], "strafatti_stefano_pirani")
        self.assertEqual(linked["first_name"], "Stefano")

        # Update course
        self.cfg_mgr.set_active_course(chat_id, "Golf Club Ancona")
        updated = self.cfg_mgr.get_linked_user(chat_id)
        self.assertEqual(updated["active_course_name"], "Golf Club Ancona")

    def test_bot_context_and_summary(self):
        bot = VoiceCaddyTelegramBot(bot_token="TEST_DUMMY_TOKEN")
        bot.config_mgr = self.cfg_mgr

        # Link chat
        self.cfg_mgr.link_chat_user(
            chat_id=12345,
            user_id="strafatti_stefano_pirani",
            group_name="strafatti",
            first_name="Stefano"
        )

        user_rec, profile, course, ai_cfg = bot._resolve_context(12345)
        self.assertEqual(user_rec.first_name, "Stefano")
        self.assertEqual(profile.player_name, "Stefano Pirani")
        self.assertEqual(course.name, "Conero Golf Club")

        # Test summary formatting
        demo_round = get_demo_golf_round()
        summary_text = bot._format_round_summary(demo_round, round_id=101, player_name="Stefano Pirani", course_name="Conero Golf Club")
        self.assertIn("VOICE CADDY PRO", summary_text)
        self.assertIn("Stefano Pirani", summary_text)
        self.assertIn("Conero Golf Club", summary_text)
        self.assertIn("Score Totale", summary_text)
        self.assertIn("Fairway Presi", summary_text)

    def test_get_chat_id_and_unlink(self):
        user_id = "strafatti_stefano_pirani"
        self.assertIsNone(self.cfg_mgr.get_chat_id_for_user(user_id))

        self.cfg_mgr.link_chat_user(
            chat_id=777888,
            user_id=user_id,
            group_name="strafatti",
            first_name="Stefano"
        )
        self.assertEqual(self.cfg_mgr.get_chat_id_for_user(user_id), "777888")

        # Unlink
        res = self.cfg_mgr.unlink_user(user_id)
        self.assertTrue(res)
        self.assertIsNone(self.cfg_mgr.get_chat_id_for_user(user_id))

    def test_deep_link_start_command(self):
        bot = VoiceCaddyTelegramBot(bot_token="TEST_DUMMY_TOKEN")
        bot.config_mgr = self.cfg_mgr
        sent_messages = []
        bot.send_message = lambda chat_id, text, **kwargs: sent_messages.append((chat_id, text))

        # Test deep link pairing
        bot.handle_command(999111, "/start link_strafatti_stefano_pirani")
        linked = self.cfg_mgr.get_linked_user(999111)
        self.assertIsNotNone(linked)
        self.assertEqual(linked["user_id"], "strafatti_stefano_pirani")
        self.assertEqual(linked["first_name"], "Stefano")
        self.assertTrue(len(sent_messages) > 0)
        self.assertIn("COLLEGAMENTO SMART COMPLETATO", sent_messages[0][1])

    def test_background_service_status(self):
        from core.telegram_service import get_telegram_service
        srv = get_telegram_service()
        status = srv.get_status_info()
        self.assertIn("is_alive", status)
        self.assertIn("has_token", status)
        self.assertIn("bot_username", status)


if __name__ == "__main__":
    unittest.main()
