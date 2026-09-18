import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.schemas import HoleData, Shot, LieType, ShotResult, TargetLandingAnalysis
from core.visualizer import GolfHoleVisualizer, CONERO_HOLE_COORDINATES


class TestGolfHoleVisualizer(unittest.TestCase):
    def setUp(self):
        self.sample_hole = HoleData(
            hole_number=1,
            par=4,
            score=4,
            fairway_hit=True,
            gir=True,
            putts=2,
            shots=[
                Shot(
                    shot_index=1,
                    club="Driver",
                    distance_meters=225,
                    lie=LieType.TEE,
                    result=ShotResult.FAIRWAY,
                    notes="Bel drive diritto al centro"
                ),
                Shot(
                    shot_index=2,
                    club="Ferro 7",
                    distance_meters=115,
                    lie=LieType.FAIRWAY,
                    result=ShotResult.GREEN,
                    notes="In green a 4 metri dalla bandiera"
                ),
                Shot(
                    shot_index=3,
                    club="Putter",
                    distance_meters=4,
                    lie=LieType.GREEN,
                    result=ShotResult.GOOD,
                    notes="Primo putt dato"
                ),
                Shot(
                    shot_index=4,
                    club="Putter",
                    distance_meters=0.5,
                    lie=LieType.GREEN,
                    result=ShotResult.GOOD,
                    notes="Imbucato per il par"
                )
            ],
            target_landing_analysis=TargetLandingAnalysis(
                ideal_target_zone="Centro fairway 210-230m",
                actual_landing_zone="Centro fairway 225m",
                tactical_verdict="Bravo! Posizionamento Tattico Perfetto",
                caddie_tactical_note="Ottimo angolo di approccio al green."
            )
        )

    def test_authentic_map_conero_hole_1(self):
        """Test rendering with authentic Conero Golf Club image and calibration."""
        fig = GolfHoleVisualizer.create_hole_trajectory_map(
            self.sample_hole,
            course_id="conero_golf_club"
        )
        self.assertIsNotNone(fig)
        # Check that layout image is present
        self.assertTrue(hasattr(fig.layout, "images"))
        self.assertGreater(len(fig.layout.images), 0)
        # Check that title contains 'Disegno Ufficiale'
        self.assertIn("Disegno Ufficiale", fig.layout.title.text)

    def test_schematic_fallback_unknown_course(self):
        """Test fallback to schematic visualization when image is not present."""
        fig = GolfHoleVisualizer.create_hole_trajectory_map(
            self.sample_hole,
            course_id="campo_inesistente_xyz"
        )
        self.assertIsNotNone(fig)
        self.assertIn("Mappa Tattica Vettoriale", fig.layout.title.text)

    def test_all_conero_calibrated_holes(self):
        """Verify all 18 Conero holes are calibrated and render without error."""
        self.assertEqual(len(CONERO_HOLE_COORDINATES), 18)
        for h_num in range(1, 19):
            test_h = HoleData(
                hole_number=h_num,
                par=4 if h_num not in (2, 6, 13, 16) else 3,
                score=4,
                fairway_hit=True,
                gir=True,
                putts=1,
                shots=[]
            )
            fig = GolfHoleVisualizer.create_hole_trajectory_map(
                test_h,
                course_id="conero_golf_club"
            )
            self.assertIsNotNone(fig)


if __name__ == "__main__":
    unittest.main()
