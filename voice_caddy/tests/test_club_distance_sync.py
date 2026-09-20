import unittest
import tempfile
import sqlite3
import json
from pathlib import Path

from core.club_distance_service import normalize_club_name, ClubDistanceService
from core.user_profile import UserProfile, ClubDetail, ShaftFlex


class TestClubDistanceSync(unittest.TestCase):
    """
    Test di conformità per la sincronizzazione della sacca:
    Confronto tra allenamento (nominale) e colpi reali su erba in gara.
    Completamente isolato con tempfile in ottemperanza alla SafeVault Policy.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_voice_caddy.db"

        # Inizializza schema tabelle minimo nel db temporaneo
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE live_shots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_id TEXT,
                hole_number INTEGER,
                shot_number INTEGER,
                club_used TEXT,
                distance_covered REAL,
                start_latitude REAL,
                start_longitude REAL,
                end_latitude REAL,
                end_longitude REAL,
                recorded_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id TEXT,
                date TEXT,
                json_data TEXT
            )
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalize_club_name(self):
        """Verifica la corretta normalizzazione dei nomi delle mazze."""
        self.assertEqual(normalize_club_name("f7"), "Ferro 7")
        self.assertEqual(normalize_club_name("Ferro 7"), "Ferro 7")
        self.assertEqual(normalize_club_name("7 iron"), "Ferro 7")
        self.assertEqual(normalize_club_name("7-iron"), "Ferro 7")

        self.assertEqual(normalize_club_name("driver"), "Driver")
        self.assertEqual(normalize_club_name("d"), "Driver")
        self.assertEqual(normalize_club_name("1w"), "Driver")

        self.assertEqual(normalize_club_name("legno 3"), "Legno 3")
        self.assertEqual(normalize_club_name("spoon"), "Legno 3")
        self.assertEqual(normalize_club_name("3w"), "Legno 3")

        self.assertEqual(normalize_club_name("ibrido 4"), "Ibrido 4")
        self.assertEqual(normalize_club_name("4h"), "Ibrido 4")

        self.assertEqual(normalize_club_name("pw"), "Pitching Wedge")
        self.assertEqual(normalize_club_name("pitching wedge"), "Pitching Wedge")

        self.assertEqual(normalize_club_name("putter"), "Putter")
        self.assertEqual(normalize_club_name(None), None)

    def test_get_club_grass_performance(self):
        """Verifica il calcolo delle distanze reali su erba da live_shots e rounds storici."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Inserisci 3 colpi di Ferro 7 (140m, 145m, 150m -> media 145m)
        cur.execute("INSERT INTO live_shots (user_id, club_used, distance_covered) VALUES ('user_1', 'Ferro 7', 140.0)")
        cur.execute("INSERT INTO live_shots (user_id, club_used, distance_covered) VALUES ('user_1', 'f7', 145.0)")
        cur.execute("INSERT INTO live_shots (user_id, club_used, distance_covered) VALUES ('user_1', '7-iron', 150.0)")

        # Inserisci 1 colpo corto di Ferro 7 (< 30m, es. chip/approccio da escludere)
        cur.execute("INSERT INTO live_shots (user_id, club_used, distance_covered) VALUES ('user_1', 'Ferro 7', 18.0)")

        # Inserisci un round storico con colpo di Driver
        round_json = {
            "holes": [
                {
                    "hole_number": 1,
                    "shots": [
                        {
                            "club": "Driver",
                            "distance_meters": 225.0,
                            "start_coords": [43.5228, 13.6060],
                            "end_coords": [43.5245, 13.6070]
                        }
                    ]
                }
            ]
        }
        cur.execute("INSERT INTO rounds (user_id, json_data) VALUES ('user_1', ?)", (json.dumps(round_json),))
        conn.commit()
        conn.close()

        stats = ClubDistanceService.get_club_grass_performance(self.db_path, user_id="user_1")

        self.assertIn("Ferro 7", stats)
        f7_stat = stats["Ferro 7"]
        self.assertEqual(f7_stat["count"], 3) # 18m escluso
        self.assertEqual(f7_stat["avg_meters"], 145.0)
        self.assertEqual(f7_stat["min_meters"], 140.0)
        self.assertEqual(f7_stat["max_meters"], 150.0)

        self.assertIn("Driver", stats)
        driver_stat = stats["Driver"]
        self.assertEqual(driver_stat["count"], 1)
        self.assertEqual(driver_stat["avg_meters"], 225.0)

    def test_sync_with_grass_statistics_no_overwrite(self):
        """Verifica che sync con update_carry=False aggiorni solo i dati erba lasciando invariato il carry nominale."""
        prof = UserProfile(
            player_name="Test Golfer",
            handicap=14.0,
            clubs_in_bag=[
                ClubDetail(club_name="Ferro 7", carry_meters=140.0),
                ClubDetail(club_name="Driver", carry_meters=220.0),
                ClubDetail(club_name="Putter", carry_meters=0.0)
            ]
        )

        mock_stats = {
            "ferro 7": {"avg_meters": 146.5, "count": 5, "min_meters": 142.0, "max_meters": 151.0},
            "driver": {"avg_meters": 232.0, "count": 4, "min_meters": 220.0, "max_meters": 240.0}
        }

        ok = prof.sync_with_grass_statistics(mock_stats, update_carry=False)
        self.assertTrue(ok)

        f7 = next(c for c in prof.clubs_in_bag if c.club_name == "Ferro 7")
        self.assertEqual(f7.carry_meters, 140.0) # Invariato
        self.assertEqual(f7.real_grass_meters, 146.5)
        self.assertEqual(f7.measured_shots_count, 5)
        self.assertIsNotNone(f7.last_synced_at)

        summary = prof.get_club_comparison_summary()
        f7_sum = next(s for s in summary if s["club_name"] == "Ferro 7")
        self.assertEqual(f7_sum["training_meters"], 140.0)
        self.assertEqual(f7_sum["grass_meters"], 146.5)
        self.assertEqual(f7_sum["delta_meters"], 6.5)
        self.assertEqual(f7_sum["shots_count"], 5)

    def test_sync_with_grass_statistics_with_overwrite(self):
        """Verifica che sync con update_carry=True aggiorni anche il carry nominale della sacca."""
        prof = UserProfile(
            player_name="Test Golfer",
            handicap=14.0,
            clubs_in_bag=[
                ClubDetail(club_name="Ferro 7", carry_meters=140.0),
                ClubDetail(club_name="Driver", carry_meters=220.0)
            ]
        )

        mock_stats = {
            "ferro 7": {"avg_meters": 148.0, "count": 6},
            "driver": {"avg_meters": 235.0, "count": 7}
        }

        ok = prof.sync_with_grass_statistics(mock_stats, update_carry=True)
        self.assertTrue(ok)

        f7 = next(c for c in prof.clubs_in_bag if c.club_name == "Ferro 7")
        self.assertEqual(f7.carry_meters, 148.0) # Aggiornato con il valore su erba!
        self.assertEqual(f7.real_grass_meters, 148.0)
        self.assertEqual(f7.measured_shots_count, 6)

        driver = next(c for c in prof.clubs_in_bag if c.club_name == "Driver")
        self.assertEqual(driver.carry_meters, 235.0)

    def test_telegram_bot_bag_comparison_rendering(self):
        """Verifica che show_bag_comparison generi correttamente il testo del messaggio e i pulsanti inline."""
        from core.telegram_bot import VoiceCaddyTelegramBot
        from unittest.mock import MagicMock

        mock_bot = VoiceCaddyTelegramBot.__new__(VoiceCaddyTelegramBot)
        mock_bot.db = MagicMock()
        mock_bot.db.db_path = self.db_path
        mock_bot._api_request = MagicMock(return_value={"ok": True})

        # Mock del contesto utente
        test_prof = UserProfile(
            player_name="Stefano Pirani",
            handicap=14.0,
            clubs_in_bag=[
                ClubDetail(club_name="Driver", carry_meters=220.0),
                ClubDetail(club_name="Ferro 7", carry_meters=145.0)
            ]
        )
        test_user = MagicMock(user_id="user_1", first_name="Stefano", last_name="Pirani")
        test_course = MagicMock(name="Conero Golf Club")
        mock_bot._resolve_context = MagicMock(return_value=(test_user, test_prof, test_course, None))
        mock_bot.send_message = MagicMock(return_value={"ok": True})
        mock_bot.edit_message_text = MagicMock(return_value={"ok": True})

        # Invia messaggio di confronto
        res = mock_bot.show_bag_comparison(chat_id=12345)
        mock_bot.send_message.assert_called_once()
        sent_text = mock_bot.send_message.call_args[0][1]
        sent_markup = mock_bot.send_message.call_args[1].get("reply_markup")

        self.assertIn("CONFRONTO SACCA: ALLENAMENTO vs ERBA IN GARA", sent_text)
        self.assertIn("Ferro 7", sent_text)
        self.assertIn("Driver", sent_text)
        self.assertIsNotNone(sent_markup)
        self.assertIn("inline_keyboard", sent_markup)


if __name__ == "__main__":
    unittest.main()
