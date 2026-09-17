import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

VOICE_CADDY_DIR = Path(__file__).resolve().parent.parent
if str(VOICE_CADDY_DIR) not in sys.path:
    sys.path.insert(0, str(VOICE_CADDY_DIR))

from core.weather_service import degrees_to_cardinal_and_arrow, WeatherService, weather_service
from core.telegram_bot import VoiceCaddyTelegramBot


class TestWeatherService(unittest.TestCase):
    def test_wind_cardinal_and_arrow(self):
        # 337.5 - 22.5: N -> ⬇️ (fluisce verso Sud)
        self.assertEqual(degrees_to_cardinal_and_arrow(0), ("N", "⬇️"))
        self.assertEqual(degrees_to_cardinal_and_arrow(10), ("N", "⬇️"))
        self.assertEqual(degrees_to_cardinal_and_arrow(350), ("N", "⬇️"))
        self.assertEqual(degrees_to_cardinal_and_arrow(720), ("N", "⬇️"))

        # 22.5 - 67.5: NE -> ↙️
        self.assertEqual(degrees_to_cardinal_and_arrow(45), ("NE", "↙️"))

        # 67.5 - 112.5: E -> ⬅️
        self.assertEqual(degrees_to_cardinal_and_arrow(90), ("E", "⬅️"))

        # 112.5 - 157.5: SE -> ↖️
        self.assertEqual(degrees_to_cardinal_and_arrow(135), ("SE", "↖️"))

        # 157.5 - 202.5: S -> ⬆️
        self.assertEqual(degrees_to_cardinal_and_arrow(180), ("S", "⬆️"))

        # 202.5 - 247.5: SO -> ↗️
        self.assertEqual(degrees_to_cardinal_and_arrow(225), ("SO", "↗️"))

        # 248 - 292.5: O -> ➡️
        self.assertEqual(degrees_to_cardinal_and_arrow(270), ("O", "➡️"))

        # 293 - 337.5: NO -> ↘️
        self.assertEqual(degrees_to_cardinal_and_arrow(315), ("NO", "↘️"))

    @patch("urllib.request.urlopen")
    def test_get_current_weather_success(self, mock_urlopen):
        sample_api_response = {
            "current": {
                "temperature_2m": 22.4,
                "relative_humidity_2m": 65,
                "weather_code": 1,
                "wind_speed_10m": 16.2,
                "wind_direction_10m": 45.0,
                "wind_gusts_10m": 25.8
            }
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(sample_api_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        svc = WeatherService(cache_ttl_seconds=60)
        res = svc.get_current_weather(43.52, 13.61)

        self.assertIsNotNone(res)
        self.assertEqual(res["temperature"], 22.4)
        self.assertEqual(res["humidity"], 65)
        self.assertEqual(res["weather_condition"], "Prevalentemente sereno")
        self.assertEqual(res["weather_emoji"], "🌤️")
        self.assertEqual(res["wind_speed"], 16.2)
        self.assertEqual(res["wind_direction_deg"], 45)
        self.assertEqual(res["wind_cardinal"], "NE")
        self.assertEqual(res["wind_arrow"], "↙️")
        self.assertEqual(res["wind_gusts"], 25.8)
        self.assertTrue(res["is_live"])

        # Verifica cache: una seconda chiamata con stesse coordinate non effettua una nuova richiesta HTTP
        mock_urlopen.reset_mock()
        cached = svc.get_current_weather(43.52, 13.61)
        mock_urlopen.assert_not_called()
        self.assertEqual(cached["wind_cardinal"], "NE")

    @patch("urllib.request.urlopen", side_effect=Exception("Timeout Open-Meteo"))
    def test_get_current_weather_fallback(self, mock_urlopen):
        svc = WeatherService(cache_ttl_seconds=60)
        res = svc.get_current_weather(43.52, 13.61)
        self.assertIsNotNone(res)
        self.assertFalse(res["is_live"])
        self.assertEqual(res["weather_condition"], "Sereno")
        self.assertEqual(res["wind_speed"], 10.0)


class TestTelegramBotWeatherFlow(unittest.TestCase):
    def setUp(self):
        self.bot = VoiceCaddyTelegramBot(bot_token="test_token_12345")
        self.bot._api_request = MagicMock(return_value={"ok": True})
        self.bot.config_mgr.notify_admin = MagicMock()

    def tearDown(self):
        mapping = self.bot.config_mgr.load_users_map()
        modified = False
        for cid in ["88888", "99999", "12345"]:
            if str(cid) in mapping:
                del mapping[str(cid)]
                modified = True
        if modified:
            with open(self.bot.config_mgr.users_map_file, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=4, ensure_ascii=False)

    def test_weather_request_keyboard_structure(self):
        kb = self.bot.get_weather_request_keyboard()
        self.assertTrue(kb["resize_keyboard"])
        self.assertTrue(kb["one_time_keyboard"])
        btn = kb["keyboard"][0][0]
        self.assertIn("vento", btn["text"].lower())
        self.assertTrue(btn["request_location"])

    def test_start_round_flow_sets_pending_and_sends_keyboard(self):
        chat_id = 99999
        self.bot.start_round_flow(chat_id, mode="gara", tee_name="gialli")
        self.assertTrue(self.bot.pending_weather[str(chat_id)])
        self.assertEqual(self.bot.get_user_mode(chat_id), "gara")

        # Verifica invio tastiera meteo
        self.bot._api_request.assert_called_once()
        call_args = self.bot._api_request.call_args[0]
        method, payload = call_args[0], call_args[1]
        self.assertEqual(method, "sendMessage")
        self.assertIn("rilevare il campo", payload["text"])
        self.assertTrue(payload["reply_markup"]["one_time_keyboard"])

    def test_keywords_trigger_start_round_flow(self):
        with patch.object(self.bot, "start_round_flow") as mock_flow:
            # Comandi
            self.bot.handle_command(12345, "/start_round")
            mock_flow.assert_called_with(12345, "training")

            mock_flow.reset_mock()
            self.bot.handle_command(12345, "/gara")
            mock_flow.assert_called_with(12345, "gara")

            # Testo normale
            mock_flow.reset_mock()
            self.bot.process_text_message(12345, "Inizio gara")
            mock_flow.assert_called_with(12345, "gara")

            mock_flow.reset_mock()
            self.bot.process_text_message(12345, "meteo e vento sul percorso")
            mock_flow.assert_called_with(12345, "training")

    @patch("core.telegram_bot.weather_service.get_current_weather")
    def test_handle_location_update_consumes_weather_and_restores_game_keyboard(self, mock_weather):
        mock_weather.return_value = {
            "temperature": 19.5,
            "humidity": 60,
            "weather_code": 0,
            "weather_desc": "Sereno ☀️",
            "weather_condition": "Sereno",
            "weather_emoji": "☀️",
            "wind_speed": 14.5,
            "wind_direction_deg": 45,
            "wind_cardinal": "NE",
            "wind_arrow": "↙️",
            "wind_gusts": 22.0,
            "is_live": True
        }

        chat_id = 88888
        self.bot.pending_weather[str(chat_id)] = True
        self.bot.set_user_mode(chat_id, "gara")

        # Invia posizione GPS iniziale
        self.bot.handle_location_update(chat_id, lat=43.5200, lon=13.6070)

        # Deve aver consumato pending_weather
        self.assertFalse(self.bot.pending_weather[str(chat_id)])

        # Deve aver inviato il messaggio formattato con ripristino tastiera da gioco persistente
        self.bot._api_request.assert_called()
        last_call = self.bot._api_request.call_args[0]
        method, payload = last_call[0], last_call[1]
        self.assertEqual(method, "sendMessage")
        self.assertIn("Modalità Round Attivata! (GARA", payload["text"])
        self.assertIn("<b>Meteo:</b> Sereno ☀️, 19.5°C", payload["text"])
        self.assertIn("<b>Vento medio:</b> 14.5 km/h da NE ↙️", payload["text"])
        self.assertIn("<b>Raffiche:</b> fino a 22.0 km/h", payload["text"])
        self.assertIn("Tee della Buca 1", payload["text"])

        # Tastiera ripristinata a quella di gioco persistente
        self.assertTrue(payload["reply_markup"]["is_persistent"])
        self.assertEqual(payload["reply_markup"]["keyboard"][0][0]["text"], "📍 Calcola Distanza & Plays Like")


if __name__ == "__main__":
    unittest.main()
