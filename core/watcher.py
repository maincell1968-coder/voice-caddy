from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Callable, Optional


class AutoImportFolderWatcher:
    """
    Auto-Import Folder Watcher for Voice Caddy.
    Monitors a designated drop folder (e.g., synced with iCloud Drive, Dropbox, or Google Drive)
    and automatically triggers transcription and analysis whenever new audio files are added.
    """

    SUPPORTED_EXTENSIONS = {".m4a", ".mp3", ".wav", ".aac", ".opus", ".ogg", ".3gp", ".amr"}

    def __init__(self, watch_folder: str | Path):
        self.watch_folder = Path(watch_folder)
        self.watch_folder.mkdir(parents=True, exist_ok=True)
        self._processed_files = set()

    def scan_new_audio_files(self) -> List[Path]:
        new_files = []
        for file_path in self.watch_folder.glob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                if str(file_path) not in self._processed_files:
                    new_files.append(file_path)
                    self._processed_files.add(str(file_path))
        return sorted(new_files, key=lambda p: p.stat().st_mtime)

    def mark_as_processed(self, file_path: str | Path):
        self._processed_files.add(str(file_path))
