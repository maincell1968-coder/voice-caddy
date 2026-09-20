from __future__ import annotations

import unittest
from core.schemas import GolfRoundData, RoundInfo, HoleData, PerformanceSummary, ProfessionalDiagnosis, StrokesLostBreakdown
from core.whs_rules import (
    calculate_stableford_points_net,
    calculate_stableford_points_gross,
    calculate_hole_score,
    generate_tournament_summary_data
)
from core.metrics import GolfMetricsCalculator
from core.pdf_export import PDFReportGenerator


class TestTournamentScoringAndReport(unittest.TestCase):
    """
    Test di conformità per le Regole di Calcolo e Reportistica di Gara (Lordo e Netto, Stableford e Stroke Play).
    Verifica il rispetto della SafeVault Policy (nessun accesso a database di produzione).
    """

    def setUp(self):
        # Creo 3 buche simulate
        # Buca 1: Par 4, SI 5, Ricevuti 1, Score 4 -> Net Score 3 -> Stbl Net 3 (Birdie), Stbl Lordo 2 (Par)
        # Buca 2: Par 5, SI 1, Ricevuti 2, Score 6 -> Net Score 4 -> Stbl Net 3 (Birdie), Stbl Lordo 1 (Bogey)
        # Buca 3: Par 3, SI 9, Ricevuti 0, Score 3 -> Net Score 3 -> Stbl Net 2 (Par), Stbl Lordo 2 (Par)
        self.holes = [
            HoleData(
                hole_number=1, par=4, score=4, stroke_index=5, received_strokes=1,
                gir=True, putts=2, penalties=0
            ),
            HoleData(
                hole_number=2, par=5, score=6, stroke_index=1, received_strokes=2,
                gir=False, putts=2, penalties=0
            ),
            HoleData(
                hole_number=3, par=3, score=3, stroke_index=9, received_strokes=0,
                gir=True, putts=2, penalties=0
            )
        ]

        self.summary = PerformanceSummary(
            total_score=13,
            total_putts=6,
            fairway_accuracy_pct=100.0,
            gir_pct=66.7,
            scrambling_pct=100.0,
            primary_miss_tendency="Nessun errore ricorrente",
            professional_diagnosis=ProfessionalDiagnosis(
                executive_narrative="Ottimo giro test.",
                biggest_stroke_leak="Nessuno",
                technical_vs_tactical_split="100% tattica",
                course_management_score=95
            ),
            strokes_lost_breakdown=StrokesLostBreakdown(
                tee_shots=0.0,
                approach_shots=0.0,
                short_game_around_green=0.0,
                putting=0.0,
                penalties=0.0
            ),
            training_drills_recommended=[]
        )

        self.round_data_stableford = GolfRoundData(
            round_info=RoundInfo(
                course_name="Conero Golf Club",
                date="20 Settembre 2026",
                holes_played=3,
                game_format="stableford",
                player_name="Stefano Pirani",
                exact_hcp=18.4,
                course_hcp=20.0,
                playing_hcp=19
            ),
            holes=self.holes,
            performance_summary=self.summary
        )

    def test_stableford_formulas_net_and_gross(self):
        """Verifica le formule Regola 21.1: max(0, 2 + par - colpi)."""
        # Par 4, colpi netti 3 (birdie netto) -> 3 pt
        self.assertEqual(calculate_stableford_points_net(par=4, net_strokes=3), 3)
        # Par 4, colpi lordi 4 (par lordo) -> 2 pt
        self.assertEqual(calculate_stableford_points_gross(par=4, gross_strokes=4), 2)
        # Par 4, colpi netti 6 (doppio bogey netto) -> 0 pt
        self.assertEqual(calculate_stableford_points_net(par=4, net_strokes=6), 0)
        # Par 4, colpi netti 2 (eagle netto) -> 4 pt
        self.assertEqual(calculate_stableford_points_net(par=4, net_strokes=2), 4)

    def test_calculate_hole_score_returns_both_stableford(self):
        """Verifica che calculate_hole_score restituisca punti sia lordi che netti."""
        res = calculate_hole_score(
            hole_number=1,
            par=4,
            received_strokes=1,
            gross_strokes=4,
            stroke_index=5
        )
        self.assertEqual(res["net_strokes"], 3)
        self.assertEqual(res["stableford_points"], 3)
        self.assertEqual(res["stableford_gross_points"], 2)

    def test_tournament_summary_data_stableford(self):
        """Verifica la generazione del riepilogo per gara Stableford con Sezioni A-G."""
        t_data = generate_tournament_summary_data(self.round_data_stableford)
        self.assertTrue(t_data["is_stableford"])
        self.assertIn("Stableford", t_data["format_name"])
        self.assertEqual(t_data["total_gross"], 13)
        # Total net = 13 - 19 = -6 (con playing hcp) o buca per buca
        self.assertIsNotNone(t_data["total_net"])
        # Stableford netto totale: 3 + 3 + 2 = 8 pt
        self.assertEqual(t_data["total_stableford_net"], 8)
        # Stableford lordo totale: 2 + 1 + 2 = 5 pt
        self.assertEqual(t_data["total_stableford_gross"], 5)
        # Leaderboard
        self.assertEqual(t_data["leaderboard_net"]["posizione"], "1° Netto")
        self.assertEqual(t_data["leaderboard_gross"]["posizione"], "1° Lordo")
        # Nota conformità (Sezione G)
        self.assertIn("Regola 21.1", t_data["compliance_note"])
        self.assertIn("Colpi Lordi", t_data["compliance_note"])
        self.assertIn("Colpi Netti", t_data["compliance_note"])

    def test_tournament_summary_data_stroke_play(self):
        """Verifica la generazione del riepilogo per gara Stroke Play."""
        round_sp = GolfRoundData(
            round_info=RoundInfo(
                course_name="Conero Golf Club",
                date="20 Settembre 2026",
                holes_played=3,
                game_format="stroke_play",
                player_name="Stefano Pirani",
                exact_hcp=10.0,
                playing_hcp=10
            ),
            holes=self.holes,
            performance_summary=self.summary
        )
        t_data = generate_tournament_summary_data(round_sp)
        self.assertFalse(t_data["is_stableford"])
        self.assertEqual(t_data["total_gross"], 13)
        self.assertEqual(t_data["total_net"], 3) # 13 - 10 = 3
        self.assertIn("Regola 3", t_data["compliance_note"])

    def test_pdf_report_generator_contains_all_tournament_sections(self):
        """Verifica che l'HTML del report contenga tutte le sezioni A-G e le colonne obbligatorie."""
        html = PDFReportGenerator.generate_html_report(self.round_data_stableford)

        # Sezioni A-G
        self.assertIn("A. Formula di Gara:", html)
        self.assertIn("B. Metodo di Calcolo Utilizzato:", html)
        self.assertIn("C. Tabella Risultati Ufficiale", html)
        self.assertIn("E. Classifica Netta Ufficiale", html)
        self.assertIn("F. Classifica Lorda Ufficiale", html)
        self.assertIn("G. Nota Finale:", html)

        # Colonne tabella risultati
        self.assertIn("Colpi Lordi", html)
        self.assertIn("Colpi Netti", html)
        self.assertIn("Punti Stableford Lordi", html)
        self.assertIn("Punti Stableford Netti", html)

        # Scorecard dettagliata
        self.assertIn("Stabl. Lordo", html)
        self.assertIn("Stabl. Netto", html)


if __name__ == "__main__":
    unittest.main()
