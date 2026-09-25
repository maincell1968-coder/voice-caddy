import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.tactical_course_manager import tactical_course_manager
from core.live_session import LiveSessionManager
from core.telegram_config import TelegramConfigManager
from core.telegram_bot import VoiceCaddyTelegramBot
from core.db import DatabaseManager
from core.auth import AuthManager


class TestShotgunGPSDetection(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.cfg_mgr = TelegramConfigManager(data_dir=self.test_dir)
        self.test_db = DatabaseManager(db_path=self.test_dir / "test_bot_tg.db")
        self.test_auth = AuthManager(data_file=self.test_dir / "test_bot_users.json")
        self.session_mgr = LiveSessionManager(db_path=self.test_dir / "test_bot_live.db")

        self.bot = VoiceCaddyTelegramBot(bot_token="TEST_SHOTGUN_TOKEN", db=self.test_db, auth_mgr=self.test_auth)
        self.bot.config_mgr = self.cfg_mgr
        self.bot.session_mgr = self.session_mgr

        self.chat_id = 998877
        self.cfg_mgr.link_chat_user(
            chat_id=self.chat_id,
            user_id="strafatti_stefano_pirani",
            group_name="strafatti",
            first_name="Stefano",
            active_course_name="Conero Golf Club"
        )
        self.sent_messages = []
        self.bot.send_message = lambda chat_id, text, **kwargs: self.sent_messages.append((chat_id, text, kwargs.get("reply_markup")))
        self.session_mgr.get_or_create_session(self.chat_id, "strafatti_stefano_pirani", "conero_golf_club")

    def tearDown(self):
        import gc
        gc.collect()
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_direct_gps_detection_conero_tees(self):
        # 1. Coordinate Buca 7 Tee Gialli (Conero Golf)
        h7 = tactical_course_manager.get_tactical_hole("conero_golf_club", 7)
        self.assertIsNotNone(h7)
        tee7_lat, tee7_lon = h7.tee_gialli

        res7 = tactical_course_manager.detect_nearest_hole_from_gps(
            "conero_golf_club", tee7_lat + 0.00005, tee7_lon + 0.00005, max_tee_distance_m=85.0
        )
        self.assertTrue(res7["detected"])
        self.assertEqual(res7["nearest_hole"], 7)
        self.assertLess(res7["distance_to_tee_m"], 15.0)
        self.assertEqual(res7["shotgun_sequence"][0], 7)
        self.assertEqual(res7["shotgun_sequence"][-1], 6)
        self.assertEqual(len(res7["shotgun_sequence"]), 18)

        # 2. Coordinate Buca 14 Tee Gialli
        h14 = tactical_course_manager.get_tactical_hole("conero_golf_club", 14)
        self.assertIsNotNone(h14)
        tee14_lat, tee14_lon = h14.tee_gialli

        res14 = tactical_course_manager.detect_nearest_hole_from_gps(
            "conero_golf_club", tee14_lat, tee14_lon, max_tee_distance_m=85.0
        )
        self.assertTrue(res14["detected"])
        self.assertEqual(res14["nearest_hole"], 14)
        self.assertEqual(res14["shotgun_sequence"][0], 14)
        self.assertEqual(res14["shotgun_sequence"][-1], 13)

        # 3. Coordinate Clubhouse (distante da tutti i tee > 85m)
        clubhouse_lat, clubhouse_lon = 43.5228, 13.6060
        res_ch = tactical_course_manager.detect_nearest_hole_from_gps(
            "conero_golf_club", clubhouse_lat, clubhouse_lon, max_tee_distance_m=85.0
        )
        self.assertFalse(res_ch["detected"])
        self.assertGreater(res_ch["distance_to_tee_m"], 85.0)

    @patch("core.telegram_bot.weather_service.get_current_weather")
    def test_handle_location_update_shotgun_start_from_tee_7(self, mock_weather):
        mock_weather.return_value = {
            "weather_desc": "Sereno ☀️",
            "temperature": 22.0,
            "wind_speed": 12.0,
            "wind_cardinal": "NE",
            "wind_arrow": "↙️",
            "wind_gusts": 18.0
        }

        # Simula avvio round con richiesta vento/meteo
        self.bot.pending_weather[str(self.chat_id)] = True
        self.bot.set_user_mode(self.chat_id, "training")

        h7 = tactical_course_manager.get_tactical_hole("conero_golf_club", 7)
        tee7_lat, tee7_lon = h7.tee_gialli

        # Invia posizione GPS dal tee della Buca 7
        self.bot.handle_location_update(self.chat_id, lat=tee7_lat, lon=tee7_lon)

        # Verifica che pending_weather sia stato consumato
        self.assertFalse(self.bot.pending_weather[str(self.chat_id)])

        # Verifica configurazione sessione: buca attiva 7 e sequenza ciclica [7..18, 1..6]
        seq = self.session_mgr.get_round_sequence(self.chat_id)
        self.assertEqual(seq[0], 7)
        self.assertEqual(seq[-1], 6)
        self.assertEqual(len(seq), 18)

        # Verifica messaggio inviato all'utente
        last_text = self.sent_messages[-1][1]
        self.assertIn("PARTENZA SHOTGUN RILEVATA DA GPS", last_text)
        self.assertIn("BUCA 7", last_text)
        self.assertIn("Meteo", last_text)
        self.assertIn("Sequenza Shotgun", last_text)

    def test_shotgun_command_prompts_for_gps(self):
        # Il giocatore digita /shotgun senza argomenti
        self.bot.handle_command(self.chat_id, "/shotgun")
        self.assertTrue(self.bot.pending_shotgun_detection[str(self.chat_id)])

        last_text = self.sent_messages[-1][1]
        self.assertIn("Rilevamento Automatico Partenza Shotgun da GPS", last_text)
        kb = self.sent_messages[-1][2]
        self.assertTrue(any(
            btn.get("request_location") for row in kb.get("keyboard", []) for btn in row
        ))

    def test_text_triggers_prompt_for_gps_shotgun(self):
        # Il giocatore scrive "partenza shotgun" o "da che buca parto"
        self.bot.process_text_message(self.chat_id, "da che buca parto")
        self.assertTrue(self.bot.pending_shotgun_detection[str(self.chat_id)])
        last_text = self.sent_messages[-1][1]
        self.assertIn("RILEVAMENTO AUTOMATICO PARTENZA SHOTGUN", last_text)

    @patch("core.telegram_bot.weather_service.get_current_weather")
    def test_spontaneous_shotgun_detection_on_course(self, mock_weather):
        mock_weather.return_value = {"weather_desc": "Soleggiato", "temperature": 20.0, "wind_speed": 5.0}

        # La sessione è appena creata (buca 1, colpo 1)
        h10 = tactical_course_manager.get_tactical_hole("conero_golf_club", 10)
        tee10_lat, tee10_lon = h10.tee_gialli

        # Il giocatore invia posizione GPS mentre è sul tee della buca 10
        self.bot.handle_location_update(self.chat_id, lat=tee10_lat, lon=tee10_lon)

        # Voice Caddy deve aver rilevato che il giocatore è sulla 10 e non sulla 1
        seq = self.session_mgr.get_round_sequence(self.chat_id)
        self.assertEqual(seq[0], 10)
        self.assertEqual(seq[-1], 9)
        last_text = self.sent_messages[-1][1]
        self.assertIn("PARTENZA SHOTGUN RILEVATA DA GPS", last_text)
        self.assertIn("BUCA 10", last_text)

    def test_shotgun_cyclic_hole_advancement(self):
        # Sequenza shotgun da buca 17: [17, 18, 1, 2, ..., 16]
        seq_17 = [17, 18] + list(range(1, 17))
        self.session_mgr.set_round_sequence(self.chat_id, seq_17)
        self.session_mgr.set_current_hole(self.chat_id, 17)

        # Avanzamento da 17 -> 18
        next_h = self.session_mgr.next_hole(self.chat_id)
        self.assertEqual(next_h, 18)

        # Avanzamento da 18 -> 1 (passaggio ciclico chiave shotgun!)
        next_h2 = self.session_mgr.next_hole(self.chat_id)
        self.assertEqual(next_h2, 1)

        # Avanzamento da 1 -> 2
        next_h3 = self.session_mgr.next_hole(self.chat_id)
        self.assertEqual(next_h3, 2)


if __name__ == "__main__":
    unittest.main()
