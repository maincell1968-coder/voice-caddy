import unittest
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.admin_inbox import AdminInboxManager, AdminMessage


class TestAdminInbox(unittest.TestCase):
    def setUp(self):
        # SafeVault isolation: temporary JSON file for test runs
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.inbox_mgr = AdminInboxManager(data_file=Path(self.temp_file.name))

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            try:
                os.remove(self.temp_file.name)
            except Exception:
                pass

    @patch("core.telegram_config.TelegramConfigManager.notify_admin")
    def test_send_message_success(self, mock_notify):
        mock_notify.return_value = (True, "OK")
        ok, msg = self.inbox_mgr.send_message(
            sender_user_id="test_user_1",
            sender_name="Mario Rossi",
            sender_contact="mario@test.it",
            subject="Domanda su calcolo Stableford",
            body="Ciao Stefano, vorrei capire come viene applicato lo Stroke Index alla buca 7.",
            category="Regole di Golf & Handicap"
        )
        self.assertTrue(ok)
        self.assertIn("successo", msg.lower())

        # Verify telegram notification was sent
        mock_notify.assert_called_once()
        call_args = mock_notify.call_args[0][0]
        self.assertIn("Mario Rossi", call_args)
        self.assertIn("Domanda su calcolo Stableford", call_args)
        self.assertIn("mario@test.it", call_args)

        # Verify unread count and message storage
        self.assertEqual(self.inbox_mgr.get_unread_count(), 1)
        messages = self.inbox_mgr.get_messages()
        self.assertEqual(len(messages), 1)
        first_msg = messages[0]
        self.assertEqual(first_msg["sender_name"], "Mario Rossi")
        self.assertFalse(first_msg["is_read"])
        self.assertEqual(first_msg["category"], "Regole di Golf & Handicap")

    def test_send_message_validation_error(self):
        # Empty subject
        ok, msg = self.inbox_mgr.send_message(
            sender_user_id="u1",
            sender_name="User",
            sender_contact="",
            subject="",
            body="Messaggio senza oggetto"
        )
        self.assertFalse(ok)
        self.assertIn("obbligatori", msg)

        # Empty body
        ok, msg = self.inbox_mgr.send_message(
            sender_user_id="u1",
            sender_name="User",
            sender_contact="",
            subject="Oggetto",
            body="   "
        )
        self.assertFalse(ok)
        self.assertIn("obbligatori", msg)

    @patch("core.telegram_config.TelegramConfigManager.notify_admin")
    def test_mark_as_read_and_unread_filter(self, mock_notify):
        self.inbox_mgr.send_message("u1", "User 1", "u1@test.it", "Msg 1", "Body 1")
        self.inbox_mgr.send_message("u2", "User 2", "u2@test.it", "Msg 2", "Body 2")

        self.assertEqual(self.inbox_mgr.get_unread_count(), 2)
        messages = self.inbox_mgr.get_messages()
        self.assertEqual(len(messages), 2)

        # Mark first message as read
        msg_1_id = messages[0]["id"]
        res = self.inbox_mgr.mark_as_read(msg_1_id)
        self.assertTrue(res)
        self.assertEqual(self.inbox_mgr.get_unread_count(), 1)

        unread = self.inbox_mgr.get_messages(unread_only=True)
        self.assertEqual(len(unread), 1)
        self.assertEqual(unread[0]["id"], messages[1]["id"])

        # Mark all as read
        self.inbox_mgr.mark_all_as_read()
        self.assertEqual(self.inbox_mgr.get_unread_count(), 0)
        self.assertEqual(len(self.inbox_mgr.get_messages(unread_only=True)), 0)

    @patch("core.telegram_config.TelegramConfigManager.notify_admin")
    def test_delete_message(self, mock_notify):
        self.inbox_mgr.send_message("u1", "User 1", "u1@test.it", "Msg 1", "Body 1")
        messages = self.inbox_mgr.get_messages()
        msg_id = messages[0]["id"]

        del_res = self.inbox_mgr.delete_message(msg_id)
        self.assertTrue(del_res)
        self.assertEqual(len(self.inbox_mgr.get_messages()), 0)
        self.assertEqual(self.inbox_mgr.get_unread_count(), 0)

        # Deleting non-existent ID should return False
        self.assertFalse(self.inbox_mgr.delete_message("non_existent_id"))


if __name__ == "__main__":
    unittest.main()
