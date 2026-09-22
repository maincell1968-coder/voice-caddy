import unittest
from pathlib import Path

from golf_strategy_ai.models import (
    PlayerCategory,
    LieCategory,
    ShotQuality,
    GeoPoint,
    HoleGeometry,
    NormalizedShot,
    ShotRecord
)
from golf_strategy_ai.club_profiles import (
    estimate_category_from_handicap,
    get_category_profile,
    rank_clubs_for_shot
)
from golf_strategy_ai.geo.projection import to_utm, from_utm
from golf_strategy_ai.geo.geometry import (
    haversine_distance_m,
    bearing_deg,
    calculate_progress_and_offset,
    point_in_polygon
)
from golf_strategy_ai.analysis.shot_metrics import classify_lie, normalize_shot
from golf_strategy_ai.analysis.dispersion import calculate_dispersion, build_dispersion_ellipse
from golf_strategy_ai.strategy.scoring import (
    calculate_strategic_position_score,
    calculate_dispersion_risk_score,
    calculate_gir_opportunity_score
)
from golf_strategy_ai.strategy.recommendations import analyze_hole_strategy, recommend_clubs_for_hole
from golf_strategy_ai.mapping.geojson_builder import load_hole_geometry_from_geojson, build_hole_geojson
from golf_strategy_ai.mapping.folium_renderer import render_hole_map_html


class TestGolfStrategyAI(unittest.TestCase):
    """Test suite completa per il modulo Golf Strategy AI."""

    def setUp(self):
        self.geojson_path = Path(__file__).resolve().parent.parent / "golf_strategy_ai" / "data" / "conero_hole1.geojson"
        self.assertTrue(self.geojson_path.exists(), f"File non trovato: {self.geojson_path}")
        self.hole = load_hole_geometry_from_geojson(self.geojson_path)

    # 1. Test Categorie & Profili Bastoni
    def test_estimate_category_from_handicap(self):
        self.assertEqual(estimate_category_from_handicap(0.0), PlayerCategory.PRIMA)
        self.assertEqual(estimate_category_from_handicap(8.5), PlayerCategory.PRIMA)
        self.assertEqual(estimate_category_from_handicap(12.0), PlayerCategory.PRIMA)
        self.assertEqual(estimate_category_from_handicap(12.1), PlayerCategory.SECONDA)
        self.assertEqual(estimate_category_from_handicap(20.0), PlayerCategory.SECONDA)
        self.assertEqual(estimate_category_from_handicap(26.0), PlayerCategory.SECONDA)
        self.assertEqual(estimate_category_from_handicap(26.1), PlayerCategory.TERZA)
        self.assertEqual(estimate_category_from_handicap(54.0), PlayerCategory.TERZA)

    def test_category_profiles_completeness(self):
        for cat in [PlayerCategory.PRIMA, PlayerCategory.SECONDA, PlayerCategory.TERZA]:
            prof = get_category_profile(cat)
            self.assertGreaterEqual(len(prof.clubs), 10)
            self.assertIn("driver", prof.clubs)
            self.assertIn("iron_7", prof.clubs)
            self.assertIn("pitching_wedge", prof.clubs)
            # Verifica che le distanze decrescano logicamente
            self.assertGreater(prof.clubs["driver"].carry_mean_m, prof.clubs["iron_7"].carry_mean_m)
            self.assertGreater(prof.clubs["iron_7"].carry_mean_m, prof.clubs["pitching_wedge"].carry_mean_m)

    def test_rank_clubs_for_shot(self):
        ranked = rank_clubs_for_shot(
            required_total_m=150.0,
            required_carry_m=145.0,
            landing_zone_width_m=25.0,
            category=PlayerCategory.PRIMA
        )
        self.assertGreater(len(ranked), 0)
        top_club = ranked[0]
        self.assertIn("club_id", top_club)
        self.assertIn("suitability_score", top_club)
        self.assertGreaterEqual(top_club["suitability_score"], 70.0)

    # 2. Test Motore Geodetico & UTM
    def test_utm_roundtrip_precision(self):
        lat, lon = 43.5228, 13.6060
        easting, northing, zone, hem = to_utm(lat, lon)
        self.assertEqual(zone, 33)
        self.assertEqual(hem, "N")
        lat_back, lon_back = from_utm(easting, northing, zone, hem)
        self.assertAlmostEqual(lat, lat_back, places=5)
        self.assertAlmostEqual(lon, lon_back, places=5)

    def test_haversine_distance_and_bearing(self):
        dist = haversine_distance_m(self.hole.tee.lat, self.hole.tee.lon, self.hole.green_center.lat, self.hole.green_center.lon)
        self.assertGreater(dist, 320.0)
        self.assertLess(dist, 360.0)
        brng = bearing_deg(self.hole.tee.lat, self.hole.tee.lon, self.hole.green_center.lat, self.hole.green_center.lon)
        self.assertGreater(brng, 150.0)
        self.assertLess(brng, 175.0)

    def test_calculate_progress_and_offset(self):
        # Punto sul tee: progress ~ 0, lateral offset ~ 0
        prog, lat_off = calculate_progress_and_offset(
            self.hole.tee.lat, self.hole.tee.lon,
            self.hole.tee.lat, self.hole.tee.lon,
            self.hole.green_center.lat, self.hole.green_center.lon
        )
        self.assertAlmostEqual(prog, 0.0, delta=1.0)
        self.assertAlmostEqual(lat_off, 0.0, delta=1.0)

        # Punto sul green: progress ~ hole length, offset ~ 0
        prog_g, lat_off_g = calculate_progress_and_offset(
            self.hole.green_center.lat, self.hole.green_center.lon,
            self.hole.tee.lat, self.hole.tee.lon,
            self.hole.green_center.lat, self.hole.green_center.lon
        )
        self.assertAlmostEqual(prog_g, self.hole.length_m, delta=15.0)
        self.assertAlmostEqual(lat_off_g, 0.0, delta=1.0)

    def test_point_in_polygon(self):
        poly = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        self.assertTrue(point_in_polygon(5.0, 5.0, poly))
        self.assertFalse(point_in_polygon(15.0, 5.0, poly))
        self.assertFalse(point_in_polygon(-1.0, 5.0, poly))

    # 3. Test Normalizzazione Colpo & Classificazione Lie
    def test_classify_lie(self):
        # Punto nel fairway
        fw_pt = (43.521128, 13.606700)
        lie = classify_lie(fw_pt[0], fw_pt[1], self.hole)
        self.assertEqual(lie, LieCategory.FAIRWAY)

        # Punto nel green
        gr_pt = (43.5199, 13.6072)
        lie_gr = classify_lie(gr_pt[0], gr_pt[1], self.hole)
        self.assertEqual(lie_gr, LieCategory.GREEN)

        # Punto nel bunker di fairway
        bk_pt = (43.5209, 13.60655)
        lie_bk = classify_lie(bk_pt[0], bk_pt[1], self.hole)
        self.assertEqual(lie_bk, LieCategory.BUNKER)

    def test_normalize_shot(self):
        raw_shot = ShotRecord(
            shot_id="s1",
            player_id="p1",
            hole_number=1,
            shot_number=1,
            club="driver",
            category=PlayerCategory.PRIMA,
            start_point=self.hole.tee,
            end_point=GeoPoint(lat=43.521128, lon=13.606700)
        )
        norm = normalize_shot(raw_shot, self.hole, target_distance_m=220.0)
        self.assertGreater(norm.distance_m, 170.0)
        self.assertEqual(norm.landing_lie, LieCategory.FAIRWAY)
        self.assertIn(norm.quality, [ShotQuality.EXCELLENT, ShotQuality.GOOD, ShotQuality.ACCEPTABLE])

    # 4. Test Dispersione Statistica ed Ellissi
    def test_dispersion_calculation(self):
        sample_shots = [
            NormalizedShot(
                shot_id=f"s_{i}",
                club="driver",
                distance_m=210.0 + i * 2,
                progress_along_line_m=205.0 + i * 2,
                lateral_offset_m=(-10.0 + i * 5),
                longitudinal_offset_m=(-5.0 + i * 2),
                residual_to_green_m=130.0,
                landing_lie=LieCategory.FAIRWAY,
                quality=ShotQuality.GOOD
            )
            for i in range(5)
        ]
        stats = calculate_dispersion(sample_shots)
        self.assertEqual(stats["count"], 5)
        self.assertIn("sigma_lateral", stats)
        self.assertIn("sigma_longitudinal", stats)
        self.assertGreater(stats["sigma_lateral"], 0.0)

    def test_build_dispersion_ellipse(self):
        ell = build_dispersion_ellipse(
            center_lat=43.521128,
            center_lon=13.606700,
            semi_major_m=22.0,
            semi_minor_m=14.0,
            rotation_deg=163.0
        )
        self.assertAlmostEqual(ell.semi_major_axis_m, 22.0)
        self.assertAlmostEqual(ell.semi_minor_axis_m, 14.0)
        self.assertGreater(ell.area_sqm, 900.0)

    # 5. Test Strategia & Scoring (SPS, DRS, GOS)
    def test_scoring_formulas(self):
        sps = calculate_strategic_position_score(
            residual_distance_m=120.0,
            landing_lie=LieCategory.FAIRWAY,
            fairway_width_m=35.0,
            has_hazard_in_line=False,
            category=PlayerCategory.PRIMA
        )
        self.assertGreaterEqual(sps, 75.0)
        self.assertLessEqual(sps, 100.0)

        drs = calculate_dispersion_risk_score(
            lateral_std_m=15.0,
            fairway_width_m=35.0,
            hazard_nearby=False,
            water_in_play=False
        )
        self.assertGreaterEqual(drs, 0.0)
        self.assertLessEqual(drs, 100.0)

        gos = calculate_gir_opportunity_score(
            residual_distance_m=120.0,
            landing_lie=LieCategory.FAIRWAY,
            category=PlayerCategory.PRIMA
        )
        self.assertGreaterEqual(gos, 60.0)
        self.assertLessEqual(gos, 100.0)

    def test_recommend_clubs_for_hole(self):
        tee_c, app_c = recommend_clubs_for_hole(self.hole, PlayerCategory.PRIMA)
        self.assertTrue("Driver" in tee_c or "Legno" in tee_c)
        self.assertTrue("Ferro" in app_c or "Wedge" in app_c)

    def test_analyze_hole_strategy(self):
        for cat in [PlayerCategory.PRIMA, PlayerCategory.SECONDA, PlayerCategory.TERZA]:
            res = analyze_hole_strategy(self.hole, cat)
            self.assertEqual(res.hole_number, 1)
            self.assertEqual(res.par, 4)
            self.assertEqual(res.category, cat)
            self.assertIsNotNone(res.recommended_landing_zone)
            self.assertGreater(res.strategic_position_score, 0)
            self.assertGreater(res.dispersion_risk_score, 0)
            self.assertGreater(res.gir_opportunity_score, 0)
            self.assertIsNotNone(res.dispersion_ellipse)
            self.assertTrue(len(res.caddy_strategy_text) > 20)

    # 6. Test Mapping, GeoJSON & Leaflet HTML
    def test_geojson_and_leaflet_html(self):
        strategy = analyze_hole_strategy(self.hole, PlayerCategory.PRIMA)
        geojson = build_hole_geojson(self.hole, strategy)
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertGreater(len(geojson["features"]), 5)

        html = render_hole_map_html(self.hole, strategy)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("https://unpkg.com/leaflet", html)
        self.assertIn("server.arcgisonline.com/ArcGIS/rest/services/World_Imagery", html)
        self.assertIn("tactical-hud", html)
        self.assertIn(f"BUCA {self.hole.hole_number}", html)


if __name__ == "__main__":
    unittest.main()
