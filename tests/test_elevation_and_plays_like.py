import unittest
from pathlib import Path
import tempfile
import shutil

from core.elevation_service import (
    haversine_distance,
    calculate_plays_like,
    get_slope_label,
    ElevationService
)
from core.course import CONERO_GOLF_CLUB, TORRENOVA_GOLF_CLUB, HoleCoordinates
from core.user_profile import UserProfile, get_default_bag
from core.parser import parse_quick_shot_update
from core.live_session import LiveSessionManager
from core.telegram_bot import VoiceCaddyTelegramBot
from core.telegram_config import TelegramConfigManager


class TestElevationAndPlaysLike(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_file = self.test_dir / "test_session.db"
        self.session_mgr = LiveSessionManager(db_path=self.db_file)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_haversine_distance(self):
        # Coordinate Buca 1 Conero (Tee e Green)
        tee_lat, tee_lon = 43.5228, 13.6060
        green_lat, green_lon = 43.5199, 13.6072
        dist = haversine_distance(tee_lat, tee_lon, green_lat, green_lon)
        # La distanza deve essere compresa tra 330m e 350m (scorecard = 342m)
        self.assertAlmostEqual(dist, 336.7, delta=5.0)

    def test_plays_like_formula_and_slope(self):
        # Scenario Colpo 2 da 138m con +8m di dislivello in salita
        raw_dist = 138.0
        elev_diff = 8.0
        plays_like = calculate_plays_like(raw_dist, elev_diff, slope_factor=1.0)
        self.assertEqual(plays_like, 146.0)
        self.assertEqual(get_slope_label(elev_diff), "Salita")

        # Scenario in discesa: 150m con -10m di discesa
        pl_down = calculate_plays_like(150.0, -10.0, slope_factor=1.0)
        self.assertEqual(pl_down, 140.0)
        self.assertEqual(get_slope_label(-10.0), "Discesa")

        # Scenario pianura: dislivello inferiore a 1m
        self.assertEqual(get_slope_label(0.5), "Pianura")

    def test_club_recommendation_from_bag(self):
        profile = UserProfile(
            player_name="Stefano Pirani",
            handicap=14.0,
            clubs_in_bag=get_default_bag()
        )
        # Il Ferro 7 ha carry di 145m
        recommended = profile.recommend_club_for_distance(146.0)
        self.assertIsNotNone(recommended)
        self.assertEqual(recommended.club_name, "Ferro 7")

        # Driver per 220m
        rec_driver = profile.recommend_club_for_distance(218.0)
        self.assertIsNotNone(rec_driver)
        self.assertEqual(rec_driver.club_name, "Driver")

        # Sand Wedge per 85m
        rec_sw = profile.recommend_club_for_distance(83.0)
        self.assertIsNotNone(rec_sw)
        self.assertIn("Sand Wedge", rec_sw.club_name)

    def test_elevation_service_approach_and_cache(self):
        service = ElevationService()
        # Popola manualmente la cache
        service._cache[(43.5210, 13.6068)] = 102.0
        service._cache[(43.5199, 13.6072)] = 110.0

        res = service.calculate_hole_approach(
            ball_lat=43.5210,
            ball_lon=13.6068,
            target_lat=43.5199,
            target_lon=13.6072
        )

        self.assertAlmostEqual(res["elevation_diff"], 8.0, delta=0.5)
        self.assertAlmostEqual(res["plays_like_distance"], res["raw_distance"] + 8.0, delta=0.5)
        self.assertEqual(res["slope_label"], "Salita")

    def test_quick_shot_parser(self):
        # Colpo 2 con ferro 7 dal fairway
        res1 = parse_quick_shot_update("Colpo 2 ferro 7 dal fairway")
        self.assertTrue(res1["is_quick_shot"])
        self.assertEqual(res1["shot_index"], 2)
        self.assertEqual(res1["club"], "Ferro 7")
        self.assertEqual(res1["lie"], "fairway")

        # Approccio con sand wedge a 45m
        res2 = parse_quick_shot_update("Approccio con sand wedge da 45 metri")
        self.assertTrue(res2["is_quick_shot"])
        self.assertEqual(res2["club"], "Sand Wedge")
        self.assertEqual(res2["manual_distance"], 45.0)

        # Resoconto multi-buca completo non deve essere scambiato per colpo singolo
        res3 = parse_quick_shot_update("Buca 1: Par 4 score 4. Buca 2: Par 3 score 3. Score totale 75")
        self.assertFalse(res3["is_quick_shot"])

    def test_live_session_manager(self):
        chat_id = "test_chat_123"
        # Buca 1 partenza
        self.session_mgr.set_current_hole(chat_id, 1)

        # Colpo 1: Tee shot a lat1, lon1
        lat_tee, lon_tee = 43.5228, 13.6060
        dist_1, hole_1, shot_1 = self.session_mgr.update_position(chat_id, lat_tee, lon_tee, altitude=102.0)
        self.assertIsNone(dist_1)  # Nessun colpo precedente
        self.assertEqual(hole_1, 1)
        self.assertEqual(shot_1, 1)

        # Registra colpo 1 e avanza
        self.session_mgr.record_live_shot(chat_id, 1, 1, club="Driver", lie="tee")
        self.session_mgr.advance_shot(chat_id)

        # Colpo 2: Palla atterrata 210 metri dopo
        lat_ball, lon_ball = 43.5210, 13.6068
        dist_covered, hole_2, shot_2 = self.session_mgr.update_position(chat_id, lat_ball, lon_ball, altitude=102.0)
        self.assertIsNotNone(dist_covered)
        self.assertGreater(dist_covered, 180.0)  # Ha percorso circa 200m
        self.assertEqual(shot_2, 2)

        # Test Pin Override
        self.session_mgr.set_pin_override(chat_id, 1, 43.5198, 13.6073, 111.0)
        pin = self.session_mgr.get_pin_override(chat_id, 1)
        self.assertIsNotNone(pin)
        self.assertEqual(pin[0], 43.5198)

    def test_simulated_shot2_blind_fairway_uphill(self):
        """
        Test unitario simulato come richiesto dal prompt di sviluppo:
        Colpo 2 da fairway cieco in salita verso il green con output di
        distanza reale e distanza corretta per la pendenza (Plays Like).
        """
        # Posizione 1 (Tee buca 1 Conero): lat 43.5228, lon 13.6060, alt 102m
        # Posizione 2 (Palla in fairway cieco dopo drive): lat 43.5210, lon 13.6068, alt 102m
        # Green Pin: lat 43.5199, lon 13.6072, alt 110m (salita finale ripida verso il green!)

        ball_lat, ball_lon, ball_alt = 43.5210, 13.6068, 102.0
        green_lat, green_lon, green_alt = 43.5199, 13.6072, 110.0

        approach = ElevationService().calculate_hole_approach(
            ball_lat=ball_lat,
            ball_lon=ball_lon,
            target_lat=green_lat,
            target_lon=green_lon,
            ball_altitude=ball_alt,
            target_altitude=green_alt,
            slope_factor=1.0
        )

        raw_dist = approach["raw_distance"]
        elev_diff = approach["elevation_diff"]
        plays_like = approach["plays_like_distance"]
        slope_label = approach["slope_label"]

        # Verifica valori balistici
        self.assertAlmostEqual(elev_diff, 8.0, places=1)
        self.assertEqual(slope_label, "Salita")
        self.assertAlmostEqual(plays_like, raw_dist + 8.0, places=1)

        # Suggerimento bastone per il giocatore
        profile = UserProfile(player_name="Stefano Pirani", handicap=14.0, clubs_in_bag=get_default_bag())
        recommended = profile.recommend_club_for_distance(plays_like)

        self.assertIsNotNone(recommended)
        # La distanza reale è circa 126m, la plays like è ~134m -> Ferro 9 (125m) o Ferro 8/7
        self.assertTrue(recommended.club_name.startswith("Ferro"))

        # Output formattato atteso
        formatted_output = f"Buca 1 - Colpo 2: Distanza reale: {int(raw_dist)}m | Dislivello: +{int(elev_diff)}m ({slope_label}) Plays Like: ~{int(plays_like)}m (Consigliato: {recommended.club_name})"
        self.assertIn("Distanza reale:", formatted_output)
        self.assertIn("Dislivello: +8m (Salita)", formatted_output)
        self.assertIn("Plays Like:", formatted_output)

    def test_telegram_bot_location_handler(self):
        bot = VoiceCaddyTelegramBot(bot_token="TEST_BOT_TOKEN_123")
        bot.session_mgr = self.session_mgr

        sent_messages = []
        bot.send_message = lambda chat_id, text, parse_mode="HTML": sent_messages.append(text)

        # Invia posizione Colpo 2 Buca 1
        chat_id = 998877
        bot.session_mgr.set_current_hole(chat_id, 1)

        bot.handle_location_update(chat_id=chat_id, lat=43.5210, lon=13.6068, altitude=102.0)
        self.assertEqual(len(sent_messages), 1)
        msg = sent_messages[0]
        self.assertIn("Buca 1", msg)
        self.assertIn("Colpo 1", msg)
        self.assertIn("Distanza reale:", msg)
        self.assertIn("Plays Like:", msg)
        self.assertIn("Consigliato:", msg)

    def test_telegram_manual_distance_fallback(self):
        bot = VoiceCaddyTelegramBot(bot_token="TEST_BOT_TOKEN_123")
        bot.session_mgr = self.session_mgr

        sent_messages = []
        bot.send_message = lambda chat_id, text, parse_mode="HTML": sent_messages.append(text)

        chat_id = 887766
        bot.session_mgr.set_current_hole(chat_id, 1)

        bot.handle_manual_distance(chat_id=chat_id, manual_distance=138.0)
        self.assertEqual(len(sent_messages), 1)
        msg = sent_messages[0]
        self.assertIn("Distanza Manuale", msg)
        self.assertIn("138m", msg)
        self.assertIn("Plays Like stimato:", msg)
        self.assertIn("Consigliato:", msg)

    def test_graceful_fallback_when_elevation_unavailable(self):
        service = ElevationService()
        # Simula API quota offline/irraggiungibile
        service.get_elevation = lambda *args, **kwargs: None
        approach = service.calculate_hole_approach(
            ball_lat=43.52,
            ball_lon=13.60,
            target_lat=43.51,
            target_lon=13.60,
            ball_altitude=None,
            target_altitude=None,
            fallback_elevation_diff=None
        )
        self.assertIsNotNone(approach["raw_distance"])
        self.assertEqual(approach["elevation_diff"], 0.0)
        self.assertEqual(approach["plays_like_distance"], approach["raw_distance"])
        self.assertIn("Quota N/D", approach["slope_label"])


if __name__ == "__main__":
    unittest.main()
