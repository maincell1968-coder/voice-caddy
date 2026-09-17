import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

VOICE_CADDY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(VOICE_CADDY_DIR))

from core.telegram_config import TelegramConfigManager
from core.telegram_bot import VoiceCaddyTelegramBot


def test_telegram_config_modes_and_admin():
    test_data_dir = VOICE_CADDY_DIR / "tests" / "temp_tg_data"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    cfg = TelegramConfigManager(data_dir=test_data_dir)

    # Test default mode
    assert cfg.get_user_mode("12345") == "training"

    # Test mode toggle
    cfg.set_user_mode("12345", "gara")
    assert cfg.get_user_mode("12345") == "gara"

    cfg.set_user_mode("12345", "training")
    assert cfg.get_user_mode("12345") == "training"

    # Test admin chat id
    cfg.set_admin_chat_id("999888777")
    assert cfg.get_admin_chat_id() == "999888777"

    # Test notify_admin mock
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true}'
        mock_url.return_value.__enter__.return_value = mock_resp

        ok = cfg.notify_admin("Test message")
        assert ok is True

    print("[OK] TelegramConfigManager modes & admin notifications verified!")


def test_bot_mode_responses():
    bot = VoiceCaddyTelegramBot(bot_token="TEST_DUMMY_TOKEN")
    chat_id = "test_chat_456"

    # Mock _api_request to capture messages
    sent_messages = []
    def fake_api_request(method, data=None):
        if method == "sendMessage":
            sent_messages.append(data)
            return {"ok": True}
        return {"ok": True}

    bot._api_request = fake_api_request

    # 1. Start in Training Mode
    bot.set_user_mode(chat_id, "training")
    assert bot.get_user_mode(chat_id) == "training"

    # Location update in Training Mode
    bot.handle_location_update(chat_id, 43.5199, 13.6072, 100.0)
    last_msg = sent_messages[-1]["text"]
    assert "Consigliato:" in last_msg
    assert "Regola 4.3" not in last_msg

    # 2. Switch to Gara Mode
    bot.set_user_mode(chat_id, "gara")
    assert bot.get_user_mode(chat_id) == "gara"

    # Location update in Gara Mode (Rule 4.3 must strictly apply)
    bot.handle_location_update(chat_id, 43.5199, 13.6072, 100.0)
    last_msg = sent_messages[-1]["text"]
    assert "Regola 4.3" in last_msg
    assert "Consigliato:" not in last_msg

    # Manual distance in Gara Mode
    bot.handle_manual_distance(chat_id, 140.0)
    last_msg = sent_messages[-1]["text"]
    assert "Regola 4.3" in last_msg
    assert "Consigliato:" not in last_msg

    # Text message asking for advice in Gara Mode
    bot.process_text_message(chat_id, "che bastone devo tirare?")
    last_msg = sent_messages[-1]["text"]
    assert "Regola 4.3" in last_msg
    assert "vietato" in last_msg.lower()

    # Keyboard buttons check
    kb_training = bot.get_on_course_keyboard("training")
    kb_text_training = str(kb_training)
    assert "Modalità Gara" in kb_text_training

    kb_gara = bot.get_on_course_keyboard("gara")
    kb_text_gara = str(kb_gara)
    assert "Modalità Training" in kb_text_gara

    print("[OK] VoiceCaddyTelegramBot Gara vs Training logic verified!")


if __name__ == "__main__":
    test_telegram_config_modes_and_admin()
    test_bot_mode_responses()
    print("[ALL TESTS PASSED SUCCESSFULLY]")
