import os
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import AuthManager, AIUserConfig, STRAFATTI_INITIAL_MEMBERS
from core.db import DatabaseManager
from core.schemas import GolfRoundData
from core.demo_data import get_demo_golf_round
from core.user_profile import UserProfile
from core.ai_provider import test_ai_connection, get_openai_client_for_config


def test_strafatti_initial_users():
    temp_dir = Path(tempfile.mkdtemp())
    users_file = temp_dir / "users.json"
    auth = AuthManager(data_file=users_file)

    # 1. Test that Stefano logs in with initial password Pirani
    ok, user, msg = auth.authenticate_strafatti("Stefano", "Pirani")
    assert ok, f"Login Stefano fallito: {msg}"
    assert user.first_name == "Stefano"
    assert user.last_name == "Pirani"
    assert user.must_change_password is True
    print("[OK] Stefano Pirani autenticato con successo (primo accesso)")

    # 2. Test wrong password for Stefano
    ok, _, msg = auth.authenticate_strafatti("Stefano", "Errata")
    assert not ok
    print("[OK] Password errata correttamente respinta")

    # 3. Test non-authorized user in Strafatti
    ok, _, msg = auth.authenticate_strafatti("Gigi", "Qualsiasi")
    assert not ok
    print("[OK] Utente non autorizzato nel Gruppo Strafatti respinto")

    # 4. Test the two Marcos: Marco Sebastianelli and Marco Fiorani
    ok_seb, user_seb, _ = auth.authenticate_strafatti("Marco", "Sebastianelli")
    assert ok_seb
    assert user_seb.last_name == "Sebastianelli"
    print("[OK] Marco Sebastianelli identificato e autenticato")

    ok_fio, user_fio, _ = auth.authenticate_strafatti("Marco", "Fiorani")
    assert ok_fio
    assert user_fio.last_name == "Fiorani"
    print("[OK] Marco Fiorani identificato e autenticato")

    # 5. Test password change for Stefano
    ok_change, msg_change = auth.change_password(user.user_id, "NuovaPasswordSegreta123")
    assert ok_change, f"Cambio password fallito: {msg_change}"
    print("[OK] Cambio password eseguito con successo")

    # 6. Verify old password no longer works
    ok_old, _, _ = auth.authenticate_strafatti("Stefano", "Pirani")
    assert not ok_old, "La vecchia password non deve più funzionare!"
    print("[OK] Vecchia password Pirani non più valida")

    # 7. Verify new password works
    ok_new, user_updated, _ = auth.authenticate_strafatti("Stefano", "NuovaPasswordSegreta123")
    assert ok_new
    assert user_updated.must_change_password is False
    print("[OK] Nuova password convalidata e must_change_password=False")


def test_amici_dynamic_users():
    temp_dir = Path(tempfile.mkdtemp())
    users_file = temp_dir / "users.json"
    auth = AuthManager(data_file=users_file)

    # 1. New friend "Mario Rossi" logs in for the first time
    ok, user, msg = auth.authenticate_amici("Mario", "Rossi")
    assert ok, f"Login amico fallito: {msg}"
    assert user.first_name == "Mario"
    assert user.last_name == "Rossi"
    assert user.must_change_password is True
    print("[OK] Amico Mario Rossi registrato al primo accesso")

    # 2. Change password for Mario
    ok_change, _ = auth.change_password(user.user_id, "GolfFriend2026")
    assert ok_change
    print("[OK] Cambio password per Amico eseguito")

    # 3. Subsequent login with new password
    ok_login, user_active, _ = auth.authenticate_amici("Mario", "GolfFriend2026")
    assert ok_login
    assert user_active.must_change_password is False
    print("[OK] Login Amico con nuova password riuscito")


def test_database_multiuser():
    temp_dir = Path(tempfile.mkdtemp())
    db_file = temp_dir / "test.db"
    db = DatabaseManager(db_path=db_file)

    demo_round = get_demo_golf_round()
    round_id1 = db.save_round(demo_round, user_id="user_stefano", group_name="strafatti")
    round_id2 = db.save_round(demo_round, user_id="user_giorgio", group_name="strafatti")

    stefano_rounds = db.get_all_rounds(user_id="user_stefano")
    assert len(stefano_rounds) == 1
    assert stefano_rounds[0]["id"] == round_id1

    giorgio_rounds = db.get_all_rounds(user_id="user_giorgio")
    assert len(giorgio_rounds) == 1
    assert giorgio_rounds[0]["id"] == round_id2

    all_rounds = db.get_all_rounds()
    assert len(all_rounds) == 2
    print("[OK] Isolamento round multi-utente verificato nel database")


def test_ai_config():
    temp_dir = Path(tempfile.mkdtemp())
    users_file = temp_dir / "users.json"
    auth = AuthManager(data_file=users_file)

    ok, user, _ = auth.authenticate_strafatti("Stefano", "Pirani")
    cfg = AIUserConfig(
        provider="ollama",
        ollama_url="http://localhost:11434",
        ollama_model="llama3.1"
    )
    saved = auth.update_user_ai_config(user.user_id, cfg)
    assert saved

    reloaded = auth.get_user_by_id(user.user_id)
    assert reloaded.ai_config.provider == "ollama"
    assert reloaded.ai_config.ollama_model == "llama3.1"
    print("[OK] Configurazione IA salvata e ricaricata per l'utente")


if __name__ == "__main__":
    test_strafatti_initial_users()
    test_amici_dynamic_users()
    test_database_multiuser()
    test_ai_config()
    print("\n[SUCCESS] TUTTI I TEST UNITARI SONO STATI SUPERATI CON SUCCESSO!")
