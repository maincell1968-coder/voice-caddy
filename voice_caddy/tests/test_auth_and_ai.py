import os
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.auth import AuthManager, AIUserConfig, STRAFATTI_INITIAL_MEMBERS, _hash_password, _verify_password
from core.db import DatabaseManager
from core.schemas import GolfRoundData
from core.demo_data import get_demo_golf_round
from core.user_profile import UserProfile, ClubDetail, ShaftFlex, sort_clubs_by_distance
from core.ai_provider import test_ai_connection, get_openai_client_for_config


def test_strafatti_initial_users():
    temp_dir = Path(tempfile.mkdtemp())
    users_file = temp_dir / "users.json"
    auth = AuthManager(data_file=users_file)

    # 1. Test that Stefano logs in with initial password Amministratore1968 and is admin
    ok, user, msg = auth.authenticate_strafatti("Stefano", "Amministratore1968")
    assert ok, f"Login Stefano fallito: {msg}"
    assert user.first_name == "Stefano"
    assert user.last_name == "Pirani"
    assert user.is_admin is True
    assert user.role == "admin"
    assert user.must_change_password is True
    print("[OK] Stefano Pirani autenticato come Amministratore con Amministratore1968")

    # 2. Test wrong password for Stefano
    ok, _, msg = auth.authenticate_strafatti("Stefano", "Errata")
    assert not ok
    print("[OK] Password errata correttamente respinta")

    # 3. Test non-authorized user in Strafatti
    ok, _, msg = auth.authenticate_strafatti("Gigi", "Qualsiasi")
    assert not ok
    print("[OK] Utente non autorizzato nel Gruppo Strafatti respinto")

    # 4. Test the two Marcos: Marco Sebastianelli and Marco Fiorani (anche con Marco S e Marco F per privacy)
    ok_seb, user_seb, _ = auth.authenticate_strafatti("Marco", "Sebastianelli")
    assert ok_seb
    assert user_seb.last_name == "Sebastianelli"
    print("[OK] Marco Sebastianelli identificato e autenticato")

    ok_fio, user_fio, _ = auth.authenticate_strafatti("Marco", "Fiorani")
    assert ok_fio
    assert user_fio.last_name == "Fiorani"
    print("[OK] Marco Fiorani identificato e autenticato")

    # 4b. Test privacy dropdown options: Marco S and Marco F
    ok_seb_s, user_seb_s, _ = auth.authenticate_strafatti("Marco S", "Sebastianelli")
    assert ok_seb_s
    assert user_seb_s.last_name == "Sebastianelli"

    ok_fio_f, user_fio_f, _ = auth.authenticate_strafatti("Marco F", "Fiorani")
    assert ok_fio_f
    assert user_fio_f.last_name == "Fiorani"
    print("[OK] Marco S e Marco F (opzioni privacy menu a tendina) identificati e autenticati")

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


def test_club_distance_sorting():
    # Creiamo un set di bastoni inseriti in ordine completamente sparso
    raw_clubs = [
        ClubDetail(club_name="Sand Wedge (56°)", carry_meters=85),
        ClubDetail(club_name="Putter", carry_meters=0),
        ClubDetail(club_name="Ferro 7", carry_meters=145),
        ClubDetail(club_name="Driver", carry_meters=230),
        ClubDetail(club_name="Legno 3", carry_meters=200),
        ClubDetail(club_name="Ferro 4", carry_meters=175),
        ClubDetail(club_name="Pitching Wedge", carry_meters=115),
    ]

    sorted_clubs = sort_clubs_by_distance(raw_clubs)
    club_names = [c.club_name for c in sorted_clubs]
    distances = [c.carry_meters for c in sorted_clubs]

    # Verifica: il Driver con la distanza maggiore deve essere primo
    assert club_names[0] == "Driver"
    assert distances[0] == 230

    # Verifica: il Putter deve essere SEMPRE l'ultimo elemento della lista
    assert club_names[-1] == "Putter"

    # Verifica: le distanze dei bastoni di gioco sono strettamente decrescenti
    game_distances = distances[:-1]
    assert game_distances == sorted(game_distances, reverse=True), f"Distanze non decrescenti: {game_distances}"

    # Test con inserimento nuovo bastone nel mezzo (es. Ibrido 3 a 190m)
    new_club = ClubDetail(club_name="Ibrido 3", carry_meters=190)
    raw_clubs.append(new_club)
    resorted = sort_clubs_by_distance(raw_clubs)
    new_names = [c.club_name for c in resorted]

    assert new_names[0] == "Driver"     # 230m
    assert new_names[1] == "Legno 3"    # 200m
    assert new_names[2] == "Ibrido 3"   # 190m (inserito correttamente al terzo posto)
    assert new_names[3] == "Ferro 4"    # 175m
    assert new_names[-1] == "Putter"    # Putter rimane in fondo
    print("[OK] Ordinamento bastoni per distanza (dal Driver più lungo al Putter) verificato con successo")


def test_password_encryption_and_verification():
    import secrets
    salt = secrets.token_hex(16)
    plain = "SuperPasswordSegreta2026!"

    # 1. Verifica che la password venga criptata con PBKDF2 (hash a 64 caratteri esadecimali)
    hashed = _hash_password(plain, salt)
    assert len(hashed) == 64
    assert hashed != plain
    assert _verify_password(plain, salt, hashed) is True
    assert _verify_password("PasswordSbagliata", salt, hashed) is False

    # 2. Verifica retrocompatibilità per hash legacy SHA-256
    import hashlib
    legacy_hash = hashlib.sha256((salt + plain).encode("utf-8")).hexdigest()
    assert _verify_password(plain, salt, legacy_hash) is True
    assert _verify_password("PasswordSbagliata", salt, legacy_hash) is False
    print("[OK] Crittografia forte PBKDF2-HMAC-SHA256 e compare_digest con retrocompatibilità verificate")


if __name__ == "__main__":
    test_strafatti_initial_users()
    test_amici_dynamic_users()
    test_database_multiuser()
    test_ai_config()
    test_club_distance_sorting()
    test_password_encryption_and_verification()
    print("\n[SUCCESS] TUTTI I TEST UNITARI SONO STATI SUPERATI CON SUCCESSO!")

