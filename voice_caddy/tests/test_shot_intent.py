from __future__ import annotations

import unittest
from core.schemas import ShotIntent, Shot, HoleData, LieType, ShotResult, RoundInfo, PerformanceSummary, GolfRoundData, ProfessionalDiagnosis, StrokesLostBreakdown
from core.parser import infer_shot_intent, parse_quick_shot_update
from core.metrics import GolfMetricsCalculator


class TestShotIntentAndCourseManagement(unittest.TestCase):

    def test_bump_and_run_explicit_and_implicit(self):
        # 1. Esplicito tramite parole chiave
        res1 = infer_shot_intent(text="Approccio a correre con ferro 7", club="Ferro 7", distance_to_green=30.0)
        self.assertEqual(res1["intent"], ShotIntent.BUMP_AND_RUN)
        self.assertFalse(res1["is_recovery"])
        self.assertFalse(res1["is_layup"])

        # 2. Implicito: Ferro 6 giocato da 30 metri senza alcuna nota speciale (il caso sollevato dall'utente!)
        res2 = infer_shot_intent(text="", club="Ferro 6", lie="fairway", distance_to_green=30.0, shot_index=2)
        self.assertEqual(res2["intent"], ShotIntent.BUMP_AND_RUN)
        self.assertIn("Bump & Run", res2["intent_reason"])

    def test_recovery_punch_explicit_and_implicit(self):
        # 1. Esplicito: rami e alberi
        res1 = infer_shot_intent(text="Colpo basso sotto i rami per uscire dagli alberi", club="Ferro 5", lie="rough")
        self.assertEqual(res1["intent"], ShotIntent.RECOVERY_PUNCH)
        self.assertTrue(res1["is_recovery"])

        # 2. Esplicito: uscita laterale di sicurezza
        res2 = infer_shot_intent(text="Uscita laterale solo per uscire dal bosco", club="Ferro 8")
        self.assertEqual(res2["intent"], ShotIntent.ESCAPE_TROUBLE)
        self.assertTrue(res2["is_recovery"])

        # 3. Implicito: ferro medio da rough con distanza corta (55m)
        res3 = infer_shot_intent(text="", club="Ferro 5", lie="rough", distance_to_green=55.0, shot_index=2)
        self.assertEqual(res3["intent"], ShotIntent.RECOVERY_PUNCH)
        self.assertTrue(res3["is_recovery"])

    def test_layup_explicit_and_implicit(self):
        # 1. Esplicito: layup prima del lago
        res1 = infer_shot_intent(text="Layup conservativo prima dell'acqua", club="Ferro 6")
        self.assertEqual(res1["intent"], ShotIntent.LAYUP)
        self.assertTrue(res1["is_layup"])

        # 2. Implicito: secondo colpo su Par 5 con ferro 5
        res2 = infer_shot_intent(text="", club="Ferro 5", distance_to_green=160.0, shot_index=2, par=5)
        self.assertEqual(res2["intent"], ShotIntent.LAYUP)
        self.assertTrue(res2["is_layup"])

    def test_parse_quick_shot_update_with_intent(self):
        # Messaggio vocale breve in tempo reale
        quick = parse_quick_shot_update("Secondo colpo ferro 6 da 30 metri dal fairway")
        self.assertTrue(quick["is_quick_shot"])
        self.assertEqual(quick["club"], "Ferro 6")
        self.assertEqual(quick["manual_distance"], 30.0)
        self.assertEqual(quick["intent"], ShotIntent.BUMP_AND_RUN)

    def test_course_management_stats_calculation(self):
        shot1 = Shot(shot_index=1, club="Driver", distance_meters=220.0, lie=LieType.TEE, result=ShotResult.GOOD, intent=ShotIntent.TEE_SHOT)
        shot2_layup = Shot(shot_index=2, club="Ferro 6", distance_meters=150.0, lie=LieType.FAIRWAY, result=ShotResult.GOOD, intent=ShotIntent.LAYUP, is_layup=True)
        shot3_pitch = Shot(shot_index=3, club="Pitching Wedge", distance_meters=80.0, lie=LieType.FAIRWAY, result=ShotResult.GREEN, intent=ShotIntent.PITCH_FLOP)
        shot4_putt = Shot(shot_index=4, club="Putter", distance_meters=3.0, lie=LieType.GREEN, result=ShotResult.GOOD, intent=ShotIntent.FULL_SHOT)

        hole1 = HoleData(
            hole_number=1, par=5, score=4, putts=1, gir=True, received_strokes=1, net_score=3,
            shots=[shot1, shot2_layup, shot3_pitch, shot4_putt]
        )

        # Buca 2: con colpo di recovery
        shot_tee = Shot(shot_index=1, club="Driver", distance_meters=200.0, lie=LieType.TEE, result=ShotResult.SLICE, intent=ShotIntent.TEE_SHOT)
        shot_rec = Shot(shot_index=2, club="Ferro 7", distance_meters=60.0, lie=LieType.ROUGH, result=ShotResult.GOOD, intent=ShotIntent.RECOVERY_PUNCH, is_recovery=True)
        shot_app = Shot(shot_index=3, club="Ferro 8", distance_meters=30.0, lie=LieType.FAIRWAY, result=ShotResult.GREEN, intent=ShotIntent.BUMP_AND_RUN)
        shot_putt = Shot(shot_index=4, club="Putter", distance_meters=2.0, lie=LieType.GREEN, result=ShotResult.GOOD, intent=ShotIntent.FULL_SHOT)

        hole2 = HoleData(
            hole_number=2, par=4, score=4, putts=1, gir=False, received_strokes=0, net_score=4,
            shots=[shot_tee, shot_rec, shot_app, shot_putt]
        )

        cm = GolfMetricsCalculator.calculate_course_management_stats([hole1, hole2])
        self.assertEqual(cm.layups_count, 1)
        self.assertEqual(cm.recoveries_count, 1)
        self.assertEqual(cm.bump_and_runs_count, 1)
        # Buca 2 chiusa in Par (4 su Par 4) -> 100% recovery success
        self.assertEqual(cm.recovery_success_rate, 100.0)
        self.assertIn("Strategia Solida", cm.course_management_rating)

    def test_recompute_and_reconcile_populates_cm_stats(self):
        round_data = GolfRoundData(
            round_info=RoundInfo(course_name="Conero Golf Club", holes_played=1),
            holes=[
                HoleData(
                    hole_number=1, par=4, score=4, putts=2, gir=True, received_strokes=1,
                    shots=[
                        Shot(shot_index=1, club="Driver", lie=LieType.TEE, result=ShotResult.FAIRWAY, intent=ShotIntent.TEE_SHOT),
                        Shot(shot_index=2, club="Ferro 7", lie=LieType.FAIRWAY, distance_meters=30.0, result=ShotResult.GREEN, intent=ShotIntent.BUMP_AND_RUN),
                    ]
                )
            ],
            performance_summary=PerformanceSummary(
                total_score=4, total_putts=2, fairway_accuracy_pct=100.0, gir_pct=100.0, scrambling_pct=100.0,
                primary_miss_tendency="Nessun errore",
                professional_diagnosis=ProfessionalDiagnosis(
                    executive_narrative="Ottimo gioco", biggest_stroke_leak="Nessuno",
                    technical_vs_tactical_split="Strategia ottimale", course_management_score=95
                ),
                strokes_lost_breakdown=StrokesLostBreakdown(
                    tee_shots=0, approach_shots=0, short_game_around_green=0, putting=0, penalties=0
                ),
                training_drills_recommended=[]
            )
        )

        reconciled = GolfMetricsCalculator.recompute_and_reconcile(round_data)
        cm = reconciled.performance_summary.course_management_stats
        self.assertIsNotNone(cm)
        self.assertEqual(cm.bump_and_runs_count, 1)


if __name__ == "__main__":
    unittest.main()
