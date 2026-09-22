import unittest
from pathlib import Path

from golf_strategy_ai.models import HoleGeometry, PlayerCategory
from golf_strategy_ai.mapping.geojson_builder import load_hole_geometry_from_geojson
from golf_strategy_ai.strategy.hole_agent import HoleStrategyAgent, HolePerformanceEvaluation
from golf_strategy_ai.mapping.tactical_views import (
    render_view_a_map_html,
    render_view_b_benchmark_html,
    render_view_c_green_radar_html
)
from core.schemas import Shot, LieType, ShotResult


class TestHoleStrategyAgent(unittest.TestCase):
    """Test suite per l'Agente Strategico di Buca e le Viste Tattiche A, B, C."""

    def setUp(self):
        self.geojson_path = Path(__file__).resolve().parent.parent / "golf_strategy_ai" / "data" / "conero_hole1.geojson"
        self.assertTrue(self.geojson_path.exists())
        self.hole = load_hole_geometry_from_geojson(self.geojson_path)
        self.agent = HoleStrategyAgent()

    def test_compute_fairway_centerline(self):
        centerline, green_entry = self.agent.compute_fairway_centerline(self.hole, num_points=10)
        self.assertGreaterEqual(len(centerline), 10)
        self.assertAlmostEqual(centerline[0][0], self.hole.tee.lat, places=4)
        self.assertAlmostEqual(centerline[0][1], self.hole.tee.lon, places=4)
        self.assertIsNotNone(green_entry)
        self.assertEqual(len(green_entry), 2)

    def test_analyze_hole_multi_category(self):
        multi_strat = self.agent.analyze_hole(self.hole)
        self.assertEqual(multi_strat.hole_number, 1)
        self.assertEqual(multi_strat.par, 4)
        # Verifica che esistano piani per tutte e 3 le categorie
        self.assertIsNotNone(multi_strat.prima)
        self.assertIsNotNone(multi_strat.seconda)
        self.assertIsNotNone(multi_strat.terza)
        self.assertEqual(multi_strat.prima.category, PlayerCategory.PRIMA)
        self.assertEqual(multi_strat.seconda.category, PlayerCategory.SECONDA)
        self.assertEqual(multi_strat.terza.category, PlayerCategory.TERZA)
        # Verifica che il piano di 3a categoria contenga la strategia Bogey-Golf
        self.assertIn("Bogey-Golf", multi_strat.terza.caddy_strategy_text)

    def test_evaluate_played_hole_and_views(self):
        # Simulazione di colpi giocati su Par 4 (Drive in fairway, approccio a 4m dalla bandiera, 2 putt)
        shots = [
            Shot(shot_index=1, club="Driver", distance_meters=215.0, lie=LieType.FAIRWAY, result=ShotResult.GOOD),
            Shot(shot_index=2, club="Ferro 7", distance_meters=125.0, lie=LieType.GREEN, result=ShotResult.GOOD)
        ]

        perf_eval = self.agent.evaluate_played_hole(
            hole=self.hole,
            shots=shots,
            user_handicap=16.4,
            score=4,
            putts=2
        )

        self.assertEqual(perf_eval.hole_number, 1)
        self.assertEqual(perf_eval.player_category, PlayerCategory.SECONDA)
        self.assertEqual(len(perf_eval.shots_evaluations), 2)

        # Verifica valutazione Colpo 1 (Tee Shot)
        s1 = perf_eval.shots_evaluations[0]
        self.assertEqual(s1.shot_index, 1)
        self.assertIn(s1.distance_status, ["ottimale", "sopra_media", "corto"])
        self.assertIn(s1.lateral_status, ["centro_perfetto", "fairway_destro", "fairway_sinistro"])

        # Verifica valutazione Green & Approccio
        self.assertIsNotNone(perf_eval.green_evaluation)
        self.assertTrue(perf_eval.green_evaluation.on_green)
        self.assertGreater(perf_eval.green_evaluation.proximity_to_pin_m, 0.0)
        self.assertEqual(perf_eval.green_evaluation.putts_count, 2)

        # Test Rendering Vista A (Mappa Tracciato ①②③)
        html_a = render_view_a_map_html(self.hole, perf_eval=perf_eval)
        self.assertIn("<!DOCTYPE html>", html_a)
        self.assertIn("VISTA A: Tracciato Colpi ①②③", html_a)
        self.assertIn("Centerline", html_a)

        # Test Rendering Vista B (Benchmark & Dispersione)
        html_b = render_view_b_benchmark_html(perf_eval=perf_eval)
        self.assertIn("VISTA B: Benchmark di Categoria", html_b)
        self.assertIn("Seconda Categoria", html_b)
        self.assertIn("Scostamento Asse Centrale", html_b)

        # Test Rendering Vista C (Green Radar & Pin)
        html_c = render_view_c_green_radar_html(self.hole, app_eval=perf_eval.green_evaluation)
        self.assertIn("<!DOCTYPE html>", html_c)
        self.assertIn("VISTA C: Green Radar & Proximity", html_c)
        self.assertIn("dal Pin", html_c)


if __name__ == "__main__":
    unittest.main()
