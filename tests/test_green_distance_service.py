import unittest
import sys
import time
from pathlib import Path

VOICE_CADDY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(VOICE_CADDY_DIR))

from core.green_distance_service import (
    calculate_geodetic_distance,
    derive_front_back_green_points,
    parse_green_distance_intent,
    calculate_green_distances,
    format_distance_response,
    GeoPoint,
    GreenCoordinates
)
from core.course import CONERO_GOLF_CLUB, TORRENOVA_GOLF_CLUB
from core.live_session import LiveSessionManager
from core.telegram_bot import VoiceCaddyTelegramBot
from core.telegram_config import TelegramConfigManager
import tempfile
import shutil


class TestGreenDistanceService(unittest.TestCase):
    """
    Test suite per il calcolo delle distanze geodetiche del green (Front, Center, Back)
    ed estrazione dell'intento vocale/testuale con gestione edge cases.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_voice_caddy.db"
        self.session_mgr = LiveSessionManager(db_path=self.db_path)

        # Mock Bot
        self.bot = VoiceCaddyTelegramBot(bot_token="TEST_BOT_TOKEN")
        self.bot.session_mgr = self.session_mgr
        self.sent_messages = []
        self.bot.send_message = lambda chat_id, text, reply_markup=None: self.sent_messages.append({"chat_id": chat_id, "text": text})

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_haversine_distance_accuracy(self):
        """Verifica che la formula di Haversine usi R=6371000m e arrotondi all'intero."""
        # Due punti noti: Conero Tee Buca 1 (43.5228, 13.6060) e Green Buca 1 (43.5199, 13.6072)
        dist = calculate_geodetic_distance(43.5228, 13.6060, 43.5199, 13.6072)
        self.assertEqual(dist, 337)

        # Stesso punto = 0 metri
        self.assertEqual(calculate_geodetic_distance(43.5199, 13.6072, 43.5199, 13.6072), 0)

    def test_derive_front_back_green_points(self):
        """Verifica che Front e Back siano calcolati sulla retta di approccio con offset corretto."""
        tee_lat, tee_lon = 43.5228, 13.6060
        center_lat, center_lon = 43.5199, 13.6072

        f_pt, b_pt = derive_front_back_green_points(tee_lat, tee_lon, center_lat, center_lon, front_offset_meters=12, back_offset_meters=12)

        dist_to_front = calculate_geodetic_distance(tee_lat, tee_lon, f_pt.lat, f_pt.lon)
        dist_to_center = calculate_geodetic_distance(tee_lat, tee_lon, center_lat, center_lon)
        dist_to_back = calculate_geodetic_distance(tee_lat, tee_lon, b_pt.lat, b_pt.lon)

        self.assertEqual(dist_to_front, 325)
        self.assertEqual(dist_to_center, 337)
        self.assertEqual(dist_to_back, 349)
        self.assertLess(dist_to_front, dist_to_center)
        self.assertLess(dist_to_center, dist_to_back)

    def test_intent_recognition_rapid(self):
        """Verifica i trigger per la MODALITÀ STANDARD (Distanza Rapida - solo Centro)."""
        rapid_queries = [
            "Distanza?",
            "Quanto ho?",
            "Quanto manca?",
            "Che distanza c'è?",
            "Distanza green",
            "/distanza"
        ]
        for q in rapid_queries:
            intent = parse_green_distance_intent(q)
            self.assertEqual(intent, "DISTANZA_RAPIDA", f"Fallito su query: '{q}'")

    def test_intent_recognition_detailed(self):
        """Verifica i trigger per la MODALITÀ SU RICHIESTA (Dettagliata - Front, Center, Back)."""
        detailed_queries = [
            "Misure green",
            "Dettaglio green",
            "Quanto ho all'inizio?",
            "Front e back",
            "Distanze complete",
            "/green"
        ]
        for q in detailed_queries:
            intent = parse_green_distance_intent(q)
            self.assertEqual(intent, "DISTANZA_DETTAGLIATA", f"Fallito su query: '{q}'")

    def test_calculate_green_distances_modalities(self):
        """Verifica il calcolo delle distanze e la formattazione dei messaggi testo e voce."""
        green_coords = GreenCoordinates(
            front=GeoPoint(lat=43.520003, lon=13.607157),
            center=GeoPoint(lat=43.519900, lon=13.607200),
            back=GeoPoint(lat=43.519797, lon=13.607243)
        )
        user_lat, user_lon = 43.52115, 13.6066  # ~140m dal centro
        now = time.time()

        res = calculate_green_distances(user_lat, user_lon, green_coords, hole_number=1, location_timestamp=now)

        # 1. Test Risposta Rapida
        t_rapid, v_rapid = format_distance_response("DISTANZA_RAPIDA", res, hole_number=1)
        self.assertIn("al centro green", t_rapid)
        self.assertIn(f"{res.center_distance} metri al centro.", v_rapid)

        # 2. Test Risposta Dettagliata
        t_det, v_det = format_distance_response("DISTANZA_DETTAGLIATA", res, hole_number=1)
        self.assertIn("Misure Green", t_det)
        self.assertIn("Inizio (Front)", t_det)
        self.assertIn("Centro (Center)", t_det)
        self.assertIn("Fondo (Back)", t_det)
        self.assertEqual(v_det, f"Inizio {res.front_distance}, centro {res.center_distance}, fondo {res.back_distance} metri.")

    def test_edge_case_stale_gps_location(self):
        """Se il GPS ha più di 2 minuti (> 120s), avvisa l'utente."""
        green_coords = GreenCoordinates(
            front=GeoPoint(lat=43.520003, lon=13.607157),
            center=GeoPoint(lat=43.519900, lon=13.607200),
            back=GeoPoint(lat=43.519797, lon=13.607243)
        )
        stale_time = time.time() - 180  # 3 minuti fa
        res = calculate_green_distances(43.52115, 13.6066, green_coords, location_timestamp=stale_time)

        self.assertTrue(res.is_location_stale)
        t_msg, v_msg = format_distance_response("DISTANZA_RAPIDA", res, hole_number=1)
        self.assertIn("Posizione GPS non aggiornata", t_msg)
        self.assertIn("Posizione GPS non aggiornata da più di due minuti", v_msg)

    def test_edge_case_missing_gps_location(self):
        """Se non c'è posizione GPS attiva, richiede l'invio della posizione."""
        green_coords = GreenCoordinates(
            front=GeoPoint(lat=43.520003, lon=13.607157),
            center=GeoPoint(lat=43.519900, lon=13.607200),
            back=GeoPoint(lat=43.519797, lon=13.607243)
        )
        res = calculate_green_distances(None, None, green_coords)
        self.assertFalse(res.has_location)

        t_msg, v_msg = format_distance_response("DISTANZA_RAPIDA", res, hole_number=1)
        self.assertIn("Posizione GPS non attiva", t_msg)
        self.assertIn("Posizione GPS non attiva. Invia la posizione", v_msg)

    def test_edge_case_on_green_proximity(self):
        """Se l'utente è entro 15 metri dal green, segnala che è già arrivato al green."""
        green_coords = GreenCoordinates(
            front=GeoPoint(lat=43.51995, lon=13.60718),
            center=GeoPoint(lat=43.51990, lon=13.60720),
            back=GeoPoint(lat=43.51985, lon=13.60722)
        )
        # Posizione a 8 metri dal centro green
        ball_lat, ball_lon = 43.51996, 13.60720
        res = calculate_green_distances(ball_lat, ball_lon, green_coords, location_timestamp=time.time())

        self.assertTrue(res.is_on_green)
        t_msg, v_msg = format_distance_response("DISTANZA_RAPIDA", res, hole_number=1)
        self.assertIn("Sei sul Green", t_msg)
        self.assertIn("Sei sul green, distanza centro", v_msg)

    def test_telegram_bot_green_distance_integration(self):
        """Verifica l'interazione end-to-end con il bot Telegram."""
        # 1. Simula arrivo posizione GPS recente
        self.session_mgr.update_position(12345, 43.5215, 13.6065)

        # 2. Richiesta rapida testuale
        self.bot.process_text_message(12345, "Quanto ho?")
        last_msg = self.sent_messages[-1]["text"]
        self.assertIn("al centro green", last_msg)

        # 3. Richiesta dettagliata testuale
        self.bot.process_text_message(12345, "Misure green")
        last_msg = self.sent_messages[-1]["text"]
        self.assertIn("Misure Green — Buca 1", last_msg)
        self.assertIn("Inizio (Front):", last_msg)
        self.assertIn("Centro (Center):", last_msg)
        self.assertIn("Fondo (Back):", last_msg)


if __name__ == "__main__":
    unittest.main()
