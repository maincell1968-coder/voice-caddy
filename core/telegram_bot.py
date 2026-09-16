from __future__ import annotations

import os
import sys
import time
import tempfile
import urllib.request
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from core.audio import VoiceCaddyAudioEngine
from core.parser import parse_golf_audio_transcript, parse_quick_shot_update
from core.metrics import GolfMetricsCalculator
from core.db import DatabaseManager
from core.auth import AuthManager, AIUserConfig, UserRecord
from core.user_profile import UserProfile
from core.course import CourseRegistry, CONERO_GOLF_CLUB, GolfCourse
from core.demo_data import get_demo_golf_round
from core.telegram_config import TelegramConfigManager
from core.elevation_service import elevation_service, haversine_distance
from core.live_session import LiveSessionManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class VoiceCaddyTelegramBot:
    """
    Motore Telegram Bot per Voice Caddy Pro.
    Supporta:
    1. Tracciamento GPS in tempo reale (singolo e Live Location).
    2. Calcolo orografico del dislivello e balistica 'Plays Like Distance' (Open-Meteo & Open-Elevation).
    3. Raccomandazione bastone basata sulla sacca personale del giocatore.
    4. Parser vocale e testuale per singoli colpi o scorecard completa.
    5. Fallback trasparente su distanze piane se GPS o elevazione sono disattivati.
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
        self.session_mgr = LiveSessionManager()
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

    def get_on_course_keyboard(self) -> dict:
        """Restituisce la tastiera persistente con pulsante GPS rapido a 1 tocco e azioni di gioco."""
        return {
            "keyboard": [
                [{"text": "📍 Calcola Distanza & Plays Like", "request_location": True}],
                [{"text": "⏩ Prossima Buca"}, {"text": "📊 Stato & Buca"}],
                [{"text": "🎒 Profilo & Sacca"}, {"text": "🔄 Nuovo Giro"}]
            ],
            "resize_keyboard": True,
            "is_persistent": True
        }

    def send_message(self, chat_id: int | str, text: str, parse_mode: str = "HTML", reply_markup: Optional[dict] = None) -> dict:
        markup = reply_markup if reply_markup is not None else self.get_on_course_keyboard()
        return self._api_request("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "reply_markup": markup
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
    # GPS Location & Plays Like Ballistic Handler
    # ---------------------------------------------------------
    def handle_location_update(
        self,
        chat_id: int | str,
        lat: float,
        lon: float,
        altitude: Optional[float] = None
    ) -> dict:
        """
        Gestisce la posizione GPS inviata dal giocatore (singola o Live Location).
        1. Recupera la buca corrente della sessione utente.
        2. Calcola la distanza percorsa dal colpo precedente.
        3. Calcola la distanza orizzontale e la quota della palla.
        4. Calcola il dislivello rispetto al green (Delta h = h_green - h_palla) e la Plays Like Distance.
        5. Suggerisce il bastone ideale dalla sacca personale del giocatore.
        6. Invia una risposta sintetica ed immediata.
        """
        user_rec, user_profile, active_course, ai_cfg = self._resolve_context(chat_id)
        session = self.session_mgr.get_or_create_session(chat_id, user_id=user_rec.user_id, course_id=active_course.course_id)

        # Aggiorna posizione e recupera metratura percorsa dal colpo precedente
        distance_covered, current_hole, current_shot = self.session_mgr.update_position(chat_id, lat, lon, altitude)

        # Risolvi target pin per la buca attiva
        pin_override = self.session_mgr.get_pin_override(chat_id, current_hole)
        hole_info = active_course.get_hole(current_hole)

        if pin_override:
            target_lat, target_lon, target_alt = pin_override
        elif hole_info and hole_info.coordinates:
            target_lat = hole_info.coordinates.target_lat
            target_lon = hole_info.coordinates.target_lon
            target_alt = hole_info.coordinates.target_altitude
        else:
            # Fallback coordinate generiche Sirolo
            target_lat, target_lon, target_alt = (43.5199, 13.6072, 110.0)

        # Fallback stima dislivello se API offline
        fallback_elev = 0.0
        if hole_info:
            prof = hole_info.slope_elevation_profile.lower()
            if "salita" in prof:
                fallback_elev = 8.0
            elif "discesa" in prof:
                fallback_elev = -8.0

        # Calcola approccio tramite elevation_service
        approach = elevation_service.calculate_hole_approach(
            ball_lat=lat,
            ball_lon=lon,
            target_lat=target_lat,
            target_lon=target_lon,
            ball_altitude=altitude,
            target_altitude=target_alt,
            slope_factor=1.0,
            fallback_elevation_diff=fallback_elev
        )

        # Suggerisci il bastone dalla sacca personale
        recommended_club = user_profile.recommend_club_for_distance(approach["plays_like_distance"])
        rec_club_str = f"{recommended_club.club_name} ({int(recommended_club.carry_meters)}m)" if recommended_club else "N/D"

        # Registra il colpo live nel database
        self.session_mgr.record_live_shot(
            chat_id=chat_id,
            hole_number=current_hole,
            shot_index=current_shot,
            club=recommended_club.club_name if recommended_club else None,
            lie="tee" if current_shot == 1 else "fairway",
            latitude=lat,
            longitude=lon,
            altitude=approach["ball_altitude"],
            distance_covered=distance_covered,
            raw_distance_to_green=approach["raw_distance"],
            plays_like_distance=approach["plays_like_distance"],
            elevation_diff=approach["elevation_diff"],
            notes=f"Plays Like: {approach['plays_like_distance']}m"
        )

        # Formatta l'output sintetico
        elev_val = int(round(approach["elevation_diff"]))
        sign = "+" if elev_val > 0 else ""
        if elev_val == 0:
            elev_str = "0m (Pianura)"
        else:
            elev_str = f"{sign}{elev_val}m ({approach['slope_label']})"

        raw_dist = int(round(approach["raw_distance"]))
        pl_dist = int(round(approach["plays_like_distance"]))
        par_val = hole_info.par if hole_info else 4

        reply_msg = (
            f"⛳ <b>Buca {current_hole}</b> (Par {par_val}) — <b>Colpo {current_shot}</b>\n\n"
            f"📏 <b>Distanza reale:</b> {raw_dist}m | ⛰️ <b>Dislivello:</b> {elev_str}\n"
            f"🎯 <b>Plays Like:</b> ~{pl_dist}m (Consigliato: <b>{rec_club_str}</b>)\n"
        )

        if distance_covered is not None and distance_covered >= 10:
            prev_shot = max(1, current_shot - 1)
            reply_msg += f"\n🚀 <i>Distanza percorsa dal Colpo {prev_shot}: <b>{int(round(distance_covered))}m</b></i>\n"

        reply_msg += (
            f"\n💡 <i>Dopo il colpo, detta/scrivi il bastone (es. 'Ferro 7 in green') "
            f"oppure usa <code>/prossima</code> per passare alla buca successiva.</i>"
        )

        return self.send_message(chat_id, reply_msg)

    def handle_manual_distance(self, chat_id: int | str, manual_distance: float) -> dict:
        """
        Fallback di resilienza quando il GPS è assente o il giocatore inserisce
        la distanza rilevata da paletti/irrigatori (es. /distanza 138).
        """
        user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
        session = self.session_mgr.get_or_create_session(chat_id, user_id=user_rec.user_id, course_id=active_course.course_id)
        current_hole = session.get("current_hole", 1)
        current_shot = session.get("current_shot_index", 1)
        hole_info = active_course.get_hole(current_hole)

        elev_diff = 0.0
        slope_label = "Pianura"
        if hole_info:
            prof = hole_info.slope_elevation_profile.lower()
            if "salita" in prof:
                elev_diff = 8.0
                slope_label = "Salita (Stima orografica)"
            elif "discesa" in prof:
                elev_diff = -8.0
                slope_label = "Discesa (Stima orografica)"

        plays_like = round(manual_distance + elev_diff, 1)
        rec_club = user_profile.recommend_club_for_distance(plays_like)
        rec_club_str = f"{rec_club.club_name} ({int(rec_club.carry_meters)}m)" if rec_club else "N/D"

        sign = "+" if elev_diff > 0 else ""
        elev_str = f"{sign}{int(elev_diff)}m ({slope_label})" if elev_diff != 0 else "0m (In pianura)"

        reply_msg = (
            f"📍 <b>Distanza Manuale (Paletto/Scorecard) — Buca {current_hole}</b>\n\n"
            f"📏 <b>Distanza indicata:</b> {int(manual_distance)}m | ⛰️ <b>Dislivello:</b> {elev_str}\n"
            f"🎯 <b>Plays Like stimato:</b> ~{int(plays_like)}m (Consigliato: <b>{rec_club_str}</b>)\n\n"
            f"💡 <i>Per inviare la posizione GPS esatta, usa l'icona graffetta 📎 ➔ Posizione su Telegram.</i>"
        )
        return self.send_message(chat_id, reply_msg)

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

            # Controllo se è un update rapido di un singolo colpo durante la buca
            quick = parse_quick_shot_update(transcript)
            if quick["is_quick_shot"]:
                session = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
                h_num = session.get("current_hole", 1)
                s_idx = quick["shot_index"] or session.get("current_shot_index", 1)
                club = quick["club"]
                lie = quick["lie"]

                self.session_mgr.record_live_shot(
                    chat_id=chat_id,
                    hole_number=h_num,
                    shot_index=s_idx,
                    club=club,
                    lie=lie,
                    notes=transcript
                )
                next_shot = self.session_mgr.advance_shot(chat_id)

                self.send_message(
                    chat_id,
                    f"🏌️‍♂️ <b>Buca {h_num} — Colpo {s_idx} Registrato!</b>\n"
                    f"• <b>Bastone:</b> {club or 'Non specificato'}\n"
                    f"• <b>Lie:</b> {lie.title()}\n"
                    f"• <i>Trascrizione:</i> «{transcript}»\n\n"
                    f"📍 <i>Raggiungi la palla e invia la posizione GPS per preparare il <b>Colpo {next_shot}</b>!</i>"
                )
                return

            # Altrimenti è un resoconto completo della partita
            self.send_message(
                chat_id,
                f"🧠 <i>Trascrizione completata:</i>\n«<i>{transcript[:180]}...</i>»\n\n<i>Analisi giro completo con l'IA in corso...</i>"
            )

            raw_data = parse_golf_audio_transcript(
                transcript_text=transcript,
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
        clean = text.strip()
        if clean in ["⏩ Prossima Buca", "📊 Stato & Buca", "🎒 Profilo & Sacca", "🔄 Nuovo Giro"]:
            return self.handle_command(chat_id, clean)

        user_rec, user_profile, active_course, ai_cfg = self._resolve_context(chat_id)
        player_name = f"{user_rec.first_name} {user_rec.last_name}"

        # Controllo se è un update rapido di un singolo colpo durante la buca
        quick = parse_quick_shot_update(text)
        if quick["is_quick_shot"]:
            session = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
            h_num = session.get("current_hole", 1)
            s_idx = quick["shot_index"] or session.get("current_shot_index", 1)
            club = quick["club"]
            lie = quick["lie"]

            self.session_mgr.record_live_shot(
                chat_id=chat_id,
                hole_number=h_num,
                shot_index=s_idx,
                club=club,
                lie=lie,
                notes=text
            )
            next_shot = self.session_mgr.advance_shot(chat_id)

            msg = (
                f"🏌️‍♂️ <b>Buca {h_num} — Colpo {s_idx} Registrato!</b>\n"
                f"• <b>Bastone:</b> {club or 'Non specificato'}\n"
                f"• <b>Lie:</b> {lie.title()}\n\n"
            )
            if quick["manual_distance"]:
                self.send_message(chat_id, msg)
                self.handle_manual_distance(chat_id, quick["manual_distance"])
            else:
                msg += f"📍 <i>Raggiungi la palla e tocca <b>[📍 Calcola Distanza & Plays Like]</b> per preparare il <b>Colpo {next_shot}</b>!</i>"
                self.send_message(chat_id, msg)
            return

        # Altrimenti è un resoconto completo della partita
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
        clean_text = text.strip()
        parts = clean_text.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # Intercettazione pulsanti rapidi da tastiera Telegram
        if "prossima" in clean_text.lower() and not clean_text.startswith("/"):
            cmd = "/prossima"
        elif "stato" in clean_text.lower() and not clean_text.startswith("/"):
            cmd = "/stato"
        elif "profilo" in clean_text.lower() and not clean_text.startswith("/"):
            cmd = "/profilo"
        elif "nuovo giro" in clean_text.lower() and not clean_text.startswith("/"):
            cmd = "/nuovogiro"

        # Support commands typed without space, e.g. /giocatoreStefano
        for prefix in ["/giocatore", "/utente", "/login", "/collega", "/campo", "/circolo", "/buca", "/h", "/distanza", "/paletto"]:
            if cmd.startswith(prefix) and cmd != prefix and not args:
                args = [text.strip()[len(prefix):].strip()]
                cmd = prefix
                break

        if cmd in ["/start", "/help", "/guida"]:
            all_users = self.auth_mgr.get_all_users()

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
                "⛳ <b>VOICE CADDY PRO — BOT GPS & PLAYS LIKE CADDIE</b>\n\n"
                "Risolve il problema delle distanze cieche, calcola il dislivello orografico "
                "e suggerisce il bastone ideale dalla tua sacca in base alla <b>Plays Like Distance</b>.\n\n"
                "<b>📱 COME GIOCARE IN CAMPO IN 3 SEMPLICI PASSAGGI:</b>\n\n"
                "1️⃣ <b>SUL TEE DI PARTENZA:</b>\n"
                "Tocca <code>⏩ Prossima Buca</code> (o <code>/buca 1</code>). Tira il tuo colpo di partenza.\n\n"
                "2️⃣ <b>QUANDO ARRIVI SULLA PALLA:</b>\n"
                "Sblocca lo smartphone e tocca il grande pulsante in basso:\n"
                "👉 <b>[ 📍 Calcola Distanza & Plays Like ]</b>\n"
                "<i>Con 1 solo tocco, Telegram invia il tuo GPS esatto. In meno di 1 secondo ricevi:</i>\n"
                "• <b>Distanza reale al green</b> (metri laser in piano)\n"
                "• <b>Dislivello altimetrico</b> (es. +8m in Salita o -10m in Discesa)\n"
                "• <b>Plays Like Distance</b> (es. 138m ➔ gioca come 146m)\n"
                "• <b>Bastone consigliato</b> (dalla tua sacca reale)\n\n"
                "3️⃣ <b>DOPO IL COLPO:</b>\n"
                "Mentre cammini verso la palla successiva o verso il green, tieni premuto il microfono per 2 secondi e detta il colpo eseguito (es. <i>'Ferro 7 dal fairway'</i>).\n"
                "<i>Zero attese, zero rallentamenti per i compagni di gioco!</i>\n\n"
                "<b>⚙️ ALTRI COMANDI RAPIDI:</b>\n"
                "• <code>/distanza [metri]</code>: Fallback manuale se leggi un paletto (es. <code>/distanza 138</code>)\n"
                "• <code>/pin [offset o coords]</code>: Personalizza la profondità della bandiera\n"
                "• <code>/stato</code>: Verifica buca e colpo attuale\n"
                "• <code>/giocatore [Nome]</code>: Collega la chat al tuo profilo\n"
                "• <code>/campo [Nome]</code>: Imposta il percorso (es. Conero Golf Club)\n\n"
                f"<b>👥 Giocatori Registrati:</b>\n"
                f"• <b>Strafatti:</b> {', '.join(strafatti_names)}\n"
            )
            if amici_names:
                help_msg += f"• <b>Amici:</b> {', '.join(amici_names)}\n"

            help_msg += "\n⚖️ <i>Voice Caddy Pro &bull; Concept, Architettura e Sviluppo: <b>Stefano Pirani</b></i>\n"

            self.send_message(chat_id, help_msg)

        elif cmd in ["/buca", "/h"]:
            if not args or not args[0].isdigit():
                self.send_message(chat_id, "⚠️ Specifica il numero della buca. Esempio: <code>/buca 4</code>")
                return
            h_val = int(args[0])
            self.session_mgr.set_current_hole(chat_id, h_val)
            self.send_message(
                chat_id,
                f"⛳ <b>Impostata Buca {h_val}!</b>\n"
                f"Invia la tua posizione GPS (📎 ➔ Posizione) per calcolare la distanza e il Plays Like al green."
            )

        elif cmd in ["/prossima", "/next"]:
            next_h = self.session_mgr.next_hole(chat_id)
            self.send_message(
                chat_id,
                f"⛳ <b>Avanzato a Buca {next_h}!</b>\n"
                f"Sei sul tee di partenza. Invia la posizione quando hai effettuato il tiro!"
            )

        elif cmd in ["/distanza", "/paletto"]:
            if not args:
                self.send_message(chat_id, "⚠️ Inserisci la metratura (es. <code>/distanza 138</code> oppure <code>/paletto 150</code>)")
                return
            try:
                d_val = float(args[0])
                self.handle_manual_distance(chat_id, d_val)
            except ValueError:
                self.send_message(chat_id, "⚠️ Distanza non valida. Inserisci un numero in metri.")

        elif cmd in ["/pin", "/bandiera"]:
            if not args:
                self.send_message(
                    chat_id,
                    "⛳ <b>Personalizzazione Posizione Bandiera (Pin):</b>\n"
                    "Puoi specificare coordinate precise o scostamenti:\n"
                    "• <code>/pin 43.5199 13.6072</code>\n"
                    "• <code>/pin centro</code> (ripristina centro green)"
                )
                return
            if args[0].lower() in ["centro", "reset", "default"]:
                user_rec, _, active_course, _ = self._resolve_context(chat_id)
                session = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
                h_num = session.get("current_hole", 1)
                hole_info = active_course.get_hole(h_num)
                if hole_info and hole_info.coordinates:
                    hole_info.coordinates.pin_lat = None
                    hole_info.coordinates.pin_lon = None
                self.send_message(chat_id, f"✅ Ripristinato pin sul centro green per la Buca {h_num}.")
            elif len(args) >= 2:
                try:
                    p_lat = float(args[0])
                    p_lon = float(args[1])
                    p_alt = float(args[2]) if len(args) > 2 else None
                    user_rec, _, active_course, _ = self._resolve_context(chat_id)
                    session = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
                    h_num = session.get("current_hole", 1)
                    self.session_mgr.set_pin_override(chat_id, h_num, p_lat, p_lon, p_alt)
                    self.send_message(chat_id, f"✅ Posizione bandiera aggiornata per Buca {h_num} ({p_lat}, {p_lon})!")
                except ValueError:
                    self.send_message(chat_id, "⚠️ Coordinate non valide. Usa: <code>/pin lat lon</code>")

        elif cmd in ["/stato", "/dove"]:
            user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
            session = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
            h_num = session.get("current_hole", 1)
            s_idx = session.get("current_shot_index", 1)
            last_lat = session.get("last_latitude")
            last_lon = session.get("last_longitude")
            pos_str = f"{last_lat:.5f}, {last_lon:.5f}" if (last_lat and last_lon) else "Nessuna posizione registrata"

            self.send_message(
                chat_id,
                f"📍 <b>STATO SESSIONE IN CAMPO:</b>\n"
                f"• <b>Giocatore:</b> {user_rec.first_name} {user_rec.last_name}\n"
                f"• <b>Campo:</b> {active_course.name}\n"
                f"• <b>Buca Attiva:</b> {h_num}\n"
                f"• <b>Colpo Corrente:</b> {s_idx}\n"
                f"• <b>Ultima Posizione GPS:</b> {pos_str}\n\n"
                f"<i>Invia la posizione per calcolare la distanza e il bastone consigliato!</i>"
            )

        elif cmd in ["/nuovogiro", "/reset"]:
            self.session_mgr.reset_session(chat_id)
            self.send_message(
                chat_id,
                "🔄 <b>Nuovo giro iniziato!</b>\n"
                "Sessione azzerata alla Buca 1, Colpo 1. Buon gioco!"
            )

        elif cmd in ["/giocatore", "/utente", "/login", "/collega"]:
            if not args:
                self.send_message(chat_id, "⚠️ Specifica il tuo nome o cognome. Esempio: <code>/giocatore Stefano</code> oppure <code>/giocatore Giorgio</code>")
                return

            search_name = " ".join(args).strip().lower()
            all_users = self.auth_mgr.get_all_users()

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
                    f"🏌️ Ora puoi inviare le coordinate GPS o note vocali durante il gioco!"
                )
            else:
                self.send_message(
                    chat_id,
                    f"❌ Nessun giocatore trovato con il nome «{search_name}».\n"
                    f"Usa <code>/start</code> per vedere la lista dei giocatori registrati."
                )

        elif cmd in ["/profilo", "/chi"]:
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
            # Non è un comando riconosciuto -> gestisci come testo dei colpi
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
            print(f"  In ascolto di posizioni GPS, note vocali e messaggi...")
            print(f"=======================================================\n")
        else:
            logging.warning(f"Avviso verifica token Telegram: {msg}")

        while self.is_running:
            try:
                res = self._api_request("getUpdates", {"offset": offset, "timeout": 15})
                if res.get("ok"):
                    for update in res.get("result", []):
                        offset = update["update_id"] + 1

                        # Supporta sia nuovi messaggi che aggiornamenti Live Location (edited_message)
                        message = update.get("message") or update.get("edited_message")
                        if not message:
                            continue

                        chat_id = message.get("chat", {}).get("id")
                        text = message.get("text", "")

                        # 1. Location GPS o Live Location
                        if "location" in message:
                            loc = message["location"]
                            lat = float(loc.get("latitude"))
                            lon = float(loc.get("longitude"))
                            alt = loc.get("altitude")
                            self.handle_location_update(chat_id, lat, lon, alt)

                        # 2. Note Vocali o Audio
                        elif "voice" in message:
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

                        # 3. Testo o Comandi
                        elif text:
                            if text.startswith("/"):
                                self.handle_command(chat_id, text)
                            else:
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
