import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO
import json

from core.mobile_pdf_report import generate_showcase_mobile_pdf, send_pdf_report_via_telegram
from core.demo_data import get_demo_golf_round


class TestMobilePDFReport(unittest.TestCase):
    def test_generate_showcase_pdf_default(self):
        pdf_bytes = generate_showcase_mobile_pdf(
            round_data=None,
            player_name="Stefano Pirani",
            handicap=18.0,
            active_course_id="conero_golf_club"
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 3000)

    def test_generate_showcase_pdf_all_courses(self):
        courses = ["conero_golf_club", "torrenova_golf_club", "golf_club_perugia", "riviera_golf_resort"]
        for cid in courses:
            pdf_b = generate_showcase_mobile_pdf(
                round_data=None,
                player_name="Test Player",
                handicap=14.5,
                active_course_id=cid
            )
            self.assertTrue(pdf_b.startswith(b"%PDF"))
            self.assertGreater(len(pdf_b), 3000)

    @patch("urllib.request.urlopen")
    @patch("core.telegram_config.TelegramConfigManager.get_token")
    def test_send_pdf_report_via_telegram_success(self, mock_token, mock_urlopen):
        mock_token.return_value = "123456:FAKE_TOKEN"

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "result": {"message_id": 999}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        fake_pdf = b"%PDF-1.4 test content"
        ok, msg = send_pdf_report_via_telegram(
            pdf_bytes=fake_pdf,
            chat_id="7133743757",
            caption="Test caption",
            filename="test.pdf"
        )

        self.assertTrue(ok)
        self.assertIn("successo", msg.lower())
        mock_urlopen.assert_called_once()

    @patch("core.telegram_config.TelegramConfigManager.get_token")
    def test_send_pdf_report_no_token(self, mock_token):
        mock_token.return_value = ""
        fake_pdf = b"%PDF-1.4 test"
        ok, msg = send_pdf_report_via_telegram(fake_pdf, "7133743757")
        self.assertFalse(ok)
        self.assertIn("nessun token", msg.lower())


if __name__ == "__main__":
    unittest.main()
