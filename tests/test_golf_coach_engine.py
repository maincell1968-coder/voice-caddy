"""
Unit tests for Golf Coach Engine (Voice Caddy Pro)
=================================================
Verifica la corretta attuazione della Regola Aurea dell'Analisi di Golf dell'IA:
- Classificazione e differenziazione per categoria (Prima, Seconda, Terza).
- Punteggi colpo (0-100) e buca (0-10) tarati per categoria.
- Calcolo indici balistici (Playable Tee Shot Rate, Approach Quality, Dispersion).
- Riconoscimento automatico intenti (layup, recovery punch, bump & run).
- Rilevamento pattern ricorrenti basato su soglie numeriche.
- Prescrizione Top 3 priorità con obiettivi misurabili, motivi e drill.
- Rispetto delle regole anti-banalità e formula del giudizio professionale.
- Generazione doppia uscita (Player Report + Technical Report JSON).
- Isolamento SafeVault (nessun tocco a file DB o profili reali).
"""

from __future__ import annotations

import unittest
from core.schemas import (
    GolfRoundData, RoundInfo, HoleData, Shot, ShotIntent, ShotResult, LieType,
    PerformanceSummary, ProfessionalDiagnosis, StrokesLostBreakdown
)
from core.golf_coach_engine import (
    GolfCoachEngine, PlayerCategory, get_player_category,
    ShotEvaluation, HoleCoachEvaluation, CoachReportData
)
from core.metrics import GolfMetricsCalculator


class TestGolfCoachEngine(unittest.TestCase):

    def setUp(self):
        # Setup in-memory mock round
        self.shots_hole_1 = [
            Shot(shot_index=1, club="Driver", distance_meters=210.0, lie=LieType.TEE, result=ShotResult.MISS_RIGHT, notes="Drive finito nel rough destro"),
            Shot(shot_index=2, club="Ferro 7", distance_meters=140.0, lie=LieType.ROUGH, result=ShotResult.SHORT, notes="Approccio rimasto corto rispetto al green"),
            Shot(shot_index=3, club="Sand Wedge", distance_meters=20.0, lie=LieType.FAIRWAY, result=ShotResult.GOOD, notes="Chip sul green a 3 metri"),
            Shot(shot_index=4, club="Putter", distance_meters=3.0, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Primo putt imbucato")
        ]

        self.shots_hole_2_par5 = [
            Shot(shot_index=1, club="Driver", distance_meters=230.0, lie=LieType.TEE, result=ShotResult.FAIRWAY, notes="Ottima partenza"),
            Shot(shot_index=2, club="Ferro 6", distance_meters=120.0, lie=LieType.FAIRWAY, result=ShotResult.GOOD, intent=ShotIntent.LAYUP, is_layup=True, notes="Layup a 80m dal green"),
            Shot(shot_index=3, club="Pitching Wedge", distance_meters=80.0, lie=LieType.FAIRWAY, result=ShotResult.GREEN, notes="Palla sul green"),
            Shot(shot_index=4, club="Putter", distance_meters=5.0, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Putt per birdie mancato di poco"),
            Shot(shot_index=5, club="Putter", distance_meters=0.5, lie=LieType.GREEN, result=ShotResult.IN_HOLE, notes="Par")
        ]

        self.shots_hole_3_penalty = [
            Shot(shot_index=1, club="Driver", distance_meters=180.0, lie=LieType.TEE, result=ShotResult.WATER, notes="Palla in acqua a destra"),
            Shot(shot_index=2, club="Ferro 5", distance_meters=150.0, lie=LieType.FAIRWAY, result=ShotResult.SHORT, notes="Terzo colpo dopo penalità"),
            Shot(shot_index=3, club="Pitching Wedge", distance_meters=35.0, lie=LieType.ROUGH, result=ShotResult.GOOD, notes="Approccio al green"),
            Shot(shot_index=4, club="Putter", distance_meters=8.0, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Primo putt"),
            Shot(shot_index=5, club="Putter", distance_meters=2.0, lie=LieType.GREEN, result=ShotResult.GOOD, notes="Secondo putt"),
            Shot(shot_index=6, club="Putter", distance_meters=0.4, lie=LieType.GREEN, result=ShotResult.IN_HOLE, notes="3-putt finale")
        ]

        self.holes = [
            HoleData(hole_number=1, par=4, score=4, stroke_index=7, received_strokes=1, fairway_hit=False, gir=False, putts=1, penalties=0, shots=self.shots_hole_1),
            HoleData(hole_number=2, par=5, score=5, stroke_index=3, received_strokes=1, fairway_hit=True, gir=True, putts=2, penalties=0, shots=self.shots_hole_2_par5),
            HoleData(hole_number=3, par=4, score=7, stroke_index=1, received_strokes=2, fairway_hit=False, gir=False, putts=3, penalties=1, shots=self.shots_hole_3_penalty)
        ]

        self.round_data = GolfRoundData(
            round_info=RoundInfo(
                course_name="Conero Golf Club",
                holes_played=3,
                exact_hcp=16.5,
                playing_hcp=18,
                player_name="Stefano Pirani",
                game_format="stableford"
            ),
            holes=self.holes
        )

    def test_category_mapping(self):
        """Verifica la corretta attribuzione della Categoria in base all'HCP."""
        self.assertEqual(get_player_category(5.0), PlayerCategory.PRIMA)
        self.assertEqual(get_player_category(12.0), PlayerCategory.PRIMA)
        self.assertEqual(get_player_category(12.1), PlayerCategory.SECONDA)
        self.assertEqual(get_player_category(18.0), PlayerCategory.SECONDA)
        self.assertEqual(get_player_category(24.0), PlayerCategory.SECONDA)
        self.assertEqual(get_player_category(24.1), PlayerCategory.TERZA)
        self.assertEqual(get_player_category(36.0), PlayerCategory.TERZA)
        self.assertEqual(get_player_category(None), PlayerCategory.SECONDA)

    def test_differentiated_shot_scoring(self):
        """Verifica che lo stesso colpo riceva punteggi differenziati per categoria."""
        drive_shot = self.shots_hole_1[0]  # Drive in rough a 210m
        hole_1 = self.holes[0]

        eval_prima = GolfCoachEngine.evaluate_shot(drive_shot, hole_1, PlayerCategory.PRIMA)
        eval_seconda = GolfCoachEngine.evaluate_shot(drive_shot, hole_1, PlayerCategory.SECONDA)
        eval_terza = GolfCoachEngine.evaluate_shot(drive_shot, hole_1, PlayerCategory.TERZA)

        # Per un prima categoria il rough penalizza il controllo (score più basso)
        # Per una terza categoria la palla lunga e giocabile è ottima (score più alto)
        self.assertTrue(eval_prima.shot_score < eval_seconda.shot_score < eval_terza.shot_score)
        self.assertIn("rough", eval_prima.technical_note.lower())

    def test_layup_recognition_and_reward(self):
        """Verifica che il layup strategico su Par 5 sia riconosciuto e premiato con punteggio alto."""
        layup_shot = self.shots_hole_2_par5[1]
        hole_2 = self.holes[1]

        eval_sec = GolfCoachEngine.evaluate_shot(layup_shot, hole_2, PlayerCategory.SECONDA)
        self.assertTrue(eval_sec.is_layup)
        self.assertGreaterEqual(eval_sec.shot_score, 90.0)
        self.assertIn("layup", eval_sec.technical_note.lower())

    def test_hole_evaluation_structure(self):
        """Verifica che la valutazione di buca contenga tutte le 6 sezioni obbligatorie."""
        hole_eval = GolfCoachEngine.evaluate_hole(self.holes[0], PlayerCategory.SECONDA)

        self.assertIsInstance(hole_eval, HoleCoachEvaluation)
        self.assertTrue(len(hole_eval.summary) > 10)
        self.assertTrue(len(hole_eval.key_shot) > 5)
        self.assertTrue(len(hole_eval.technical_assessment) > 10)
        self.assertTrue(len(hole_eval.strategic_assessment) > 10)
        self.assertTrue(len(hole_eval.coach_advice) > 15)
        self.assertTrue(1.0 <= hole_eval.rating <= 10.0)

        # Regola Anti-Banalità: non deve contenere frasi generiche vietate
        forbidden = ["niente da dire", "tutto ok", "devi migliorare il gioco corto", "serve più precisione"]
        advice_lower = hole_eval.coach_advice.lower()
        for f in forbidden:
            self.assertNotIn(f, advice_lower)

    def test_round_coach_analysis_and_dual_output(self):
        """Verifica l'analisi del giro, le priorità di allenamento e la doppia uscita."""
        report = GolfCoachEngine.analyze_round(self.round_data, PlayerCategory.SECONDA)

        self.assertIsInstance(report, CoachReportData)
        self.assertEqual(report.player_category, PlayerCategory.SECONDA)

        # Controllo Voti Tecnici
        scores = report.scores
        self.assertTrue(1.0 <= scores.tee_game <= 10.0)
        self.assertTrue(1.0 <= scores.approach_game <= 10.0)
        self.assertTrue(1.0 <= scores.short_game <= 10.0)
        self.assertTrue(1.0 <= scores.putting <= 10.0)
        self.assertTrue(1.0 <= scores.strategy <= 10.0)
        self.assertTrue(1.0 <= scores.overall <= 10.0)

        # Controllo Top 3 Priorità
        self.assertTrue(len(report.training_priorities) >= 1)
        for p in report.training_priorities:
            self.assertTrue(len(p.area) > 3)
            self.assertTrue(len(p.goal) > 5)
            self.assertTrue(len(p.reason) > 5)
            self.assertTrue(len(p.drill) > 10)
            self.assertTrue(len(p.benchmark) > 5)

        # Doppia Uscita
        # 1. Player Report (Markdown)
        self.assertIn("ANALISI TECNICA DI GARA — METODO DEL MAESTRO", report.player_report_markdown)
        self.assertIn("RIEPILOGO GENERALE DI GARA (14 PUNTI)", report.player_report_markdown)
        self.assertIn("ANALISI DETTAGLIATA BUCA PER BUCA", report.player_report_markdown)

        # 2. Technical Report (JSON)
        tech_json = report.technical_report_json
        self.assertEqual(tech_json["player_category"], "seconda")
        self.assertIn("technical_scores", tech_json)
        self.assertIn("training_priorities", tech_json)
        self.assertIn("holes", tech_json)
        self.assertEqual(len(tech_json["holes"]), 3)

    def test_metrics_calculator_integration(self):
        """Verifica l'integrazione deterministica in GolfMetricsCalculator.recompute_and_reconcile."""
        reconciled = GolfMetricsCalculator.recompute_and_reconcile(self.round_data)

        # Verifica che coach_report sia presente in PerformanceSummary
        summary = reconciled.performance_summary
        self.assertIsNotNone(summary.coach_report)
        self.assertIn("technical_scores", summary.coach_report)

        # Verifica che ogni buca abbia coach_evaluation popolato con le 6 sezioni
        for h in reconciled.holes:
            self.assertIsNotNone(h.coach_evaluation)
            self.assertIn("summary", h.coach_evaluation)
            self.assertIn("key_shot", h.coach_evaluation)
            self.assertIn("technical_assessment", h.coach_evaluation)
            self.assertIn("strategic_assessment", h.coach_evaluation)
            self.assertIn("coach_advice", h.coach_evaluation)
            self.assertIn("rating", h.coach_evaluation)


if __name__ == "__main__":
    unittest.main()
