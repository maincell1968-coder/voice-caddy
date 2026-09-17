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
from core.weather_service import weather_service

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
        self.user_modes: Dict[str, str] = {}
        self.pending_weather: Dict[str, bool] = {}
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

    # ---------------------------------------------------------
    # Game Mode (Gara vs Training) & Weather Round Startup
    # ---------------------------------------------------------
    def get_user_mode(self, chat_id: int | str) -> str:
        """Restituisce la modalità corrente ('gara' o 'training') per la chat."""
        cid = str(chat_id)
        if cid not in self.user_modes:
            self.user_modes[cid] = self.config_mgr.get_user_mode(cid)
        return self.user_modes[cid]

    def set_user_mode(self, chat_id: int | str, mode: str):
        """Imposta la modalità ('gara' o 'training') e invia conferma con tastiera aggiornata."""
        cid = str(chat_id)
        clean = "gara" if "gara" in str(mode).lower() else "training"
        self.user_modes[cid] = clean
        self.config_mgr.set_user_mode(cid, clean)

        if clean == "gara":
            msg = (
                "⚖️ <b>MODALITÀ GARA (R&A / USGA) ATTIVATA!</b>\n\n"
                "In conformità alla <b>Regola 4.3</b> delle Regole del Golf:\n"
                "• 📏 <b>Consentito:</b> riceverai la sola distanza in metri al bersaglio/green.\n"
                "• 🚫 <b>Disattivato:</b> nessun consiglio sul bastone da usare né indicazioni strategiche.\n\n"
                "<i>Buona gara! Per tornare alla modalità con bastoni consigliati scrivi <code>/training</code>.</i>"
            )
        else:
            msg = (
                "🎯 <b>MODALITÀ TRAINING (ALLENAMENTO) ATTIVATA!</b>\n\n"
                "Voice Caddy ti fornirà:\n"
                "• 📏 <b>Distanza reale</b> e <b>Plays Like Distance</b> compensata col dislivello.\n"
                "• 🏌️‍♂️ <b>Bastone consigliato</b> ottimale dalla tua sacca personale.\n\n"
                "<i>Per attivare la modalità regolamentare da torneo scrivi <code>/gara</code>.</i>"
            )
        return self.send_message(chat_id, msg, reply_markup=self.get_on_course_keyboard(clean))

    def get_weather_request_keyboard(self) -> dict:
        """Restituisce la tastiera temporanea a 1 tocco per inviare la posizione all'avvio del round."""
        return {
            "keyboard": [
                [{"text": "📍 Invia posizione per rilevare il vento", "request_location": True}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }

    def start_round_flow(self, chat_id: int | str, mode: Optional[str] = None):
        """
        Avvia il round chiedendo la posizione per rilevare meteo e vento sul campo
        tramite l'API gratuita di Open-Meteo.
        """
        cid = str(chat_id)
        if mode:
            clean = "gara" if "gara" in str(mode).lower() else "training"
            self.user_modes[cid] = clean
            self.config_mgr.set_user_mode(cid, clean)

        self.pending_weather[cid] = True
        msg = "Ottimo, buon giro! Tocca il pulsante qui sotto per rilevare il campo e calcolare vento e meteo sul percorso."
        return self.send_message(
            chat_id,
            msg,
            reply_markup=self.get_weather_request_keyboard()
        )

    def get_on_course_keyboard(self, mode: str = "training") -> dict:
        """Restituisce la tastiera persistente con pulsante GPS rapido a 1 tocco e toggle Modalità Gara/Training."""
        mode_btn = "⚖️ Modalità Gara" if mode == "training" else "🎯 Modalità Training"
        return {
            "keyboard": [
                [{"text": "📍 Calcola Distanza & Plays Like", "request_location": True}],
                [{"text": "⏩ Prossima Buca"}, {"text": "📊 Stato & Buca"}],
                [{"text": mode_btn}, {"text": "🎒 Profilo & Sacca"}],
                [{"text": "🔄 Nuovo Giro"}]
            ],
            "resize_keyboard": True,
            "is_persistent": True
        }

    def send_message(self, chat_id: int | str, text: str, parse_mode: str = "HTML", reply_markup: Optional[dict] = None) -> dict:
        mode = self.get_user_mode(chat_id)
        markup = reply_markup if reply_markup is not None else self.get_on_course_keyboard(mode)
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
        # Controllo se è la posizione iniziale richiesta per meteo & vento
        cid = str(chat_id)
        if self.pending_weather.get(cid, False):
            self.pending_weather[cid] = False
            user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
            user_mode = self.get_user_mode(chat_id)
            mode_label = "GARA (Regola 4.3)" if user_mode == "gara" else "TRAINING"

            # Reset sessione alla Buca 1 per il nuovo giro
            self.session_mgr.reset_session(chat_id)

            # Rileva meteo e vento in tempo reale da Open-Meteo
            w = weather_service.get_current_weather(lat, lon)
            cond = w.get("weather_desc", "Sereno ☀️")
            temp = w.get("temperature", 20.0)
            w_speed = w.get("wind_speed", 0.0)
            w_card = w.get("wind_cardinal", "N")
            w_arrow = w.get("wind_arrow", "⬇️")
            w_gusts = w.get("wind_gusts", w_speed)

            # Notifica all'amministratore (se giocatore diverso da Stefano)
            if user_rec and user_rec.user_id != "strafatti_stefano_pirani":
                self.config_mgr.notify_admin(
                    f"🏌️‍♂️ <b>Avvio Partita Live in Campo</b>\n"
                    f"👤 <b>Giocatore:</b> {user_rec.first_name} {user_rec.last_name}\n"
                    f"⛳ <b>Campo:</b> {active_course.name}\n"
                    f"💨 <b>Vento:</b> {w_speed} km/h da {w_card} {w_arrow} (Raffiche: {w_gusts} km/h)\n"
                    f"⚖️ <b>Modalità:</b> {user_mode.upper()}"
                )

            reply_msg = (
                f"🏌️‍♂️ <b>Modalità Round Attivata! ({mode_label})</b>\n\n"
                f"🌤️ <b>Meteo:</b> {cond}, {temp}°C\n"
                f"💨 <b>Vento medio:</b> {w_speed} km/h da {w_card} {w_arrow}\n"
                f"⚠️ <b>Raffiche:</b> fino a {w_gusts} km/h\n\n"
                f"⛳ <i>Sei sul Tee della Buca 1. Tira il colpo di partenza e tocca "
                f"<b>[📍 Calcola Distanza & Plays Like]</b> appena arrivi sulla palla!</i>"
            )
            # Rimuove il pulsante temporaneo e ripristina la tastiera da gioco persistente
            return self.send_message(chat_id, reply_msg, reply_markup=self.get_on_course_keyboard(user_mode))

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
        user_mode = self.get_user_mode(chat_id)

        # Notifica Admin al primo colpo del giro (se il giocatore non è Stefano)
        if current_hole == 1 and current_shot == 1:
            if user_rec and user_rec.user_id != "strafatti_stefano_pirani":
                self.config_mgr.notify_admin(
                    f"🏌️‍♂️ <b>Nuova Partita Live in Campo</b>\n"
                    f"👤 <b>Giocatore:</b> {user_rec.first_name} {user_rec.last_name} ({user_rec.group.upper()})\n"
                    f"⛳ <b>Campo:</b> {active_course.name}\n"
                    f"⚖️ <b>Modalità:</b> {user_mode.upper()}"
                )

        if user_mode == "gara":
            # MODALITÀ GARA (R&A Regola 4.3): Solo distanze regolamentari, divieto assoluto consiglio bastone
            reply_msg = (
                f"⛳ <b>Buca {current_hole}</b> (Par {par_val}) — <b>Colpo {current_shot}</b>\n\n"
                f"📏 <b>Distanza alla bandiera:</b> <b>{raw_dist}m</b>\n\n"
                f"⚖️ <i>Modalità Gara attiva: per la <b>Regola 4.3</b> delle Regole del Golf non posso suggerire il bastone.</i>\n"
            )
        else:
            # MODALITÀ TRAINING: Distanza reale, dislivello, Plays Like e raccomandazione bastone
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

        user_mode = self.get_user_mode(chat_id)
        if user_mode == "gara":
            reply_msg = (
                f"📍 <b>Distanza Manuale — Buca {current_hole}</b>\n\n"
                f"📏 <b>Distanza indicata:</b> <b>{int(manual_distance)}m</b>\n\n"
                f"⚖️ <i>Modalità Gara attiva: per la <b>Regola 4.3</b> non posso suggerire il bastone.</i>\n\n"
                f"💡 <i>Per inviare la posizione GPS esatta, tocca [📍 Calcola Distanza & Plays Like].</i>"
            )
        else:
            reply_msg = (
                f"📍 <b>Distanza Manuale (Paletto/Scorecard) — Buca {current_hole}</b>\n\n"
                f"📏 <b>Distanza indicata:</b> {int(manual_distance)}m | ⛰️ <b>Dislivello:</b> {elev_str}\n"
                f"🎯 <b>Plays Like stimato:</b> ~{int(plays_like)}m (Consigliato: <b>{rec_club_str}</b>)\n\n"
                f"💡 <i>Per inviare la posizione GPS esatta, tocca [📍 Calcola Distanza & Plays Like].</i>"
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
        clean_lower = clean.lower()
        # Intercettazione avvio round con richiesta meteo & vento a 1 tocco
        start_keywords = [
            "gara", "training", "allenamento", "meteo", "vento",
            "start round", "start_round", "inizio round", "avvia giro"
        ]
        if clean in ["⚖️ Modalità Gara", "🎯 Modalità Training"] or any(kw in clean_lower for kw in start_keywords):
            if "gara" in clean_lower:
                new_mode = "gara"
            elif any(k in clean_lower for k in ["training", "allenamento"]):
                new_mode = "training"
            else:
                new_mode = self.get_user_mode(chat_id)
            return self.start_round_flow(chat_id, new_mode)

        if clean in ["⏩ Prossima Buca", "📊 Stato & Buca", "🎒 Profilo & Sacca", "🔄 Nuovo Giro"]:
            return self.handle_command(chat_id, clean)

        user_rec, user_profile, active_course, ai_cfg = self._resolve_context(chat_id)
        player_name = f"{user_rec.first_name} {user_rec.last_name}"
        user_mode = self.get_user_mode(chat_id)

        # Se in modalità gara e l'utente fa domande esplicite sul bastone da tirare
        if user_mode == "gara" and any(w in clean_lower for w in ["bastone", "mazza", "ferro", "legno", "ibrido", "che tiro", "cosa tiro", "consiglio"]):
            return self.send_message(
                chat_id,
                "⚖️ <b>Modalità Gara attiva:</b>\n"
                "In conformità alla <b>Regola 4.3 (R&A / USGA)</b>, è severamente vietato "
                "ricevere consigli sul bastone o sulla strategia durante una gara ufficiale.\n\n"
                "📍 <i>Tocca <b>[📍 Calcola Distanza & Plays Like]</b> per ottenere la sola distanza regolamentare in metri.</i>"
            )

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
        elif "gara" in clean_text.lower() and not clean_text.startswith("/"):
            cmd = "/gara"
        elif "training" in clean_text.lower() and not clean_text.startswith("/"):
            cmd = "/training"
        elif any(k in clean_text.lower() for k in ["start_round", "start round", "meteo", "vento"]):
            cmd = "/start_round"

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
                "• <b>Bastone consigliato</b> (se in modalità Training)\n\n"
                "3️⃣ <b>DOPO IL COLPO:</b>\n"
                "Mentre cammini verso la palla successiva o verso il green, tieni premuto il microfono per 2 secondi e detta il colpo eseguito (es. <i>'Ferro 7 dal fairway'</i>).\n"
                "<i>Zero attese, zero rallentamenti per i compagni di gioco!</i>\n\n"
                "<b>⚖️ AVVIO ROUND & METEO:</b>\n"
                "• <code>/start_round</code>: Avvia il giro con rilevamento meteo e vento in tempo reale\n"
                "• <code>/gara</code>: Avvia il giro in <b>Modalità Gara R&A</b> (Regola 4.3: solo distanze)\n"
                "• <code>/training</code>: Avvia il giro in <b>Modalità Training</b> (distanza + bastone consigliato)\n"
                "• <code>/meteo</code> o <code>/vento</code>: Calcola vento e meteo sul percorso via GPS\n"
                "• <code>/modalita</code>: Mostra la modalità attiva\n\n"
                "<b>⚙️ ALTRI COMANDI RAPIDI:</b>\n"
                "• <code>/distanza [metri]</code>: Fallback manuale se leggi un paletto (es. <code>/distanza 138</code>)\n"
                "• <code>/pin [offset o coords]</code>: Personalizza la profondità della bandiera\n"
                "• <code>/stato</code>: Verifica buca, colpo attuale e modalità\n"
                "• <code>/giocatore [Nome]</code>: Collega la chat al tuo profilo\n"
                "• <code>/campo [Nome]</code>: Imposta il percorso (es. Conero Golf Club)\n\n"
                f"<b>👥 Giocatori Registrati:</b>\n"
                f"• <b>Strafatti:</b> {', '.join(strafatti_names)}\n"
            )
            if amici_names:
                help_msg += f"• <b>Amici:</b> {', '.join(amici_names)}\n"

            help_msg += "\n⚖️ <i>Voice Caddy Pro &bull; Concept, Architettura e Sviluppo: <b>Stefano Pirani</b></i>\n"

            self.send_message(chat_id, help_msg)

        elif cmd in ["/gara", "/modalitagara"]:
            self.start_round_flow(chat_id, "gara")

        elif cmd in ["/training", "/allenamento", "/modalitatraining"]:
            self.start_round_flow(chat_id, "training")

        elif cmd in ["/start_round", "/round", "/meteo", "/vento"]:
            cur_mode = self.get_user_mode(chat_id)
            self.start_round_flow(chat_id, cur_mode)

        elif cmd in ["/modalita", "/mode"]:
            cur_mode = self.get_user_mode(chat_id)
            cur_label = "⚖️ GARA (Regola 4.3: solo distanze, no bastone)" if cur_mode == "gara" else "🎯 TRAINING (distanza + bastone consigliato)"
            self.send_message(
                chat_id,
                f"⚙️ <b>MODALITÀ DI GIOCO ATTIVA:</b>\n👉 <b>{cur_label}</b>\n\n"
                f"• Per passare a GARA: <code>/gara</code>\n"
                f"• Per passare a TRAINING: <code>/training</code>\n\n"
                f"<i>Puoi anche toccare il pulsante dedicato sulla tastiera in basso!</i>"
            )

        elif cmd in ["/admin", "/setadmin"]:
            user_rec, _, _, _ = self._resolve_context(chat_id)
            if user_rec and (user_rec.is_admin or user_rec.user_id == "strafatti_stefano_pirani"):
                self.config_mgr.set_admin_chat_id(chat_id)
                self.send_message(
                    chat_id,
                    f"👑 <b>Accesso Amministratore Riconosciuto!</b>\n\n"
                    f"Chat ID <code>{chat_id}</code> registrato come Amministratore Principale (<b>{user_rec.first_name} {user_rec.last_name}</b>).\n"
                    f"🔔 Riceverai notifiche Telegram istantanee quando i giocatori accedono da PC (Web) o da smartphone (Telegram)."
                )
            else:
                self.send_message(
                    chat_id,
                    "⚠️ <i>Questo comando è riservato all'Amministratore (Stefano Pirani).</i>\n"
                    "Collega prima il tuo profilo con <code>/giocatore Stefano</code>."
                )

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
            cur_mode = self.get_user_mode(chat_id)
            mode_str = "⚖️ GARA (Solo distanze, Regola 4.3)" if cur_mode == "gara" else "🎯 TRAINING (Distanza + Bastoni)"

            self.send_message(
                chat_id,
                f"📍 <b>STATO SESSIONE IN CAMPO:</b>\n"
                f"• <b>Giocatore:</b> {user_rec.first_name} {user_rec.last_name}\n"
                f"• <b>Campo:</b> {active_course.name}\n"
                f"• <b>Buca Attiva:</b> {h_num}\n"
                f"• <b>Colpo Corrente:</b> {s_idx}\n"
                f"• <b>Modalità:</b> {mode_str}\n"
                f"• <b>Ultima Posizione GPS:</b> {pos_str}\n\n"
                f"<i>Invia la posizione GPS per calcolare la distanza!</i>"
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
                cur_mode = self.get_user_mode(chat_id)
                mode_str = "⚖️ GARA (Regola 4.3)" if cur_mode == "gara" else "🎯 TRAINING"

                # Se l'utente collegato è Stefano (Amministratore), registra il suo chat_id per ricevere gli avvisi
                if matched_user.is_admin or matched_user.user_id == "strafatti_stefano_pirani":
                    self.config_mgr.set_admin_chat_id(chat_id)

                self.send_message(
                    chat_id,
                    f"✅ <b>Chat collegata con successo a {matched_user.first_name} {matched_user.last_name}!</b>\n\n"
                    f"• <b>Gruppo:</b> {matched_user.group.upper()}\n"
                    f"• <b>Handicap Registrato:</b> {prof.handicap}\n"
                    f"• <b>Categoria & Tono Caddie:</b> {prof.category.value}\n"
                    f"• <b>Modalità Attiva:</b> {mode_str}\n"
                    f"• <b>Mazza più lunga:</b> {prof.clubs_in_bag[0].club_name if prof.clubs_in_bag else 'Driver'}\n\n"
                    f"🏌️ Ora puoi inviare le coordinate GPS o note vocali durante il gioco!"
                )

                # Notifica all'amministratore (Stefano) dell'accesso via Telegram di un compagno
                if not matched_user.is_admin and matched_user.user_id != "strafatti_stefano_pirani":
                    self.config_mgr.notify_admin(
                        f"📱 <b>Nuovo Accesso Telefono (Telegram)</b>\n"
                        f"👤 <b>Utente:</b> {matched_user.first_name} {matched_user.last_name}\n"
                        f"🏷️ <b>Gruppo:</b> {matched_user.group.upper()}\n"
                        f"💬 Ha appena collegato il suo account Telegram."
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
