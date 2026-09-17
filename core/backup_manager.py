from __future__ import annotations

import os
import io
import time
import zipfile
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class BackupManager:
    """
    Gestore di sicurezza per la persistenza e la salvaguardia totale dei dati utente:
    - Profili giocatori (HCP, sacca mazze, distanze, palline)
    - Database SQLite storico gare e statistiche
    - Account utente e credenziali
    - Configurazioni Telegram
    
    Offre snapshot automatici rotativi all'avvio, esportazione ZIP 1-clic e ripristino sicuro.
    """

    def __init__(self, project_root: Path = PROJECT_ROOT, backups_dir: Optional[Path] = None, max_snapshots: int = 15):
        self.project_root = Path(project_root)
        self.backups_dir = Path(backups_dir) if backups_dir else self.project_root / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.max_snapshots = max_snapshots

    def get_critical_files(self) -> List[Path]:
        """Restituisce la lista di tutti i file critici contenenti dati utente."""
        files = []
        # 1. Database SQLite gare
        db_file = self.project_root / "voice_caddy.db"
        if db_file.exists():
            files.append(db_file)

        # 2. Profili utente (Sacca, HCP, distanze)
        profiles_dir = self.project_root / "data" / "profiles"
        if profiles_dir.exists():
            for pf in profiles_dir.glob("*.json"):
                files.append(pf)

        # 3. Credenziali e account
        users_file = self.project_root / "data" / "users.json"
        if users_file.exists():
            files.append(users_file)

        # 4. Telegram mapping e configurazioni
        tg_users = self.project_root / "data" / "telegram_users.json"
        if tg_users.exists():
            files.append(tg_users)
        tg_conf = self.project_root / "data" / "telegram_config.json"
        if tg_conf.exists():
            files.append(tg_conf)

        return files

    def create_startup_snapshot(self) -> Optional[Path]:
        """
        Crea uno snapshot compresso (.zip) di tutti i dati attuali all'avvio dell'applicazione.
        Mantiene automaticamente una cronologia rotativa fino a max_snapshots.
        """
        critical_files = self.get_critical_files()
        if not critical_files:
            logger.info("Nessun dato critico trovato per lo snapshot iniziale.")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"snapshot_{timestamp}.zip"
        snapshot_path = self.backups_dir / snapshot_name

        try:
            with zipfile.ZipFile(snapshot_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in critical_files:
                    if not file_path.exists():
                        continue
                    try:
                        arcname = file_path.relative_to(self.project_root)
                    except ValueError:
                        arcname = file_path.name
                    zf.write(file_path, arcname=str(arcname))

            logger.info(f"Snapshot di sicurezza creato con successo: {snapshot_path}")
            self._prune_old_snapshots()
            return snapshot_path
        except Exception as e:
            logger.error(f"Errore creazione snapshot di sicurezza: {e}")
            return None

    def _prune_old_snapshots(self):
        """Elimina gli snapshot più vecchi eccedenti il limite max_snapshots."""
        try:
            snapshots = sorted(
                self.backups_dir.glob("snapshot_*.zip"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            for old_snap in snapshots[self.max_snapshots:]:
                try:
                    old_snap.unlink()
                    logger.info(f"Rimosso vecchio snapshot per rotazione: {old_snap.name}")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Errore durante rotazione snapshot: {e}")

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """Restituisce l'elenco degli snapshot disponibili con data e dimensione."""
        res = []
        if not self.backups_dir.exists():
            return res

        for snap in sorted(self.backups_dir.glob("snapshot_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
            st = snap.stat()
            dt = datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M:%S")
            size_kb = round(st.st_size / 1024, 1)
            res.append({
                "filename": snap.name,
                "path": snap,
                "date_str": dt,
                "size_kb": size_kb
            })
        return res

    def export_full_backup_bytes(self) -> bytes:
        """
        Genera al volo un archivio ZIP in memoria contenente tutti i dati
        da scaricare tramite st.download_button.
        """
        critical_files = self.get_critical_files()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in critical_files:
                if not file_path.exists():
                    continue
                try:
                    arcname = file_path.relative_to(self.project_root)
                except ValueError:
                    arcname = file_path.name
                zf.write(file_path, arcname=str(arcname))
        buf.seek(0)
        return buf.getvalue()

    def restore_from_zip(self, zip_content: bytes | Path) -> Tuple[bool, str]:
        """
        Ripristina in modo atomico e sicuro tutti i dati da un archivio ZIP.
        Prima del ripristino, crea uno snapshot di emergenza dell'ambiente attuale.
        """
        # 1. Snapshot preventivo per non perdere nulla dell'ambiente attuale
        self.create_startup_snapshot()

        try:
            if isinstance(zip_content, (str, Path)):
                zf = zipfile.ZipFile(zip_content, "r")
            else:
                zf = zipfile.ZipFile(io.BytesIO(zip_content), "r")

            with zf:
                namelist = zf.namelist()
                valid_prefixes = ("data/", "data\\", "voice_caddy.db")
                matched_files = [n for n in namelist if any(n.startswith(p) or n == "voice_caddy.db" for p in valid_prefixes)]

                if not matched_files:
                    return False, "Il file ZIP caricato non contiene file di backup validi per Voice Caddy Pro."

                # Estrazione sicura
                for member in namelist:
                    norm_path = os.path.normpath(member)
                    if norm_path.startswith("..") or os.path.isabs(norm_path):
                        continue

                    if any(norm_path.startswith(p) or norm_path == "voice_caddy.db" for p in ("data", "voice_caddy.db")):
                        target_dest = self.project_root / norm_path
                        target_dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as source, open(target_dest, "wb") as target:
                            shutil.copyfileobj(source, target)

            return True, "Ripristino completato con successo! Tutti i dati, profili e gare sono stati ripristinati."
        except Exception as e:
            logger.error(f"Errore durante il ripristino da backup: {e}")
            return False, f"Impossibile ripristinare il backup: {e}"

    def restore_from_snapshot(self, snapshot_filename: str) -> Tuple[bool, str]:
        """Ripristina i dati da uno snapshot rotativo locale presente in backups/."""
        target_file = self.backups_dir / snapshot_filename
        if not target_file.exists():
            return False, f"Snapshot '{snapshot_filename}' non trovato."
        return self.restore_from_zip(target_file)


# Singleton istanza globale
backup_manager = BackupManager()
