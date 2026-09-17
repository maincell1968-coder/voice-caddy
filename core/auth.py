from __future__ import annotations

import os
import json
import hashlib
import secrets
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"


class AIUserConfig(BaseModel):
    provider: str = Field(default="groq", description="Provider IA: 'groq', 'ollama', 'openai', 'custom'")
    groq_api_key: str = Field(default="", description="Chiave API Groq personale o di circolo (100% gratuita)")
    groq_model: str = Field(default="groq/compound-mini", description="Modello Groq (es. groq/compound-mini, qwen/qwen3.8-27b, groq/compound, openai/gpt-oss-120b)")
    ollama_url: str = Field(default="http://localhost:11434", description="URL dell'istanza Ollama locale o remota")
    ollama_model: str = Field(default="llama3", description="Modello Ollama da utilizzare (es. llama3, mistral, qwen2.5)")
    openai_api_key: str = Field(default="", description="Chiave API OpenAI personale dell'utente")
    openai_model: str = Field(default="gpt-4o", description="Modello OpenAI (es. gpt-4o, gpt-4o-mini)")
    custom_base_url: str = Field(default="", description="Base URL per endpoint compatibile OpenAI (es. DeepSeek, Together, LM Studio)")
    custom_api_key: str = Field(default="", description="Chiave API per endpoint custom")
    custom_model: str = Field(default="", description="Nome modello per endpoint custom")


class UserRecord(BaseModel):
    user_id: str
    group: str  # "strafatti" or "amici"
    first_name: str
    last_name: str
    username: str
    password_hash: str
    salt: str
    must_change_password: bool = True
    is_admin: bool = False
    role: str = "user"  # "admin" or "user"
    ai_config: AIUserConfig = Field(default_factory=AIUserConfig)
    created_at: Optional[str] = None


# Initial 8 authorized users for Gruppo Strafatti
# Stefano is the System Administrator with initial password Amministratore1968
STRAFATTI_INITIAL_MEMBERS = [
    {
        "first_name": "Stefano", "last_name": "Pirani", "username": "Stefano",
        "initial_pwd": "Amministratore1968", "user_id": "strafatti_stefano_pirani",
        "is_admin": True, "role": "admin",
        "alt_pwd": "Pirani"
    },
    {"first_name": "Giorgio", "last_name": "Marchetti", "username": "Giorgio", "initial_pwd": "Marchetti", "user_id": "strafatti_giorgio_marchetti", "is_admin": False, "role": "user"},
    {"first_name": "Marco", "last_name": "Sebastianelli", "username": "Marco S", "initial_pwd": "Sebastianelli", "user_id": "strafatti_marco_sebastianelli", "is_admin": False, "role": "user"},
    {"first_name": "Gianluca", "last_name": "Basili", "username": "Gianluca", "initial_pwd": "Basili", "user_id": "strafatti_gianluca_basili", "is_admin": False, "role": "user"},
    {"first_name": "Alessandro", "last_name": "Campanelli", "username": "Alessandro", "initial_pwd": "Campanelli", "user_id": "strafatti_alessandro_campanelli", "is_admin": False, "role": "user"},
    {"first_name": "Renzo", "last_name": "Gallina", "username": "Renzo", "initial_pwd": "Gallina", "user_id": "strafatti_renzo_gallina", "is_admin": False, "role": "user"},
    {"first_name": "Luca", "last_name": "Sandroni", "username": "Luca", "initial_pwd": "Sandroni", "user_id": "strafatti_luca_sandroni", "is_admin": False, "role": "user"},
    {"first_name": "Marco", "last_name": "Fiorani", "username": "Marco F", "initial_pwd": "Fiorani", "user_id": "strafatti_marco_fiorani", "is_admin": False, "role": "user"}
]


def _hash_password(password: str, salt: str) -> str:
    """
    Cripta in modo sicuro la password tramite PBKDF2-HMAC-SHA256 con 100.000 iterazioni e salt crittografico.
    """
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000
    ).hex()


def _verify_password(password_attempt: str, salt: str, expected_hash: str) -> bool:
    """
    Verifica se la password corrisponde all'hash criptato utilizzando secrets.compare_digest
    per prevenire qualsiasi vulnerabilità di timing attack.
    Supporta la crittografia moderna PBKDF2-HMAC-SHA256 ed offre retrocompatibilità con hash legacy SHA-256.
    """
    if not password_attempt or not salt or not expected_hash:
        return False
    # 1. Verifica crittografica principale PBKDF2-HMAC-SHA256
    pbkdf2_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password_attempt.encode("utf-8"),
        salt.encode("utf-8"),
        100_000
    ).hex()
    if secrets.compare_digest(pbkdf2_hash, expected_hash):
        return True

    # 2. Retrocompatibilità con hash legacy SHA-256 semplice
    legacy_hash = hashlib.sha256((salt + password_attempt).encode("utf-8")).hexdigest()
    if secrets.compare_digest(legacy_hash, expected_hash):
        return True

    return False


class AuthManager:
    """
    Manages authentication, user accounts, password rotation, and per-user configurations.
    Includes administrator privileges for Stefano.
    """

    def __init__(self, data_file: Path = USERS_FILE):
        self.data_file = Path(data_file)
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_initialized()

    def _ensure_initialized(self):
        users = self._load_all_users()
        modified = False

        for m in STRAFATTI_INITIAL_MEMBERS:
            u_id = m["user_id"]
            if u_id not in users:
                salt = secrets.token_hex(16)
                pwd_hash = _hash_password(m["initial_pwd"], salt)
                user = UserRecord(
                    user_id=u_id,
                    group="strafatti",
                    first_name=m["first_name"],
                    last_name=m["last_name"],
                    username=m["username"],
                    password_hash=pwd_hash,
                    salt=salt,
                    must_change_password=True,
                    is_admin=m.get("is_admin", False),
                    role=m.get("role", "user"),
                    ai_config=AIUserConfig()
                )
                users[u_id] = user.model_dump()
                modified = True
            else:
                # Ensure Stefano always has is_admin=True and role='admin'
                if m.get("is_admin") and not users[u_id].get("is_admin"):
                    users[u_id]["is_admin"] = True
                    users[u_id]["role"] = "admin"
                    modified = True

        if modified or not self.data_file.exists():
            self._save_all_users(users)

    def _load_all_users(self) -> Dict[str, dict]:
        if not self.data_file.exists():
            return {}
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_all_users(self, users: Dict[str, dict]):
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)

    def get_user_by_id(self, user_id: str) -> Optional[UserRecord]:
        users = self._load_all_users()
        if user_id in users:
            return UserRecord.model_validate(users[user_id])
        return None

    def get_user(self, user_id: str) -> Optional[UserRecord]:
        """Alias per get_user_by_id."""
        return self.get_user_by_id(user_id)

    def get_all_users(self) -> List[UserRecord]:
        users = self._load_all_users()
        return [UserRecord.model_validate(u) for u in users.values()]

    def find_strafatti_candidates(self, username_query: str) -> List[UserRecord]:
        users = self._load_all_users()
        candidates = []
        q = username_query.strip().lower()
        for u_data in users.values():
            if u_data.get("group") == "strafatti":
                u = UserRecord.model_validate(u_data)
                full_name = f"{u.first_name} {u.last_name}".lower()
                short_name = f"{u.first_name} {u.last_name[:1]}".lower()  # "marco s", "marco f"
                short_name_dot = f"{u.first_name} {u.last_name[:1]}.".lower()  # "marco s.", "marco f."
                if (q == u.username.lower() or 
                    q == u.first_name.lower() or 
                    q == full_name or 
                    q == short_name or 
                    q == short_name_dot or 
                    q == u.last_name.lower()):
                    candidates.append(u)
        return candidates

    def authenticate_strafatti(self, username: str, password_attempt: str) -> Tuple[bool, Optional[UserRecord], str]:
        """
        Authenticates a user for Gruppo Strafatti.
        Only the 8 designated members are allowed.
        For Stefano, supports 'Amministratore1968' (and 'Pirani').
        """
        candidates = self.find_strafatti_candidates(username)
        if not candidates:
            return False, None, "Utente non autorizzato nel Gruppo Strafatti. Accesso consentito esclusivamente agli 8 membri designati."

        password_attempt = password_attempt.strip()

        for user in candidates:
            if _verify_password(password_attempt, user.salt, user.password_hash):
                return True, user, "Autenticazione riuscita."
            
            # Special check for Stefano if on initial password
            if user.first_name.lower() == "stefano" and user.must_change_password:
                if password_attempt in ["Amministratore1968", "Pirani"]:
                    return True, user, "Autenticazione Amministratore riuscita (primo accesso)."

        return False, None, "Password non corretta. Al primo accesso inserisci la tua prima password."

    def authenticate_amici(self, first_name: str, password_attempt: str) -> Tuple[bool, Optional[UserRecord], str]:
        first_name = first_name.strip().capitalize()
        password_attempt = password_attempt.strip()

        if not first_name or not password_attempt:
            return False, None, "Inserisci sia il Nome che la Password (Cognome al primo accesso)."

        users = self._load_all_users()

        amici_candidates = []
        for u_data in users.values():
            if u_data.get("group") == "amici":
                u = UserRecord.model_validate(u_data)
                if u.first_name.lower() == first_name.lower() or u.username.lower() == first_name.lower():
                    amici_candidates.append(u)

        if amici_candidates:
            for user in amici_candidates:
                if _verify_password(password_attempt, user.salt, user.password_hash):
                    return True, user, "Autenticazione riuscita."
            
            for user in amici_candidates:
                if user.must_change_password and password_attempt.lower() == user.last_name.lower():
                    return True, user, "Autenticazione riuscita (primo accesso)."

            return False, None, "Password errata per l'utente specificato."

        last_name = password_attempt.capitalize()
        clean_name = first_name.lower().replace(" ", "_")
        clean_last = last_name.lower().replace(" ", "_")
        user_id = f"amici_{clean_name}_{clean_last}"

        salt = secrets.token_hex(16)
        pwd_hash = _hash_password(password_attempt, salt)

        new_user = UserRecord(
            user_id=user_id,
            group="amici",
            first_name=first_name,
            last_name=last_name,
            username=first_name,
            password_hash=pwd_hash,
            salt=salt,
            must_change_password=True,
            is_admin=False,
            role="user",
            ai_config=AIUserConfig()
        )

        users[user_id] = new_user.model_dump()
        self._save_all_users(users)
        return True, new_user, "Primo accesso registrato con successo nel Gruppo Amici! Imposta ora la tua password personale."

    def change_password(self, user_id: str, new_password: str) -> Tuple[bool, str]:
        new_password = new_password.strip()
        if len(new_password) < 4:
            return False, "La nuova password deve contenere almeno 4 caratteri."

        users = self._load_all_users()
        if user_id not in users:
            return False, "Utente non trovato."

        user = UserRecord.model_validate(users[user_id])
        salt = secrets.token_hex(16)
        new_hash = _hash_password(new_password, salt)

        user.password_hash = new_hash
        user.salt = salt
        user.must_change_password = False

        users[user_id] = user.model_dump()
        self._save_all_users(users)
        return True, "Password aggiornata con successo!"

    def update_user_ai_config(self, user_id: str, ai_config: AIUserConfig) -> bool:
        users = self._load_all_users()
        if user_id not in users:
            return False

        user = UserRecord.model_validate(users[user_id])
        user.ai_config = ai_config
        users[user_id] = user.model_dump()
        self._save_all_users(users)
        return True

    def admin_reset_user_password(self, target_user_id: str) -> Tuple[bool, str]:
        """
        Admin feature: resets a user's password to their initial surname and sets must_change_password=True.
        """
        users = self._load_all_users()
        if target_user_id not in users:
            return False, "Utente non trovato."

        user = UserRecord.model_validate(users[target_user_id])
        default_pwd = user.last_name
        if user.first_name.lower() == "stefano":
            default_pwd = "Amministratore1968"

        salt = secrets.token_hex(16)
        user.password_hash = _hash_password(default_pwd, salt)
        user.salt = salt
        user.must_change_password = True

        users[target_user_id] = user.model_dump()
        self._save_all_users(users)
        return True, f"Password reimpostata con successo al valore iniziale '{default_pwd}'."

    def admin_delete_user(self, target_user_id: str) -> Tuple[bool, str]:
        """
        Admin feature: deletes an Amici member or test user.
        """
        users = self._load_all_users()
        if target_user_id not in users:
            return False, "Utente non trovato."

        user = UserRecord.model_validate(users[target_user_id])
        if user.is_admin or target_user_id == "strafatti_stefano_pirani":
            return False, "Impossibile eliminare l'Amministratore di Sistema."

        del users[target_user_id]
        self._save_all_users(users)
        return True, f"Utente '{user.first_name} {user.last_name}' eliminato con successo."
