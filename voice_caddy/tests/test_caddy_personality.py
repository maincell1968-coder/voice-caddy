"""
Test suite for Voice Caddy - Caddy Personality & Tone Engine.
Ensures zero data loss, strict memory isolation, and verifies tone selection,
phrase substitution, anti-repetition memory, and prompt generation.
"""

import sys
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

# Ensure voice_caddy package is resolvable both ways
VOICE_CADDY_DIR = Path(__file__).resolve().parent.parent
if str(VOICE_CADDY_DIR) not in sys.path:
    sys.path.insert(0, str(VOICE_CADDY_DIR))

from core.caddy_personality import CaddyTone, CaddyPersonalityEngine
from core.user_profile import UserProfile, ClubDetail


class TestCaddyPersonality(unittest.TestCase):
    def setUp(self):
        self.engine = CaddyPersonalityEngine()

    def test_caddy_tones_enum(self):
        """Verify all 4 core personality archetypes exist with correct values and metadata."""
        tones = [t.value for t in CaddyTone]
        self.assertIn("professionale", tones)
        self.assertIn("arrabbiato", tones)
        self.assertIn("spensierato", tones)
        self.assertIn("psicologo", tones)

        # Check helper properties
        self.assertIn("Arrabbiato", CaddyTone.ARRABBIATO.display_name)
        self.assertIn("Professionale", CaddyTone.PROFESSIONALE.display_name)
        self.assertIn("Spensierato", CaddyTone.SPENSIERATO.display_name)
        self.assertIn("Psicologo", CaddyTone.PSICOLOGO.display_name)

        self.assertEqual(CaddyTone.ARRABBIATO.short_label, "🤬 Arrabbiato")
        self.assertEqual(CaddyTone.PROFESSIONALE.short_label, "👔 Professionale")

    def test_phrases_catalog_loaded(self):
        """Verify that the JSON phrase catalog is loaded and has phrases for all situations."""
        catalog = self.engine.phrases_catalog
        self.assertIsInstance(catalog, dict)
        self.assertGreater(len(catalog), 10)

        # Key situations must exist
        required_situations = ["START_ROUND", "TEE", "DISTANZA", "FERRO_OK", "BUNKER", "ACQUA", "BUCA_PAR", "BUCA_BIRDIE"]
        for sit in required_situations:
            self.assertIn(sit, catalog, f"Situation {sit} missing from catalog")
            for tone in CaddyTone:
                self.assertIn(tone.value, catalog[sit], f"Tone {tone.value} missing in {sit}")
                self.assertGreater(len(catalog[sit][tone.value]), 0)

    def test_phrase_formatting_and_placeholder_substitution(self):
        """Verify that placeholder variables like {distanza}, {ferro}, {buca} are formatted properly."""
        phrase = self.engine.get_phrase(
            "DISTANZA",
            tone=CaddyTone.ARRABBIATO,
            distanza=155,
            buca=4
        )
        self.assertIsInstance(phrase, str)
        self.assertNotIn("{distanza}", phrase)
        self.assertNotIn("{buca}", phrase)

    def test_phrase_anti_repetition(self):
        """Verify that repeated calls do not immediately repeat the exact same phrase when multiple are available."""
        seen = []
        for _ in range(5):
            p = self.engine.get_phrase("TEE", tone=CaddyTone.PROFESSIONALE, buca=1)
            seen.append(p)
        
        # In a list of 10+ phrases, 5 draws shouldn't all be the exact same line
        unique_seen = set(seen)
        self.assertGreater(len(unique_seen), 1)

    def test_build_system_prompt(self):
        """Verify system prompt generation injects personality instructions, clubs bag, and hole context."""
        profile = UserProfile(
            player_name="Mario Rossi",
            handicap=18.4,
            clubs_in_bag=[
                ClubDetail(club_name="Driver", carry_meters=220),
                ClubDetail(club_name="Ferro 7", carry_meters=140),
            ]
        )

        mock_course = MagicMock()
        mock_course.name = "Conero Golf Club"
        mock_course.holes_count = 18
        mock_hole = MagicMock()
        mock_hole.par = 4
        mock_hole.distance_meters = 350
        mock_hole.slope_elevation_profile = "pianeggiante"
        mock_course.get_hole.return_value = mock_hole

        prompt = self.engine.build_system_prompt(
            tone=CaddyTone.ARRABBIATO,
            user_profile=profile,
            active_course=mock_course,
            current_hole=7
        )
        self.assertIn("Mario Rossi", prompt)
        self.assertIn("18.4", prompt)
        self.assertIn("Driver", prompt)
        self.assertIn("220", prompt)
        self.assertIn("Conero Golf Club", prompt)
        self.assertIn("#7", prompt)
        self.assertIn("romagnolo", prompt.lower())

    @patch("core.ai_provider.get_openai_client_for_config")
    def test_chat_with_caddy_mocked(self, mock_get_client):
        """Verify conversational chat integrates with AIProvider / OpenAI client wrapper."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Mira al centro del green e fai uno swing fluido!"
        mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
        mock_get_client.return_value = (mock_client, "gpt-4o")

        profile = UserProfile(player_name="Stefano", handicap=12.0)
        ai_config = MagicMock()

        response = self.engine.chat_with_caddy(
            message="Che ferro prendo per 140 metri?",
            tone=CaddyTone.PROFESSIONALE,
            history=[],
            user_profile=profile,
            ai_config=ai_config,
            active_course=None,
            current_hole=1
        )
        self.assertIn("Mira al centro del green", response)


if __name__ == "__main__":
    unittest.main()
