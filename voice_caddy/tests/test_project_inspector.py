"""
Test suite per Voice Caddy Project Inspector (Zero-Token Diagnostic Engine).
Isolato e conforme alle regole SafeVault (nessuna modifica a database o profili di produzione).
"""

import unittest
import sys
from pathlib import Path

VOICE_CADDY_DIR = Path(__file__).resolve().parent.parent
if str(VOICE_CADDY_DIR) not in sys.path:
    sys.path.insert(0, str(VOICE_CADDY_DIR))

from core.project_inspector import VoiceCaddyProjectInspector, project_inspector


class TestProjectInspector(unittest.TestCase):
    def setUp(self):
        self.inspector = project_inspector

    def test_safevault_check(self):
        sv = self.inspector.check_safevault()
        self.assertIn("healthy", sv)
        self.assertIn("db_integrity", sv)
        self.assertIn("tables", sv)
        self.assertTrue(sv["healthy"], "SafeVault dovrebbe risultare conforme")
        self.assertEqual(sv["db_integrity"], "ok", "L'integrità SQLite deve essere 'ok'")
        self.assertIn("rounds", sv["tables"])
        self.assertIn("user_profiles", sv["tables"])

    def test_dependencies_check(self):
        deps = self.inspector.check_dependencies()
        self.assertIn("root_packages", deps)
        self.assertIn("vc_packages", deps)
        # streamlit e pandas devono risultare installati
        self.assertNotIn("streamlit", deps.get("missing_installed", []))
        self.assertNotIn("pandas", deps.get("missing_installed", []))

    def test_codebase_syntax_check(self):
        cb = self.inspector.check_codebase_syntax()
        self.assertGreater(cb["total_py_files"], 10)
        self.assertEqual(len(cb["syntax_errors"]), 0, f"Errori di sintassi rilevati: {cb['syntax_errors']}")

    def test_full_inspection_summary(self):
        summary = self.inspector.run_full_inspection()
        self.assertIsNotNone(summary.timestamp)
        self.assertIsNotNone(summary.python_version)
        self.assertTrue(summary.safevault_healthy)
        self.assertGreaterEqual(summary.db_tables_count, 5)

    def test_generate_markdown_report_and_ai_prompt(self):
        summary = self.inspector.run_full_inspection()
        report = self.inspector.generate_markdown_report(summary)
        self.assertIn("# ⛳ VOICE CADDY PRO — RESUME STATO PROGETTO & AUDIT", report)
        self.assertIn("METRICHE CHIAVE DI SISTEMA", report)
        self.assertIn("PROMPT DI INTERVENTO PER IA ESTERNA", report)

        prompt = self.inspector.generate_ai_prompt(summary)
        self.assertIn("Senior Fullstack Python Developer", prompt)
        self.assertIn("Voice Caddy Pro", prompt)
        self.assertIn("SafeVault Policy", prompt)

    def test_chat_response_commands(self):
        # Test 'resume'
        resp_resume = self.inspector.chat_response("resume")
        self.assertIn("VOICE CADDY PRO", resp_resume)
        self.assertIn("METRICHE CHIAVE", resp_resume)

        # Test 'alert'
        resp_alert = self.inspector.chat_response("mostrami gli alert")
        self.assertTrue(len(resp_alert) > 10)

        # Test 'safevault'
        resp_sv = self.inspector.chat_response("safevault")
        self.assertIn("Stato SafeVault", resp_sv)

        # Test 'git'
        resp_git = self.inspector.chat_response("git")
        self.assertIn("Stato Git", resp_git)

        # Test 'help'
        resp_help = self.inspector.chat_response("help")
        self.assertIn("Comandi disponibili", resp_help)


if __name__ == "__main__":
    unittest.main()
