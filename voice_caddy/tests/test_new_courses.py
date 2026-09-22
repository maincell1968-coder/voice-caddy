import unittest
from core.course import CourseRegistry


class TestNewCoursesIntegration(unittest.TestCase):
    """Test suite per la verifica dei nuovi campi da golf integrati nel sistema."""

    def setUp(self):
        self.registry = CourseRegistry()

    def test_all_expected_courses_available(self):
        courses = self.registry.list_courses()
        course_ids = {c.course_id for c in courses}

        self.assertIn("conero_golf_club", course_ids)
        self.assertIn("torrenova_golf_club", course_ids)
        self.assertIn("riviera_golf_resort", course_ids)
        self.assertIn("golf_club_perugia", course_ids)

    def test_riviera_golf_resort_spec(self):
        riviera = self.registry.get_course("riviera_golf_resort")
        self.assertIsNotNone(riviera)
        self.assertEqual(riviera.holes_count, 18)
        self.assertEqual(riviera.total_par, 70)
        self.assertIn("San Giovanni in Marignano", riviera.city)

        # Verifica Tee
        self.assertIn("bianchi", riviera.tees)
        self.assertIn("gialli", riviera.tees)
        self.assertIn("rossi", riviera.tees)
        self.assertEqual(riviera.tees["bianchi"].course_rating, 72.4)
        self.assertEqual(riviera.tees["bianchi"].slope_rating, 128)

        # Verifica buche (18 buche)
        self.assertEqual(len(riviera.holes), 18)
        # Buca 1 deve essere Par 4 HCP 2
        h1 = riviera.get_hole(1)
        self.assertIsNotNone(h1)
        self.assertEqual(h1.par, 4)
        self.assertEqual(h1.handicap_index, 2)
        self.assertGreater(h1.distance_meters, 350)
        self.assertIsNotNone(h1.coordinates)
        self.assertAlmostEqual(h1.coordinates.tee_lat, 43.942, delta=0.05)

    def test_golf_club_perugia_spec(self):
        perugia = self.registry.get_course("golf_club_perugia")
        self.assertIsNotNone(perugia)
        self.assertEqual(perugia.holes_count, 18)
        self.assertEqual(perugia.total_par, 72)
        self.assertIn("Perugia", perugia.city)

        # Verifica Tee
        self.assertIn("gialli", perugia.tees)
        self.assertIn("rossi", perugia.tees)
        self.assertEqual(perugia.tees["gialli"].slope_rating, 125)

        # Verifica buche (18 buche)
        self.assertEqual(len(perugia.holes), 18)
        # Buca 1 deve essere Par 5 HCP 8
        h1 = perugia.get_hole(1)
        self.assertIsNotNone(h1)
        self.assertEqual(h1.par, 5)
        self.assertEqual(h1.handicap_index, 8)
        self.assertGreater(h1.distance_meters, 440)
        self.assertIsNotNone(h1.coordinates)
        self.assertAlmostEqual(h1.coordinates.tee_lat, 43.080, delta=0.05)

    def test_torrenova_golf_club_spec(self):
        torrenova = self.registry.get_course("torrenova_golf_club")
        self.assertIsNotNone(torrenova)
        self.assertEqual(torrenova.holes_count, 9)
        self.assertEqual(torrenova.total_par, 34)
        self.assertEqual(len(torrenova.holes), 9)


if __name__ == "__main__":
    unittest.main()
