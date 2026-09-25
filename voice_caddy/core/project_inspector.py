"""
Voice Caddy Pro — Zero-Token Project Inspector & Diagnostic Engine
Modulo deterministico a zero token che scansiona lo stato del progetto,
rileva criticità, anomalie e genera report strutturati con prompt
pronto per qualsiasi IA esterna (Claude, ChatGPT, Gemini, Ollama).
"""

from __future__ import annotations

import os
import sys
import json
import sqlite3
import subprocess
import platform
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class ProjectAlert:
    level: str  # "CRITICAL", "WARNING", "INFO"
    category: str  # "SafeVault", "Cloud/Git", "Dependencies", "Codebase", "AI/Services"
    title: str
    description: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    remediation_hint: str = ""


@dataclass
class ProjectStateSummary:
    timestamp: str
    python_version: str
    os_info: str
    is_cloud: bool
    safevault_healthy: bool
    git_branch: str
    git_commit: str
    untracked_files_count: int
    uncommitted_changes_count: int
    db_tables_count: int
    db_rounds_count: int
    db_profiles_count: int
    alerts: List[ProjectAlert] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class VoiceCaddyProjectInspector:
    """
    Ispettore deterministico del progetto Voice Caddy Pro.
    Garantisce zero consumo di token (0 LLM cost) ed esegue controlli completi:
    1. Integrità SafeVault & Database
    2. Allineamento Git & Cloud Deployment (Streamlit Cloud readiness)
    3. Dipendenze e pacchetti requirements.txt
    4. Sintassi e coerenza dei file Python
    5. Configurazione AI, Telegram e percorsi GPS
    """

    def __init__(self, root_dir: Optional[Path] = None):
        if root_dir:
            self.root_dir = Path(root_dir).resolve()
        else:
            # Rileva automaticamente se siamo in voice_caddy o nella cartella genitore
            cur = Path(__file__).resolve().parent.parent
            if (cur / "voice_caddy").exists() and (cur / "app.py").exists():
                self.root_dir = cur
            else:
                self.root_dir = cur.parent if cur.name == "voice_caddy" else cur

        self.vc_dir = self.root_dir / "voice_caddy" if (self.root_dir / "voice_caddy").exists() else self.root_dir

    def _is_streamlit_cloud(self) -> bool:
        """Determina se l'esecuzione è su Streamlit Community Cloud."""
        return (
            os.environ.get("STREAMLIT_SERVER_ENVIRONMENT") == "cloud"
            or os.environ.get("IS_STREAMLIT_CLOUD") == "true"
            or Path("/mount/src").exists()
        )

    # -------------------------------------------------------------
    # 1. CONTROLLO SAFEVAULT & DATABASE
    # -------------------------------------------------------------
    def check_safevault(self) -> Dict[str, Any]:
        result = {
            "healthy": True,
            "alerts": [],
            "db_path": "",
            "db_size_kb": 0,
            "db_integrity": "UNKNOWN",
            "tables": {},
            "profiles_count": 0,
            "users_count": 0,
            "has_coordinate_campi": False,
            "backups_count": 0,
            "latest_backup": "N/D"
        }

        # 1.1 Database SQLite
        db_path = self.vc_dir / "voice_caddy.db"
        if not db_path.exists():
            db_path = self.root_dir / "voice_caddy.db"

        if not db_path.exists():
            result["healthy"] = False
            result["alerts"].append(ProjectAlert(
                level="CRITICAL",
                category="SafeVault",
                title="Database voice_caddy.db non trovato",
                description="Il file voice_caddy.db non è presente nella cartella operativa.",
                file_path=str(db_path),
                remediation_hint="Ripristinare il database da un backup SafeVault o eseguire un'inizializzazione controllata senza cancellare dati storici."
            ))
        else:
            result["db_path"] = str(db_path)
            result["db_size_kb"] = round(db_path.stat().st_size / 1024, 1)

            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()

                # PRAGMA integrity_check
                cursor.execute("PRAGMA integrity_check;")
                check_row = cursor.fetchone()
                result["db_integrity"] = check_row[0] if check_row else "error"
                if result["db_integrity"] != "ok":
                    result["healthy"] = False
                    result["alerts"].append(ProjectAlert(
                        level="CRITICAL",
                        category="SafeVault",
                        title=f"Corruzione Database rilevata: {result['db_integrity']}",
                        description="Il controllo PRAGMA integrity_check ha rilevato errori sul file SQLite.",
                        file_path=str(db_path),
                        remediation_hint="Eseguire immediatamente un backup di sicurezza ed effettuare un dump/restore di SQLite."
                    ))

                # Tabelle e conteggi
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [r[0] for r in cursor.fetchall()]
                for t in tables:
                    try:
                        cursor.execute(f"SELECT count(*) FROM {t};")
                        cnt = cursor.fetchone()[0]
                        result["tables"][t] = cnt
                    except Exception:
                        result["tables"][t] = -1

                conn.close()

                # Validazione tabelle chiave
                for essential in ["rounds", "user_profiles"]:
                    if essential not in result["tables"]:
                        result["alerts"].append(ProjectAlert(
                            level="WARNING",
                            category="SafeVault",
                            title=f"Tabella essenziale '{essential}' assente nel DB",
                            description=f"La tabella '{essential}' non è presente nello schema di voice_caddy.db.",
                            file_path=str(db_path),
                            remediation_hint="Eseguire la migrazione schema in core/db.py per ripristinare la tabella."
                        ))

            except Exception as e:
                result["healthy"] = False
                result["alerts"].append(ProjectAlert(
                    level="CRITICAL",
                    category="SafeVault",
                    title="Errore di accesso al database SQLite",
                    description=str(e),
                    file_path=str(db_path),
                    remediation_hint="Verificare i permessi di lettura/scrittura sul file voice_caddy.db."
                ))

        # 1.2 Profili Utente JSON
        profiles_dir = self.vc_dir / "data" / "profiles"
        if profiles_dir.exists():
            profile_files = list(profiles_dir.glob("*.json"))
            result["profiles_count"] = len(profile_files)
            for p_file in profile_files:
                try:
                    with open(p_file, "r", encoding="utf-8") as pf:
                        p_data = json.load(pf)
                        if "player_name" not in p_data and "name" not in p_data:
                            result["alerts"].append(ProjectAlert(
                                level="WARNING",
                                category="SafeVault",
                                title=f"Profilo giocatore incompleto: {p_file.name}",
                                description="Manca la chiave 'player_name' nel profilo JSON.",
                                file_path=str(p_file),
                                remediation_hint="Verificare e completare il file JSON del profilo giocatore."
                            ))
                except Exception as e:
                    result["alerts"].append(ProjectAlert(
                        level="WARNING",
                        category="SafeVault",
                        title=f"Errore parsing JSON profilo: {p_file.name}",
                        description=str(e),
                        file_path=str(p_file),
                        remediation_hint="Correggere la sintassi JSON del file profilo."
                    ))

        # 1.3 Users & Telegram Config
        users_file = self.vc_dir / "data" / "users.json"
        if users_file.exists():
            try:
                with open(users_file, "r", encoding="utf-8") as uf:
                    u_data = json.load(uf)
                    result["users_count"] = len(u_data) if isinstance(u_data, list) else len(u_data.keys())
            except Exception as e:
                result["alerts"].append(ProjectAlert(
                    level="WARNING",
                    category="SafeVault",
                    title="Errore lettura data/users.json",
                    description=str(e),
                    file_path=str(users_file),
                    remediation_hint="Verificare che users.json sia un JSON valido."
                ))

        # 1.4 Coordinate Campi & Tactical JSON
        coord_excel = self.vc_dir / "data" / "coordinate_campi.xlsx"
        tactical_json = self.vc_dir / "data" / "tactical_courses.json"
        result["has_coordinate_campi"] = coord_excel.exists() or tactical_json.exists()
        if not result["has_coordinate_campi"]:
            result["alerts"].append(ProjectAlert(
                level="WARNING",
                category="SafeVault",
                title="Coordinate Campi Tattici assenti",
                description="Né coordinate_campi.xlsx né tactical_courses.json sono presenti in data/.",
                file_path=str(coord_excel),
                remediation_hint="Ripristinare il file coordinate_campi.xlsx per il calcolo del corridoio 3D e radar green."
            ))

        # 1.5 Backups
        backup_dir = self.vc_dir / "backups"
        root_backups = list(self.root_dir.glob("Voice_Caddy_BACKUP*.zip"))
        all_backups = list(backup_dir.glob("*.zip")) if backup_dir.exists() else []
        all_backups.extend(root_backups)
        result["backups_count"] = len(all_backups)
        if all_backups:
            latest = max(all_backups, key=lambda b: b.stat().st_mtime)
            dt = datetime.fromtimestamp(latest.stat().st_mtime)
            result["latest_backup"] = dt.strftime("%Y-%m-%d %H:%M:%S")

        return result

    # -------------------------------------------------------------
    # 2. CONTROLLO GIT & CLOUD READINESS
    # -------------------------------------------------------------
    def check_git_and_cloud(self) -> Dict[str, Any]:
        result = {
            "is_git_repo": False,
            "branch": "N/D",
            "commit": "N/D",
            "commit_msg": "",
            "untracked_files": [],
            "modified_files": [],
            "ahead": 0,
            "behind": 0,
            "alerts": []
        }

        try:
            # Check git
            branch_out = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self.root_dir), capture_output=True, text=True, timeout=5
            )
            if branch_out.returncode == 0:
                result["is_git_repo"] = True
                result["branch"] = branch_out.stdout.strip()

                commit_out = subprocess.run(
                    ["git", "log", "-1", "--format=%h - %s"],
                    cwd=str(self.root_dir), capture_output=True, text=True, timeout=5
                )
                if commit_out.returncode == 0:
                    c_parts = commit_out.stdout.strip().split(" - ", 1)
                    result["commit"] = c_parts[0]
                    result["commit_msg"] = c_parts[1] if len(c_parts) > 1 else ""

                # Untracked in voice_caddy/
                status_out = subprocess.run(
                    ["git", "status", "--porcelain", "voice_caddy/"],
                    cwd=str(self.root_dir), capture_output=True, text=True, timeout=5
                )
                if status_out.returncode == 0:
                    for line in status_out.stdout.splitlines():
                        code = line[:2]
                        fname = line[3:].strip()
                        if "??" in code:
                            result["untracked_files"].append(fname)
                            # Se è un file .py non tracciato in voice_caddy, ALERTA CRITICA PER STREAMLIT CLOUD
                            if fname.endswith(".py"):
                                result["alerts"].append(ProjectAlert(
                                    level="WARNING",
                                    category="Cloud/Git",
                                    title=f"File Python non tracciato in Git: {fname}",
                                    description="Se questo file viene importato dall'app ma non è committato, Streamlit Cloud andrà in ModuleNotFoundError.",
                                    file_path=fname,
                                    remediation_hint=f"Eseguire 'git add {fname}' e commit prima del deploy cloud."
                                ))
                        elif any(c in code for c in ["M", "A", "D", "R"]):
                            result["modified_files"].append(fname)

        except Exception as e:
            result["alerts"].append(ProjectAlert(
                level="INFO",
                category="Cloud/Git",
                title="Git CLI non disponibile o non configurato",
                description=str(e),
                remediation_hint="Verificare che Git sia installato ed accessibile nel path di sistema."
            ))

        return result

    # -------------------------------------------------------------
    # 3. CONTROLLO DIPENDENZE E REQUIREMENTS
    # -------------------------------------------------------------
    def check_dependencies(self) -> Dict[str, Any]:
        result = {
            "root_req_exists": False,
            "vc_req_exists": False,
            "root_packages": [],
            "vc_packages": [],
            "missing_installed": [],
            "alerts": []
        }

        root_req = self.root_dir / "requirements.txt"
        vc_req = self.vc_dir / "requirements.txt"

        if root_req.exists():
            result["root_req_exists"] = True
            with open(root_req, "r", encoding="utf-8") as f:
                result["root_packages"] = [l.strip() for l in f if l.strip() and not l.startswith("#")]

        if vc_req.exists():
            result["vc_req_exists"] = True
            with open(vc_req, "r", encoding="utf-8") as f:
                result["vc_packages"] = [l.strip() for l in f if l.strip() and not l.startswith("#")]

        # Verifica sincronizzazione tra root e vc requirements
        root_pkgs_names = {p.split(">=")[0].split("==")[0].lower() for p in result["root_packages"]}
        vc_pkgs_names = {p.split(">=")[0].split("==")[0].lower() for p in result["vc_packages"]}

        diff = root_pkgs_names.symmetric_difference(vc_pkgs_names)
        if diff:
            result["alerts"].append(ProjectAlert(
                level="WARNING",
                category="Dependencies",
                title="Discrepanza tra requirements.txt (root) e voice_caddy/requirements.txt",
                description=f"Pacchetti disallineati: {', '.join(sorted(diff))}. Questo può provocare build fallite a seconda di come Streamlit Cloud avvia l'app.",
                file_path=str(root_req),
                remediation_hint="Allineare entrambi i file requirements.txt con gli stessi pacchetti."
            ))

        # Verifica pacchetti critici installati nel runtime corrente
        critical_modules = [
            ("streamlit", "streamlit"),
            ("pandas", "pandas"),
            ("plotly", "plotly"),
            ("pydantic", "pydantic"),
            ("openpyxl", "openpyxl"),
            ("PIL", "Pillow"),
            ("fpdf", "fpdf2"),
            ("supabase", "supabase")
        ]

        for mod_name, pkg_name in critical_modules:
            try:
                __import__(mod_name)
            except ImportError:
                result["missing_installed"].append(pkg_name)
                result["alerts"].append(ProjectAlert(
                    level="CRITICAL",
                    category="Dependencies",
                    title=f"Pacchetto critico non installato nell'ambiente: {pkg_name}",
                    description=f"Impossibile importare '{mod_name}'. L'applicazione fallirà all'avvio.",
                    remediation_hint=f"Eseguire 'pip install {pkg_name}'."
                ))

        return result

    # -------------------------------------------------------------
    # 4. CONTROLLO SINTASSI PYTHON CODEBASE
    # -------------------------------------------------------------
    def check_codebase_syntax(self) -> Dict[str, Any]:
        result = {
            "total_py_files": 0,
            "syntax_errors": [],
            "alerts": []
        }

        py_files = []
        for root, dirs, files in os.walk(str(self.vc_dir)):
            if "__pycache__" in root or ".state" in root or "logs" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    py_files.append(Path(root) / f)

        # Include root app.py
        root_app = self.root_dir / "app.py"
        if root_app.exists() and root_app not in py_files:
            py_files.append(root_app)

        result["total_py_files"] = len(py_files)

        for p_file in py_files:
            try:
                with open(p_file, "r", encoding="utf-8") as pf:
                    code = pf.read()
                compile(code, str(p_file), "exec")
            except SyntaxError as se:
                rel_path = str(p_file.relative_to(self.root_dir))
                err_desc = f"{se.msg} (riga {se.lineno})"
                result["syntax_errors"].append({"file": rel_path, "error": err_desc})
                result["alerts"].append(ProjectAlert(
                    level="CRITICAL",
                    category="Codebase",
                    title=f"Errore di Sintassi Python in {rel_path}",
                    description=err_desc,
                    file_path=rel_path,
                    line_number=se.lineno,
                    remediation_hint="Correggere l'errore di sintassi indicato nel file."
                ))
            except Exception:
                pass

        return result

    # -------------------------------------------------------------
    # 5. CONTROLLO AI & SERVIZI (TELEGRAM / SUPABASE / GROQ)
    # -------------------------------------------------------------
    def check_ai_and_services(self) -> Dict[str, Any]:
        result = {
            "telegram_configured": False,
            "supabase_configured": False,
            "groq_configured": False,
            "alerts": []
        }

        # Telegram
        tg_conf = self.vc_dir / "data" / "telegram_config.json"
        if tg_conf.exists():
            try:
                with open(tg_conf, "r", encoding="utf-8") as f:
                    t_data = json.load(f)
                    tok = t_data.get("bot_token", "")
                    if tok and tok != "INSERISCI_QUI_IL_TOKEN":
                        result["telegram_configured"] = True
            except Exception:
                pass

        # Supabase
        sb_url = os.environ.get("SUPABASE_URL", "")
        sb_key = os.environ.get("SUPABASE_KEY", "")
        # Controlla anche in .streamlit/secrets.toml se presente
        secrets_file = self.vc_dir / ".streamlit" / "secrets.toml"
        if secrets_file.exists():
            try:
                content = secrets_file.read_text(encoding="utf-8")
                if "supabase" in content.lower():
                    result["supabase_configured"] = True
            except Exception:
                pass
        if sb_url and sb_key:
            result["supabase_configured"] = True

        # Groq
        if os.environ.get("GROQ_API_KEY"):
            result["groq_configured"] = True

        return result

    # -------------------------------------------------------------
    # 6. ESECUZIONE COMPLETA ISPEZIONE
    # -------------------------------------------------------------
    def run_full_inspection(self) -> ProjectStateSummary:
        safevault = self.check_safevault()
        git_cloud = self.check_git_and_cloud()
        deps = self.check_dependencies()
        codebase = self.check_codebase_syntax()
        services = self.check_ai_and_services()

        all_alerts: List[ProjectAlert] = []
        all_alerts.extend(safevault.get("alerts", []))
        all_alerts.extend(git_cloud.get("alerts", []))
        all_alerts.extend(deps.get("alerts", []))
        all_alerts.extend(codebase.get("alerts", []))
        all_alerts.extend(services.get("alerts", []))

        # Ordinamento alert per severità: CRITICAL > WARNING > INFO
        severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        all_alerts.sort(key=lambda a: severity_order.get(a.level, 3))

        summary = ProjectStateSummary(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            python_version=platform.python_version(),
            os_info=f"{platform.system()} {platform.release()}",
            is_cloud=self._is_streamlit_cloud(),
            safevault_healthy=safevault.get("healthy", False),
            git_branch=git_cloud.get("branch", "N/D"),
            git_commit=git_cloud.get("commit", "N/D"),
            untracked_files_count=len(git_cloud.get("untracked_files", [])),
            uncommitted_changes_count=len(git_cloud.get("modified_files", [])),
            db_tables_count=len(safevault.get("tables", {})),
            db_rounds_count=safevault.get("tables", {}).get("rounds", 0),
            db_profiles_count=safevault.get("profiles_count", 0),
            alerts=all_alerts,
            details={
                "safevault": safevault,
                "git_cloud": git_cloud,
                "dependencies": deps,
                "codebase": codebase,
                "services": services
            }
        )

        return summary

    # -------------------------------------------------------------
    # 7. GENERATORE REPORT MARKDOWN STRUTTURATO
    # -------------------------------------------------------------
    def generate_markdown_report(self, summary: Optional[ProjectStateSummary] = None) -> str:
        if summary is None:
            summary = self.run_full_inspection()

        crit_count = sum(1 for a in summary.alerts if a.level == "CRITICAL")
        warn_count = sum(1 for a in summary.alerts if a.level == "WARNING")
        info_count = sum(1 for a in summary.alerts if a.level == "INFO")

        status_emoji = "🟢 STATO OTTIMALE" if crit_count == 0 and warn_count == 0 else ("🟡 ATTENZIONE" if crit_count == 0 else "🔴 CRITICITÀ RILEVATE")

        md = []
        md.append(f"# ⛳ VOICE CADDY PRO — RESUME STATO PROGETTO & AUDIT")
        md.append(f"**Generato:** `{summary.timestamp}` | **Ambiente:** `{'☁️ Streamlit Cloud' if summary.is_cloud else '💻 Locale'}` | **Valutazione Generale:** **{status_emoji}**\n")

        md.append("---")
        md.append("## 📊 1. METRICHE CHIAVE DI SISTEMA")
        md.append(f"- **Runtime:** Python `{summary.python_version}` su `{summary.os_info}`")
        md.append(f"- **Git Branch & Commit:** `{summary.git_branch}` (`{summary.git_commit}`)")
        md.append(f"- **Integrità SafeVault Policy:** `{'🛡️ CONFORME' if summary.safevault_healthy else '⚠️ ANOMALIA'}`")
        md.append(f"- **Database SQLite (`voice_caddy.db`):** {summary.details['safevault'].get('db_size_kb', 0)} KB | {summary.db_tables_count} Tabelle | {summary.db_rounds_count} Partite Storiche")
        md.append(f"- **Profili Giocatori & Membri:** {summary.db_profiles_count} profili JSON | {summary.details['safevault'].get('users_count', 0)} utenti registrati")
        md.append(f"- **Ultimo Backup di Sicurezza:** `{summary.details['safevault'].get('latest_backup', 'N/D')}` (Totale archivi: {summary.details['safevault'].get('backups_count', 0)})")
        md.append(f"- **File Python Verificati:** {summary.details['codebase'].get('total_py_files', 0)} file compilati senza errori di sintassi")
        md.append(f"- **File Modificati / Non Tracciati:** {summary.uncommitted_changes_count} modificati | {summary.untracked_files_count} untracked\n")

        md.append("---")
        md.append(f"## 🚨 2. QUADRO ALLERTE & CRITICITÀ ({crit_count} Critiche, {warn_count} Avvisi, {info_count} Info)")

        if not summary.alerts:
            md.append("✅ **Nessuna criticità rilevata!** Il sistema è allineato, integro e pronto all'uso sia in locale che sul cloud.\n")
        else:
            for idx, a in enumerate(summary.alerts, 1):
                icon = "🔴" if a.level == "CRITICAL" else ("🟡" if a.level == "WARNING" else "🔵")
                md.append(f"### {icon} #{idx} [{a.level}] {a.title} ({a.category})")
                md.append(f"- **Descrizione:** {a.description}")
                if a.file_path:
                    loc = f"`{a.file_path}`" + (f" (riga {a.line_number})" if a.line_number else "")
                    md.append(f"- **File interessato:** {loc}")
                if a.remediation_hint:
                    md.append(f"- **Risoluzione suggerita:** {a.remediation_hint}")
                md.append("")

        md.append("---")
        md.append("## 🤖 3. PROMPT DI INTERVENTO PER IA ESTERNA (Copia & Incolla)")
        md.append("*(Copia il blocco sottostante e incollalo a qualsiasi IA per richiedere la risoluzione immediata)*\n")

        prompt_text = self.generate_ai_prompt(summary)
        md.append("```markdown")
        md.append(prompt_text)
        md.append("```\n")

        return "\n".join(md)

    # -------------------------------------------------------------
    # 8. GENERATORE PROMPT IA PER INTERVENTI AD HOC
    # -------------------------------------------------------------
    def generate_ai_prompt(self, summary: ProjectStateSummary) -> str:
        prompt_lines = []
        prompt_lines.append("Agisci come Senior Fullstack Python Developer & Architect per il progetto Voice Caddy Pro.")
        prompt_lines.append("Di seguito è riportato il resoconto dello stato del progetto con le criticità e gli alert rilevati dal modulo di monitoraggio zero-token:\n")

        prompt_lines.append(f"**CONTESTO DI SISTEMA:**")
        prompt_lines.append(f"- Stack: Python {summary.python_version}, Streamlit, SQLite (SafeVault), Plotly, Faster-Whisper, Telegram Bot FSM.")
        prompt_lines.append(f"- Branch: {summary.git_branch} (commit {summary.git_commit})")
        prompt_lines.append(f"- SafeVault Policy: È FATTO ASSOLUTO DIVIETO di cancellare, sovrascrivere o resettare voice_caddy.db, i profili JSON in data/profiles/ e data/coordinate_campi.xlsx.\n")

        crit_alerts = [a for a in summary.alerts if a.level in ["CRITICAL", "WARNING"]]
        if not crit_alerts:
            prompt_lines.append("**STATO ATTUALE:** Tutte le componenti principali sono stabili e senza errori critici.")
            prompt_lines.append("Richiesta: Proponi eventuali ottimizzazioni di performance, pulizia codice o miglioramenti architetturali coerenti con il progetto.")
        else:
            prompt_lines.append(f"**ELENCO DELLE ANOMALIE DA RISOLVERE (Totale: {len(crit_alerts)}):**")
            for idx, a in enumerate(crit_alerts, 1):
                icon = "🔴" if a.level == "CRITICAL" else "🟡"
                prompt_lines.append(f"{idx}. {icon} [{a.level}] {a.title} ({a.category})")
                prompt_lines.append(f"   - Dettaglio: {a.description}")
                if a.file_path:
                    loc = a.file_path + (f":{a.line_number}" if a.line_number else "")
                    prompt_lines.append(f"   - Posizione: {loc}")
                if a.remediation_hint:
                    prompt_lines.append(f"   - Azione raccomandata: {a.remediation_hint}")
            prompt_lines.append("")
            prompt_lines.append("**OBIETTIVO DELL'INTERVENTO:**")
            prompt_lines.append("1. Analizza la causa esatta di ciascuna anomalia sopra elencata.")
            prompt_lines.append("2. Fornisci il codice corretto pronto per l'integrazione, specificando chiaramente file target e modifiche.")
            prompt_lines.append("3. Assicurati che l'intervento preservi al 100% i dati SafeVault e sia pienamente compatibile con Streamlit Cloud.")

        return "\n".join(prompt_lines)

    # -------------------------------------------------------------
    # 9. MOTORE CHAT DETERMINISTICO A ZERO TOKEN
    # -------------------------------------------------------------
    def chat_response(self, user_message: str) -> str:
        """
        Elabora il messaggio utente in modo 100% deterministico a zero token.
        Comandi supportati:
        - resume, /resume, stato, report, audit -> Genera report completo
        - alert, criticità, warning -> Mostra solo gli alert
        - safevault, db, database -> Stato database e profili
        - git, cloud -> Stato branch, untracked e cloud readiness
        - ai, telegram -> Servizi e chiavi API
        - help, comandi -> Guida ai comandi rapidi
        """
        msg = (user_message or "").strip().lower()

        if any(w in msg for w in ["resume", "stato", "report", "audit", "status", "/resume"]):
            summary = self.run_full_inspection()
            return self.generate_markdown_report(summary)

        elif any(w in msg for w in ["alert", "criticit", "warning", "problemi", "errori"]):
            summary = self.run_full_inspection()
            if not summary.alerts:
                return "✅ **Nessun alert attivo!** Il progetto Voice Caddy Pro non presenta anomalie né criticità da sanare."
            res = [f"### 🚨 Quadro Alert e Criticità Rilevate ({len(summary.alerts)})"]
            for idx, a in enumerate(summary.alerts, 1):
                icon = "🔴" if a.level == "CRITICAL" else ("🟡" if a.level == "WARNING" else "🔵")
                res.append(f"**{icon} #{idx} [{a.level}] {a.title}** ({a.category})")
                res.append(f"- *Problema:* {a.description}")
                if a.file_path:
                    res.append(f"- *File:* `{a.file_path}`")
                if a.remediation_hint:
                    res.append(f"- *Azione:* {a.remediation_hint}")
                res.append("")
            return "\n".join(res)

        elif any(w in msg for w in ["safevault", "db", "database", "partite"]):
            sv = self.check_safevault()
            res = [
                "### 🛡️ Stato SafeVault & Database",
                f"- **Integrità:** `{'CONFORME' if sv['healthy'] else 'NON CONFORME'}` (PRAGMA: `{sv['db_integrity']}`)",
                f"- **Dimensione DB:** `{sv['db_size_kb']} KB`",
                f"- **Profili Giocatori:** `{sv['profiles_count']} profili JSON salvati`",
                f"- **Utenti Registrati:** `{sv['users_count']} account`",
                f"- **Coordinate Campi GPS:** `{'Presenti' if sv['has_coordinate_campi'] else 'Assenti'}`",
                f"- **Ultimo Backup:** `{sv['latest_backup']}` (Totale archivi: `{sv['backups_count']}`)",
                "\n**Conteggio Righe Tabelle:**"
            ]
            for t, cnt in sv.get("tables", {}).items():
                res.append(f"- `{t}`: {cnt} record")
            return "\n".join(res)

        elif any(w in msg for w in ["git", "cloud", "deploy", "branch", "commit"]):
            gc = self.check_git_and_cloud()
            res = [
                "### ☁️ Stato Git & Streamlit Cloud Readiness",
                f"- **Branch Attivo:** `{gc['branch']}`",
                f"- **Ultimo Commit:** `{gc['commit']}` ({gc['commit_msg']})",
                f"- **File Modificati:** `{len(gc['modified_files'])} file`",
                f"- **File Non Tracciati (Untracked):** `{len(gc['untracked_files'])} file`"
            ]
            if gc["untracked_files"]:
                res.append("\n*File non tracciati in voice_caddy/:*")
                for u in gc["untracked_files"][:8]:
                    res.append(f"- `{u}`")
                if len(gc["untracked_files"]) > 8:
                    res.append(f"- ...altri {len(gc['untracked_files']) - 8} file")
            return "\n".join(res)

        elif any(w in msg for w in ["ai", "telegram", "servizi", "supabase", "groq"]):
            srv = self.check_ai_and_services()
            return (
                "### 🤖 Stato Servizi Esterni & Integrazioni\n"
                f"- **Bot Telegram:** `{'Configurato & Attivo' if srv['telegram_configured'] else 'Token non configurato o default'}`\n"
                f"- **Database Supabase Cloud:** `{'Configurato' if srv['supabase_configured'] else 'Non configurato (modalità locale attiva)'}`\n"
                f"- **Groq Cloud AI:** `{'Chiave API presente' if srv['groq_configured'] else 'Non rilevata in variabili di ambiente'}`\n"
            )

        else:
            return (
                "👋 **Chat Ispettore Progetto Voice Caddy (Zero Token)**\n\n"
                "Questa chat opera al **100% in modalità deterministica locale** senza consumare token di alcun modello LLM.\n\n"
                "💡 **Comandi disponibili:**\n"
                "- `resume` o `/resume`: Genera il dossier completo dello stato del progetto con gli alert e il prompt per l'IA.\n"
                "- `alert`: Mostra solo le criticità e gli avvisi da correggere.\n"
                "- `safevault`: Mostra i dettagli di database, integrità, profili e backup.\n"
                "- `git`: Mostra lo stato di Git, branch, commit e cloud readiness.\n"
                "- `servizi`: Mostra lo stato di Telegram, Supabase e Groq.\n"
                "- `help`: Mostra questa guida."
            )


# Istanza singleton globale
project_inspector = VoiceCaddyProjectInspector()


# -------------------------------------------------------------
# CLI ENTRY POINT (per esecuzione diretta da terminale o bat)
# -------------------------------------------------------------
if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "resume"
    resp = project_inspector.chat_response(cmd)
    # Stampa sicura su Windows stdout
    try:
        print(resp)
    except UnicodeEncodeError:
        print(resp.encode("ascii", "backslashreplace").decode("ascii"))
