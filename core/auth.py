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
    provider: str = Field(default="ollama", description="Provider IA: 'ollama', 'openai', 'custom'")
    ollama_url: str = Field(default="http://localhost:11434", description="URL dell'istanza Ollama locale o remota")
    ollama_model: str = Field(default="llama3.1", description="Modello Ollama da utilizzare (es. llama3.1, mistral, qwen2.5)")
    openai_api_key: str = Field(default="", description="Chiave API OpenAI personale dell'utente")
    openai_model: str = Field(default="gpt-4o", description="Modello OpenAI (es. gpt-4o, gpt-4o-mini)")
    custom_base_url: str = Field(default="", description="Base URL per endpoint compatibile OpenAI (es. Groq, DeepSeek, Together, LM Studio)")
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
    ai_config: AIUserConfig = Field(default_factory=AIUserConfig)
    created_at: Optional[str] = None


# Initial 8 authorized users for Gruppo Strafatti
STRAFATTI_INITIAL_MEMBERS = [
    {"first_name": "Stefano", "last_name": "Pirani", "username": "Stefano", "initial_pwd": "Pirani", "user_id": "strafatti_stefano_pirani"},
    {"first_name": "Giorgio", "last_name": "Marchetti", "username": "Giorgio", "initial_pwd": "Marchetti", "user_id": "strafatti_giorgio_marchetti"},
    {"first_name": "Marco", "last_name": "Sebastianelli", "username": "Marco", "initial_pwd": "Sebastianelli", "user_id": "strafatti_marco_sebastianelli"},
    {"first_name": "Gianluca", "last_name": "Basili", "username": "Gianluca", "initial_pwd": "Basili", "user_id": "strafatti_gianluca_basili"},
    {"first_name": "Alessandro", "last_name": "Campanelli", "username": "Alessandro", "initial_pwd": "Campanelli", "user_id": "strafatti_alessandro_campanelli"},
    {"first_name": "Renzo", "last_name": "Gallina", "username": "Renzo", "initial_pwd": "Gallina", "user_id": "strafatti_renzo_gallina"},
    {"first_name": "Luca", "last_name": "Sandroni", "username": "Luca", "initial_pwd": "Sandroni", "user_id": "strafatti_luca_sandroni"},
    {"first_name": "Marco", "last_name": "Fiorani", "username": "Marco", "initial_pwd": "Fiorani", "user_id": "strafatti_marco_fiorani"}
]


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


class AuthManager:
    """
    Manages authentication, user accounts, password rotation, and per-user configurations.
    """

    def __init__(self, data_file: Path = USERS_FILE):
        self.data_file = Path(data_file)
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_initialized()

    def _ensure_initialized(self):
        if not self.data_file.exists():
            users = {}
            # Seed Strafatti initial members
            for m in STRAFATTI_INITIAL_MEMBERS:
                salt = secrets.token_hex(16)
                pwd_hash = _hash_password(m["initial_pwd"], salt)
                user = UserRecord(
                    user_id=m["user_id"],
                    group="strafatti",
                    first_name=m["first_name"],
                    last_name=m["last_name"],
                    username=m["username"],
                    password_hash=pwd_hash,
                    salt=salt,
                    must_change_password=True,
                    ai_config=AIUserConfig()
                )
                users[m["user_id"]] = user.model_dump()
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

    def find_strafatti_candidates(self, username_query: str) -> List[UserRecord]:
        """
        Finds matching Strafatti members by username, first name or full name.
        """
        users = self._load_all_users()
        candidates = []
        q = username_query.strip().lower()
        for u_data in users.values():
            if u_data.get("group") == "strafatti":
                u = UserRecord.model_validate(u_data)
                full_name = f"{u.first_name} {u.last_name}".lower()
                if (q == u.username.lower() or 
                    q == u.first_name.lower() or 
                    q == full_name or 
                    q == u.last_name.lower()):
                    candidates.append(u)
        return candidates

    def authenticate_strafatti(self, username: str, password_attempt: str) -> Tuple[bool, Optional[UserRecord], str]:
        """
        Authenticates a user for Gruppo Strafatti.
        Only the 8 designated members are allowed.
        Handles disambiguation between the two Marcos automatically based on password.
        """
        candidates = self.find_strafatti_candidates(username)
        if not candidates:
            return False, None, "Utente non autorizzato nel Gruppo Strafatti. Accesso consentito esclusivamente agli 8 membri designati."

        password_attempt = password_attempt.strip()

        # Check each matching candidate (in case of 'Marco' where there are two members)
        for user in candidates:
            attempt_hash = _hash_password(password_attempt, user.salt)
            if attempt_hash == user.password_hash:
                return True, user, "Autenticazione riuscita."

        return False, None, "Password non corretta. Al primo accesso inserisci il tuo Cognome."

    def authenticate_amici(self, first_name: str, password_attempt: str) -> Tuple[bool, Optional[UserRecord], str]:
        """
        Authenticates or registers a user for Gruppo Amici.
        At first access, the user provides their Nome and their Cognome as initial password.
        The user is automatically registered and required to change password.
        """
        first_name = first_name.strip().capitalize()
        password_attempt = password_attempt.strip()

        if not first_name or not password_attempt:
            return False, None, "Inserisci sia il Nome che la Password (Cognome al primo accesso)."

        users = self._load_all_users()

        # Check if already registered in Amici with this first_name
        amici_candidates = []
        for u_data in users.values():
            if u_data.get("group") == "amici":
                u = UserRecord.model_validate(u_data)
                if u.first_name.lower() == first_name.lower() or u.username.lower() == first_name.lower():
                    amici_candidates.append(u)

        if amici_candidates:
            # Existing user - check password
            for user in amici_candidates:
                attempt_hash = _hash_password(password_attempt, user.salt)
                if attempt_hash == user.password_hash:
                    return True, user, "Autenticazione riuscita."
            
            # If they typed their cognome, check if any user matches last_name
            for user in amici_candidates:
                if user.must_change_password and password_attempt.lower() == user.last_name.lower():
                    return True, user, "Autenticazione riuscita (primo accesso)."

            return False, None, "Password errata per l'utente specificato."

        # If not found, treat as first access: first_name = Name, password_attempt = Last Name
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
            ai_config=AIUserConfig()
        )

        users[user_id] = new_user.model_dump()
        self._save_all_users(users)
        return True, new_user, "Primo accesso registrato con successo nel Gruppo Amici! Imposta ora la tua password personale."

    def change_password(self, user_id: str, new_password: str) -> Tuple[bool, str]:
        """
        Updates a user's password and removes the must_change_password requirement.
        """
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
        """
        Saves the user's private AI configuration.
        """
        users = self._load_all_users()
        if user_id not in users:
            return False

        user = UserRecord.model_validate(users[user_id])
        user.ai_config = ai_config
        users[user_id] = user.model_dump()
        self._save_all_users(users)
        return True
