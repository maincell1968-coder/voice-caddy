import os
import gc
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from core.backup_manager import BackupManager
from core.user_profile import UserProfile, ClubDetail, ShaftFlex, PlayerCategory
from core.db import DatabaseManager


class TestBackupAndPersistence(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.backups_dir = self.test_dir / "backups"
        self.data_dir = self.test_dir / "data"
        self.profiles_dir = self.data_dir / "profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

        self.mgr = BackupManager(project_root=self.test_dir, backups_dir=self.backups_dir, max_snapshots=3)

    def tearDown(self):
        gc.collect()
        if self.test_dir.exists():
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_create_snapshot_and_pruning(self):
        # Crea finti file critici
        f1 = self.profiles_dir / "test_user.json"
        f1.write_text('{"player_name": "Test Player"}', encoding="utf-8")

        # Mock get_critical_files
        self.mgr.get_critical_files = lambda: [f1]

        # Crea snapshot
        snap1 = self.mgr.create_startup_snapshot()
        self.assertIsNotNone(snap1)
        self.assertTrue(snap1.exists())

        # Crea altri snapshot per verificare la rotazione (max 3)
        import time
        time.sleep(0.05)
        snap2 = self.mgr.create_startup_snapshot()
        time.sleep(0.05)
        snap3 = self.mgr.create_startup_snapshot()
        time.sleep(0.05)
        snap4 = self.mgr.create_startup_snapshot()

        snapshots = self.mgr.list_snapshots()
        self.assertLessEqual(len(snapshots), 3)

    def test_export_and_restore_zip(self):
        profile_file = self.profiles_dir / "stefano.json"
        profile_file.write_text(json.dumps({
            "player_name": "Stefano Pirani",
            "handicap": 12.4,
            "clubs_in_bag": [
                {"club_name": "Driver", "carry_meters": 230.0}
            ]
        }), encoding="utf-8")

        self.mgr.get_critical_files = lambda: [profile_file]

        zip_bytes = self.mgr.export_full_backup_bytes()
        self.assertGreater(len(zip_bytes), 50)

        # Rimuovi file e ripristina
        profile_file.unlink()
        self.assertFalse(profile_file.exists())

        ok, msg = self.mgr.restore_from_zip(zip_bytes)
        self.assertTrue(ok)
        self.assertTrue(profile_file.exists())

    def test_fault_tolerant_profile_loading(self):
        test_file = self.profiles_dir / "corrupted_user.json"
        custom_data = {
            "player_name": "Stefano Test",
            "handicap": 11.2,
            "category": "InvalidCategoryVal",
            "preferred_ball": "Callaway Chrome Soft",
            "clubs_in_bag": [
                {"club_name": "Ferro 7 Custom", "brand": "Mizuno", "carry_meters": 155.0, "unexpected_key": "xyz"}
            ]
        }
        test_file.write_text(json.dumps(custom_data), encoding="utf-8")

        profile = UserProfile.load_from_file(test_file)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.player_name, "Stefano Test")
        self.assertEqual(profile.handicap, 11.2)
        self.assertEqual(profile.preferred_ball, "Callaway Chrome Soft")
        self.assertEqual(len(profile.clubs_in_bag), 1)
        self.assertEqual(profile.clubs_in_bag[0].club_name, "Ferro 7 Custom")
        self.assertEqual(profile.clubs_in_bag[0].carry_meters, 155.0)

    def test_profile_save_creates_bak(self):
        profile = UserProfile(
            player_name="Stefano Pirani",
            handicap=14.0,
            clubs_in_bag=[ClubDetail(club_name="Driver", carry_meters=220.0)]
        )
        test_path = self.profiles_dir / "save_test.json"
        ok1 = profile.save_to_file(test_path)
        self.assertTrue(ok1)
        self.assertTrue(test_path.exists())

        profile.handicap = 13.5
        ok2 = profile.save_to_file(test_path)
        self.assertTrue(ok2)
        bak_file = self.profiles_dir / "save_test.json.bak"
        self.assertTrue(bak_file.exists())

    def test_db_backup(self):
        db_path = self.test_dir / "test_db.db"
        db = DatabaseManager(db_path=db_path)
        self.assertTrue(db_path.exists())

        backup_file = db.backup_database()
        self.assertTrue(backup_file.exists())
        self.assertGreaterEqual(backup_file.stat().st_size, 0)
        # Ensure connection closed cleanly
        del db
        gc.collect()


if __name__ == "__main__":
    unittest.main()
