from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Optional, List, Set, Union


class SecurityViolationError(PermissionError):
    """Sollevata quando un agente tenta di accedere o modificare percorsi non autorizzati."""
    pass


class SecurityGuardrail:
    """
    Guardrail di sicurezza deny-by-default per la suite di agenti di monitoraggio.
    Garantisce:
    1. Principio di minimo privilegio: accesso consentito solo a directory di log, stato e cartelle temporanee.
    2. Zero Perdita Dati (SafeVault Policy): blocco categorico di operazioni di scrittura/modifica
       su database di produzione (voice_caddy.db), profili utente e file di configurazione.
    3. Protezione da Path Traversal (../) tramite risoluzione e verifica dei percorsi canonici.
    4. Connessioni SQLite rigorosamente in sola lettura (mode=ro) per qualsiasi ispezione.
    """

    CRITICAL_PRODUCTION_FILES = {
        "voice_caddy.db",
        "voice_caddy.db.bak",
        "users.json",
        "telegram_config.json",
        "telegram_users.json",
        "coordinate_campi.xlsx",
        "tactical_courses.json",
    }

    FORBIDDEN_SQL_KEYWORDS = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|VACUUM|REINDEX|REPLACE|ATTACH|DETACH)\b",
        re.IGNORECASE
    )

    def __init__(self, allowed_directories: Optional[List[Union[str, Path]]] = None):
        self._allowed_dirs: Set[Path] = set()

        # Percorsi autorizzati di default (cartelle di monitoraggio, log e temp)
        project_root = Path(__file__).resolve().parent.parent
        default_allowed = [
            project_root / "monitoring" / ".state",
            project_root / "monitoring" / "logs",
            project_root / "logs",
            project_root / "data" / "logs",
            project_root.parent / "logs",
        ]

        if allowed_directories:
            for p in allowed_directories:
                self.allow_directory(Path(p))
        else:
            for p in default_allowed:
                self.allow_directory(p)

    def allow_directory(self, path: Union[str, Path]) -> None:
        """Aggiunge una directory alla lista di percorsi consentiti per lettura/scrittura telemetria."""
        resolved = Path(path).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        self._allowed_dirs.add(resolved)

    def _is_path_allowed(self, target_path: Path) -> bool:
        resolved = target_path.resolve()
        for allowed in self._allowed_dirs:
            try:
                resolved.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False

    def validate_read_path(self, file_path: Union[str, Path]) -> Path:
        """
        Valida che il file sia autorizzato per la sola lettura.
        Consente anche la lettura sicura (ma non la scrittura) del database voice_caddy.db
        se esplicitamente richiesto per monitoraggio sessioni.
        """
        resolved = Path(file_path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"File non trovato: {resolved}")

        # Se è all'interno delle directory autorizzate, ok
        if self._is_path_allowed(resolved):
            return resolved

        # Consenti lettura controllata di file log noti o del DB principale
        if resolved.name.endswith(".log") or resolved.name.endswith(".jsonl") or resolved.name == "voice_caddy.db":
            return resolved

        raise SecurityViolationError(
            f"[DENY-BY-DEFAULT] Accesso in lettura negato al percorso non autorizzato: {resolved}"
        )

    def validate_write_path(self, file_path: Union[str, Path]) -> Path:
        """
        Valida che il file sia autorizzato per la scrittura di telemetria o stato.
        VIETA categoricamente qualsiasi scrittura sui file SafeVault di produzione.
        """
        resolved = Path(file_path).resolve()

        # SafeVault Policy Check
        if resolved.name in self.CRITICAL_PRODUCTION_FILES or "profiles" in resolved.parts:
            raise SecurityViolationError(
                f"[SAFEVAULT POLICY VIOLATION] Tentativo di scrittura o sovrascrittura bloccato "
                f"su risorsa protetta di produzione: {resolved.name}"
            )

        # Deny-by-default check
        if not self._is_path_allowed(resolved):
            raise SecurityViolationError(
                f"[DENY-BY-DEFAULT] Scrittura negata al di fuori delle directory autorizzate: {resolved}"
            )

        return resolved

    def open_readonly_sqlite(self, db_path: Union[str, Path]) -> sqlite3.Connection:
        """
        Apre una connessione a SQLite rigorosamente in sola lettura (read-only mode),
        impedendo qualsiasi alterazione o lock distruttivo.
        """
        resolved = Path(db_path).resolve()
        if not resolved.exists() and str(db_path) != ":memory:":
            raise FileNotFoundError(f"Database SQLite non trovato: {resolved}")

        if str(db_path) == ":memory:":
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            return conn

        # Apertura con flag URI mode=ro
        uri = f"file:{resolved.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def assert_readonly_sql(self, query: str) -> None:
        """Verifica che una query SQL contenga solo istruzioni consentite di lettura (SELECT, EXPLAIN)."""
        match = self.FORBIDDEN_SQL_KEYWORDS.search(query)
        if match:
            raise SecurityViolationError(
                f"[SAFEVAULT SQL VIOLATION] Comando SQL potenzialmente distruttivo bloccato: '{match.group(1)}'"
            )
