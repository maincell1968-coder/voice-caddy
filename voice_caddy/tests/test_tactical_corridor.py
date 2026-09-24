"""
Test automatizzati per TacticalCourseManager, il Corridoio Tattico 3D su Piano Inclinato
e lo Spettro Balistico del Green (~50m diametro).
Conforme a SafeVault Policy: usa percorsi in memoria / temporanei e non tocca file utente.
"""

import unittest
from pathlib import Path

from core.tactical_course_manager import tactical_course_manager, TacticalHole
from core.schemas import Shot, LieType, ShotResult
from golf_strategy_ai.mapping.tactical_corridor_3d import render_tactical_corridor_html, render_green_spectrum_html


class TestTacticalCorridor(unittest.TestCase):

    def test_four_courses_loaded(self):
        """Verifica che tutti e 4 i campi descritti dall'utente siano caricati correttamente."""
        courses = tactical_course_manager.courses
        self.assertIn("conero_golf_club", courses)
        self.assertIn("torrenova_golf_club", courses)
        self.assertIn("riviera_golf_resort", courses)
        self.assertIn("golf_club_perugia", courses)

        self.assertEqual(courses["conero_golf_club"].holes_count, 18)
        self.assertEqual(courses["torrenova_golf_club"].holes_count, 9)
        self.assertEqual(courses["riviera_golf_resort"].holes_count, 18)
        self.assertEqual(courses["golf_club_perugia"].holes_count, 18)

    def test_landing_zones_depth_and_width(self):
        """
        Verifica che la fascia orizzontale della landing area abbia:
        - Centro sul punto landing
        - 20 metri in più verso la bandiera e 20 metri in meno verso il tee (40m totali)
        - Larghezza corrispondente al fairway della buca
        """
        h1 = tactical_course_manager.get_tactical_hole("conero_golf_club", 1)
        self.assertIsNotNone(h1)
        lz = tactical_course_manager.get_landing_zones_info(h1)
        self.assertGreaterEqual(len(lz), 1)

        z1 = lz[0]
        self.assertEqual(z1["depth_forward_m"], 20.0)
        self.assertEqual(z1["depth_backward_m"], 20.0)
        self.assertEqual(z1["total_depth_m"], 40.0)
        self.assertEqual(z1["width_m"], h1.fairway_width)

    def test_playing_line_waypoints(self):
        """Verifica che la playing line colleghi Tee -> Landing Area(s) -> Green."""
        h1 = tactical_course_manager.get_tactical_hole("conero_golf_club", 1)
        pts = tactical_course_manager.get_playing_line_waypoints(h1, tee_color="gialli")
        self.assertGreaterEqual(len(pts), 3)  # Tee, L1, Green
        self.assertEqual(pts[0], h1.tee_gialli)
        self.assertEqual(pts[1], h1.landing_1)
        self.assertEqual(pts[-1], h1.green_center)

    def test_shot_projection_and_colors(self):
        """
        Verifica che i colpi siano proiettati con i colori registrati autentici:
        - Fairway -> Verde Smeraldo (#10B981)
        - Green -> Ciano/Menta (#06B6D4)
        - Rough -> Ambra (#F59E0B)
        - Bunker -> Giallo Sabbia (#FBBF24)
        """
        h1 = tactical_course_manager.get_tactical_hole("conero_golf_club", 1)
        
        # Colpo 1: Drive in fairway
        shot1 = Shot(shot_index=1, club="Driver", distance_meters=220, lie=LieType.TEE, result=ShotResult.FAIRWAY)
        proj1 = tactical_course_manager.project_shot_along_corridor(h1, shot1)
        self.assertEqual(proj1["color"], "#10B981")
        self.assertEqual(proj1["dist_m"], 220.0)

        # Colpo 2: Ferro in rough a sinistra
        shot2 = Shot(shot_index=2, club="Ferro 6", distance_meters=140, lie=LieType.ROUGH, result=ShotResult.MISS_LEFT)
        proj2 = tactical_course_manager.project_shot_along_corridor(h1, shot2, prev_cumulative_dist=220.0)
        self.assertEqual(proj2["color"], "#F59E0B")
        self.assertLess(proj2["lateral_offset_m"], 0.0)  # a sinistra

        # Colpo 3: Uscita dal bunker al green
        shot3 = Shot(shot_index=3, club="Sand Wedge", distance_meters=20, lie=LieType.BUNKER, result=ShotResult.GREEN)
        proj3 = tactical_course_manager.project_shot_along_corridor(h1, shot3, prev_cumulative_dist=360.0)
        self.assertEqual(proj3["color"], "#06B6D4")

    def test_corridor_and_spectrum_html_rendering(self):
        """Verifica la generazione corretta del markup SVG/HTML per 3D corridor e spettro radar."""
        h1 = tactical_course_manager.get_tactical_hole("conero_golf_club", 1)
        shots = [
            Shot(shot_index=1, club="Driver", distance_meters=210, lie=LieType.TEE, result=ShotResult.FAIRWAY),
            Shot(shot_index=2, club="Ferro 7", distance_meters=108, lie=LieType.FAIRWAY, result=ShotResult.GREEN),
            Shot(shot_index=3, club="Putter", distance_meters=3.5, lie=LieType.GREEN, result=ShotResult.GOOD)
        ]

        html_corr = render_tactical_corridor_html(h1, shots=shots, tee_color="gialli")
        self.assertIn("turf-slab-3d", html_corr)
        self.assertIn("TARGET ZONE", html_corr)
        self.assertIn("PLAYING LINE", html_corr.upper())
        self.assertIn("GREEN (~50m)", html_corr)

        html_spec = render_green_spectrum_html(h1, shots=shots, tee_color="gialli")
        self.assertIn("Diagramma a Spettro", html_spec)
        self.assertIn("GIR", html_spec)
        self.assertIn("BACK-LEFT", html_spec)
        self.assertIn("FRONT-RIGHT", html_spec)


if __name__ == "__main__":
    unittest.main()
