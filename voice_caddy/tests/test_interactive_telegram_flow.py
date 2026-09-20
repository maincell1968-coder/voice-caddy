import unittest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.live_session import LiveSessionManager
from core.telegram_bot import VoiceCaddyTelegramBot
from core.auth import AuthManager, UserRecord
from core.user_profile import UserProfile
from core.course import CONERO_GOLF_CLUB


class TestInteractiveTelegramFlow(unittest.TestCase):
    def setUp(self):
        # Utilizza un database temporaneo isolato per rispettare rigorosamente la SafeVault Policy
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_voice_caddy.db"
        self.session_mgr = LiveSessionManager(db_path=self.db_path)

        # Mock Bot Telegram senza chiamate HTTP esterne
        self.bot = VoiceCaddyTelegramBot(bot_token="123456:TEST_TOKEN", db=MagicMock(), auth_mgr=MagicMock())
        self.bot.session_mgr = self.session_mgr
        self.bot._api_request = MagicMock(return_value={"ok": True, "result": {"message_id": 999}})

        # Mock contesto utente
        test_user = UserRecord(
            user_id="test_stefano",
            username="stefano_p",
            first_name="Stefano",
            last_name="Pirani",
            group="strafatti",
            password_hash="dummy_hash",
            salt="dummy_salt"
        )
        test_profile = UserProfile(
            player_name="Stefano Pirani",
            handicap=14.0
        )
        self.bot._resolve_context = MagicMock(return_value=(test_user, test_profile, CONERO_GOLF_CLUB, MagicMock()))

        self.chat_id = 12345678

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_full_interactive_round_flow(self):
        """Test end-to-end del flusso interattivo a pulsanti (Zero Audio)."""

        # 1. Avvio procedura guidata (Wizard)
        res_wizard = self.bot.start_interactive_wizard(self.chat_id)
        self.bot._api_request.assert_called_with("sendMessage", unittest.mock.ANY)
        call_args = self.bot._api_request.call_args[0][1]
        self.assertIn("AVVIO GARA INTERATTIVA", call_args["text"])
        self.assertIn("inline_keyboard", call_args["reply_markup"])

        # 2. Selezione Tee (Tee Gialli)
        query_tee = {
            "id": "cb_1",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "tee_gialli"
        }
        self.bot.handle_callback_query(query_tee)
        edit_args = self.bot._api_request.call_args[0][1]
        self.assertIn("Tee Gialli", edit_args["text"])
        self.assertIn("buca di partenza", edit_args["text"])

        # 3. Selezione Buca di Partenza (Buca 1)
        query_hole1 = {
            "id": "cb_2",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "start_hole_1"
        }
        self.bot.handle_callback_query(query_hole1)
        istate = self.session_mgr.get_interactive_state(self.chat_id)
        self.assertEqual(istate.get("current_hole"), 1)
        self.assertEqual(istate.get("current_shot_number"), 1)

        # 4. Colpo 1: Drive dal Tee
        query_shot1 = {
            "id": "cb_3",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "shot_drive"
        }
        self.bot.handle_callback_query(query_shot1)
        istate = self.session_mgr.get_interactive_state(self.chat_id)
        self.assertIsNotNone(istate.get("active_shot"))
        self.assertEqual(istate["active_shot"]["club"], "Drive")

        # 5. Raggiunge la palla: invia posizione GPS (Haversine calcola la distanza)
        # Coordinate Tee Buca 1 Conero: lat 43.5228, lon 13.6060 (ipotizziamo atterraggio a 210m)
        h1_coords = CONERO_GOLF_CLUB.get_hole(1).coordinates
        tee_lat = h1_coords.tee_lat if h1_coords else 43.5228
        tee_lon = h1_coords.tee_lon if h1_coords else 13.6060
        # Circa 200m a sud
        ball_lat = tee_lat - 0.0018
        ball_lon = tee_lon

        # Imposta attesa GPS
        self.bot.handle_callback_query({
            "id": "cb_calc",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "calc_dist"
        })
        # Arriva aggiornamento posizione GPS
        self.bot.handle_location_update(self.chat_id, ball_lat, ball_lon)
        istate = self.session_mgr.get_interactive_state(self.chat_id)
        self.assertIsNotNone(istate["active_shot"].get("distance_meters"))
        self.assertGreater(istate["active_shot"]["distance_meters"], 100)

        # 6. Scelta Lie della palla: Fairway
        query_lie = {
            "id": "cb_4",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "lie_fairway"
        }
        self.bot.handle_callback_query(query_lie)
        istate = self.session_mgr.get_interactive_state(self.chat_id)
        self.assertEqual(len(istate["hole_shots"]), 1)
        self.assertEqual(istate["hole_shots"][0]["lie"], "Fairway")
        self.assertEqual(istate["current_shot_number"], 2)

        # 7. Colpo 2: Ferro verso il green
        query_shot2 = {
            "id": "cb_5",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "shot_iron"
        }
        self.bot.handle_callback_query(query_shot2)

        # 8. Palla in Green!
        query_green = {
            "id": "cb_6",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "reached_green"
        }
        self.bot.handle_callback_query(query_green)
        istate = self.session_mgr.get_interactive_state(self.chat_id)
        self.assertEqual(len(istate["hole_shots"]), 2)
        self.assertEqual(istate["hole_shots"][1]["lie"], "Green")

        # 9. Scelta Putt: 2 Putt
        query_putts = {
            "id": "cb_7",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "putts_2"
        }
        self.bot.handle_callback_query(query_putts)

        # Verifica chiusura Buca 1
        card = self.session_mgr.get_round_scorecard(self.chat_id)
        self.assertEqual(card["holes_played"], 1)
        h1_res = card["completed_holes"][0]
        self.assertEqual(h1_res["hole_number"], 1)
        self.assertEqual(h1_res["gross_strokes"], 4)  # 2 colpi + 2 putt = 4 (Par)
        self.assertEqual(h1_res["putts"], 2)
        self.assertGreaterEqual(h1_res["stableford_points"], 2)  # Almeno 2 pt Stableford

        # 10. Passaggio a Buca 2
        query_next = {
            "id": "cb_8",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "next_hole"
        }
        self.bot.handle_callback_query(query_next)
        istate = self.session_mgr.get_interactive_state(self.chat_id)
        self.assertEqual(istate.get("current_hole"), 2)
        self.assertEqual(istate.get("current_shot_number"), 1)
        self.assertEqual(len(istate.get("hole_shots", [])), 0)

        # 11. Test Annulla Colpo su Buca 2
        self.bot.handle_callback_query({
            "id": "cb_9",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "shot_drive"
        })
        self.bot.handle_callback_query({
            "id": "cb_10",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "undo_shot"
        })
        istate = self.session_mgr.get_interactive_state(self.chat_id)
        self.assertIsNone(istate.get("active_shot"))

        # 12. Test Penalità (+1 Acqua)
        self.bot.handle_callback_query({
            "id": "cb_11",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "shot_wood"
        })
        self.bot.handle_callback_query({
            "id": "cb_12",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "penalty_water"
        })
        istate = self.session_mgr.get_interactive_state(self.chat_id)
        self.assertEqual(len(istate.get("hole_penalties", [])), 1)

        # 13. Visualizzazione Scorecard
        res_score = self.bot.show_interactive_scorecard(self.chat_id)
        call_score_text = self.bot._api_request.call_args[0][1]["text"]
        self.assertIn("SCORECARD UFFICIALE", call_score_text)
        self.assertIn("Buca | Par | SI | Lor | Net | StbN | StbL | Put", call_score_text)
        self.assertIn("Totale Stableford", call_score_text)

        # 14. Termina e Salva Gara
        self.bot.handle_callback_query({
            "id": "cb_13",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "finalize_round"
        })
        final_text = self.bot._api_request.call_args[0][1]["text"]
        self.assertIn("GARA CONCLUSA & REGISTRATA", final_text)
        self.assertIn("Punti Stableford Netti", final_text)
        self.assertIn("Punti Stableford Lordi", final_text)

    def test_text_triggers_and_commands(self):
        """Verifica i trigger testuali da tastiera rapida e i comandi Telegram per la modalità bot."""
        # 1. Trigger testuale "🟢 Inizia Gara a Pulsanti"
        self.bot.process_text_message(self.chat_id, "🟢 Inizia Gara a Pulsanti")
        call_args = self.bot._api_request.call_args[0][1]
        self.assertIn("AVVIO GARA INTERATTIVA", call_args["text"])

        # 2. Comando /gara_bot
        self.bot.handle_command(self.chat_id, "/gara_bot")
        call_args = self.bot._api_request.call_args[0][1]
        self.assertIn("AVVIO GARA INTERATTIVA", call_args["text"])

        # 3. Trigger testuale "📊 Score"
        self.bot.process_text_message(self.chat_id, "📊 Score")
        call_args = self.bot._api_request.call_args[0][1]
        self.assertIn("SCORECARD UFFICIALE", call_args["text"])

        # 4. Comando /score_bot
        self.bot.handle_command(self.chat_id, "/score_bot")
        call_args = self.bot._api_request.call_args[0][1]
        self.assertIn("SCORECARD UFFICIALE", call_args["text"])

        # 5. Callback lie_water -> apre menu penalità
        self.bot.handle_callback_query({
            "id": "cb_lie_w",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "lie_water"
        })
        call_args = self.bot._api_request.call_args[0][1]
        self.assertIn("Palla in Acqua", call_args["text"])
        self.assertIn("inline_keyboard", call_args["reply_markup"])

        # 6. Callback edit_hole -> apre menu selezione buca
        self.bot.handle_callback_query({
            "id": "cb_edit",
            "message": {"chat": {"id": self.chat_id}, "message_id": 100},
            "data": "edit_hole"
        })
        call_args = self.bot._api_request.call_args[0][1]
        self.assertIn("Seleziona la buca da modificare", call_args["text"])


if __name__ == "__main__":
    unittest.main()

