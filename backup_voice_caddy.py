"""
Script di Backup Completo e Sicuro per Voice Caddy Pro
Conforme alla SAFEVAULT POLICY di Voice Caddy.
Crea un archivio compresso con timestamp e aggiorna i backup correnti.
"""

import os
import sys
import shutil
import zipfile
from datetime import datetime

# Assicura compatibilità output console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
VOICE_CADDY_DIR = os.path.join(ROOT_DIR, "voice_caddy")
BACKUPS_DIR = os.path.join(ROOT_DIR, "backups")
VOICE_CADDY_BACKUP_DIR = os.path.join(ROOT_DIR, "Voice_Caddy_BACKUP")

SAFEVAULT_FILES = [
    os.path.join(VOICE_CADDY_DIR, "voice_caddy.db"),
    os.path.join(VOICE_CADDY_DIR, "data", "users.json"),
    os.path.join(VOICE_CADDY_DIR, "data", "telegram_config.json"),
    os.path.join(VOICE_CADDY_DIR, "data", "telegram_users.json"),
    os.path.join(VOICE_CADDY_DIR, "data", "golf_courses.json"),
]

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git"}
EXCLUDE_EXTENSIONS = {".pyc", ".pyo"}

def verify_safevault():
    """Verifica l'integrità dei file protetti da SafeVault prima del backup."""
    print("🛡️ Verifica SafeVault...")
    for file_path in SAFEVAULT_FILES:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"[ERRORE CRITICO] File protetto mancante: {file_path}")
        size = os.path.getsize(file_path)
        if size == 0:
            raise ValueError(f"[ERRORE CRITICO] File protetto vuoto (0 bytes): {file_path}")
        print(f"  [OK] {os.path.basename(file_path)} ({size:,} bytes)")
    
    # Verifica profili
    profiles_dir = os.path.join(VOICE_CADDY_DIR, "data", "profiles")
    if os.path.exists(profiles_dir):
        profiles = [p for p in os.listdir(profiles_dir) if p.endswith(".json")]
        print(f"  [OK] Profili giocatore trovati: {len(profiles)}")
        if not profiles:
            print("  [ATTENZIONE] Nessun profilo JSON presente in data/profiles/")
    else:
        print("  [ATTENZIONE] Directory profili non trovata!")

def create_zip_backup():
    """Crea l'archivio ZIP con timestamp e aggiorna il LATEST."""
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"Voice_Caddy_BACKUP_{now_str}.zip"
    zip_path = os.path.join(ROOT_DIR, zip_name)
    latest_zip_path = os.path.join(ROOT_DIR, "Voice_Caddy_BACKUP_LATEST.zip")
    
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    backup_sub_path = os.path.join(BACKUPS_DIR, f"voice_caddy_backup_{now_str}.zip")

    print(f"\n📦 Creazione archivio ZIP: {zip_name}...")
    file_count = 0
    total_uncompressed = 0

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(VOICE_CADDY_DIR):
            # Filtra directory escluse
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in EXCLUDE_EXTENSIONS:
                    continue
                if file.endswith(".db.bak") or file.endswith(".bak"):
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, ROOT_DIR)
                
                file_size = os.path.getsize(full_path)
                total_uncompressed += file_size
                file_count += 1
                zf.write(full_path, rel_path)

    # Verifica integrità zip
    with zipfile.ZipFile(zip_path, 'r') as zf:
        bad_file = zf.testzip()
        if bad_file is not None:
            raise RuntimeError(f"Errore CRC durante il test dello zip sul file: {bad_file}")

    zip_size = os.path.getsize(zip_path)
    print(f"  Archivio creato con successo: {file_count} file, {total_uncompressed:,} bytes (compresso: {zip_size:,} bytes)")

    # Aggiorna LATEST
    shutil.copy2(zip_path, latest_zip_path)
    print(f"  [OK] Aggiornato {os.path.basename(latest_zip_path)}")

    # Copia in backups/
    shutil.copy2(zip_path, backup_sub_path)
    print(f"  [OK] Copia archiviata in backups/{os.path.basename(backup_sub_path)}")

    return zip_name, file_count, zip_size

def update_backup_folder():
    """Aggiorna la cartella Voice_Caddy_BACKUP."""
    print(f"\n📂 Aggiornamento cartella specchio Voice_Caddy_BACKUP...")
    os.makedirs(VOICE_CADDY_BACKUP_DIR, exist_ok=True)
    target_vc = os.path.join(VOICE_CADDY_BACKUP_DIR, "voice_caddy")
    os.makedirs(target_vc, exist_ok=True)

    copied = 0
    for root, dirs, files in os.walk(VOICE_CADDY_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        rel_root = os.path.relpath(root, VOICE_CADDY_DIR)
        
        dest_dir_in_vc = os.path.join(target_vc, rel_root)
        dest_dir_in_root = os.path.join(VOICE_CADDY_BACKUP_DIR, rel_root)
        os.makedirs(dest_dir_in_vc, exist_ok=True)
        os.makedirs(dest_dir_in_root, exist_ok=True)

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in EXCLUDE_EXTENSIONS or file.endswith(".bak"):
                continue
            src_file = os.path.join(root, file)
            # Copia in entrambi i target per mantenere compatibilità con la struttura esistente
            shutil.copy2(src_file, os.path.join(dest_dir_in_vc, file))
            shutil.copy2(src_file, os.path.join(dest_dir_in_root, file))
            copied += 1

    print(f"  [OK] Cartella specchio aggiornata: {copied} file sincronizzati.")

if __name__ == "__main__":
    print("=" * 60)
    print("⛳ VOICE CADDY PRO - BACKUP MODIFICHE")
    print("=" * 60)
    verify_safevault()
    zip_name, file_count, zip_size = create_zip_backup()
    update_backup_folder()
    print("\n" + "=" * 60)
    print(f"✅ BACKUP COMPLETATO CON SUCCESSO: {zip_name}")
    print("=" * 60)
