from __future__ import annotations

import os
import sys
import time
import tempfile
import urllib.request
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from core.audio import VoiceCaddyAudioEngine
from core.parser import parse_golf_audio_transcript
from core.metrics import GolfMetricsCalculator
from core.db import DatabaseManager
from core.auth import AuthManager, AIUserConfig, UserRecord
from core.user_profile import UserProfile
from core.course import CourseRegistry, CONERO_GOLF_CLUB, GolfCourse
from core.demo_data import get_demo_golf_round
from core.telegram_config import TelegramConfigManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class VoiceCaddyTelegramBot:
    """
    Motore Telegram Bot per Voice Caddy Pro.
    Permette ai golfisti di inviare note vocali o messaggi di testo direttamente dal campo,
    ricevendo una scorecard ufficiale istantanea, statistiche balistiche e consigli tattici del Caddie PGA.
    """

    def __init__(self, bot_token: Optional[str] = None):
        self.config_mgr = TelegramConfigManager()
        self.bot_token = bot_token or self.config_mgr.get_token()
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN non configurato. Inseriscilo nella configurazione o come variabile d'ambiente.")

        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.audio_engine = VoiceCaddyAudioEngine(model_size="base")
        self.db = DatabaseManager()
        self.auth_mgr = AuthManager()
        self.course_registry = CourseRegistry(storage_dir=PROJECT_ROOT / "courses")
        self.is_running = False

    def _api_request(self, method: str, data: Optional[dict] = None) -> dict:
        url = f"{self.api_url}/{method}"
        req = urllib.request.Request(url)
        req.add_header('Content-Type', 'application/json')
        payload = json.dumps(data).encode('utf-8') if data else None

        try:
            with urllib.request.urlopen(req, data=payload, timeout=30) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logging.error(f"Errore chiamata Telegram API ({method}): {e}")
            return {"ok": False, "error": str(e)}

    def send_message(self, chat_id: int | str, text: str, parse_mode: str = "HTML") -> dict:
        return self._api_request("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        })

    def get_file_path(self, file_id: str) -> Optional[str]:
        res = self._api_request("getFile", {"file_id": file_id})
        if res.get("ok"):
            return res["result"]["file_path"]
        return None

    def download_file(self, file_path: str, dest_path: str):
        url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        urllib.request.urlretrieve(url, dest_path)

    # ---------------------------------------------------------
    # Context Resolution (Player, Course, AI Engine)
    # ---------------------------------------------------------
    def _resolve_context(self, chat_id: int | str) -> Tuple[UserRecord, UserProfile, GolfCourse, AIUserConfig]:
        linked = self.config_mgr.get_linked_user(chat_id)
        all_users = self.auth_mgr.get_all_users()

        user_rec: Optional[UserRecord] = None
        if linked:
            u_id = linked.get("user_id")
            user_rec = self.auth_mgr.get_user_by_id(u_id)

        if not user_rec:
            # Fallback to Stefano as Administrator default
            user_rec = self.auth_mgr.get_user_by_id("strafatti_stefano_pirani")
            if not user_rec and all_users:
                user_rec = all_users[0]

        # Load Profile (clubs, handicap)
        u_id = user_rec.user_id if user_rec else "strafatti_stefano_pirani"
        u_name = f"{user_rec.first_name} {user_rec.last_name}" if user_rec else "Stefano Pirani"
        user_profile = UserProfile.load_for_user(user_id=u_id, default_name=u_name)

        # Course
        active_course_name = linked.get("active_course_name", "Conero Golf Club") if linked else "Conero Golf Club"
        course = None
        for c in self.course_registry.list_courses():
            if c.name.lower() in active_course_name.lower() or active_course_name.lower() in c.name.lower():
                course = c
                break
        if not course:
            course = CONERO_GOLF_CLUB

        # AI Configuration
        ai_cfg = user_rec.ai_config if user_rec else AIUserConfig()

        return user_rec, user_profile, course, ai_cfg

    # ---------------------------------------------------------
    # Response Formatter
    # ---------------------------------------------------------
    def _format_round_summary(self, validated_data, round_id: int, player_name: str, course_name: str) -> str:
        summary = validated_data.performance_summary
        info = validated_data.round_info
        diag = summary.professional_diagnosis

        rel_par = GolfMetricsCalculator.calculate_score_relation_to_par(validated_data.holes)
        rel_par_str = f"+{rel_par}" if rel_par > 0 else ("Par" if rel_par == 0 else f"{rel_par}")

        holes_count = info.holes_played or len(validated_data.holes)
        putts_avg = round(summary.total_putts / holes_count, 2) if holes_count else 0.0

        reply_msg = (
            f"⛳ <b>VOICE CADDY PRO — SCORECARD UFFICIALE</b>\n"
            f"👤 <b>Giocatore:</b> {player_name}\n"
            f"📍 <b>Campo:</b> {course_name}\n"
            f"🔢 <b>Buche giocate:</b> {holes_count}\n\n"
            f"📊 <b>RISULTATI CHIAVE:</b>\n"
            f"• <b>Score Totale:</b> {summary.total_score} ({rel_par_str})\n"
            f"• <b>Fairway Presi (FIR):</b> {summary.fairway_accuracy_pct}%\n"
            f"• <b>Green in Reg. (GIR):</b> {summary.gir_pct}%\n"
            f"• <b>Scrambling:</b> {summary.scrambling_pct}%\n"
            f"• <b>Totale Putt:</b> {summary.total_putts} (Media {putts_avg}/buca)\n"
            f"• <b>Course Mgmt Score:</b> {diag.course_management_score}/100\n\n"
            f"🎯 <b>TENDENZA ERRORE PRINCIPALE:</b>\n"
            f"<i>{summary.primary_miss_tendency}</i>\n\n"
            f"🧠 <b>DIAGNOSI CADDIE PGA:</b>\n"
            f"<i>{diag.executive_narrative[:350]}...</i>\n\n"
        )

        if summary.training_drills_recommended:
            drill = summary.training_drills_recommended[0]
            reply_msg += f"🏋️ <b>ESERCIZIO CONSIGLIATO:</b>\n<b>[{drill.target_area}] {drill.drill_name}:</b> {drill.setup_and_execution}\n\n"

        reply_msg += f"✅ <i>Partita archiviata nel tuo storico (ID #{round_id}). Apri Voice Caddy su PC per visualizzare la mappa vettoriale buca per buca!</i>"
        return reply_msg

    # ---------------------------------------------------------
    # Processing Voice & Text Messages
    # ---------------------------------------------------------
    def process_voice_message(self, chat_id: int | str, file_id: str):
        user_rec, user_profile, active_course, ai_cfg = self._resolve_context(chat_id)
        player_name = f"{user_rec.first_name} {user_rec.last_name}"

        self.send_message(
            chat_id,
            f"🎙️ <i>Nota vocale ricevuta per <b>{player_name}</b> su <b>{active_course.name}</b>!\nTrascrizione Whisper in corso...</i>"
        )

        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
        temp_audio_path = temp_audio.name
        temp_audio.close()

        try:
            telegram_file_path = self.get_file_path(file_id)
            if not telegram_file_path:
                self.send_message(chat_id, "❌ Impossibile scaricare il file audio da Telegram.")
                return

            self.download_file(telegram_file_path, temp_audio_path)

            # Transcribe with Whisper (supports Groq, OpenAI, or local)
            whisper_key = ai_cfg.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
            groq_key = ai_cfg.groq_api_key or os.environ.get("GROQ_API_KEY", "")
            transcript, meta = self.audio_engine.transcribe(
                temp_audio_path,
                engine_mode="local",
                api_key=whisper_key,
                groq_api_key=groq_key
            )

            self.send_message(
                chat_id,
                f"🧠 <i>Trascrizione completata:</i>\n«<i>{transcript[:180]}...</i>»\n\n<i>Analisi colpi con l'IA personale in corso...</i>"
            )

            # Parse with user AI
            raw_data = parse_golf_audio_transcript(
                transcript_text=transcript,
                user_profile=user_profile,
                course=active_course,
                ai_config=ai_cfg
            )

            # Reconcile metrics deterministically
            validated_data = GolfMetricsCalculator.recompute_and_reconcile(raw_data)

            # Save to SQLite with linked user & group
            round_id = self.db.save_round(
                round_data=validated_data,
                user_id=user_rec.user_id,
                group_name=user_rec.group
            )

            reply_msg = self._format_round_summary(validated_data, round_id, player_name, active_course.name)
            self.send_message(chat_id, reply_msg)

        except Exception as e:
            logging.error(f"Errore durante l'elaborazione vocale: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ Si è verificato un errore: {str(e)}")
        finally:
            if os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except OSError:
                    pass

    def process_text_message(self, chat_id: int | str, text: str):
        """Elabora il resoconto testuale dei colpi digitato dal golfista."""
        user_rec, user_profile, active_course, ai_cfg = self._resolve_context(chat_id)
        player_name = f"{user_rec.first_name} {user_rec.last_name}"

        self.send_message(
            chat_id,
            f"📝 <i>Resoconto testuale ricevuto per <b>{player_name}</b> su <b>{active_course.name}</b>.\nAnalisi colpi con l'IA in corso...</i>"
        )

        try:
            raw_data = parse_golf_audio_transcript(
                transcript_text=text,
                user_profile=user_profile,
                course=active_course,
                ai_config=ai_cfg
            )

            validated_data = GolfMetricsCalculator.recompute_and_reconcile(raw_data)

            round_id = self.db.save_round(
                round_data=validated_data,
                user_id=user_rec.user_id,
                group_name=user_rec.group
            )

            reply_msg = self._format_round_summary(validated_data, round_id, player_name, active_course.name)
            self.send_message(chat_id, reply_msg)

        except Exception as e:
            logging.error(f"Errore durante l'elaborazione testuale: {e}", exc_info=True)
            self.send_message(chat_id, f"❌ Errore durante l'analisi: {str(e)}")

    # ---------------------------------------------------------
    # Telegram Commands Handler
    # ---------------------------------------------------------
    def handle_command(self, chat_id: int | str, text: str):
        parts = text.strip().split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # Support commands typed without space, e.g. /giocatoreStefano
        for prefix in ["/giocatore", "/utente", "/login", "/collega", "/campo", "/circolo"]:
            if cmd.startswith(prefix) and cmd != prefix and not args:
                args = [text.strip()[len(prefix):].strip()]
                cmd = prefix
                break

        if cmd in ["/start", "/help", "/guida"]:
            all_users = self.auth_mgr.get_all_users()

            # Format names clearly, disambiguating homonyms
            def format_roster(users_list):
                counts = {}
                for u in users_list:
                    counts[u.first_name.lower()] = counts.get(u.first_name.lower(), 0) + 1
                items = []
                for u in users_list:
                    if counts[u.first_name.lower()] > 1:
                        items.append(f"{u.first_name} {u.last_name[:1]}. ({u.last_name})")
                    else:
                        items.append(u.first_name)
                return items

            strafatti_list = [u for u in all_users if u.group == "strafatti"]
            amici_list = [u for u in all_users if u.group == "amici"]
            strafatti_names = format_roster(strafatti_list)
            amici_names = format_roster(amici_list)

            help_msg = (
                "⛳ <b>BENVENUTO IN VOICE CADDY PRO BOT!</b>\n\n"
                "Usa questo bot durante la partita per registrare i tuoi colpi via voce o testo e ricevere la scorecard immediata.\n\n"
                "<b>📱 COME INVIARE I DATI IN GIOCO:</b>\n"
                "• <b>Nota Vocale:</b> Tieni premuto il microfono di Telegram e descrivi i colpi (buca per buca o a fine giro).\n"
                "• <b>Messaggio di Testo:</b> Scrivi il resoconto (es. <i>'Buca 1: Par 4. Driver 215m in fairway, ferro 7 sul green a 3m, 2 putt, Par'</i>).\n\n"
                "<b>⚙️ COMANDI DISPONIBILI:</b>\n"
                "• <code>/giocatore [Nome]</code>: Collega la chat al tuo profilo (es. <code>/giocatore Stefano</code>)\n"
                "• <code>/profilo</code>: Visualizza il giocatore collegato, handicap e sacca\n"
                "• <code>/campo [Nome]</code>: Imposta il campo di gioco (es. <code>/campo Conero</code>)\n"
                "• <code>/demo</code>: Invia subito una partita PGA di prova per testare il bot\n"
                "• <code>/chi</code>: Mostra chi è il giocatore attualmente attivo\n\n"
                f"<b>👥 Giocatori Registrati:</b>\n"
                f"• <b>Strafatti:</b> {', '.join(strafatti_names)}\n"
            )
            if amici_names:
                help_msg += f"• <b>Amici:</b> {', '.join(amici_names)}\n"

            self.send_message(chat_id, help_msg)

        elif cmd in ["/giocatore", "/utente", "/login", "/collega"]:
            if not args:
                self.send_message(chat_id, "⚠️ Specifica il tuo nome o cognome. Esempio: <code>/giocatore Stefano</code> oppure <code>/giocatore Giorgio</code>")
                return

            search_name = " ".join(args).strip().lower()
            all_users = self.auth_mgr.get_all_users()

            # 1. Exact matches (username, full name, surname, short name like 'marco s')
            exact_matches = []
            for u in all_users:
                full_name = f"{u.first_name} {u.last_name}".lower()
                short_name = f"{u.first_name} {u.last_name[:1]}".lower()
                short_dot = f"{u.first_name} {u.last_name[:1]}.".lower()
                if search_name in [u.username.lower(), full_name, short_name, short_dot, u.last_name.lower()]:
                    exact_matches.append(u)

            if len(exact_matches) == 1:
                matched_user = exact_matches[0]
            elif len(exact_matches) > 1:
                options = "\n".join([f"• <code>/giocatore {u.first_name} {u.last_name}</code>" for u in exact_matches])
                self.send_message(
                    chat_id,
                    f"⚠️ <b>Trovati più giocatori corrispondenti:</b>\n\n{options}\n\n"
                    f"<i>Riprova specificando Nome e Cognome.</i>"
                )
                return
            else:
                # 2. Check first name or partial matches
                partial_matches = []
                for u in all_users:
                    full_name = f"{u.first_name} {u.last_name}".lower()
                    if search_name == u.first_name.lower() or search_name in full_name:
                        partial_matches.append(u)

                if len(partial_matches) == 1:
                    matched_user = partial_matches[0]
                elif len(partial_matches) > 1:
                    options = "\n".join([f"• <code>/giocatore {u.first_name} {u.last_name}</code> (oppure <code>/giocatore {u.username}</code>)" for u in partial_matches])
                    self.send_message(
                        chat_id,
                        f"⚠️ <b>Ci sono più giocatori con il nome «{search_name.title()}»!</b>\n\n"
                        f"Per associare la sacca e l'handicap corretti, specifica il cognome o l'iniziale:\n"
                        f"{options}"
                    )
                    return
                else:
                    matched_user = None

            if matched_user:
                self.config_mgr.link_chat_user(
                    chat_id=chat_id,
                    user_id=matched_user.user_id,
                    group_name=matched_user.group,
                    first_name=matched_user.first_name
                )
                prof = UserProfile.load_for_user(matched_user.user_id)
                self.send_message(
                    chat_id,
                    f"✅ <b>Chat collegata con successo a {matched_user.first_name} {matched_user.last_name}!</b>\n\n"
                    f"• <b>Gruppo:</b> {matched_user.group.upper()}\n"
                    f"• <b>Handicap Registrato:</b> {prof.handicap}\n"
                    f"• <b>Categoria & Tono Caddie:</b> {prof.category.value}\n"
                    f"• <b>Mazza più lunga:</b> {prof.clubs_in_bag[0].club_name if prof.clubs_in_bag else 'Driver'}\n\n"
                    f"🏌️ Ora puoi inviare le tue note vocali o messaggi durante il gioco: saranno registrati nel tuo archivio!"
                )
            else:
                self.send_message(
                    chat_id,
                    f"❌ Nessun giocatore trovato con il nome «{search_name}».\n"
                    f"Usa <code>/start</code> per vedere la lista dei giocatori registrati."
                )

        elif cmd in ["/profilo", "/chi", "/status"]:
            user_rec, user_profile, active_course, ai_cfg = self._resolve_context(chat_id)
            bag_summary = "\n".join([f"• <b>{c.club_name}:</b> {c.carry_meters}m ({c.shaft_flex.value})" for c in user_profile.clubs_in_bag[:8]])

            self.send_message(
                chat_id,
                f"🏌️‍♂️ <b>PROFILO GIOCATORE ATTIVO:</b>\n"
                f"• <b>Nome:</b> {user_rec.first_name} {user_rec.last_name}\n"
                f"• <b>Gruppo:</b> {user_rec.group.upper()}\n"
                f"• <b>Handicap:</b> {user_profile.handicap} ({user_profile.category.value})\n"
                f"• <b>Campo attivo:</b> {active_course.name}\n"
                f"• <b>Provider IA:</b> {ai_cfg.provider.upper()}\n\n"
                f"🎒 <b>Prime mazze in sacca:</b>\n{bag_summary}\n\n"
                f"<i>Per cambiare giocatore scrivi: <code>/giocatore [Nome]</code></i>"
            )

        elif cmd in ["/campo", "/circolo"]:
            if not args:
                courses = self.course_registry.list_courses()
                c_names = [f"• {c.name}" for c in courses]
                self.send_message(chat_id, f"⛳ <b>Campi disponibili:</b>\n" + "\n".join(c_names) + "\n\nUsa: <code>/campo [Nome]</code>")
                return

            c_query = " ".join(args).strip()
            self.config_mgr.set_active_course(chat_id, c_query)
            self.send_message(chat_id, f"✅ Campo da gioco impostato su: <b>{c_query}</b>")

        elif cmd in ["/demo", "/test"]:
            user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
            player_name = f"{user_rec.first_name} {user_rec.last_name}"
            self.send_message(chat_id, "🎮 <i>Generazione Giro Dimostrativo PGA in corso...</i>")

            demo_round = get_demo_golf_round()
            round_id = self.db.save_round(demo_round, user_id=user_rec.user_id, group_name=user_rec.group)
            reply_msg = self._format_round_summary(demo_round, round_id, player_name, active_course.name)
            self.send_message(chat_id, reply_msg)

        else:
            # Not a recognized command -> treat as golf shots text description!
            self.process_text_message(chat_id, text)

    # ---------------------------------------------------------
    # Main Polling Loop
    # ---------------------------------------------------------
    def run_polling(self):
        """Esegue il long-polling continuo per ricevere aggiornamenti da Telegram."""
        self.is_running = True
        offset = 0
        logging.info("⛳ Bot Telegram Voice Caddy Pro avviato in ascolto...")

        # Verify bot identity on startup
        ok, msg, bot_uname = self.config_mgr.test_token(self.bot_token)
        if ok:
            logging.info(f"Bot attivo: @{bot_uname} ({msg})")
            print(f"\n=======================================================")
            print(f"  VOICE CADDY PRO — BOT TELEGRAM ATTIVO!")
            print(f"  Bot Username: @{bot_uname}")
            print(f"  Link diretto: https://t.me/{bot_uname}")
            print(f"  In ascolto di note vocali e messaggi da smartphone...")
            print(f"=======================================================\n")
        else:
            logging.warning(f"Avviso verifica token Telegram: {msg}")

        while self.is_running:
            try:
                res = self._api_request("getUpdates", {"offset": offset, "timeout": 15})
                if res.get("ok"):
                    for update in res.get("result", []):
                        offset = update["update_id"] + 1
                        message = update.get("message", {})
                        if not message:
                            continue

                        chat_id = message.get("chat", {}).get("id")
                        text = message.get("text", "")

                        if "voice" in message:
                            file_id = message["voice"]["file_id"]
                            self.process_voice_message(chat_id, file_id)
                        elif "audio" in message:
                            file_id = message["audio"]["file_id"]
                            self.process_voice_message(chat_id, file_id)
                        elif "video_note" in message:
                            file_id = message["video_note"]["file_id"]
                            self.process_voice_message(chat_id, file_id)
                        elif "video" in message:
                            file_id = message["video"]["file_id"]
                            self.process_voice_message(chat_id, file_id)
                        elif text:
                            if text.startswith("/"):
                                self.handle_command(chat_id, text)
                            else:
                                # Normal text description of golf round
                                self.process_text_message(chat_id, text)

                time.sleep(0.5)
            except KeyboardInterrupt:
                logging.info("Interruzione manuale del bot.")
                self.stop()
                break
            except Exception as e:
                logging.error(f"Errore loop polling Telegram: {e}")
                time.sleep(3)

    def stop(self):
        self.is_running = False


if __name__ == "__main__":
    cfg = TelegramConfigManager()
    token = sys.argv[1] if len(sys.argv) > 1 else cfg.get_token()

    if not token:
        print("\n" + "=" * 60)
        print("  VOICE CADDY PRO — CONFIGURAZIONE BOT TELEGRAM")
        print("=" * 60)
        print("Nessun TELEGRAM_BOT_TOKEN trovato.")
        print("Incolla qui sotto il token ricevuto da @BotFather:")
        try:
            token = input("Token: ").strip()
        except EOFError:
            token = ""

        if token:
            cfg.set_token(token)
            print(f"✅ Token salvato in {cfg.config_file}")
        else:
            print("❌ Token non inserito. Uscita.")
            sys.exit(1)

    bot = VoiceCaddyTelegramBot(bot_token=token)
    bot.run_polling()
