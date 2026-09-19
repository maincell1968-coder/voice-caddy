import unittest
import tempfile
import shutil
from pathlib import Path

from core.parser import (
    parse_round_sequence_intent,
    detect_hole_anomalies,
    parse_audit_correction
)
from core.live_session import LiveSessionManager
from core.telegram_config import TelegramConfigManager
from core.telegram_bot import VoiceCaddyTelegramBot
from core.db import DatabaseManager
from core.auth import AuthManager
from core.demo_data import get_demo_golf_round


class TestRoundSequenceParsing(unittest.TestCase):
    def test_standard_18(self):
        res = parse_round_sequence_intent("giro standard 18 buche", total_course_holes=18)
        self.assertTrue(res["is_sequence_intent"])
        self.assertEqual(res["sequence_type"], "standard_18")
        self.assertEqual(res["sequence"], list(range(1, 19)))
        self.assertEqual(res["total_holes"], 18)

    def test_shotgun_from_7(self):
        res = parse_round_sequence_intent("shotgun da buca 7", total_course_holes=18)
        self.assertTrue(res["is_sequence_intent"])
        self.assertEqual(res["sequence_type"], "shotgun")
        self.assertEqual(res["start_hole"], 7)
        expected = list(range(7, 19)) + list(range(1, 7))
        self.assertEqual(res["sequence"], expected)
        self.assertEqual(res["total_holes"], 18)

    def test_shotgun_from_10(self):
        res = parse_round_sequence_intent("partenza da buca 10", total_course_holes=18)
        self.assertTrue(res["is_sequence_intent"])
        self.assertEqual(res["sequence_type"], "shotgun")
        self.assertEqual(res["start_hole"], 10)
        expected = list(range(10, 19)) + list(range(1, 10))
        self.assertEqual(res["sequence"], expected)

    def test_front_9(self):
        res = parse_round_sequence_intent("ho giocato le prime 9", total_course_holes=18)
        self.assertTrue(res["is_sequence_intent"])
        self.assertEqual(res["sequence_type"], "front_9")
        self.assertEqual(res["sequence"], list(range(1, 10)))
        self.assertEqual(res["total_holes"], 9)

    def test_back_9(self):
        res = parse_round_sequence_intent("seconde 9 buche", total_course_holes=18)
        self.assertTrue(res["is_sequence_intent"])
        self.assertEqual(res["sequence_type"], "back_9")
        self.assertEqual(res["sequence"], list(range(10, 19)))
        self.assertEqual(res["total_holes"], 9)

    def test_custom_partial(self):
        res = parse_round_sequence_intent("ho giocato solo 1-6 e 15-18", total_course_holes=18)
        self.assertTrue(res["is_sequence_intent"])
        self.assertEqual(res["sequence_type"], "custom_partial")
        self.assertEqual(res["sequence"], [1, 2, 3, 4, 5, 6, 15, 16, 17, 18])
        self.assertEqual(res["total_holes"], 10)

    def test_tee_and_gender_detection(self):
        res = parse_round_sequence_intent("donna shotgun buca 5 tee rossi", total_course_holes=18)
        self.assertTrue(res["is_sequence_intent"])
        self.assertEqual(res["gender"], "Donne")
        self.assertEqual(res["tee"], "rossi")
        self.assertEqual(res["start_hole"], 5)


class TestHoleAnomalyDetection(unittest.TestCase):
    def test_water_without_penalty(self):
        hole_data = {
            "hole_number": 4,
            "par": 4,
            "score": 4,
            "penalties": 0,
            "shots": [
                {"shot_index": 1, "club": "Driver", "lie": "tee", "result": "fairway"},
                {"shot_index": 2, "club": "Ferro 7", "lie": "fairway", "result": "water", "notes": "finita nel lago"},
                {"shot_index": 3, "club": "Putter", "lie": "green", "result": "good"}
            ],
            "putts": 1
        }
        anomalies = detect_hole_anomalies(hole_data)
        self.assertTrue(any("acqua" in a.lower() for a in anomalies))

    def test_out_of_bounds_without_penalty(self):
        hole_data = {
            "hole_number": 8,
            "par": 5,
            "score": 5,
            "penalties": 0,
            "shots": [
                {"shot_index": 1, "club": "Driver", "lie": "tee", "result": "out_of_bounds", "notes": "palla fuori limite a destra"},
                {"shot_index": 2, "club": "Driver", "lie": "tee", "result": "fairway"}
            ],
            "putts": 2
        }
        anomalies = detect_hole_anomalies(hole_data)
        self.assertTrue(any("fuori limite" in a.lower() for a in anomalies))

    def test_par4_in_2_without_eagle(self):
        hole_data = {
            "hole_number": 1,
            "par": 4,
            "score": 2,
            "penalties": 0,
            "shots": [
                {"shot_index": 1, "club": "Driver", "lie": "tee", "result": "fairway"},
                {"shot_index": 2, "club": "Putter", "lie": "green", "result": "good"}
            ],
            "putts": 1,
            "description": "buca chiusa in 2 colpi"
        }
        anomalies = detect_hole_anomalies(hole_data)
        self.assertTrue(any("eagle" in a.lower() or "soli 2 colpi" in a.lower() for a in anomalies))

    def test_direct_tee_to_putt_jump(self):
        hole_data = {
            "hole_number": 2,
            "par": 4,
            "score": 2,
            "penalties": 0,
            "shots": [
                {"shot_index": 1, "club": "Driver", "lie": "tee", "result": "fairway"},
                {"shot_index": 2, "club": "Putter", "lie": "green", "result": "good"}
            ],
            "putts": 1
        }
        anomalies = detect_hole_anomalies(hole_data)
        self.assertTrue(any("passaggio diretto" in a.lower() for a in anomalies))

    def test_green_without_putts(self):
        hole_data = {
            "hole_number": 3,
            "par": 3,
            "score": 2,
            "penalties": 0,
            "shots": [
                {"shot_index": 1, "club": "Ferro 7", "lie": "tee", "result": "green"}
            ],
            "putts": 0,
            "description": "primo colpo in green"
        }
        anomalies = detect_hole_anomalies(hole_data)
        self.assertTrue(any("putt" in a.lower() for a in anomalies))


class TestAuditCorrectionParsing(unittest.TestCase):
    def test_confirmation_intent(self):
        res = parse_audit_correction("tutto corretto, procedi")
        self.assertTrue(res["is_confirmation"])
        self.assertFalse(res["is_correction"])

        res2 = parse_audit_correction("/conferma")
        self.assertTrue(res2["is_confirmation"])

    def test_add_penalty(self):
        res = parse_audit_correction("Buca 8: aggiungi una penalità per palla in acqua")
        self.assertTrue(res["is_correction"])
        self.assertEqual(res["hole_number"], 8)
        self.assertEqual(res["action"], "add_penalty")
        self.assertEqual(res["details"]["penalty_strokes"], 1)
        self.assertIn("Acqua", res["details"]["penalty_type"])

    def test_update_putts(self):
        res = parse_audit_correction("Buca 12: ho fatto 3 putt, non 2")
        self.assertTrue(res["is_correction"])
        self.assertEqual(res["hole_number"], 12)
        self.assertEqual(res["action"], "update_putts")
        self.assertEqual(res["details"]["putts"], 3)

    def test_add_or_update_shot(self):
        res = parse_audit_correction("Buca 4: manca un colpo con ferro 7 verso il green")
        self.assertTrue(res["is_correction"])
        self.assertEqual(res["hole_number"], 4)
        self.assertEqual(res["action"], "add_or_update_shot")
        self.assertEqual(res["details"]["club"], "Ferro 7")
        self.assertEqual(res["details"]["result"], "green")


class TestLiveSessionPendingAudit(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "test_session.db"
        self.session_mgr = LiveSessionManager(db_path=self.db_path)
        self.chat_id = "123456"
        self.session_mgr.get_or_create_session(self.chat_id, "user_test", "conero_golf_club")

    def tearDown(self):
        import gc
        gc.collect()
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_round_sequence(self):
        seq = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 1, 2, 3, 4, 5, 6]
        self.session_mgr.set_round_sequence(self.chat_id, seq)
        retrieved = self.session_mgr.get_round_sequence(self.chat_id)
        self.assertEqual(retrieved, seq)

    def test_pending_round_and_corrections(self):
        dummy_round = {
            "round_info": {"course_name": "Conero Golf Club", "holes_played": 1},
            "holes": [
                {
                    "hole_number": 4,
                    "par": 4,
                    "score": 4,
                    "gross_strokes": 4,
                    "putts": 2,
                    "penalties": 0,
                    "shots": [
                        {"shot_index": 1, "club": "Driver", "lie": "tee", "result": "fairway"},
                        {"shot_index": 2, "club": "Putter", "lie": "green", "result": "good"}
                    ]
                }
            ]
        }
        self.session_mgr.set_pending_round(self.chat_id, dummy_round, state="AWAITING_VERIFICATION")
        self.assertEqual(self.session_mgr.get_round_state(self.chat_id), "AWAITING_VERIFICATION")

        # Add penalty
        self.session_mgr.add_pending_hole_penalty(self.chat_id, hole_number=4, penalty_type="Acqua", strokes=1)
        pending = self.session_mgr.get_pending_round(self.chat_id)
        h4 = pending["holes"][0]
        self.assertEqual(h4["penalties"], 1)
        self.assertEqual(h4["gross_strokes"], 3)  # 2 shots + 1 penalty

        # Update putts
        self.session_mgr.update_pending_hole_putts(self.chat_id, hole_number=4, putts=3)
        pending = self.session_mgr.get_pending_round(self.chat_id)
        self.assertEqual(pending["holes"][0]["putts"], 3)

        # Clear
        self.session_mgr.clear_pending_round(self.chat_id)
        self.assertEqual(self.session_mgr.get_round_state(self.chat_id), "IDLE")
        self.assertIsNone(self.session_mgr.get_pending_round(self.chat_id))


class TestTelegramBotAuditFlow(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.cfg_mgr = TelegramConfigManager(data_dir=self.test_dir)
        self.test_db = DatabaseManager(db_path=self.test_dir / "test_bot_tg.db")
        self.test_auth = AuthManager(data_file=self.test_dir / "test_bot_users.json")

        self.bot = VoiceCaddyTelegramBot(bot_token="TEST_BOT_TOKEN", db=self.test_db, auth_mgr=self.test_auth)
        self.bot.config_mgr = self.cfg_mgr
        self.bot.session_mgr = LiveSessionManager(db_path=self.test_dir / "test_bot_live.db")

        self.chat_id = 998877
        self.cfg_mgr.link_chat_user(
            chat_id=self.chat_id,
            user_id="strafatti_stefano_pirani",
            group_name="strafatti",
            first_name="Stefano",
            active_course_name="Conero Golf Club"
        )
        self.sent_messages = []
        self.bot.send_message = lambda chat_id, text, **kwargs: self.sent_messages.append((chat_id, text))

    def tearDown(self):
        import gc
        gc.collect()
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_tee_resolution_man_and_woman(self):
        tee_man, gender_man = self.bot._resolve_default_tee_for_gender(self.chat_id)
        self.assertEqual(tee_man, "gialli")
        self.assertEqual(gender_man, "Uomini")

        tee_woman, gender_woman = self.bot._resolve_default_tee_for_gender(self.chat_id, gender="donna")
        self.assertEqual(tee_woman, "rossi")
        self.assertEqual(gender_woman, "Donne")

    def test_sequence_command(self):
        self.bot.handle_command(self.chat_id, "/sequenza shotgun 7")
        seq = self.bot.session_mgr.get_round_sequence(self.chat_id)
        self.assertEqual(seq[0], 7)
        self.assertEqual(len(seq), 18)
        self.assertTrue(any("Sequenza Buche Impostata" in m[1] for m in self.sent_messages))

    def test_audit_correction_and_confirmation_flow(self):
        # Set up a dummy pending round
        demo = get_demo_golf_round()
        demo_dict = demo.model_dump()
        self.bot.session_mgr.set_pending_round(self.chat_id, demo_dict, state="AWAITING_VERIFICATION")

        # Test user sends correction
        self.bot.process_text_message(self.chat_id, "Buca 4: aggiungi una penalità per palla in acqua")
        self.assertTrue(any("Aggiunta penalità" in m[1] for m in self.sent_messages))

        # Check pending state updated
        pending = self.bot.session_mgr.get_pending_round(self.chat_id)
        h4 = next(h for h in pending["holes"] if h["hole_number"] == 4)
        self.assertEqual(h4["penalties"], 1)

        # Test user sends confirmation
        self.bot.process_text_message(self.chat_id, "✅ Tutto Corretto, Analizza!")
        self.assertTrue(any("Tutto confermato" in m[1] for m in self.sent_messages))
        self.assertTrue(any("VOICE CADDY PRO" in m[1] for m in self.sent_messages))

        # Check pending round cleared
        self.assertEqual(self.bot.session_mgr.get_round_state(self.chat_id), "IDLE")
        self.assertIsNone(self.bot.session_mgr.get_pending_round(self.chat_id))


if __name__ == "__main__":
    unittest.main()
