import unittest
import sys
from pathlib import Path

VOICE_CADDY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(VOICE_CADDY_DIR))

from core.whs_rules import (
    calculate_course_handicap,
    calculate_playing_handicap,
    allocate_hole_strokes,
    calculate_hole_score,
    compare_match_play_hole,
    build_round_handicap_profile,
    TeeRating,
    RoundHandicapProfile
)
from core.course import CONERO_GOLF_CLUB, TORRENOVA_GOLF_CLUB
from core.live_session import LiveSessionManager
from core.telegram_bot import VoiceCaddyTelegramBot
from core.telegram_config import TelegramConfigManager
import tempfile
import shutil


class TestWHSRulesAndHandicap(unittest.TestCase):
    """
    Test di conformità deterministica per il Modulo Regole WHS e Parametri Campi.
    """

    def test_official_prompt_whs_example(self):
        """
        Verifica fedele dell'esempio matematico fornito nel prompt:
        Exact HCP 18.4, CR 71.2, Slope 125, Par 72, Stableford 95%
        Course HCP = (18.4 * 125 / 113) + (71.2 - 72) = 20.35398 - 0.8 = 19.55398
        Playing HCP = Round(19.55 * 0.95) = Round(18.57) = 19 colpi.
        """
        exact_hcp = 18.4
        slope = 125
        cr = 71.2
        par = 72
        format_pct = 0.95

        # 1. Course HCP
        chcp = calculate_course_handicap(exact_hcp, slope, cr, par)
        self.assertAlmostEqual(chcp, 19.554, places=2)

        # 2. Playing HCP
        phcp = calculate_playing_handicap(chcp, format_pct)
        self.assertEqual(phcp, 19)

        # 3. Assegnazione Colpi buca per buca
        stroke_indices = {i: i for i in range(1, 19)}
        table = allocate_hole_strokes(phcp, stroke_indices, holes_count=18)

        # Buca con SI 1 riceve 2 colpi (1 base + 1 supplementare)
        self.assertEqual(table[1], 2)
        # Buche con SI da 2 a 18 ricevono 1 colpo base
        for si in range(2, 19):
            self.assertEqual(table[si], 1)

        # 4. Calcolo score a fine buca su Par 4 con 2 colpi ricevuti
        # Par Netto = 4 + 2 = 6
        # Se fa 5 colpi lordi: Stableford = max(0, 6 - 5 + 2) = 3 pt (Net Birdie)
        score_res = calculate_hole_score(hole_number=1, par=4, received_strokes=2, gross_strokes=5, stroke_index=1)
        self.assertEqual(score_res["net_par"], 6)
        self.assertEqual(score_res["net_strokes"], 3)
        self.assertEqual(score_res["stableford_points"], 3)
        self.assertEqual(score_res["score_label"], "Net Birdie")

        # Se fa 6 colpi lordi: Stableford = 2 pt (Net Par)
        par_score = calculate_hole_score(hole_number=1, par=4, received_strokes=2, gross_strokes=6, stroke_index=1)
        self.assertEqual(par_score["stableford_points"], 2)
        self.assertEqual(par_score["score_label"], "Net Par")

        # Se fa 7 colpi lordi: Stableford = 1 pt (Net Bogey)
        bogey_score = calculate_hole_score(hole_number=1, par=4, received_strokes=2, gross_strokes=7, stroke_index=1)
        self.assertEqual(bogey_score["stableford_points"], 1)
        self.assertEqual(bogey_score["score_label"], "Net Bogey")

        # Se fa 8 colpi lordi: Stableford = 0 pt
        double_score = calculate_hole_score(hole_number=1, par=4, received_strokes=2, gross_strokes=8, stroke_index=1)
        self.assertEqual(double_score["stableford_points"], 0)

        # Se fa 4 colpi lordi: Stableford = 4 pt (Net Eagle)
        eagle_score = calculate_hole_score(hole_number=1, par=4, received_strokes=2, gross_strokes=4, stroke_index=1)
        self.assertEqual(eagle_score["stableford_points"], 4)
        self.assertEqual(eagle_score["score_label"], "Net Eagle")

    def test_conero_golf_club_tees(self):
        """Verifica i parametri ufficiali dei Tee di Conero Golf Club."""
        conero = CONERO_GOLF_CLUB
        self.assertIn("bianchi", conero.tees)
        self.assertIn("gialli", conero.tees)
        self.assertIn("verdi", conero.tees)
        self.assertIn("rossi", conero.tees)
        self.assertIn("arancioni", conero.tees)

        gialli = conero.get_tee("gialli")
        self.assertIsNotNone(gialli)
        self.assertEqual(gialli.course_rating, 70.2)
        self.assertEqual(gialli.slope_rating, 129)
        self.assertEqual(gialli.par, 71)

        bianchi = conero.get_tee("bianchi")
        self.assertEqual(bianchi.course_rating, 71.4)
        self.assertEqual(bianchi.slope_rating, 131)

        rossi = conero.get_tee("rossi", gender="Donne")
        self.assertEqual(rossi.course_rating, 73.3)
        self.assertEqual(rossi.slope_rating, 125)

    def test_round_profile_builder_and_card(self):
        """Verifica la costruzione del RoundHandicapProfile e la formattazione della card."""
        tee = CONERO_GOLF_CLUB.get_tee("gialli")
        profile = build_round_handicap_profile(
            user_id="user_stefano",
            player_name="Stefano Pirani",
            exact_hcp=14.0,
            course_id="conero_golf_club",
            course_name="Conero Golf Club",
            tee_rating=tee,
            stroke_indices=CONERO_GOLF_CLUB.get_stroke_indices(),
            hole_pars=CONERO_GOLF_CLUB.get_hole_pars(),
            format_name="stableford"
        )
        self.assertEqual(profile.exact_hcp, 14.0)
        self.assertGreater(profile.playing_hcp, 0)
        self.assertEqual(len(profile.hole_strokes_table), 18)

        card = profile.format_summary_card()
        self.assertIn("SCHEDA HANDICAP WHS", card)
        self.assertIn("Stefano Pirani", card)
        self.assertIn("Course HCP:", card)
        self.assertIn("Playing HCP:", card)

    def test_torrenova_9_holes(self):
        """Verifica percorso 9 buche Torrenova Golf."""
        torrenova = TORRENOVA_GOLF_CLUB
        gialli_9 = torrenova.get_tee("gialli")
        self.assertIsNotNone(gialli_9)
        self.assertEqual(gialli_9.par, 34)
        self.assertEqual(gialli_9.course_rating, 34.9)
        self.assertEqual(gialli_9.slope_rating, 128)

        profile = build_round_handicap_profile(
            user_id="user_test",
            player_name="Test Golfer",
            exact_hcp=10.0,
            course_id=torrenova.course_id,
            course_name=torrenova.name,
            tee_rating=gialli_9,
            stroke_indices=torrenova.get_stroke_indices(),
            hole_pars=torrenova.get_hole_pars(),
            format_name="stableford"
        )
        self.assertEqual(profile.holes_count, 9)
        self.assertEqual(len(profile.hole_strokes_table), 9)

    def test_match_play_hole_comparison(self):
        """Verifica il confronto colpi netti buca per buca in Match Play."""
        # Giocatore 1 fa 5 lordo con 1 colpo ricevuto -> 4 netto
        # Giocatore 2 fa 4 lordo con 0 colpi ricevuti -> 4 netto
        # Risultato: Parità (halved -> 0)
        self.assertEqual(compare_match_play_hole(5, 1, 4, 0), 0)

        # Giocatore 1 fa 4 lordo con 1 colpo -> 3 netto
        # Giocatore 2 fa 4 lordo con 0 colpi -> 4 netto
        # Risultato: Vince Giocatore 1 (1)
        self.assertEqual(compare_match_play_hole(4, 1, 4, 0), 1)

        # Giocatore 1 fa 5 lordo con 0 colpi -> 5 netto
        # Giocatore 2 fa 5 lordo con 1 colpo -> 4 netto
        # Risultato: Vince Giocatore 2 (-1)
        self.assertEqual(compare_match_play_hole(5, 0, 5, 1), -1)


class TestTelegramWHSIntegration(unittest.TestCase):
    """Verifica l'integrazione del flusso WHS nel Bot Telegram."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.cfg_mgr = TelegramConfigManager(data_dir=self.test_dir)
        self.db_file = self.test_dir / "test_whs.db"
        self.session_mgr = LiveSessionManager(db_path=self.db_file)
        self.bot = VoiceCaddyTelegramBot(bot_token="TEST_DUMMY_TOKEN")
        self.bot.config_mgr = self.cfg_mgr
        self.bot.session_mgr = self.session_mgr

        # Mock API request per evitare chiamate di rete reali
        self.sent_messages = []
        self.bot._api_request = self._mock_api_request

        # Link utente
        self.cfg_mgr.link_chat_user(
            chat_id=12345,
            user_id="strafatti_stefano_pirani",
            group_name="strafatti",
            first_name="Stefano",
            active_course_name="Conero Golf Club"
        )

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _mock_api_request(self, method: str, data: dict = None) -> dict:
        if method == "sendMessage":
            self.sent_messages.append(data)
            return {"ok": True, "result": {"message_id": len(self.sent_messages)}}
        return {"ok": True, "result": {}}

    def test_start_round_flow_asks_for_tee(self):
        """Se il tee non è specificato all'avvio, il bot chiede 'Da quali tee parti oggi?'"""
        self.bot.start_round_flow(chat_id=12345)
        self.assertTrue(self.session_mgr.is_awaiting_tee_choice(12345))
        last_msg = self.sent_messages[-1]["text"]
        self.assertIn("Da quali tee parti oggi?", last_msg)

    def test_tee_selection_computes_whs_and_saves_profile(self):
        """Quando l'utente seleziona il tee, il bot calcola il WHS e memorizza il profilo."""
        # Seleziona Tee Gialli
        self.bot.process_text_message(12345, "🟡 Gialli")
        self.assertFalse(self.session_mgr.is_awaiting_tee_choice(12345))

        profile = self.session_mgr.get_handicap_profile(12345)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.tee_name.lower(), "gialli")
        self.assertEqual(profile.course_name, "Conero Golf Club")
        self.assertGreater(profile.playing_hcp, 0)
        self.assertEqual(len(profile.hole_strokes_table), 18)

        last_msg = self.sent_messages[-1]["text"]
        self.assertIn("SCHEDA HANDICAP WHS", last_msg)
        self.assertIn("Playing HCP:", last_msg)

    def test_command_whs(self):
        """Il comando /whs restituisce la scheda tecnica deterministica."""
        self.bot.handle_command(12345, "/whs")
        last_msg = self.sent_messages[-1]["text"]
        self.assertIn("SCHEDA HANDICAP WHS", last_msg)
        self.assertIn("Course HCP:", last_msg)

    def test_command_score_calculates_net_par_and_stableford(self):
        """Il comando /score [colpi] calcola Par Netto e Punti Stableford."""
        self.bot.handle_command(12345, "/score 4")
        last_msg = self.sent_messages[-1]["text"]
        self.assertIn("Buca 1 Conclusa!", last_msg)
        self.assertIn("Par Netto:", last_msg)
        self.assertIn("Punti Stableford:", last_msg)


if __name__ == "__main__":
    unittest.main()
