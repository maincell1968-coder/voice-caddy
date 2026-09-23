import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd

from core.user_profile import ClubDetail, ShaftFlex
from core.demo_data import get_demo_golf_round
from core.supabase_service import (
    get_supabase_credentials,
    init_supabase,
    reset_supabase_client_cache,
    normalize_club_dict,
    df_to_clubs_json,
    clubs_json_to_df,
    clubs_json_to_club_details,
    club_details_to_clubs_json,
    load_golf_bag_from_supabase,
    save_golf_bag_to_supabase,
    check_supabase_health,
    save_round_to_supabase,
    load_rounds_from_supabase,
    get_user_rounds_cloud_count,
    sync_all_local_rounds_to_supabase,
    MAX_CLOUD_ROUNDS_PER_USER
)


class TestSupabaseBagService(unittest.TestCase):
    def setUp(self):
        reset_supabase_client_cache()

    def tearDown(self):
        reset_supabase_client_cache()

    def test_normalize_club_dict_italian_keys(self):
        raw = {
            "mazza": "Legno 3",
            "marca": "Callaway",
            "modello": "Paradym",
            "shaft": "Regular",
            "distanza_carry": 220
        }
        res = normalize_club_dict(raw)
        self.assertEqual(res["mazza"], "Legno 3")
        self.assertEqual(res["marca"], "Callaway")
        self.assertEqual(res["modello"], "Paradym")
        self.assertEqual(res["shaft"], "Regular")
        self.assertEqual(res["distanza_carry"], 220)

    def test_normalize_club_dict_df_keys(self):
        raw = {
            "Mazza": "Driver",
            "Marca": "TaylorMade",
            "Modello / Tipo": "Qi10",
            "Shaft": "Stiff",
            "Distanza Carry (m)": 235
        }
        res = normalize_club_dict(raw)
        self.assertEqual(res["mazza"], "Driver")
        self.assertEqual(res["marca"], "TaylorMade")
        self.assertEqual(res["modello"], "Qi10")
        self.assertEqual(res["shaft"], "Stiff")
        self.assertEqual(res["distanza_carry"], 235)

    def test_normalize_club_dict_english_keys(self):
        raw = {
            "club_name": "Ferro 7",
            "brand": "Titleist",
            "model_type": "T200",
            "shaft_flex": "Stiff",
            "carry_meters": 145.4
        }
        res = normalize_club_dict(raw)
        self.assertEqual(res["mazza"], "Ferro 7")
        self.assertEqual(res["marca"], "Titleist")
        self.assertEqual(res["modello"], "T200")
        self.assertEqual(res["shaft"], "Stiff")
        self.assertEqual(res["distanza_carry"], 145)

    def test_df_to_clubs_json_and_back(self):
        df = pd.DataFrame([
            {"Mazza": "Driver", "Marca": "Ping", "Modello / Tipo": "G430", "Shaft": "Regular", "Distanza Carry (m)": 215},
            {"Mazza": "Putter", "Marca": "Scotty Cameron", "Modello / Tipo": "Phantom", "Shaft": "Regular", "Distanza Carry (m)": 0},
        ])
        json_data = df_to_clubs_json(df)
        self.assertEqual(len(json_data), 2)
        self.assertEqual(json_data[0]["mazza"], "Driver")
        self.assertEqual(json_data[1]["mazza"], "Putter")

        df_restored = clubs_json_to_df(json_data)
        self.assertEqual(len(df_restored), 2)
        self.assertEqual(df_restored.iloc[0]["Mazza"], "Driver")
        self.assertEqual(df_restored.iloc[0]["Distanza Carry (m)"], 215)

    def test_club_details_conversion(self):
        clubs = [
            ClubDetail(club_name="Driver", brand="Titleist", model_type="TSR2", shaft_flex=ShaftFlex.STIFF, carry_meters=225),
            ClubDetail(club_name="Sand Wedge (56°)", brand="Cleveland", model_type="RTX", shaft_flex=ShaftFlex.REGULAR, carry_meters=80),
        ]
        json_data = club_details_to_clubs_json(clubs)
        self.assertEqual(len(json_data), 2)
        self.assertEqual(json_data[0]["mazza"], "Driver")
        self.assertEqual(json_data[0]["distanza_carry"], 225)

        restored_clubs = clubs_json_to_club_details(json_data)
        self.assertEqual(len(restored_clubs), 2)
        self.assertEqual(restored_clubs[0].club_name, "Driver")
        self.assertEqual(restored_clubs[0].shaft_flex, ShaftFlex.STIFF)

    @patch("core.supabase_service.get_supabase_credentials")
    def test_init_supabase_missing_credentials(self, mock_creds):
        mock_creds.return_value = (None, None)
        client, err = init_supabase()
        self.assertIsNone(client)
        self.assertIn("Credenziali Supabase mancanti", err)

    @patch("core.supabase_service.init_supabase")
    def test_save_golf_bag_to_supabase_upsert(self, mock_init):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_upsert = MagicMock()
        mock_execute = MagicMock()

        mock_init.return_value = (mock_client, None)
        mock_client.table.return_value = mock_table
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute.return_value = MagicMock(data=[{"id": "uuid-123"}])

        clubs = [
            {"mazza": "Legno 3", "marca": "Callaway", "modello": "", "shaft": "Regular", "distanza_carry": 220}
        ]
        ok, msg = save_golf_bag_to_supabase(clubs, bag_id="default")
        self.assertTrue(ok)
        self.assertIn("correttamente", msg)

        # Verifica chiamata upsert con on_conflict="bag_id"
        mock_client.table.assert_called_with("golf_bag")
        args, kwargs = mock_table.upsert.call_args
        self.assertEqual(kwargs.get("on_conflict"), "bag_id")
        self.assertEqual(args[0]["bag_id"], "default")
        self.assertEqual(len(args[0]["clubs"]), 1)
        self.assertEqual(args[0]["clubs"][0]["mazza"], "Legno 3")

    @patch("core.supabase_service.init_supabase")
    def test_load_golf_bag_from_supabase_success(self, mock_init):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()

        mock_init.return_value = (mock_client, None)
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq
        mock_eq.execute.return_value = MagicMock(data=[{
            "bag_id": "default",
            "clubs": [
                {"mazza": "Ferro 5", "marca": "Titleist", "modello": "T200", "shaft": "Stiff", "distanza_carry": 160}
            ]
        }])

        clubs, err = load_golf_bag_from_supabase(bag_id="default")
        self.assertIsNone(err)
        self.assertIsNotNone(clubs)
        self.assertEqual(len(clubs), 1)
        self.assertEqual(clubs[0]["mazza"], "Ferro 5")
        self.assertEqual(clubs[0]["distanza_carry"], 160)

    @patch("core.supabase_service.init_supabase")
    def test_load_golf_bag_from_supabase_empty_table(self, mock_init):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()

        mock_init.return_value = (mock_client, None)
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq
        # Tabella vuota: data = []
        mock_eq.execute.return_value = MagicMock(data=[])

        clubs, err = load_golf_bag_from_supabase(bag_id="default")
        self.assertIsNone(err)
        self.assertEqual(clubs, [])

    @patch("core.supabase_service.init_supabase")
    def test_load_golf_bag_error_handling(self, mock_init):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_init.return_value = (mock_client, None)
        mock_client.table.return_value = mock_table
        mock_table.select.side_effect = Exception("Connessione rifiutata dal server")

        clubs, err = load_golf_bag_from_supabase(bag_id="default")
        self.assertIsNone(clubs)
        self.assertIn("Errore durante il caricamento da Supabase", err)

    @patch("core.supabase_service.get_supabase_credentials")
    def test_health_check_unconfigured(self, mock_creds):
        mock_creds.return_value = (None, None)
        health = check_supabase_health()
        self.assertEqual(health["status"], "not_configured")

    @patch("core.supabase_service.init_supabase")
    def test_save_round_to_supabase(self, mock_init):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_upsert = MagicMock()

        mock_init.return_value = (mock_client, None)
        mock_client.table.return_value = mock_table
        mock_table.upsert.return_value = mock_upsert
        mock_upsert.execute.return_value = MagicMock(data=[{"id": "uuid-round"}])

        round_data = get_demo_golf_round()
        ok, msg = save_round_to_supabase(round_id=42, round_data=round_data, user_id="user_test", group_name="strafatti")
        self.assertTrue(ok)
        self.assertIn("successo", msg)

        mock_client.table.assert_called_with("golf_rounds")
        args, kwargs = mock_table.upsert.call_args
        self.assertEqual(kwargs.get("on_conflict"), "round_key")
        self.assertEqual(args[0]["round_key"], "user_test_42")
        self.assertEqual(args[0]["user_id"], "user_test")

    @patch("core.supabase_service.init_supabase")
    def test_load_rounds_from_supabase(self, mock_init):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_order = MagicMock()
        mock_limit = MagicMock()

        mock_init.return_value = (mock_client, None)
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq
        mock_eq.order.return_value = mock_order
        mock_order.limit.return_value = mock_limit
        mock_limit.execute.return_value = MagicMock(data=[{
            "id": "uuid-1",
            "round_key": "user_test_1",
            "user_id": "user_test",
            "course_name": "Conero Golf Club",
            "total_score": 85
        }])

        rounds, err = load_rounds_from_supabase(user_id="user_test")
        self.assertIsNone(err)
        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0]["course_name"], "Conero Golf Club")

    @patch("core.supabase_service.save_round_to_supabase")
    def test_sync_all_local_rounds_to_supabase(self, mock_save):
        mock_save.return_value = (True, "OK")
        mock_db = MagicMock()
        mock_db.get_all_rounds.return_value = [
            {"id": 1, "user_id": "user_1", "group_name": "strafatti"},
            {"id": 2, "user_id": "user_1", "group_name": "strafatti"}
        ]
        mock_db.get_round_by_id.return_value = get_demo_golf_round()

        synced, total = sync_all_local_rounds_to_supabase(mock_db, user_id="user_1")
        self.assertEqual(synced, 2)
        self.assertEqual(total, 2)
        self.assertEqual(mock_save.call_count, 2)


if __name__ == "__main__":
    unittest.main()
