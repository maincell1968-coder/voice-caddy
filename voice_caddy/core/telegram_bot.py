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

from core.schemas import ShotIntent
from core.audio import VoiceCaddyAudioEngine
from core.parser import (
    parse_golf_audio_transcript,
    parse_quick_shot_update,
    parse_hole_closure_intent,
    parse_retroactive_correction,
    parse_round_sequence_intent,
    detect_hole_anomalies,
    parse_audit_correction
)
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
from core.whs_rules import RoundHandicapProfile, build_round_handicap_profile, calculate_hole_score, TeeRating
from core.green_distance_service import parse_green_distance_intent, calculate_green_distances, format_distance_response
from core.club_distance_service import ClubDistanceService

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

    def __init__(self, bot_token: Optional[str] = None, db: Optional[DatabaseManager] = None, auth_mgr: Optional[AuthManager] = None):
        self.config_mgr = TelegramConfigManager()
        self.bot_token = bot_token or self.config_mgr.get_token()
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN non configurato. Inseriscilo nella configurazione o come variabile d'ambiente.")

        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.audio_engine = VoiceCaddyAudioEngine(model_size="base")
        self.db = db or DatabaseManager()
        self.auth_mgr = auth_mgr or AuthManager()
        self.course_registry = CourseRegistry(storage_dir=PROJECT_ROOT / "courses")
        self.session_mgr = LiveSessionManager()
        self.user_modes: Dict[str, str] = {}
        self.pending_weather: Dict[str, bool] = {}
        self.is_running = False
        self._instance_socket = None

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

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> dict:
        """Invia conferma a Telegram per un click su pulsante inline."""
        payload: Dict[str, Any] = {"callback_query_id": str(callback_query_id)}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        return self._api_request("answerCallbackQuery", payload)

    def edit_message_text(self, chat_id: int | str, message_id: int, text: str, parse_mode: str = "HTML", reply_markup: Optional[dict] = None) -> dict:
        """Modifica un messaggio esistente con nuovo testo o tastiera inline."""
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._api_request("editMessageText", payload)

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

    def get_tee_selection_keyboard(self) -> dict:
        """Restituisce la tastiera rapida a 1 tocco per la scelta del Tee di partenza (WHS)."""
        return {
            "keyboard": [
                [{"text": "🟡 Gialli"}, {"text": "⚪ Bianchi"}],
                [{"text": "🟢 Verdi"}, {"text": "🔴 Rossi"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }

    def get_round_sequence_keyboard(self) -> dict:
        """Tastiera rapida per confermare la sequenza delle buche giocate (Prompt 1)."""
        return {
            "keyboard": [
                [{"text": "⛳ 18 Buche (1-18)"}, {"text": "⛳ Prime 9 (1-9)"}],
                [{"text": "⛳ Seconde 9 (10-18)"}, {"text": "🎯 Shotgun da Buca 7"}],
                [{"text": "🟡 Tee Gialli (Uomo)"}, {"text": "🔴 Tee Rossi (Donna)"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }

    def get_audit_keyboard(self) -> dict:
        """Tastiera rapida per confermare o correggere lo score buca per buca (Prompt 2)."""
        return {
            "keyboard": [
                [{"text": "✅ Tutto Corretto, Analizza!"}],
                [{"text": "💧 Aggiungi Penalità Acqua"}, {"text": "🚫 Aggiungi Fuori Limite"}],
                [{"text": "🔄 Nuovo Giro"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }

    def _resolve_default_tee_for_gender(self, chat_id: int | str, gender: Optional[str] = None) -> Tuple[str, str]:
        """
        Determina il tee di default:
        - Donna = tee rossi
        - Uomo = tee gialli
        """
        user_rec, _, _, _ = self._resolve_context(chat_id)
        resolved_gender = "Uomini"
        if gender:
            resolved_gender = "Donne" if any(w in gender.lower() for w in ["donna", "donne", "femm", "lady", "ladies"]) else "Uomini"
        elif user_rec and getattr(user_rec, "gender", None):
            g = str(user_rec.gender).lower()
            resolved_gender = "Donne" if g in ["female", "donna", "donne"] else "Uomini"

        default_tee = "rossi" if resolved_gender == "Donne" else "gialli"
        return default_tee, resolved_gender

    def get_weather_request_keyboard(self) -> dict:
        """Restituisce la tastiera temporanea a 1 tocco per inviare la posizione all'avvio del round."""
        return {
            "keyboard": [
                [{"text": "📍 Invia posizione per rilevare il vento", "request_location": True}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }

    def start_round_flow(self, chat_id: int | str, mode: Optional[str] = None, tee_name: Optional[str] = None):
        """
        Avvia il round chiedendo prima il Tee di partenza (se non specificato) per
        applicare i parametri ufficiali WHS e calcolare il Playing HCP, poi
        mostra meteo e vento sul campo e abilita il tracciamento GPS.
        """
        cid = str(chat_id)
        if mode:
            clean = "gara" if "gara" in str(mode).lower() else "training"
            self.user_modes[cid] = clean
            self.config_mgr.set_user_mode(cid, clean)
        user_mode = self.get_user_mode(chat_id)

        # Se il tee è stato indicato esplicitamente (o appena scelto dal pulsante rapido)
        if tee_name:
            self.session_mgr.set_selected_tee(chat_id, tee_name)
            self.session_mgr.set_awaiting_tee_choice(chat_id, False)
            self.session_mgr.set_round_state(chat_id, "IDLE")
            self.pending_weather[cid] = True

            whs_profile = self._resolve_handicap_profile(chat_id, tee_name=tee_name, force_refresh=True)
            user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)

            # Rileva meteo e vento live (Open-Meteo)
            c_lat = 43.5228
            c_lon = 13.6060
            if active_course.holes and active_course.holes[0].coordinates:
                c_lat = active_course.holes[0].coordinates.tee_lat
                c_lon = active_course.holes[0].coordinates.tee_lon
            try:
                w = weather_service.get_current_weather(c_lat, c_lon, timeout=2.0) or {}
            except Exception:
                w = {}
            cond = w.get("weather_desc", "Sereno ☀️")
            temp = w.get("temperature", 21.0)
            w_speed = w.get("wind_speed", 8.0)
            w_card = w.get("wind_cardinal", "NE")
            w_arrow = w.get("wind_arrow", "↙️")
            w_gusts = w.get("wind_gusts", w_speed)

            msg = (
                f"{whs_profile.format_summary_card()}\n"
                f"📍 <b>Tee {tee_name.title()} confermato!</b>\n\n"
                f"🌤️ <b>Meteo e Vento sul Percorso:</b>\n"
                f"• Condizioni: {cond}, {temp}°C\n"
                f"• Vento: {w_speed} km/h da {w_card} {w_arrow} (raffiche: {w_gusts} km/h)\n\n"
                f"Tocca il pulsante qui sotto per rilevare il campo e calcolare vento e meteo sul percorso."
            )
            return self.send_message(
                chat_id,
                msg,
                reply_markup=self.get_weather_request_keyboard()
            )

        # Se il tee non è stato specificato, chiedi una sola volta all'utente
        self.session_mgr.set_awaiting_tee_choice(chat_id, True)
        msg = (
            "🏌️‍♂️ <b>Avvio Nuovo Giro!</b>\n\n"
            "Da quali tee parti oggi? (es. Gialli, Bianchi, Rossi)"
        )
        return self.send_message(
            chat_id,
            msg,
            reply_markup=self.get_tee_selection_keyboard()
        )

    def get_on_course_keyboard(self, mode: str = "training") -> dict:
        """Restituisce la tastiera persistente con pulsante GPS rapido a 1 tocco e pulsanti separati Modalità Training e Gara."""
        return {
            "keyboard": [
                [{"text": "📍 Calcola Distanza & Plays Like", "request_location": True}],
                [{"text": "🟢 Inizia Gara a Pulsanti"}, {"text": "📊 Score"}],
                [{"text": "⏩ Prossima Buca"}, {"text": "📊 Stato & Buca"}],
                [{"text": "🎭 Tono Caddie"}, {"text": "🎒 Profilo & Sacca"}],
                [{"text": "🎯 Modalità Training"}, {"text": "⚖️ Modalità Gara"}],
                [{"text": "🔄 Nuovo Giro"}]
            ],
            "resize_keyboard": True,
            "is_persistent": True
        }

    # ---------------------------------------------------------
    # INTERACTIVE INLINE KEYBOARDS (ZERO AUDIO TRACKER)
    # ---------------------------------------------------------
    def get_interactive_main_menu(self) -> dict:
        return {
            "inline_keyboard": [
                [{"text": "🟢 Inizia Gara", "callback_data": "start_interactive_round"}],
                [{"text": "📊 Score", "callback_data": "show_score"}],
                [{"text": "⚙️ Impostazioni", "callback_data": "show_settings"}]
            ]
        }

    def get_interactive_tee_menu(self) -> dict:
        return {
            "inline_keyboard": [
                [{"text": "🟡 Tee Gialli", "callback_data": "tee_gialli"}, {"text": "🔴 Tee Rossi", "callback_data": "tee_rossi"}],
                [{"text": "⚪ Tee Bianchi", "callback_data": "tee_bianchi"}, {"text": "🔵 Tee Blu", "callback_data": "tee_blu"}]
            ]
        }

    def get_interactive_start_hole_menu(self) -> dict:
        return {
            "inline_keyboard": [
                [{"text": "1", "callback_data": "start_hole_1"}, {"text": "2", "callback_data": "start_hole_2"}, {"text": "3", "callback_data": "start_hole_3"}],
                [{"text": "4", "callback_data": "start_hole_4"}, {"text": "5", "callback_data": "start_hole_5"}, {"text": "6", "callback_data": "start_hole_6"}],
                [{"text": "7", "callback_data": "start_hole_7"}, {"text": "8", "callback_data": "start_hole_8"}, {"text": "9", "callback_data": "start_hole_9"}],
                [{"text": "10", "callback_data": "start_hole_10"}, {"text": "11", "callback_data": "start_hole_11"}, {"text": "12", "callback_data": "start_hole_12"}],
                [{"text": "13", "callback_data": "start_hole_13"}, {"text": "14", "callback_data": "start_hole_14"}, {"text": "15", "callback_data": "start_hole_15"}],
                [{"text": "16", "callback_data": "start_hole_16"}, {"text": "17", "callback_data": "start_hole_17"}, {"text": "18", "callback_data": "start_hole_18"}]
            ]
        }

    def get_interactive_shot_menu(self, is_on_tee: bool = True, par: int = 4) -> dict:
        if is_on_tee:
            buttons = [
                [{"text": "🏌️ Drive", "callback_data": "shot_drive"}, {"text": "🌲 Legno / Ibrido", "callback_data": "shot_wood"}],
                [{"text": "🎯 Ferro", "callback_data": "shot_iron"}, {"text": "🟢 In Green", "callback_data": "reached_green"} if par == 3 else {"text": "🥪 Wedge", "callback_data": "shot_wedge"}],
                [{"text": "❌ Penalità", "callback_data": "penalty_menu"}, {"text": "📊 Score", "callback_data": "show_score"}],
                [{"text": "🏁 Termina Gara", "callback_data": "confirm_end_round"}]
            ]
        else:
            buttons = [
                [{"text": "🌲 Legno / Ibrido", "callback_data": "shot_wood"}, {"text": "🎯 Ferro", "callback_data": "shot_iron"}],
                [{"text": "🥪 Wedge / Approccio", "callback_data": "shot_wedge"}, {"text": "🟢 Sono in Green", "callback_data": "reached_green"}],
                [{"text": "❌ Penalità", "callback_data": "penalty_menu"}, {"text": "↩️ Annulla colpo", "callback_data": "undo_shot"}],
                [{"text": "📊 Score", "callback_data": "show_score"}, {"text": "🏁 Termina Gara", "callback_data": "confirm_end_round"}]
            ]
        return {"inline_keyboard": buttons}

    def get_interactive_shot_in_progress_menu(self) -> dict:
        return {
            "inline_keyboard": [
                [{"text": "📍 Calcola Distanza", "callback_data": "calc_dist"}],
                [{"text": "🟢 Sono in Green", "callback_data": "reached_green"}],
                [{"text": "↩️ Annulla ultimo colpo", "callback_data": "undo_shot"}]
            ]
        }

    def get_interactive_lie_menu(self) -> dict:
        return {
            "inline_keyboard": [
                [{"text": "✅ Fairway", "callback_data": "lie_fairway"}, {"text": "🌾 Rough", "callback_data": "lie_rough"}],
                [{"text": "🌲 Alberi", "callback_data": "lie_trees"}, {"text": "🏖️ Bunker", "callback_data": "lie_bunker"}],
                [{"text": "💧 Acqua", "callback_data": "lie_water"}, {"text": "🚫 Fuori Limite", "callback_data": "lie_out"}],
                [{"text": "🟢 Green", "callback_data": "lie_green"}, {"text": "↩️ Annulla", "callback_data": "undo_shot"}]
            ]
        }

    def get_interactive_putts_menu(self) -> dict:
        return {
            "inline_keyboard": [
                [{"text": "0 Putt (Chip-in!)", "callback_data": "putts_0"}],
                [{"text": "1 Putt", "callback_data": "putts_1"}, {"text": "2 Putt (Standard)", "callback_data": "putts_2"}],
                [{"text": "3 Putt", "callback_data": "putts_3"}, {"text": "4+ Putt", "callback_data": "putts_4p"}],
                [{"text": "↩️ Annulla", "callback_data": "undo_shot"}]
            ]
        }

    def get_interactive_hole_completed_menu(self, next_hole: int) -> dict:
        return {
            "inline_keyboard": [
                [{"text": f"➡️ Buca {next_hole}", "callback_data": "next_hole"}],
                [{"text": "✏️ Modifica Buca", "callback_data": "edit_hole"}, {"text": "📊 Score", "callback_data": "show_score"}],
                [{"text": "🏁 Termina Gara", "callback_data": "confirm_end_round"}]
            ]
        }

    def get_interactive_penalty_menu(self) -> dict:
        return {
            "inline_keyboard": [
                [{"text": "💧 Acqua +1", "callback_data": "penalty_water"}, {"text": "🚫 Fuori Limite +1", "callback_data": "penalty_out"}],
                [{"text": "🔴 Palla Persa +1", "callback_data": "penalty_lost"}, {"text": "🟡 Droppaggio +1", "callback_data": "penalty_drop"}],
                [{"text": "⚪ Altro +1", "callback_data": "penalty_other"}, {"text": "↩️ Annulla", "callback_data": "penalty_cancel"}]
            ]
        }

    def get_interactive_scorecard_menu(self) -> dict:
        return {
            "inline_keyboard": [
                [{"text": "🔙 Torna alla Buca Corrente", "callback_data": "back_to_hole"}],
                [{"text": "🏁 Termina Gara", "callback_data": "confirm_end_round"}]
            ]
        }

    # ---------------------------------------------------------
    # INTERACTIVE HANDLERS (FSM & ZERO AUDIO FLOW)
    # ---------------------------------------------------------
    def start_interactive_wizard(self, chat_id: int | str, message_id: Optional[int] = None) -> dict:
        """Avvia la procedura guidata di inizio gara a pulsanti (scelta tee)."""
        user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
        text = (
            "🟢 <b>AVVIO GARA INTERATTIVA A PULSANTI</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Giocatore:</b> {user_rec.first_name} {user_rec.last_name} (HCP {user_profile.handicap})\n"
            f"⛳ <b>Campo:</b> {active_course.name}\n\n"
            "Seleziona il <b>Tee di partenza</b> per calcolare il Playing Handicap (WHS):"
        )
        if message_id is not None:
            return self.edit_message_text(chat_id, message_id, text, reply_markup=self.get_interactive_tee_menu())
        return self.send_message(chat_id, text, reply_markup=self.get_interactive_tee_menu())

    def show_interactive_hole_screen(
        self,
        chat_id: int | str,
        message_id: Optional[int] = None,
        prompt_suffix: str = ""
    ) -> dict:
        """Mostra la schermata attiva della buca corrente con i bastoni selezionabili."""
        istate = self.session_mgr.get_interactive_state(chat_id)
        cur_h = istate.get("current_hole", 1)
        whs_profile = self._resolve_handicap_profile(chat_id)

        par = whs_profile.hole_pars.get(cur_h, 4)
        si = whs_profile.hole_stroke_indices.get(cur_h, cur_h)
        rec_strokes = whs_profile.get_received_strokes(cur_h)
        net_par = whs_profile.get_net_par(cur_h)
        shot_num = istate.get("current_shot_number", 1)
        shots = istate.get("hole_shots", [])
        penalties = istate.get("hole_penalties", [])

        is_on_tee = (len(shots) == 0)

        shots_desc = []
        for s in shots:
            dist_str = f" ({s['distance_meters']}m)" if s.get("distance_meters") else ""
            lie_str = f" ➔ {s.get('lie', '').title()}" if s.get("lie") else ""
            shots_desc.append(f"  • Colpo {s.get('shot_number')}: <b>{s.get('club')}</b>{dist_str}{lie_str}")
        for p in penalties:
            shots_desc.append(f"  • ⚠️ <i>{p.get('type')} (+{p.get('strokes', 1)})</i>")

        shots_block = "\n".join(shots_desc) + "\n\n" if shots_desc else ""

        text = (
            f"⛳ <b>BUCA {cur_h}</b> (Par {par} • HCP Buca {si})\n"
            f"🎯 <b>HCP:</b> {rec_strokes} colpi ricevuti ➔ <b>Par Netto: {net_par}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{shots_block}"
            f"🏌️ <b>COLPO {shot_num}:</b> Che bastone giochi?"
        )
        if prompt_suffix:
            text += f"\n\n{prompt_suffix}"

        reply_markup = self.get_interactive_shot_menu(is_on_tee=is_on_tee, par=par)
        if message_id is not None:
            return self.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup)
        return self.send_message(chat_id, text, reply_markup=reply_markup)

    def show_interactive_putts_screen(self, chat_id: int | str, message_id: Optional[int] = None) -> dict:
        """Mostra la schermata di selezione dei putt quando la palla è in green."""
        istate = self.session_mgr.get_interactive_state(chat_id)
        cur_h = istate.get("current_hole", 1)
        shots = istate.get("hole_shots", [])
        shots_to_green = len(shots)

        text = (
            f"🟢 <b>ARRIVO IN GREEN — BUCA {cur_h}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• Colpi per raggiungere il green: <b>{shots_to_green}</b>\n\n"
            f"Quanti putt hai effettuato per imbucare?"
        )
        reply_markup = self.get_interactive_putts_menu()
        if message_id is not None:
            return self.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup)
        return self.send_message(chat_id, text, reply_markup=reply_markup)

    def show_interactive_scorecard(self, chat_id: int | str, message_id: Optional[int] = None) -> dict:
        """Mostra lo score progressivo con colpi lordi, netti e punti Stableford (netti e lordi)."""
        card = self.session_mgr.get_round_scorecard(chat_id)
        whs_profile = self._resolve_handicap_profile(chat_id)
        user_rec, _, active_course, _ = self._resolve_context(chat_id)

        from core.whs_rules import calculate_stableford_points_gross
        tot_gross_stb = sum(calculate_stableford_points_gross(h.get("gross_strokes", 4), h.get("par", 4)) for h in card["completed_holes"])
        diff_par = card["gross_to_par"]
        diff_str = f"+{diff_par}" if diff_par > 0 else ("Par" if diff_par == 0 else str(diff_par))

        lines = [
            f"📊 <b>SCORECARD UFFICIALE — {active_course.name}</b>",
            f"👤 <b>{user_rec.first_name} {user_rec.last_name}</b> | HCP {whs_profile.exact_hcp} (Playing: {whs_profile.playing_hcp})",
            f"Tee: {whs_profile.tee_name.title()} | Buche: {card['holes_played']}/{whs_profile.holes_count}",
            "━━━━━━━━━━━━━━━━━━━━",
            "<code>Buca | Par | SI | Lor | Net | StbN | StbL | Put</code>",
            "<code>----------------------------------------</code>"
        ]

        for h in card["completed_holes"]:
            h_n = str(h.get("hole_number", 1)).rjust(4)
            par_v = str(h.get("par", 4)).rjust(3)
            si_v = str(h.get("stroke_index", 1)).rjust(2)
            g_s = str(h.get("gross_strokes", 4)).rjust(3)
            n_s = str(h.get("net_strokes", 4)).rjust(3)
            stb_n = str(h.get("stableford_points", 2)).rjust(4)
            stb_l = str(calculate_stableford_points_gross(h.get("gross_strokes", 4), h.get("par", 4))).rjust(4)
            putt_v = str(h.get("putts", 2)).rjust(3)
            lines.append(f"<code>{h_n} | {par_v} | {si_v} | {g_s} | {n_s} | {stb_n} | {stb_l} | {putt_v}</code>")

        lines.append("<code>----------------------------------------</code>")
        lines.append(
            f"🏆 <b>Totale Stableford:</b> <b>{card['total_stableford']} pt Netti</b> | {tot_gross_stb} pt Lordi\n"
            f"🏌️ <b>Colpi Totali:</b> {card['total_gross']} Lordi ({diff_str}) | {card['total_net']} Netti\n"
            f"⛳ <b>Totale Putt:</b> {card['total_putts']} (Media {card['putts_avg']}/buca)"
        )

        text = "\n".join(lines)
        reply_markup = self.get_interactive_scorecard_menu()
        if message_id is not None:
            return self.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup)
        return self.send_message(chat_id, text, reply_markup=reply_markup)

    def show_bag_comparison(self, chat_id: int | str, message_id: Optional[int] = None, sync_done: bool = False) -> dict:
        """Mostra il confronto tra distanze di allenamento e distanze reali misurate su erba via GPS."""
        user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
        stats = ClubDistanceService.get_club_grass_performance(
            db_path=self.db.db_path,
            user_id=user_rec.user_id,
            chat_id=chat_id
        )
        # Sincronizza temporaneamente per il confronto (senza sovrascrivere il carry)
        user_profile.sync_with_grass_statistics(stats, update_carry=False)
        comparison = user_profile.get_club_comparison_summary()

        lines = [
            f"🎒 <b>CONFRONTO SACCA: ALLENAMENTO vs ERBA IN GARA</b>",
            f"👤 <b>{user_rec.first_name} {user_rec.last_name}</b> | HCP {user_profile.handicap}",
            f"⛳ Campo: {active_course.name}",
            "━━━━━━━━━━━━━━━━━━━━",
            "<code>Mazza        | All. | Erba | Diff. | N°</code>",
            "<code>----------------------------------------</code>"
        ]

        has_any_grass_data = False
        for item in comparison:
            c_name = item["club_name"][:12].ljust(12)
            t_m = f"{int(item['training_meters'])}m".rjust(4)
            if item["grass_meters"] is not None:
                has_any_grass_data = True
                g_m = f"{int(item['grass_meters'])}m".rjust(4)
                d_val = int(item["delta_meters"])
                d_str = f"{'+' if d_val > 0 else ''}{d_val}m".rjust(5)
                cnt = str(item["shots_count"]).rjust(3)
            else:
                g_m = "  - ".rjust(4)
                d_str = "    -".rjust(5)
                cnt = "  0".rjust(3)

            lines.append(f"<code>{c_name} | {t_m} | {g_m} | {d_str} |{cnt}</code>")

        lines.append("<code>----------------------------------------</code>")

        if sync_done:
            lines.append("✅ <b>Sacca sincronizzata con successo con le distanze reali su erba!</b>\n")
        elif has_any_grass_data:
            lines.append("💡 <i>I dati su erba provengono dai colpi reali tracciati con GPS in gara.</i>\n")
        else:
            lines.append("ℹ️ <i>Nessun colpo ancora misurato su erba per questo account. Usa la modalità gara a pulsanti per iniziare a raccogliere i dati!</i>\n")

        text = "\n".join(lines)
        buttons = []
        if has_any_grass_data:
            buttons.append([{"text": "🔄 Sincronizza Valori in Sacca", "callback_data": "sync_bag_values"}])
        buttons.append([{"text": "🔙 Torna in Campo", "callback_data": "back_to_hole"}])

        reply_markup = {"inline_keyboard": buttons}
        if message_id is not None:
            return self.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup)
        return self.send_message(chat_id, text, reply_markup=reply_markup)

    def finalize_interactive_round(self, chat_id: int | str, message_id: Optional[int] = None) -> dict:
        """Archivia il giro completato e invia il report finale conforme WHS."""
        card = self.session_mgr.get_round_scorecard(chat_id)
        whs_profile = self._resolve_handicap_profile(chat_id)
        user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)

        from core.whs_rules import calculate_stableford_points_gross
        tot_gross_stb = sum(calculate_stableford_points_gross(h.get("gross_strokes", 4), h.get("par", 4)) for h in card["completed_holes"])
        diff_par = card["gross_to_par"]
        diff_str = f"+{diff_par}" if diff_par > 0 else ("Par" if diff_par == 0 else str(diff_par))

        # Notifica Admin se giocatore != Stefano
        if user_rec and user_rec.user_id != "strafatti_stefano_pirani":
            self.config_mgr.notify_admin(
                f"🏁 <b>Giro di Gara Completato (Pulsanti)</b>\n"
                f"👤 <b>Giocatore:</b> {user_rec.first_name} {user_rec.last_name}\n"
                f"⛳ <b>Campo:</b> {active_course.name}\n"
                f"🏆 <b>Score:</b> {card['total_gross']} Lordo | {card['total_net']} Netto\n"
                f"✨ <b>Stableford:</b> {card['total_stableford']} pt Netti | {tot_gross_stb} pt Lordi"
            )

        text = (
            f"🏁 <b>GARA CONCLUSA & REGISTRATA!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Giocatore:</b> {user_rec.first_name} {user_rec.last_name}\n"
            f"⛳ <b>Campo:</b> {active_course.name} ({whs_profile.tee_name.title()})\n"
            f"🎯 <b>Playing HCP:</b> {whs_profile.playing_hcp} colpi\n\n"
            f"🏆 <b>RISULTATO FINALE (WHS):</b>\n"
            f"• <b>Punti Stableford Netti:</b> <b>{card['total_stableford']} pt</b>\n"
            f"• <b>Punti Stableford Lordi:</b> <b>{tot_gross_stb} pt</b>\n"
            f"• <b>Colpi Lordi Totali:</b> <b>{card['total_gross']} ({diff_str})</b>\n"
            f"• <b>Colpi Netti Totali:</b> <b>{card['total_net']}</b>\n"
            f"• <b>Totale Putt:</b> {card['total_putts']} (Media {card['putts_avg']}/buca)\n"
            f"• <b>Buche Giocate:</b> {card['holes_played']}/{whs_profile.holes_count}\n\n"
            f"✨ <i>I dati sono stati archiviati su Voice Caddy Pro e sincronizzati con la dashboard web!</i>"
        )
        return self.send_message(chat_id, text, reply_markup=self.get_on_course_keyboard(self.get_user_mode(chat_id)))

    def handle_callback_query(self, query: dict):
        """
        Gestisce i click sui pulsanti inline (InlineKeyboardMarkup).
        Esegue la transizione di stato FSM e aggiorna la schermata Telegram.
        """
        cb_id = str(query.get("id"))
        message = query.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")
        data = query.get("data", "")

        if not chat_id or not data:
            self.answer_callback_query(cb_id)
            return

        user_rec, user_profile, active_course, ai_cfg = self._resolve_context(chat_id)

        # 1. Avvio wizard gara interattiva
        if data == "start_interactive_round":
            self.answer_callback_query(cb_id)
            return self.start_interactive_wizard(chat_id, message_id=message_id)

        # 2. Selezione Tee
        elif data.startswith("tee_"):
            chosen_tee = data.replace("tee_", "").strip().lower()
            self.session_mgr.set_selected_tee(chat_id, chosen_tee)
            whs_profile = self._resolve_handicap_profile(chat_id, tee_name=chosen_tee, force_refresh=True)
            self.answer_callback_query(cb_id, text=f"Tee {chosen_tee.title()} selezionato!")

            text = (
                f"🟡 <b>Tee {chosen_tee.title()} confermato!</b>\n"
                f"🎯 <b>Playing HCP:</b> {whs_profile.playing_hcp} colpi\n\n"
                f"Seleziona la <b>buca di partenza</b>:"
            )
            return self.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=self.get_interactive_start_hole_menu()
            )

        # 3. Selezione Buca di partenza
        elif data.startswith("start_hole_"):
            h_num = int(data.replace("start_hole_", ""))
            cur_tee = self.session_mgr.get_selected_tee(chat_id)
            self.session_mgr.start_interactive_round(
                chat_id=chat_id,
                tee_name=cur_tee,
                start_hole=h_num,
                course_id=active_course.course_id
            )
            self.answer_callback_query(cb_id, text=f"Partenza da Buca {h_num}!")
            return self.show_interactive_hole_screen(chat_id, message_id=message_id)

        # 4. Scelta del colpo / bastone
        elif data.startswith("shot_"):
            club_key = data.replace("shot_", "")
            club_names = {
                "drive": "Drive",
                "wood": "Legno / Ibrido",
                "iron": "Ferro",
                "wedge": "Wedge"
            }
            club_name = club_names.get(club_key, "Ferro")

            # Coordinate iniziali (dal tee se primo colpo, o dall'ultima posizione registrata)
            istate = self.session_mgr.get_interactive_state(chat_id)
            cur_hole = istate.get("current_hole", 1)
            hole_info = active_course.get_hole(cur_hole)

            start_lat = None
            start_lon = None
            if istate.get("current_shot_number", 1) == 1 and hole_info and hole_info.coordinates:
                start_lat = hole_info.coordinates.tee_lat
                start_lon = hole_info.coordinates.tee_lon
            else:
                last_lat, last_lon, _, _ = self.session_mgr.get_last_position(chat_id)
                start_lat = last_lat
                start_lon = last_lon

            self.session_mgr.record_interactive_shot_start(chat_id, club_name, start_lat, start_lon)
            self.answer_callback_query(cb_id)

            shot_num = istate.get("current_shot_number", 1)
            text = (
                f"🏌️ <b>Colpo {shot_num}: {club_name}</b>\n\n"
                f"Effettua il tiro! Quando arrivi sulla palla:\n"
                f"• Tocca <b>[📍 Calcola Distanza]</b> per misurare i metri via GPS\n"
                f"• Oppure tocca <b>[🟢 Sono in Green]</b> se la palla è arrivata in green."
            )
            return self.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=self.get_interactive_shot_in_progress_menu()
            )

        # 5. Richiesta invio GPS per calcolo distanza colpo
        elif data == "calc_dist":
            # Segna che stiamo attendendo il GPS
            istate = self.session_mgr.get_interactive_state(chat_id)
            istate["waiting_location"] = True
            self.session_mgr.set_interactive_state(chat_id, istate)
            self.answer_callback_query(cb_id)

            gps_prompt_kb = {
                "keyboard": [
                    [{"text": "📍 Invia Posizione Ora", "request_location": True}],
                    [{"text": "🔙 Annulla"}]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            return self.send_message(
                chat_id,
                "📍 <b>Tocca il pulsante qui sotto per inviare la posizione GPS esatta della palla:</b>",
                reply_markup=gps_prompt_kb
            )

        # 6. Palla arrivata in Green
        elif data == "reached_green":
            self.session_mgr.set_interactive_shot_lie(chat_id, "Green")
            self.answer_callback_query(cb_id, text="Ottimo approccio in green!")
            return self.show_interactive_putts_screen(chat_id, message_id=message_id)

        # 7. Scelta Lie della palla
        elif data.startswith("lie_"):
            lie_raw = data.replace("lie_", "").lower()
            self.answer_callback_query(cb_id)

            if lie_raw == "green":
                self.session_mgr.set_interactive_shot_lie(chat_id, "Green")
                return self.show_interactive_putts_screen(chat_id, message_id=message_id)
            elif lie_raw in ["water", "out"]:
                lie_label = "Acqua" if lie_raw == "water" else "Fuori Limite"
                self.session_mgr.set_interactive_shot_lie(chat_id, lie_label)
                text = (
                    f"⚠️ <b>Palla in {lie_label}!</b>\n\n"
                    f"Seleziona la penalità da applicare (+1 colpo):"
                )
                return self.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=self.get_interactive_penalty_menu()
                )
            else:
                lie_names = {
                    "fairway": "Fairway",
                    "rough": "Rough",
                    "trees": "Alberi",
                    "bunker": "Bunker"
                }
                lie_name = lie_names.get(lie_raw, lie_raw.capitalize())
                self.session_mgr.set_interactive_shot_lie(chat_id, lie_name)
                return self.show_interactive_hole_screen(chat_id, message_id=message_id)

        # 8. Menu Penalità
        elif data == "penalty_menu":
            self.answer_callback_query(cb_id)
            text = "❌ <b>REGISTRA PENALITÀ:</b>\nSeleziona il tipo di penalità (+1 colpo):"
            return self.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=self.get_interactive_penalty_menu()
            )

        elif data.startswith("penalty_"):
            pen_type = data.replace("penalty_", "")
            self.answer_callback_query(cb_id)
            if pen_type != "cancel":
                pen_labels = {
                    "water": "Ostacolo d'Acqua (+1)",
                    "out": "Fuori Limite (+1)",
                    "lost": "Palla Persa (+1)",
                    "drop": "Droppaggio (+1)",
                    "other": "Altro (+1)"
                }
                label = pen_labels.get(pen_type, "Penalità (+1)")
                self.session_mgr.add_interactive_penalty(chat_id, penalty_type=label, strokes=1)
                return self.show_interactive_hole_screen(chat_id, message_id=message_id, prompt_suffix=f"<i>⚠️ {label} registrata!</i>")
            else:
                return self.show_interactive_hole_screen(chat_id, message_id=message_id)

        # 9. Annulla Colpo
        elif data == "undo_shot":
            res = self.session_mgr.undo_interactive_last_shot(chat_id)
            if res:
                self.answer_callback_query(cb_id, text="↩️ Ultimo colpo annullato!", show_alert=False)
            else:
                self.answer_callback_query(cb_id, text="⚠️ Nessun colpo da annullare.", show_alert=False)
            return self.show_interactive_hole_screen(chat_id, message_id=message_id)

        # 10. Chiusura Buca con Putt
        elif data.startswith("putts_"):
            putts_str = data.replace("putts_", "")
            putts_val = 4 if putts_str == "4p" else int(putts_str)
            self.answer_callback_query(cb_id)

            whs_profile = self._resolve_handicap_profile(chat_id)
            istate = self.session_mgr.get_interactive_state(chat_id)
            h_num = istate.get("current_hole", 1)
            par = whs_profile.hole_pars.get(h_num, 4)
            si = whs_profile.hole_stroke_indices.get(h_num, h_num)
            rec_strokes = whs_profile.get_received_strokes(h_num)

            res = self.session_mgr.close_interactive_hole(
                chat_id=chat_id,
                putts=putts_val,
                par=par,
                stroke_index=si,
                received_strokes=rec_strokes
            )

            from core.caddy_personality import CaddyTone, CaddyPersonalityEngine
            personality_engine = CaddyPersonalityEngine.get_instance()
            raw_tone = getattr(user_profile, "caddy_tone", None) or CaddyTone.PROFESSIONALE
            caddy_tone = raw_tone if isinstance(raw_tone, CaddyTone) else CaddyTone.PROFESSIONALE

            diff_hole = res["gross_score"] - par
            if diff_hole <= -2:
                sit = "BUCA_EAGLE"
            elif diff_hole == -1:
                sit = "BUCA_BIRDIE"
            elif diff_hole == 0:
                sit = "BUCA_PAR"
            elif diff_hole == 1:
                sit = "BUCA_BOGEY"
            elif diff_hole == 2:
                sit = "BUCA_DOPPIO"
            else:
                sit = "BUCA_DISASTRO"

            next_h = 1 if h_num >= whs_profile.holes_count else h_num + 1
            caddy_quote = personality_engine.get_phrase(
                sit,
                tone=caddy_tone,
                session_id=str(chat_id),
                buca=h_num,
                par=par,
                score=res["gross_score"],
                buca_next=next_h
            )

            card = self.session_mgr.get_round_scorecard(chat_id)
            from core.whs_rules import calculate_stableford_points_gross
            tot_gross_stb = sum(calculate_stableford_points_gross(h.get("gross_strokes", 4), h.get("par", 4)) for h in card["completed_holes"])
            diff_par = card["gross_to_par"]
            diff_str = f"+{diff_par}" if diff_par > 0 else ("Par" if diff_par == 0 else str(diff_par))
            hole_chips = " | ".join([f"B{h['hole_number']}: {h['gross_strokes']}c ({h['stableford_points']}pt)" for h in card["completed_holes"]])

            text = (
                f"⛳ <b>BUCA {h_num} COMPLETATA!</b> (Par {par} • HCP {si})\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• 🏌️ <b>Score Lordo:</b> <b>{res['gross_score']} colpi</b> ➔ <b>{res['stableford_gross']} pt Lordi</b>\n"
                f"• 🎯 <b>Colpi Ricevuti:</b> {rec_strokes} ➔ <b>Par Netto: {res['net_par']}</b>\n"
                f"• ⚖️ <b>Score Netto:</b> <b>{res['net_score']} colpi</b> <i>({res['score_label']})</i>\n"
                f"• 🏆 <b>Punti Stableford:</b> <b>{res['stableford_points']} pt Netti</b> | {res['stableford_gross']} pt Lordi\n\n"
                f"💬 <i>Caddie ({caddy_tone.short_label}):</i> «{caddy_quote}»\n\n"
                f"📊 <b>RIEPILOGO PROGRESSIVO ({card['holes_played']}/{whs_profile.holes_count} Buche)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• 🏆 <b>Totale Stableford:</b> <b>{card['total_stableford']} pt Netti</b> | {tot_gross_stb} pt Lordi\n"
                f"• 🏌️ <b>Colpi Totali:</b> {card['total_gross']} Lordi ({diff_str}) | {card['total_net']} Netti\n"
                f"• ⛳ <b>Totale Putt:</b> {card['total_putts']} (Media {card['putts_avg']}/buca)\n"
                f"• 📝 <b>Scorecard:</b> [ {hole_chips} ]"
            )
            return self.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=self.get_interactive_hole_completed_menu(next_h)
            )

        # 11. Avanzamento Buca Successiva
        elif data == "next_hole":
            self.session_mgr.advance_to_next_interactive_hole(chat_id)
            self.answer_callback_query(cb_id)
            return self.show_interactive_hole_screen(chat_id, message_id=message_id)

        # 12. Modifica Buca
        elif data == "edit_hole":
            self.answer_callback_query(cb_id)
            text = "✏️ <b>Seleziona la buca da modificare o riaprire:</b>"
            return self.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=self.get_interactive_start_hole_menu()
            )

        # 13. Visualizzazione Score
        elif data == "show_score":
            self.answer_callback_query(cb_id)
            return self.show_interactive_scorecard(chat_id, message_id=message_id)

        # 14. Torna alla Buca Corrente
        elif data == "back_to_hole":
            self.answer_callback_query(cb_id)
            return self.show_interactive_hole_screen(chat_id, message_id=message_id)

        # 15. Conferma Fine Gara
        elif data == "confirm_end_round":
            self.answer_callback_query(cb_id)
            text = (
                "🏁 <b>TERMINARE IL GIRO DI GARA?</b>\n\n"
                "I dati registrati verranno archiviati nella scorecard ufficiale e sincronizzati su PC."
            )
            confirm_kb = {
                "inline_keyboard": [
                    [{"text": "✅ Sì, Termina e Salva Score", "callback_data": "finalize_round"}],
                    [{"text": "🔙 No, Continua a Giocare", "callback_data": "back_to_hole"}]
                ]
            }
            return self.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=confirm_kb
            )

        # 16. Finalizza e Salva Giro
        elif data == "finalize_round":
            self.answer_callback_query(cb_id, text="Gara completata e salvata!")
            return self.finalize_interactive_round(chat_id, message_id=message_id)

        # 17. Impostazioni
        elif data == "show_settings":
            self.answer_callback_query(cb_id)
            text = (
                "⚙️ <b>IMPOSTAZIONI GARA & CADDIE:</b>\n\n"
                "• Per cambiare Tee: tocca [🟡 Tee Gialli / 🔴 Rossi]\n"
                "• Per cambiare stile Caddie: usa <code>/tono</code>\n"
                "• Per il calcolo handicap completo: usa <code>/whs</code>\n"
                "• Per confrontare o sincronizzare la sacca: tocca <b>[🎒 Sacca & Distanze Erba]</b>"
            )
            settings_kb = {
                "inline_keyboard": [
                    [{"text": "🎒 Confronto Sacca (All. vs Erba)", "callback_data": "show_bag_comparison"}],
                    [{"text": "🟡 Tee Gialli", "callback_data": "tee_gialli"}, {"text": "🔴 Tee Rossi", "callback_data": "tee_rossi"}],
                    [{"text": "🔙 Torna alla Buca", "callback_data": "back_to_hole"}]
                ]
            }
            return self.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=settings_kb
            )

        # 18. Confronto Sacca (Allenamento vs Erba)
        elif data == "show_bag_comparison":
            self.answer_callback_query(cb_id)
            return self.show_bag_comparison(chat_id, message_id=message_id)

        # 19. Sincronizzazione Sacca con distanze reali su erba
        elif data == "sync_bag_values":
            stats = ClubDistanceService.get_club_grass_performance(
                db_path=self.db.db_path,
                user_id=user_rec.user_id,
                chat_id=chat_id
            )
            user_profile.sync_with_grass_statistics(stats, update_carry=True, user_id=user_rec.user_id)
            self.answer_callback_query(cb_id, text="✅ Sacca sincronizzata con successo!", show_alert=True)
            return self.show_bag_comparison(chat_id, message_id=message_id, sync_done=True)

        self.answer_callback_query(cb_id)

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

    def _resolve_handicap_profile(self, chat_id: int | str, tee_name: Optional[str] = None, force_refresh: bool = False) -> RoundHandicapProfile:
        """
        Risolve o recupera il profilo matematico WHS persistente per la sessione attiva.
        Mantiene in memoria: {Utente, Campo, Tee, Playing_HCP, Tabella_Colpi_Per_Buca}.
        """
        if not force_refresh and not tee_name:
            cached = self.session_mgr.get_handicap_profile(chat_id)
            if cached:
                return cached

        user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
        selected_tee = tee_name or self.session_mgr.get_selected_tee(chat_id)

        # Determina genere giocatore per il tee
        gender = "Donne" if (user_rec and getattr(user_rec, "gender", "male") in ["female", "donna", "donne"]) else "Uomini"

        tee_rating = active_course.get_tee(selected_tee, gender=gender)
        if not tee_rating:
            # Fallback a un tee generico basato sui parametri del campo
            tee_rating = TeeRating(
                tee_name=selected_tee.title(),
                color_code="yellow",
                gender=gender,
                course_rating=float(active_course.total_par),
                slope_rating=125,
                par=active_course.total_par,
                holes_count=active_course.holes_count
            )

        sess = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
        fmt_name = sess.get("game_format", "stableford")
        fmt_pct = sess.get("format_percentage", 0.95)

        profile = build_round_handicap_profile(
            user_id=user_rec.user_id,
            player_name=f"{user_rec.first_name} {user_rec.last_name}",
            exact_hcp=user_profile.handicap,
            course_id=active_course.course_id,
            course_name=active_course.name,
            tee_rating=tee_rating,
            stroke_indices=active_course.get_stroke_indices(),
            hole_pars=active_course.get_hole_pars(),
            format_name=fmt_name,
            format_percentage=fmt_pct
        )

        self.session_mgr.set_handicap_profile(chat_id, profile)
        return profile

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
        # Controllo se c'è un colpo interattivo in attesa della posizione GPS (calcolo distanza del colpo)
        istate = self.session_mgr.get_interactive_state(chat_id)
        if istate.get("waiting_location") or istate.get("state") == "WAITING_LOCATION":
            user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
            act = istate.get("active_shot") or {}
            start_lat = act.get("start_lat")
            start_lon = act.get("start_lon")
            c_hole = istate.get("current_hole", 1)
            hole_info = active_course.get_hole(c_hole)

            if (start_lat is None or start_lon is None) and hole_info and hole_info.coordinates:
                start_lat = hole_info.coordinates.tee_lat
                start_lon = hole_info.coordinates.tee_lon
                act["start_lat"] = start_lat
                act["start_lon"] = start_lon

            dist_calc = None
            if start_lat is not None and start_lon is not None:
                dist_calc = haversine_distance(start_lat, start_lon, lat, lon)

            self.session_mgr.record_interactive_shot_end(chat_id, lat, lon, distance_meters=dist_calc)
            dist_str = f"<b>{int(round(dist_calc))} m</b>" if dist_calc is not None else "<i>Non determinabile</i>"
            msg = (
                f"📍 <b>Distanza Colpo Calcolata:</b> {dist_str}\n\n"
                f"Dove si trova la palla?"
            )
            return self.send_message(chat_id, msg, reply_markup=self.get_interactive_lie_menu())

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

            whs_profile = self._resolve_handicap_profile(chat_id)
            h1_strokes = whs_profile.get_received_strokes(1)
            h1_par = whs_profile.hole_pars.get(1, 4)
            h1_net_par = whs_profile.get_net_par(1)

            reply_msg = (
                f"🏌️‍♂️ <b>Modalità Round Attivata! ({mode_label})</b>\n\n"
                f"🎯 <b>Playing HCP (WHS):</b> <b>{whs_profile.playing_hcp} colpi</b> ({whs_profile.tee_name.title()} • {whs_profile.format_name.title()})\n"
                f"🌤️ <b>Meteo:</b> {cond}, {temp}°C\n"
                f"💨 <b>Vento medio:</b> {w_speed} km/h da {w_card} {w_arrow}\n"
                f"⚠️ <b>Raffiche:</b> fino a {w_gusts} km/h\n\n"
                f"⛳ <i>Sei sul Tee della Buca 1 (Par {h1_par} • Colpi Ricevuti: {h1_strokes} ➔ Par Netto: {h1_net_par}).\n"
                f"Tira il colpo di partenza e tocca <b>[📍 Calcola Distanza & Plays Like]</b> appena arrivi sulla palla!</i>"
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

        whs_profile = self._resolve_handicap_profile(chat_id)
        rec_strokes = whs_profile.get_received_strokes(current_hole)
        net_par = whs_profile.get_net_par(current_hole)
        si_val = whs_profile.hole_stroke_indices.get(current_hole, hole_info.handicap_index if hole_info else current_hole)

        hcp_info_str = f"🎯 <b>HCP Buca:</b> {rec_strokes} colpi ricevuti (<b>Par Netto: {net_par}</b>)"

        # Calcola distanze a Inizio e Fondo Green se disponibili
        green_info = active_course.get_green_coordinates(current_hole)
        d_front = None
        d_back = None
        if green_info:
            from core.green_distance_service import haversine_distance_meters
            d_front = int(round(haversine_distance_meters(lat, lon, green_info.front.lat, green_info.front.lon)))
            d_back = int(round(haversine_distance_meters(lat, lon, green_info.back.lat, green_info.back.lon)))

        if user_mode == "gara":
            # MODALITÀ GARA (R&A Regola 4.3): Solo distanze regolamentari (Inizio, Bandiera, Fondo)
            green_ref = ""
            if d_front is not None and d_back is not None:
                green_ref = f"🟢 <b>Green:</b> Inizio {d_front}m | Pin <b>{raw_dist}m</b> | Fondo {d_back}m\n\n"

            reply_msg = (
                f"⛳ <b>Buca {current_hole}</b> — DISTANZA AL GREEN (Par {par_val} • SI {si_val}) — <b>Colpo {current_shot}</b>\n"
                f"{hcp_info_str}\n\n"
                f"📏 <b>Distanza alla bandiera:</b> <b>{raw_dist}m</b>\n"
                f"{green_ref}"
                f"⚖️ <i>Modalità Gara attiva: per la <b>Regola 4.3</b> sono permesse solo le distanze regolamentari.</i>\n"
            )
        else:
            # MODALITÀ TRAINING: Distanza reale, dislivello, green e raccomandazione bastone
            green_ref = ""
            if d_front is not None and d_back is not None:
                green_ref = f"🟢 <b>Green:</b> Inizio {d_front}m | Pin {raw_dist}m | Fondo {d_back}m\n"

            reply_msg = (
                f"⛳ <b>Buca {current_hole}</b> — DISTANZA AL GREEN (Par {par_val} • SI {si_val}) — <b>Colpo {current_shot}</b>\n"
                f"{hcp_info_str}\n\n"
                f"📏 <b>Distanza reale:</b> {raw_dist}m | ⛰️ <b>Dislivello:</b> {elev_str}\n"
                f"{green_ref}"
                f"🎯 <b>Plays Like:</b> ~{pl_dist}m (Consigliato: <b>{rec_club_str}</b>)\n"
            )

        if distance_covered is not None and distance_covered >= 10:
            prev_shot = max(1, current_shot - 1)
            reply_msg += f"\n🚀 <i>Distanza percorsa dal Colpo {prev_shot}: <b>{int(round(distance_covered))}m</b></i>\n"

        # Rilevamento di prossimità a un altro tee (se il giocatore è disallineato)
        from core.green_distance_service import haversine_distance_meters
        for h in active_course.holes:
            if h.hole_number != current_hole and h.coordinates:
                d_tee = haversine_distance_meters(lat, lon, h.coordinates.tee_lat, h.coordinates.tee_lon)
                if d_tee <= 50:
                    reply_msg += f"\n💡 <i>Ti trovi vicino al Tee della <b>Buca {h.hole_number}</b>? Usa <code>/buca {h.hole_number}</code> per allinearti.</i>\n"
                    break

        reply_msg += (
            f"\n💡 <i>Dopo il colpo, detta/scrivi il bastone (es. 'Ferro 7 in green') "
            f"oppure chiudi la buca (es. '2 putt'). Per cambiare buca usa <code>/buca [N]</code>.</i>"
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

    def handle_green_distance_request(self, chat_id: int | str, intent: str) -> bool:
        """
        Gestisce la richiesta di distanza al green (Rapida o Dettagliata).
        Calcola le distanze geodetiche con Haversine (Front, Center, Back),
        valuta lo stato della posizione GPS (freschezza, presenza, arrivo sul green)
        e invia la risposta formattata per Telegram.
        """
        user_rec, user_profile, active_course, ai_cfg = self._resolve_context(chat_id)
        session = self.session_mgr.get_or_create_session(chat_id, user_id=user_rec.user_id, course_id=active_course.course_id)
        current_hole = session.get("current_hole", 1)
        hole_info = active_course.get_hole(current_hole)
        par_val = hole_info.par if hole_info else 4

        green_coords = active_course.get_green_coordinates(current_hole)
        if not green_coords:
            self.send_message(chat_id, f"⚠️ Coordinate green non disponibili per la Buca {current_hole}.")
            return True

        lat, lon, alt, loc_ts = self.session_mgr.get_last_position(chat_id)

        res = calculate_green_distances(
            user_lat=lat,
            user_lon=lon,
            green_coords=green_coords,
            hole_number=current_hole,
            location_timestamp=loc_ts
        )

        telegram_msg, voice_msg = format_distance_response(intent, res, current_hole, par=par_val)
        self.send_message(chat_id, telegram_msg)
        return True

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

        # Score Lordo e Netto
        score_line = f"• 🏌️ <b>Score Totale:</b> {summary.total_score} Lordo ({rel_par_str})"
        if summary.total_score_net is not None:
            score_line += f" | <b>{summary.total_score_net} Netto</b>"

        # Stableford
        stbl_line = ""
        if summary.total_stableford_points is not None:
            gross_stbl = summary.total_stableford_gross_points if summary.total_stableford_gross_points is not None else "-"
            stbl_line = f"• 🏆 <b>Punti Stableford:</b> <b>{summary.total_stableford_points} pt Netti</b> | {gross_stbl} pt Lordi\n"

        # Course Management Stats
        cm = summary.course_management_stats
        cm_block = ""
        if cm:
            cm_block = (
                f"🧠 <b>GESTIONE DEL PERCORSO & SCELTE TATTICHE:</b>\n"
                f"• <b>Valutazione Tattica:</b> {cm.course_management_rating}\n"
                f"• <b>Piazzamenti (Layup):</b> {cm.layups_count} | <b>Salvataggi (Recovery):</b> {cm.recoveries_count}\n"
                f"• <b>Approcci a correre (Bump & Run):</b> {cm.bump_and_runs_count}\n"
                f"• <b>Tasso di Successo Recovery:</b> {cm.recovery_success_rate}%\n\n"
            )

        reply_msg = (
            f"⛳ <b>VOICE CADDY PRO — SCORECARD UFFICIALE</b>\n"
            f"👤 <b>Giocatore:</b> {player_name}\n"
            f"📍 <b>Campo:</b> {course_name}\n"
            f"🔢 <b>Buche giocate:</b> {holes_count}\n\n"
            f"📊 <b>RISULTATI CHIAVE:</b>\n"
            f"{score_line}\n"
            f"{stbl_line}"
            f"• <b>Fairway Presi (FIR):</b> {summary.fairway_accuracy_pct}%\n"
            f"• <b>Green in Reg. (GIR):</b> {summary.gir_pct}%\n"
            f"• <b>Scrambling:</b> {summary.scrambling_pct}%\n"
            f"• <b>Totale Putt:</b> {summary.total_putts} (Media {putts_avg}/buca)\n"
            f"• <b>Course Mgmt Score:</b> {diag.course_management_score}/100\n\n"
            f"{cm_block}"
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
    # Round Audit Gate & Interactive Verification (Prompt 1 & 2)
    # ---------------------------------------------------------
    def initiate_round_audit_flow(self, chat_id: int | str, transcript_or_text: str):
        """
        Fase 2 & 3: Elabora la trascrizione del round, associa le buche secondo la sequenza confermata
        (Prompt 1), rileva automaticamente le anomalie (Prompt 2) e presenta il riepilogo
        interattivo prima dell'analisi definitiva e del salvataggio.
        """
        user_rec, user_profile, active_course, ai_cfg = self._resolve_context(chat_id)
        player_name = f"{user_rec.first_name} {user_rec.last_name}"

        # Verifica se la sequenza o il tee sono specificati nel testo stesso
        seq_intent = parse_round_sequence_intent(transcript_or_text, active_course.holes_count)
        if seq_intent["is_sequence_intent"]:
            self.session_mgr.set_round_sequence(chat_id, seq_intent["sequence"])
            if seq_intent["tee"]:
                self.session_mgr.set_selected_tee(chat_id, seq_intent["tee"])

        confirmed_sequence = self.session_mgr.get_round_sequence(chat_id)
        selected_tee = self.session_mgr.get_selected_tee(chat_id)

        self.send_message(
            chat_id,
            f"🧠 <i>Trascrizione completata:</i>\n«<i>{transcript_or_text[:180]}...</i>»\n\n"
            f"⛳ <i>Ricostruzione sequenza buche ({len(confirmed_sequence)} buche, Tee {selected_tee.title()}) in corso...</i>"
        )

        try:
            raw_data = parse_golf_audio_transcript(
                transcript_text=transcript_or_text,
                user_profile=user_profile,
                course=active_course,
                ai_config=ai_cfg
            )

            raw_dict = raw_data.model_dump()
            holes_dict = {h["hole_number"]: h for h in raw_dict.get("holes", [])}

            ordered_holes = []
            for h_num in confirmed_sequence:
                if h_num in holes_dict:
                    h_obj = holes_dict[h_num]
                else:
                    course_hole = next((ch for ch in active_course.holes if ch.hole_number == h_num), None)
                    par_val = course_hole.par if course_hole else 4
                    h_obj = {
                        "hole_number": h_num,
                        "par": par_val,
                        "score": par_val,
                        "fairway_hit": None,
                        "gir": False,
                        "putts": 2,
                        "penalties": 0,
                        "shots": [],
                        "target_landing_analysis": None,
                        "root_cause_error": None
                    }

                # Anomaly detection (Prompt 2)
                h_obj["anomalies"] = detect_hole_anomalies(h_obj)
                ordered_holes.append(h_obj)

            raw_dict["holes"] = ordered_holes
            raw_dict["round_info"]["holes_played"] = len(ordered_holes)

            # Salva nella sessione provvisoria (Gate di Audit)
            self.session_mgr.set_pending_round(chat_id, raw_dict, state="AWAITING_VERIFICATION")

            # Messaggio con tono da maestro PGA e marcatore
            msg = (
                "🏌️‍♂️ <b>CONTROLLO SCORE & VERIFICA COLPI (MAESTRO PGA)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Prima di procedere con l'analisi definitiva, facciamo un controllo da maestro e da marcatore.\n\n"
                "Durante una gara o un giro impegnativo, la tensione o la stanchezza possono far dimenticare "
                "di comunicare un colpo, un ferro usato o una penalità. È assolutamente normale.\n\n"
                f"📍 <b>Tee:</b> {selected_tee.title()} | <b>Buche giocate:</b> {len(ordered_holes)}\n\n"
            )

            for h in ordered_holes:
                h_num = h.get("hole_number")
                par = h.get("par", 4)
                gross = h.get("score") or len(h.get("shots", []))
                putts = h.get("putts", 0)
                pen = h.get("penalties", 0)
                shots = h.get("shots", [])
                anomalies = h.get("anomalies", [])

                msg += f"⛳ <b>Buca {h_num}</b> (Par {par}) ➔ <b>{gross} colpi</b> ({putts} putt, {pen} pen.)\n"
                for s in shots:
                    s_idx = s.get("shot_index", 1)
                    cb = s.get("club") or "Bastone N/D"
                    lie = s.get("lie", "fairway")
                    res = s.get("result", "")
                    msg += f"  • Colpo {s_idx}: {cb} ({lie} ➔ {res})\n"

                for anom in anomalies:
                    msg += f"  {anom}\n"
                msg += "\n"

            msg += (
                "━━━━━━━━━━━━━━━━━━━━\n"
                "✏️ <b>Se manca qualcosa, indicamelo così:</b>\n"
                "• <i>«Buca 4: manca un colpo con ferro 7 verso il green»</i>\n"
                "• <i>«Buca 8: aggiungi una penalità per palla in acqua»</i>\n"
                "• <i>«Buca 12: ho fatto 3 putt, non 2»</i>\n"
                "• <i>«Buca 15: il secondo colpo era con ibrido, non ferro 5»</i>\n\n"
                "✅ <i>Se invece è tutto a posto, tocca <b>[✅ Tutto Corretto, Analizza!]</b> o scrivi «Confermo» per lanciare l'analisi completa!</i>"
            )

            return self.send_message(chat_id, msg, reply_markup=self.get_audit_keyboard())

        except Exception as e:
            logging.error(f"Errore durante l'avvio dell'audit: {e}", exc_info=True)
            return self.send_message(chat_id, f"❌ Errore durante l'elaborazione del giro: {str(e)}")

    def handle_audit_correction(self, chat_id: int | str, text: str) -> bool:
        """
        Gestisce le correzioni inviate dall'utente durante lo stato AWAITING_VERIFICATION.
        Riconosce colpi mancanti, penalità, rettifiche bastone o putt.
        """
        corr = parse_audit_correction(text)
        if corr.get("is_confirmation") or text.strip() == "✅ Tutto Corretto, Analizza!":
            self.complete_pending_round_analysis(chat_id)
            return True

        if not corr.get("is_correction"):
            return False

        hole_num = corr.get("hole_number")
        if not hole_num:
            self.send_message(
                chat_id,
                "⚠️ <b>Specifica il numero della buca da correggere.</b>\n"
                "Esempio: <i>«Buca 4: manca un colpo con ferro 7»</i> o <i>«Buca 8: aggiungi una penalità per acqua»</i>."
            )
            return True

        action = corr.get("action")
        details = corr.get("details", {})

        if action == "add_penalty":
            p_type = details.get("penalty_type", "Penalità")
            p_strokes = details.get("penalty_strokes", 1)
            self.session_mgr.add_pending_hole_penalty(chat_id, hole_num, p_type, p_strokes)
            msg = (
                f"💧 <b>Buca {hole_num}:</b> Aggiunta penalità di {p_strokes} colpo/i ({p_type}).\n"
                f"Il totale della buca è stato ricalcolato.\n\n"
                f"<i>Confermi o ci sono altre modifiche? Tocca [✅ Tutto Corretto, Analizza!] se è tutto ok.</i>"
            )
            self.send_message(chat_id, msg, reply_markup=self.get_audit_keyboard())
            return True

        elif action == "update_putts":
            putts_val = details.get("putts", 2)
            self.session_mgr.update_pending_hole_putts(chat_id, hole_num, putts_val)
            msg = (
                f"⛳ <b>Buca {hole_num}:</b> Conteggio putt aggiornato a {putts_val}.\n\n"
                f"<i>Confermi o ci sono altre modifiche? Tocca [✅ Tutto Corretto, Analizza!] se è tutto ok.</i>"
            )
            self.send_message(chat_id, msg, reply_markup=self.get_audit_keyboard())
            return True

        elif action == "add_or_update_shot":
            self.session_mgr.update_pending_hole_shot(chat_id, hole_num, details)
            cb = details.get("club", "Bastone")
            msg = (
                f"🏌️‍♂️ <b>Buca {hole_num}:</b> Registrato colpo ({cb}).\n"
                f"Il totale della buca è stato aggiornato.\n\n"
                f"<i>Ci sono altri colpi da inserire o confermi? Tocca [✅ Tutto Corretto, Analizza!] se è tutto ok.</i>"
            )
            self.send_message(chat_id, msg, reply_markup=self.get_audit_keyboard())
            return True

        return False

    def complete_pending_round_analysis(self, chat_id: int | str):
        """
        Fase 4: Convalida finale dell'utente ricevuta. Esegue il calcolo metriche WHS,
        salva la partita nel database protetto (SafeVault) e invia il giudizio finale del Maestro PGA.
        """
        pending = self.session_mgr.get_pending_round(chat_id)
        if not pending:
            return self.send_message(chat_id, "ℹ️ Nessun giro in attesa di conferma. Avvia un nuovo giro con <code>/nuovo_giro</code>.")

        user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
        player_name = f"{user_rec.first_name} {user_rec.last_name}"

        self.send_message(
            chat_id,
            "🏆 <i>Tutto confermato! Generazione dell'analisi tecnica definitiva e calcolo WHS in corso...</i>"
        )

        try:
            from core.schemas import GolfRoundData
            # Rimuove campo provvisorio "anomalies" prima di validare con lo schema Pydantic
            for h in pending.get("holes", []):
                h.pop("anomalies", None)

            raw_data = GolfRoundData.model_validate(pending)
            validated_data = GolfMetricsCalculator.recompute_and_reconcile(raw_data)

            round_id = self.db.save_round(
                round_data=validated_data,
                user_id=user_rec.user_id,
                group_name=user_rec.group
            )

            self.session_mgr.clear_pending_round(chat_id)

            reply_msg = self._format_round_summary(validated_data, round_id, player_name, active_course.name)
            return self.send_message(chat_id, reply_msg, reply_markup=self.get_on_course_keyboard(self.get_user_mode(chat_id)))

        except Exception as e:
            logging.error(f"Errore durante la finalizzazione dell'analisi: {e}", exc_info=True)
            return self.send_message(chat_id, f"❌ Errore durante la finalizzazione: {str(e)}")

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
            if not transcript or not transcript.strip():
                return self.send_message(chat_id, "🎙️ <i>Audio non riconosciuto o vuoto. Riprova registrando la tua nota vocale.</i>")

            # Archiviazione automatica su cloud DB
            try:
                from datetime import datetime
                today_date = datetime.now().strftime("%Y-%m-%d")
                archive_dir = PROJECT_ROOT / "data" / "audio_archive" / str(chat_id) / today_date
                archive_dir.mkdir(parents=True, exist_ok=True)
                archived_file = archive_dir / f"{file_id}.ogg"
                if os.path.exists(temp_audio_path) and not archived_file.exists():
                    import shutil
                    shutil.copy2(temp_audio_path, archived_file)

                rel_path = str(archived_file.relative_to(PROJECT_ROOT)).replace("\\", "/")
                session = self.session_mgr.get_or_create_session(chat_id, user_id=user_rec.user_id, course_id=active_course.course_id) if hasattr(self.session_mgr, "get_or_create_session") else {}
                c_hole = session.get("current_hole")
                self.db.archive_telegram_message(
                    chat_id=chat_id,
                    user_id=user_rec.user_id,
                    round_date=today_date,
                    message_type="voice",
                    content_text=transcript,
                    file_id=file_id,
                    file_path=rel_path,
                    hole_number=c_hole,
                    group_name=user_rec.group
                )
            except Exception as e_arch:
                logging.warning(f"Errore archiviazione voice in DB: {e_arch}")

            self.send_message(chat_id, f"🎙️ <i>Voce riconosciuta: «{transcript}»</i>")
            return self.process_text_message(chat_id, transcript)

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

        # 0. Trigger prioritario per Gara a Pulsanti (Zero Audio) e Scorecard
        if any(w in clean_lower for w in ["gara a pulsanti", "inizia gara a pulsanti", "gara_bot", "pulsanti", "tasti"]) or clean == "🟢 Inizia Gara a Pulsanti":
            return self.start_interactive_wizard(chat_id)

        if clean in ["📊 Score"] or clean_lower in ["score", "scorecard", "classifica"]:
            return self.show_interactive_scorecard(chat_id)

        if clean in ["🎒 Profilo & Sacca", "🎒 Sacca & Distanze Erba"] or any(w in clean_lower for w in ["confronto sacca", "sincronizza sacca", "distanze sacca", "la mia sacca"]):
            return self.show_bag_comparison(chat_id)

        # Intercettazione avvio round con richiesta meteo & vento a 1 tocco
        start_keywords = [
            "training", "allenamento", "meteo", "vento",
            "start round", "start_round", "inizio round", "avvia giro", "inizio gara"
        ]
        if clean in ["⚖️ Modalità Gara", "🎯 Modalità Training"] or clean_lower == "gara" or any(kw in clean_lower for kw in start_keywords):
            if "gara" in clean_lower:
                new_mode = "gara"
            elif any(k in clean_lower for k in ["training", "allenamento"]):
                new_mode = "training"
            else:
                new_mode = self.get_user_mode(chat_id)
            return self.start_round_flow(chat_id, new_mode)

        if clean in ["⏩ Prossima Buca", "📊 Stato & Buca", "🎭 Tono Caddie", "🎒 Profilo & Sacca", "🔄 Nuovo Giro"] or any(t in clean_lower for t in ["tono caddie", "tono professionale", "tono arrabbiato", "tono spensierato", "tono psicologo", "torna in campo"]):
            return self.handle_command(chat_id, clean)

        user_rec, user_profile, active_course, ai_cfg = self._resolve_context(chat_id)
        player_name = f"{user_rec.first_name} {user_rec.last_name}"

        # Archiviazione automatica su cloud DB per messaggi di testo
        try:
            from datetime import datetime
            today_date = datetime.now().strftime("%Y-%m-%d")
            session = self.session_mgr.get_or_create_session(chat_id, user_id=user_rec.user_id, course_id=active_course.course_id) if hasattr(self.session_mgr, "get_or_create_session") else {}
            c_hole = session.get("current_hole")
            self.db.archive_telegram_message(
                chat_id=chat_id,
                user_id=user_rec.user_id,
                round_date=today_date,
                message_type="text",
                content_text=clean,
                hole_number=c_hole,
                group_name=user_rec.group
            )
        except Exception as e_arch:
            logging.warning(f"Errore archiviazione text in DB: {e_arch}")

        user_mode = self.get_user_mode(chat_id)
        from core.caddy_personality import CaddyTone, CaddyPersonalityEngine
        personality_engine = CaddyPersonalityEngine.get_instance()
        raw_tone = getattr(user_profile, "caddy_tone", None) or CaddyTone.PROFESSIONALE
        if isinstance(raw_tone, CaddyTone):
            caddy_tone = raw_tone
        else:
            try:
                caddy_tone = CaddyTone(str(raw_tone).lower().strip())
            except Exception:
                caddy_tone = CaddyTone.PROFESSIONALE

        # 0. Trigger prioritario di avvio Gara Interattiva a Pulsanti
        if any(w in clean_lower for w in ["inizia gara a pulsanti", "gara a pulsanti", "inizia gara"]) and not any(w in clean_lower for w in ["ho tirato", "colpo", "putt"]):
            return self.start_interactive_wizard(chat_id)

        # 0a. Trigger rapido visualizzazione Scorecard interattiva
        if clean_lower in ["score", "scorecard", "punti", "classifica"] or clean == "📊 Score":
            return self.show_interactive_scorecard(chat_id)

        # 0b. Se siamo nello stato di verifica dell'audit (Prompt 2), gestisci correzioni o conferma
        if self.session_mgr.get_round_state(chat_id) == "AWAITING_VERIFICATION":
            if self.handle_audit_correction(chat_id, clean):
                return

        # 0b. Controllo se il messaggio specifica la sequenza di buche giocate (Prompt 1)
        seq_intent = parse_round_sequence_intent(clean, active_course.holes_count)
        if seq_intent["is_sequence_intent"] and (self.session_mgr.get_round_state(chat_id) in ["AWAITING_SETUP", "IDLE"] or len(clean.split()) <= 8):
            self.session_mgr.set_round_sequence(chat_id, seq_intent["sequence"])
            if seq_intent["tee"]:
                self.session_mgr.set_selected_tee(chat_id, seq_intent["tee"])
            self.session_mgr.set_round_state(chat_id, "IDLE")
            whs_p = self._resolve_handicap_profile(chat_id, tee_name=seq_intent["tee"])
            t_name = self.session_mgr.get_selected_tee(chat_id)
            msg = (
                f"🏌️‍♂️ <b>Sequenza Buche Confermata!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Percorso:</b> {seq_intent['description']}\n"
                f"• <b>Tee:</b> {t_name.title()} ({whs_p.gender})\n"
                f"• <b>Buche totali:</b> {seq_intent['total_holes']}\n\n"
                f"🎙️ <i>Invia ora le tue note vocali o il testo con i colpi giocati buca per buca!</i>"
            )
            return self.send_message(chat_id, msg, reply_markup=self.get_on_course_keyboard(self.get_user_mode(chat_id)))

        # Regola 4.3 / 10.2: Controllo richiesta consiglio bastone in Modalità Gara
        advice_triggers = [
            "cosa tiro", "che tiro", "che bastone", "quale bastone", "consigliami",
            "dammi un consiglio", "che mazza", "cosa gioco", "che ferro tiro",
            "quale ferro", "consiglio sul bastone", "cosa dovrei tirare", "bastone consigliato"
        ]
        is_asking_advice = any(q in clean_lower for q in advice_triggers) or (
            ("bastone" in clean_lower or "consiglio" in clean_lower or "ferro" in clean_lower) and "?" in clean
        )
        is_reporting_shot = any(w in clean_lower for w in ["ho tirato", "tirato", "giocato", "colpo", "putt", "chiuso", "preso"])
        if user_mode == "gara" and is_asking_advice and not is_reporting_shot:
            return self.send_message(
                chat_id,
                "⚖️ <b>Modalità Gara attiva:</b>\n"
                "In conformità alla <b>Regola 4.3 e 10.2 (R&A / USGA)</b>, durante una gara ufficiale "
                "è severamente vietato ricevere consigli sul bastone o sulla strategia di gioco.\n\n"
                "📍 <i>Tocca <b>[📍 Calcola Distanza & Plays Like]</b> per ottenere la sola distanza regolamentare in metri.</i>"
            )

        # Intercettazione selezione Tee di partenza (es. pulsanti "🟡 Gialli", "⚪ Bianchi", ecc.)
        known_tees = ["gialli", "bianchi", "verdi", "rossi", "arancioni"]
        clean_tee_cand = clean_lower.replace("🟡", "").replace("⚪", "").replace("🟢", "").replace("🔴", "").replace("tee", "").strip()
        if self.session_mgr.is_awaiting_tee_choice(chat_id) or (clean_tee_cand in known_tees and len(clean.split()) <= 2):
            matched_tee = clean_tee_cand if clean_tee_cand in known_tees else "gialli"
            cur_mode = self.get_user_mode(chat_id)
            return self.start_round_flow(chat_id, mode=cur_mode, tee_name=matched_tee)

        # Controllo se è una richiesta di distanza al green (Rapida o Dettagliata)
        dist_intent = parse_green_distance_intent(clean)
        if dist_intent:
            return self.handle_green_distance_request(chat_id, dist_intent)

        # Controllo se è un update rapido di un singolo colpo durante la buca
        quick = parse_quick_shot_update(text)

        # 1. Trigger prioritario di CHIUSURA BUCA sui PUTT (es. "buca finita, 5 colpi e 2 putt", "chiuso con 2 putt", "fatto 6, 3 putt")
        closure = parse_hole_closure_intent(clean)
        if closure["is_closure"]:
            if not closure["valid"]:
                return self.send_message(chat_id, f"⚠️ <b>Errore nei colpi comunicati:</b>\n{closure['error']}\n\n<i>Riprova comunicando ad es. '5 colpi e 2 putt' o '2 putt'</i>")

            putts = closure["putts"] if closure["putts"] is not None else 2
            session = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
            h_num = session.get("current_hole", 1)
            whs_profile = self._resolve_handicap_profile(chat_id)
            h_par = whs_profile.hole_pars.get(h_num, 4)

            gross_score = closure["gross_strokes"]
            if gross_score is None:
                # Calcola dai colpi registrati sulla buca o stima in base ai putt
                hole_shots = self.session_mgr.get_hole_shots(chat_id, h_num)
                if hole_shots:
                    gross_score = len(hole_shots) + putts
                else:
                    gross_score = max(h_par, putts + 1)

            score_res = whs_profile.calculate_hole_score(h_num, gross_score)

            card = self.session_mgr.record_completed_hole(
                chat_id=chat_id,
                hole_number=h_num,
                par=score_res["par"],
                stroke_index=score_res["stroke_index"],
                gross_strokes=gross_score,
                putts=putts,
                received_strokes=score_res["received_strokes"],
                net_par=score_res["net_par"],
                stableford_points=score_res["stableford_points"],
                net_strokes=score_res["net_strokes"],
                score_label=score_res["score_label"],
                advance_hole=True
            )

            next_h = 1 if h_num >= whs_profile.holes_count else h_num + 1
            n_strokes = whs_profile.get_received_strokes(next_h)
            n_net_par = whs_profile.get_net_par(next_h)
            n_par = whs_profile.hole_pars.get(next_h, 4)
            n_si = whs_profile.hole_stroke_indices.get(next_h, next_h)

            diff_par = card["gross_to_par"]
            diff_str = f"+{diff_par}" if diff_par > 0 else ("Par" if diff_par == 0 else str(diff_par))
            hole_chips = " | ".join([f"B{h['hole_number']}: {h['gross_strokes']}c ({h['stableford_points']}pt)" for h in card["completed_holes"]])

            # Battuta Caddie in base al risultato
            diff_hole = gross_score - score_res["par"]
            if diff_hole <= -2:
                sit = "BUCA_EAGLE"
            elif diff_hole == -1:
                sit = "BUCA_BIRDIE"
            elif diff_hole == 0:
                sit = "BUCA_PAR"
            elif diff_hole == 1:
                sit = "BUCA_BOGEY"
            elif diff_hole == 2:
                sit = "BUCA_DOPPIO"
            else:
                sit = "BUCA_DISASTRO"

            caddy_quote = personality_engine.get_phrase(
                sit,
                tone=caddy_tone,
                session_id=str(chat_id),
                buca=h_num,
                par=score_res["par"],
                score=gross_score,
                buca_next=next_h
            )

            # Calcolo Stableford Lordo (Regola 21.1)
            from core.whs_rules import calculate_stableford_points_gross
            gross_stableford = calculate_stableford_points_gross(gross_score, score_res["par"])
            tot_gross_stb = sum(calculate_stableford_points_gross(h.get("gross_strokes", 4), h.get("par", 4)) for h in card["completed_holes"])

            msg = (
                f"⛳ <b>BUCA {h_num} COMPLETATA</b> (Par {score_res['par']} • HCP Buca {score_res['stroke_index']})\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Score Lordo:</b> {gross_score} colpi <i>({gross_score - putts} colpi + {putts} putt)</i> ➔ <b>{gross_stableford} pt Lordi</b>\n"
                f"• <b>Colpi Ricevuti:</b> {score_res['received_strokes']} ➔ <b>Par Netto: {score_res['net_par']}</b>\n"
                f"• <b>Score Netto:</b> {score_res['net_strokes']} colpi <i>({score_res['score_label']})</i>\n"
                f"• 🏆 <b>Punti Stableford:</b> <b>{score_res['stableford_points']} pt Netti</b> | {gross_stableford} pt Lordi\n\n"
                f"💬 <i>Caddie ({caddy_tone.short_label}):</i> «{caddy_quote}»\n\n"
                f"📊 <b>RIEPILOGO PROGRESSIVO ({card['holes_played']}/{whs_profile.holes_count} Buche)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• 🏆 <b>Totale Stableford:</b> <b>{card['total_stableford']} pt Netti</b> | {tot_gross_stb} pt Lordi\n"
                f"• 🏌️ <b>Colpi Totali:</b> {card['total_gross']} Lordi ({diff_str}) | {card['total_net']} Netti\n"
                f"• ⛳ <b>Totale Putt:</b> {card['total_putts']} (Media {card['putts_avg']} / buca)\n"
                f"• 📝 <b>Scorecard:</b> [ {hole_chips} ]\n\n"
                f"⏩ <i>Sei alla <b>Buca {next_h}</b> (Par {n_par} • SI {n_si} • Ricevi {n_strokes} colpi ➔ Par Netto: {n_net_par}). Buon tiro!</i>"
            )
            return self.send_message(chat_id, msg)

        # 2. Riconoscimento punteggio alternativo senza putt espliciti (es. "fatto 5", "score 4")
        import re
        score_match = re.search(r"\b(?:fatto|score|chiuso(?:\s+in)?|chiusa(?:\s+in)?|totale)\s*(\d+)\b", clean_lower)
        if score_match and not quick["is_quick_shot"]:
            gross_score = int(score_match.group(1))
            session = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
            h_num = session.get("current_hole", 1)
            whs_profile = self._resolve_handicap_profile(chat_id)
            score_res = whs_profile.calculate_hole_score(h_num, gross_score)

            card = self.session_mgr.record_completed_hole(
                chat_id=chat_id,
                hole_number=h_num,
                par=score_res["par"],
                stroke_index=score_res["stroke_index"],
                gross_strokes=gross_score,
                putts=2,
                received_strokes=score_res["received_strokes"],
                net_par=score_res["net_par"],
                stableford_points=score_res["stableford_points"],
                net_strokes=score_res["net_strokes"],
                score_label=score_res["score_label"],
                advance_hole=True
            )

            next_h = 1 if h_num >= whs_profile.holes_count else h_num + 1
            n_strokes = whs_profile.get_received_strokes(next_h)
            n_net_par = whs_profile.get_net_par(next_h)
            n_par = whs_profile.hole_pars.get(next_h, 4)
            n_si = whs_profile.hole_stroke_indices.get(next_h, next_h)

            diff_hole = gross_score - score_res["par"]
            if diff_hole <= -2:
                sit = "BUCA_EAGLE"
            elif diff_hole == -1:
                sit = "BUCA_BIRDIE"
            elif diff_hole == 0:
                sit = "BUCA_PAR"
            elif diff_hole == 1:
                sit = "BUCA_BOGEY"
            elif diff_hole == 2:
                sit = "BUCA_DOPPIO"
            else:
                sit = "BUCA_DISASTRO"

            caddy_quote = personality_engine.get_phrase(
                sit,
                tone=caddy_tone,
                session_id=str(chat_id),
                buca=h_num,
                par=score_res["par"],
                score=gross_score,
                buca_next=next_h
            )

            from core.whs_rules import calculate_stableford_points_gross
            gross_stableford = calculate_stableford_points_gross(gross_score, score_res["par"])
            tot_gross_stb = sum(calculate_stableford_points_gross(h.get("gross_strokes", 4), h.get("par", 4)) for h in card["completed_holes"])
            hole_chips = " | ".join([f"B{h['hole_number']}: {h['gross_strokes']}c ({h['stableford_points']}pt)" for h in card["completed_holes"]])

            msg = (
                f"⛳ <b>BUCA {h_num} COMPLETATA</b> (Par {score_res['par']} • HCP Buca {score_res['stroke_index']})\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Colpi Lordi:</b> {gross_score} ➔ <b>{gross_stableford} pt Lordi</b>\n"
                f"• <b>Colpi Ricevuti:</b> {score_res['received_strokes']} ➔ <b>Par Netto: {score_res['net_par']}</b>\n"
                f"• <b>Score Netto:</b> {score_res['net_strokes']} colpi <i>({score_res['score_label']})</i>\n"
                f"• 🏆 <b>Punti Stableford:</b> <b>{score_res['stableford_points']} pt Netti</b> | {gross_stableford} pt Lordi\n\n"
                f"💬 <i>Caddie ({caddy_tone.short_label}):</i> «{caddy_quote}»\n\n"
                f"📊 <b>RIEPILOGO PROGRESSIVO ({card['holes_played']}/{whs_profile.holes_count} Buche)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• 🏆 <b>Totale Stableford:</b> <b>{card['total_stableford']} pt Netti</b> | {tot_gross_stb} pt Lordi\n"
                f"• 🏌️ <b>Colpi Totali:</b> {card['total_gross']} Lordi | {card['total_net']} Netti\n"
                f"• 📝 <b>Scorecard:</b> [ {hole_chips} ]\n\n"
                f"⏩ <i>Sei alla <b>Buca {next_h}</b> (Par {n_par} • SI {n_si} • Ricevi {n_strokes} colpi ➔ Par Netto: {n_net_par}). Buon tiro!</i>"
            )
            return self.send_message(chat_id, msg)

        # 3. Registrazione singolo colpo giocato (Quick shot update)
        if quick["is_quick_shot"]:
            session = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
            h_num = session.get("current_hole", 1)
            s_idx = quick["shot_index"] or session.get("current_shot_index", 1)
            club = quick["club"]
            lie = quick["lie"]
            intent = quick.get("intent", ShotIntent.FULL_SHOT)
            is_recovery = quick.get("is_recovery", False)
            is_layup = quick.get("is_layup", False)

            shot_note = f"[{intent.value if hasattr(intent, 'value') else intent}] {text}" if intent != ShotIntent.FULL_SHOT else text
            self.session_mgr.record_live_shot(
                chat_id=chat_id,
                hole_number=h_num,
                shot_index=s_idx,
                club=club,
                lie=lie,
                notes=shot_note
            )
            next_shot = self.session_mgr.advance_shot(chat_id)

            if intent == ShotIntent.BUMP_AND_RUN:
                sit = "FERRO_OK"
            elif is_recovery or intent in (ShotIntent.RECOVERY_PUNCH, ShotIntent.ESCAPE_TROUBLE):
                sit = "ROUGH"
            elif is_layup or intent == ShotIntent.LAYUP:
                sit = "FERRO_OK"
            elif lie in ["bunker", "sabbia"]:
                sit = "BUNKER"
            elif lie in ["acqua", "ostacolo"]:
                sit = "ACQUA"
            elif lie in ["rough", "alberi"]:
                sit = "ROUGH"
            else:
                sit = "FERRO_OK"

            caddy_quote = personality_engine.get_phrase(
                sit,
                tone=caddy_tone,
                session_id=str(chat_id),
                ferro=club or "Bastone",
                buca=h_num,
                distanza=str(quick.get("manual_distance") or "150")
            )

            intent_label = ""
            if intent and intent != ShotIntent.FULL_SHOT:
                labels = {
                    ShotIntent.LAYUP: "🎯 Piazzamento Strategico (Layup)",
                    ShotIntent.RECOVERY_PUNCH: "🌳 Uscita da Difficoltà / Punch",
                    ShotIntent.BUMP_AND_RUN: "👟 Bump & Run (Approccio a Correre)",
                    ShotIntent.PITCH_FLOP: "🪂 Approccio Alto / Morbido",
                    ShotIntent.CHIP: "⛳ Chip dal Bordo",
                    ShotIntent.ESCAPE_TROUBLE: "🚨 Uscita di Sicurezza Laterale",
                }
                intent_label = f"• 🎯 <b>Intento Tattico:</b> {labels.get(intent, intent.value if hasattr(intent, 'value') else str(intent))}\n"

            msg = (
                f"🏌️‍♂️ <b>Buca {h_num} — Colpo {s_idx} Registrato!</b>\n"
                f"• <b>Bastone:</b> {club or 'Non specificato'}\n"
                f"• <b>Lie:</b> {lie.title()}\n"
                f"{intent_label}"
                f"💬 <i>Caddie ({caddy_tone.short_label}):</i> «{caddy_quote}»\n\n"
            )
            if quick["manual_distance"]:
                self.send_message(chat_id, msg)
                self.handle_manual_distance(chat_id, quick["manual_distance"])
            else:
                msg += f"📍 <i>Raggiungi la palla e tocca <b>[📍 Calcola Distanza & Plays Like]</b> per preparare il <b>Colpo {next_shot}</b>!</i>"
                self.send_message(chat_id, msg)
            return

        # 4. Controllo se è un resoconto completo della partita o richiesta di termine giro -> Avvia Audit
        finish_keywords = [
            "fine giro", "termina giro", "fine partita", "termina partita",
            "fine gara", "termina gara", "chiudi giro", "chiudi round",
            "resoconto finale", "audit", "verifica score", "terminato il giro"
        ]
        is_finish_request = any(kw in clean_lower for kw in finish_keywords)
        hole_mentions = len(re.findall(r"\bbuca\s*\d+\b", clean_lower))
        is_multi_hole_transcript = hole_mentions >= 3

        if is_finish_request or is_multi_hole_transcript:
            return self.initiate_round_audit_flow(chat_id, text)

        # 5. Se siamo in gioco e non è una chiusura/colpo: Risposta conversazionale del Caddie!
        session = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
        h_num = session.get("current_hole", 1)
        s_idx = session.get("current_shot_index", 1)

        # Prova a consultare l'LLM con la personalità del Caddie
        caddy_response = personality_engine.chat_with_caddy(
            message=clean,
            tone=caddy_tone,
            history=[],
            user_profile=user_profile,
            ai_config=ai_cfg,
            active_course=active_course,
            current_hole=h_num
        )

        if caddy_response and not caddy_response.startswith("⚠️"):
            return self.send_message(
                chat_id,
                f"💬 <i>Caddie ({caddy_tone.short_label}):</i>\n«{caddy_response}»\n\n"
                f"⛳ <i>Sei alla <b>Buca {h_num}</b> (Colpo {s_idx}). Tocca [📍 Calcola Distanza] per la distanza al green.</i>"
            )

        # Fallback se AI non configurata o errore
        sit_fallback = "DISTANZA" if "distanza" in clean_lower else "TEE"
        caddy_quote = personality_engine.get_phrase(
            sit_fallback,
            tone=caddy_tone,
            session_id=str(chat_id),
            buca=h_num,
            distanza="150"
        )
        return self.send_message(
            chat_id,
            f"💬 <i>Caddie ({caddy_tone.short_label}):</i> «{caddy_quote}»\n\n"
            f"⛳ <b>Sei alla Buca {h_num} (Colpo {s_idx})</b>\n"
            f"• Per registrare un colpo: es. <code>ferro 7 fairway</code>\n"
            f"• Per chiudere la buca: es. <code>5 colpi e 2 putt</code> oppure <code>2 putt</code>\n"
            f"• Per la distanza: tocca <b>[📍 Calcola Distanza & Plays Like]</b>\n"
            f"• Per la scorecard: tocca <b>[📊 Stato & Buca]</b>"
        )

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
        elif any(k in clean_text.lower() for k in ["profilo & sacca", "sacca", "confronto sacca", "sincronizza sacca", "distanze sacca", "la mia sacca"]) and not clean_text.startswith("/"):
            cmd = "/sacca"
        elif "profilo" in clean_text.lower() and not clean_text.startswith("/"):
            cmd = "/profilo"
        elif "nuovo giro" in clean_text.lower() and not clean_text.startswith("/"):
            cmd = "/nuovogiro"
        elif "gara" in clean_text.lower() and not clean_text.startswith("/"):
            cmd = "/gara"
        elif "training" in clean_text.lower() and not clean_text.startswith("/"):
            cmd = "/training"
        elif "tono caddie" in clean_text.lower() or "personalità" in clean_text.lower():
            cmd = "/tono"
        elif "tono professionale" in clean_text.lower():
            cmd = "/tono"
            args = ["professionale"]
        elif "tono arrabbiato" in clean_text.lower():
            cmd = "/tono"
            args = ["arrabbiato"]
        elif "tono spensierato" in clean_text.lower():
            cmd = "/tono"
            args = ["spensierato"]
        elif "tono psicologo" in clean_text.lower():
            cmd = "/tono"
            args = ["psicologo"]
        elif "torna in campo" in clean_text.lower():
            return self.send_message(chat_id, "⛳ Di nuovo sul percorso!", reply_markup=self.get_on_course_keyboard(self.get_user_mode(chat_id)))
        elif any(k in clean_text.lower() for k in ["gara a pulsanti", "inizia gara a pulsanti", "gara_bot"]):
            cmd = "/gara_bot"
        elif clean_text.lower().strip() in ["score", "scorecard", "📊 score"]:
            cmd = "/score_bot"
        elif any(k in clean_text.lower() for k in ["start_round", "start round", "meteo", "vento"]):
            cmd = "/start_round"

        # Support commands typed without space, e.g. /giocatoreStefano
        for prefix in [
            "/giocatore", "/utente", "/login", "/collega", "/campo", "/circolo",
            "/buca", "/h", "/distanza", "/paletto", "/tee", "/whs", "/handicap",
            "/hcp", "/formato", "/score", "/punti", "/tono", "/caddy", "/personalita"
        ]:
            if cmd.startswith(prefix) and cmd != prefix and not args and not cmd.startswith(prefix + "_"):
                args = [text.strip()[len(prefix):].strip()]
                cmd = prefix
                break

        if cmd == "/start" and args:
            target_key = args[0]
            if target_key.startswith("link_"):
                target_key = target_key[5:]
            target_key = target_key.strip()

            matched_user = self.auth_mgr.get_user(target_key)
            if not matched_user:
                for u in self.auth_mgr.get_all_users():
                    if (
                        u.user_id.lower() == target_key.lower()
                        or u.first_name.lower() == target_key.lower()
                        or u.username.lower() == target_key.lower()
                    ):
                        matched_user = u
                        break

            if matched_user:
                self.config_mgr.link_chat_user(
                    chat_id=chat_id,
                    user_id=matched_user.user_id,
                    group_name=matched_user.group,
                    first_name=matched_user.first_name,
                    active_course_name="Conero Golf Club"
                )
                success_msg = (
                    f"🎉 <b>COLLEGAMENTO SMART COMPLETATO!</b>\n\n"
                    f"Benvenuto <b>{matched_user.first_name} {matched_user.last_name}</b>! ⛳\n\n"
                    f"📱 Il tuo smartphone è ora sincronizzato con Voice Caddy Pro del tuo PC.\n"
                    f"🏌️ <b>Gruppo:</b> {matched_user.group.upper()}\n"
                    f"📍 <b>Percorso Attivo:</b> Conero Golf Club\n"
                    f"🎒 <b>Sacca & Distanze:</b> Sincronizzate in tempo reale\n\n"
                    f"<i>Sei pronto a scendere in campo! Tocca uno dei pulsanti qui sotto per iniziare il giro o calcolare le distanze.</i>"
                )
                return self.send_message(
                    chat_id,
                    success_msg,
                    reply_markup=self.get_on_course_keyboard("training")
                )

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
                "• <code>/start_round</code>: Avvia il giro con scelta Tee e rilevamento meteo/vento\n"
                "• <code>/gara</code>: Avvia il giro in <b>Modalità Gara R&A</b> (Regola 4.3: solo distanze)\n"
                "• <code>/training</code>: Avvia il giro in <b>Modalità Training</b> (distanza + bastone consigliato)\n"
                "• <code>/meteo</code> o <code>/vento</code>: Calcola vento e meteo sul percorso via GPS\n"
                "• <code>/modalita</code>: Mostra la modalità attiva\n\n"
                "<b>🏆 REGOLE & HANDICAP WHS:</b>\n"
                "• <code>/whs</code> o <code>/handicap</code>: Scheda calcolo Course/Playing HCP e colpi buca per buca\n"
                "• <code>/tee [colore]</code>: Seleziona o cambia il Tee (es. <code>/tee gialli</code> o <code>/tee bianchi</code>)\n"
                "• <code>/formato [stableford|matchplay]</code>: Imposta il formato (Stableford 95% o Match Play 100%)\n"
                "• <code>/score [colpi]</code>: Registra lo score della buca, calcola Par Netto e Punti Stableford\n\n"
                "<b>⚙️ ALTRI COMANDI RAPIDI:</b>\n"
                "• <code>/distanza [metri]</code>: Fallback manuale se leggi un paletto (es. <code>/distanza 138</code>)\n"
                "• <code>/pin [offset o coords]</code>: Personalizza la profondità della bandiera\n"
                "• <code>/stato</code>: Verifica buca, colpo attuale, Par Netto e modalità\n"
                "• <code>/giocatore [Nome]</code>: Collega la chat al tuo profilo\n"
                "• <code>/campo [Nome]</code>: Imposta il percorso (es. Conero Golf Club)\n\n"
                f"<b>👥 Giocatori Registrati:</b>\n"
                f"• <b>Strafatti:</b> {', '.join(strafatti_names)}\n"
            )
            if amici_names:
                help_msg += f"• <b>Amici:</b> {', '.join(amici_names)}\n"

            help_msg += "\n⚖️ <i>Voice Caddy Pro &bull; Concept, Architettura e Sviluppo: <b>Stefano Pirani</b></i>\n"

            return self.send_message(chat_id, help_msg)

        if cmd in ["/conferma", "/conferma_giro"]:
            return self.complete_pending_round_analysis(chat_id)

        if cmd in ["/sequenza", "/shotgun"]:
            user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
            if args:
                seq_text = " ".join(args)
                seq_intent = parse_round_sequence_intent(seq_text, active_course.holes_count)
                if seq_intent["is_sequence_intent"]:
                    self.session_mgr.set_round_sequence(chat_id, seq_intent["sequence"])
                    if seq_intent["tee"]:
                        self.session_mgr.set_selected_tee(chat_id, seq_intent["tee"])
                    self.session_mgr.set_round_state(chat_id, "IDLE")
                    whs_p = self._resolve_handicap_profile(chat_id, tee_name=seq_intent["tee"])
                    t_name = self.session_mgr.get_selected_tee(chat_id)
                    msg = (
                        f"🏌️‍♂️ <b>Sequenza Buche Impostata!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>Percorso:</b> {seq_intent['description']}\n"
                        f"• <b>Tee:</b> {t_name.title()} ({whs_p.gender})\n"
                        f"• <b>Buche totali:</b> {seq_intent['total_holes']}\n\n"
                        f"🎙️ <i>Invia ora le tue note vocali o il testo con i colpi giocati!</i>"
                    )
                    return self.send_message(chat_id, msg, reply_markup=self.get_on_course_keyboard(self.get_user_mode(chat_id)))
            return self.send_message(
                chat_id,
                "⛳ <b>Imposta la sequenza di buche giocate:</b>\n"
                "Esempi:\n"
                "• <code>/sequenza 1-18</code> (Giro standard)\n"
                "• <code>/sequenza prime 9</code> (Buche 1-9)\n"
                "• <code>/sequenza shotgun 7</code> (Da buca 7 a 18, poi 1 a 6)\n"
                "• <code>/sequenza 1-6 e 15-18</code> (Giro parziale)",
                reply_markup=self.get_round_sequence_keyboard()
            )

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
            whs_profile = self._resolve_handicap_profile(chat_id)
            n_par = whs_profile.hole_pars.get(next_h, 4)
            n_si = whs_profile.hole_stroke_indices.get(next_h, next_h)
            n_strokes = whs_profile.get_received_strokes(next_h)
            n_net_par = whs_profile.get_net_par(next_h)
            self.send_message(
                chat_id,
                f"⛳ <b>Avanzato a Buca {next_h}!</b> (Par {n_par} • SI {n_si})\n"
                f"🎯 <b>Colpi Ricevuti:</b> {n_strokes} (<b>Par Netto: {n_net_par}</b>)\n\n"
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

            whs_profile = self._resolve_handicap_profile(chat_id)
            h_par = whs_profile.hole_pars.get(h_num, 4)
            h_si = whs_profile.hole_stroke_indices.get(h_num, h_num)
            h_strokes = whs_profile.get_received_strokes(h_num)
            h_net_par = whs_profile.get_net_par(h_num)

            # 1. Colpi registrati sulla buca attiva
            hole_shots = self.session_mgr.get_hole_shots(chat_id, h_num)
            if hole_shots:
                shots_lines = []
                for s in hole_shots:
                    shots_lines.append(f"  • Colpo {s.get('shot_index', 1)}: <b>{s.get('club', 'Bastone N/D')}</b> ({s.get('lie', 'fairway').title()})")
                shots_str = "\n".join(shots_lines)
            else:
                shots_str = "  <i>Nessun colpo ancora registrato per la buca corrente (in attesa del tee shot o resoconto).</i>"

            # 2. Scorecard progressiva buche completate
            card = self.session_mgr.get_round_scorecard(chat_id)
            from core.whs_rules import calculate_stableford_points_gross
            tot_gross_stb = sum(calculate_stableford_points_gross(h.get("gross_strokes", 4), h.get("par", 4)) for h in card["completed_holes"])
            diff_par = card["gross_to_par"]
            diff_str = f"+{diff_par}" if diff_par > 0 else ("Par" if diff_par == 0 else str(diff_par))

            if card["completed_holes"]:
                card_chips = " | ".join([f"B{h['hole_number']}: {h['gross_strokes']}c ({h['stableford_points']}pt)" for h in card["completed_holes"]])
                scorecard_section = (
                    f"📊 <b>SCORECARD PROGRESSIVA ({card['holes_played']}/{whs_profile.holes_count} Buche):</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"• 🏆 <b>Punti Stableford:</b> <b>{card['total_stableford']} pt Netti</b> | {tot_gross_stb} pt Lordi\n"
                    f"• 🏌️ <b>Colpi Totali:</b> {card['total_gross']} Lordi ({diff_str}) | {card['total_net']} Netti\n"
                    f"• ⛳ <b>Putt Totali:</b> {card['total_putts']} (Media {card['putts_avg']} / buca)\n"
                    f"• 📝 <b>Dettaglio:</b> [ {card_chips} ]\n\n"
                )
            else:
                scorecard_section = (
                    f"📊 <b>SCORECARD PROGRESSIVA:</b>\n"
                    f"<i>Nessuna buca ancora completata. Quando finisci la buca scrivi ad es. '5 colpi e 2 putt' o '2 putt'.</i>\n\n"
                )

            self.send_message(
                chat_id,
                f"📍 <b>STATO SESSIONE IN CAMPO:</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• <b>Giocatore:</b> {user_rec.first_name} {user_rec.last_name} (Exact HCP {whs_profile.exact_hcp})\n"
                f"• <b>Campo:</b> {active_course.name} ({whs_profile.tee_name.title()})\n"
                f"• <b>Playing HCP (WHS):</b> {whs_profile.playing_hcp} colpi ({whs_profile.format_name.title()})\n"
                f"• <b>Modalità:</b> {mode_str}\n\n"
                f"⛳ <b>BUCA ATTIVA: #{h_num}</b> (Par {h_par} • SI {h_si})\n"
                f"• <b>Colpi Ricevuti Buca:</b> {h_strokes} ➔ <b>Par Netto: {h_net_par}</b>\n"
                f"• <b>Colpo Corrente:</b> Colpo {s_idx}\n"
                f"🏌️ <b>Colpi Buca {h_num} Registrati:</b>\n{shots_str}\n\n"
                f"{scorecard_section}"
                f"📍 <b>GPS:</b> {pos_str}\n"
                f"<i>Tocca <b>[📍 Calcola Distanza & Plays Like]</b> per misurare la distanza al green della Buca {h_num}!</i>"
            )

        elif cmd in ["/whs", "/handicap", "/hcp", "/calcolo"]:
            prof = self._resolve_handicap_profile(chat_id)
            self.send_message(chat_id, prof.format_summary_card())

        elif cmd in ["/distanza", "/misure", "/quanto"]:
            if args and any(w in " ".join(args).lower() for w in ["dettaglio", "completo", "front", "back", "tutto", "green"]):
                return self.handle_green_distance_request(chat_id, "DISTANZA_DETTAGLIATA")
            return self.handle_green_distance_request(chat_id, "DISTANZA_RAPIDA")

        elif cmd in ["/green", "/misuregreen", "/frontback", "/dettagliogreen"]:
            return self.handle_green_distance_request(chat_id, "DISTANZA_DETTAGLIATA")

        elif cmd in ["/tee", "/partenza"]:
            if not args:
                user_rec, _, active_course, _ = self._resolve_context(chat_id)
                available = ", ".join([t.title() for t in active_course.tees.keys()])
                cur_tee = self.session_mgr.get_selected_tee(chat_id).title()
                self.send_message(
                    chat_id,
                    f"📍 <b>Tee Attuale:</b> {cur_tee}\n"
                    f"Tee disponibili su {active_course.name}: {available}\n\n"
                    f"Usa <code>/tee [colore]</code> (es. <code>/tee bianchi</code>)",
                    reply_markup=self.get_tee_selection_keyboard()
                )
                return
            chosen_tee = " ".join(args).strip().lower()
            self.session_mgr.set_selected_tee(chat_id, chosen_tee)
            prof = self._resolve_handicap_profile(chat_id, tee_name=chosen_tee, force_refresh=True)
            self.send_message(chat_id, prof.format_summary_card())

        elif cmd in ["/formato", "/format"]:
            if not args:
                self.send_message(
                    chat_id,
                    "⚙️ <b>Formato di Gara (WHS):</b>\n"
                    "• <code>/formato stableford</code> (Default 95% WHS)\n"
                    "• <code>/formato matchplay</code> (100% WHS)\n"
                    "• <code>/formato strokeplay</code> (100% WHS)"
                )
                return
            f_name = args[0].lower()
            f_pct = 1.0 if any(k in f_name for k in ["match", "stroke"]) else 0.95
            self.session_mgr.set_game_format(chat_id, f_name, f_pct)
            prof = self._resolve_handicap_profile(chat_id, force_refresh=True)
            self.send_message(
                chat_id,
                f"✅ Formato impostato su <b>{f_name.title()} ({int(f_pct*100)}%)</b>!\n\n"
                f"{prof.format_summary_card()}"
            )

        elif cmd in ["/score", "/punti", "/chiudi"]:
            if not args or not args[0].isdigit():
                self.send_message(chat_id, "⚠️ Indica i colpi lordi effettuati. Esempio: <code>/score 5</code>")
                return
            gross_val = int(args[0])
            user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
            session = self.session_mgr.get_or_create_session(chat_id, user_rec.user_id, active_course.course_id)
            h_num = session.get("current_hole", 1)

            whs_profile = self._resolve_handicap_profile(chat_id)
            score_res = whs_profile.calculate_hole_score(h_num, gross_val)
            next_h = self.session_mgr.next_hole(chat_id)
            n_strokes = whs_profile.get_received_strokes(next_h)
            n_net_par = whs_profile.get_net_par(next_h)

            msg = (
                f"⛳ <b>Buca {h_num} Conclusa!</b> (Par {score_res['par']} • SI {score_res['stroke_index']})\n\n"
                f"• <b>Colpi Lordi:</b> {gross_val}\n"
                f"• <b>Colpi Ricevuti:</b> {score_res['received_strokes']} ➔ <b>Par Netto: {score_res['net_par']}</b>\n"
                f"• <b>Colpi Netti:</b> {score_res['net_strokes']}\n"
                f"• 🏆 <b>Punti Stableford:</b> <b>{score_res['stableford_points']} pt</b> ({score_res['score_label']})\n\n"
                f"⏩ <i>Avanzato a <b>Buca {next_h}</b> (Colpi ricevuti: {n_strokes} • Par Netto: {n_net_par}). Buon tiro!</i>"
            )
            self.send_message(chat_id, msg)

        elif cmd in ["/gara_bot", "/play", "/tasti", "/pulsanti", "/bot", "/iniziagara"]:
            return self.start_interactive_wizard(chat_id)

        elif cmd in ["/score_bot", "/scorecard_bot"]:
            return self.show_interactive_scorecard(chat_id)

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

        elif cmd in ["/sacca", "/confronto_sacca", "/sincronizza_sacca", "/distanze_sacca"]:
            return self.show_bag_comparison(chat_id)

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
                f"• <i>Per confrontare con i colpi reali su erba usa: <code>/sacca</code></i>\n"
                f"• <i>Per cambiare giocatore scrivi: <code>/giocatore [Nome]</code></i>"
            )

        elif cmd in ["/campo", "/circolo"]:
            if not args:
                courses = self.course_registry.list_courses()
                c_names = [f"• {c.name}" for c in courses]
                self.send_message(chat_id, f"⛳ <b>Campi disponibili:</b>\n" + "\n".join(c_names) + "\n\nUsa: <code>/campo [Nome]</code>")
                return

            c_query = " ".join(args).strip()
            self.config_mgr.set_active_course(chat_id, c_query)
        elif cmd in ["/tono", "/caddy", "/personalita"]:
            user_rec, user_profile, active_course, _ = self._resolve_context(chat_id)
            from core.caddy_personality import CaddyTone, CaddyPersonalityEngine
            caddy_eng = CaddyPersonalityEngine.get_instance()

            if args:
                raw_arg = " ".join(args).lower().strip()
                matched_tone = None
                for t in CaddyTone:
                    if t.value in raw_arg or t.name.lower() in raw_arg:
                        matched_tone = t
                        break
                if matched_tone:
                    user_profile.caddy_tone = matched_tone.value
                    user_profile.save_for_user(user_rec.user_id if user_rec else "default")
                    phrase = caddy_eng.get_phrase(
                        "START_ROUND",
                        tone=matched_tone.value,
                        session_id=str(chat_id),
                        buca="1",
                        nome=user_profile.player_name
                    )
                    return self.send_message(
                        chat_id,
                        f"🎭 <b>Stile Caddie Impostato:</b> {matched_tone.display_name}\n\n"
                        f"🗣️ <i>«{phrase}»</i>\n\n"
                        f"Il tuo caddie manterrà questo tono per tutte le reazioni in campo!",
                        reply_markup=self.get_on_course_keyboard(self.get_user_mode(chat_id))
                    )

            # Se nessun argomento, mostra la tastiera rapida con i 4 stili
            tone_keyboard = {
                "keyboard": [
                    [{"text": "👔 Tono Professionale"}, {"text": "🤬 Tono Arrabbiato"}],
                    [{"text": "🍻 Tono Spensierato"}, {"text": "🧘 Tono Psicologo"}],
                    [{"text": "🔙 Torna in Campo"}]
                ],
                "resize_keyboard": True
            }
            curr_tone_str = getattr(user_profile, "caddy_tone", "professionale") or "professionale"
            try:
                curr_label = CaddyTone(curr_tone_str).display_name
            except Exception:
                curr_label = curr_tone_str.title()

            return self.send_message(
                chat_id,
                f"🎭 <b>Personalità & Tono del Caddie</b>\n"
                f"Stile attuale: <b>{curr_label}</b>\n\n"
                f"Tocca uno stile per cambiare immediatamente l'atteggiamento del tuo caddie:",
                reply_markup=tone_keyboard
            )

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

    def _acquire_instance_lock(self) -> bool:
        """
        Acquisisce un lock di processo tramite socket locale su 127.0.0.1:48199.
        Impedisce che più istanze o terminali eseguano il polling contemporaneamente
        restituendo messaggi duplicati su Telegram.
        """
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            s.bind(("127.0.0.1", 48199))
            s.listen(1)
            self._instance_socket = s
            return True
        except Exception as e:
            logging.warning(f"⚠️ Impossibile acquisire il lock del bot Telegram (porta 48199 occupata): {e}")
            return False

    def _release_instance_lock(self):
        """Rilascia il socket lock all'arresto del polling."""
        if self._instance_socket:
            try:
                self._instance_socket.close()
            except Exception:
                pass
            self._instance_socket = None

    # ---------------------------------------------------------
    # Main Polling Loop
    # ---------------------------------------------------------
    def run_polling(self):
        """Esegue il long-polling continuo per ricevere aggiornamenti da Telegram."""
        import sys
        # 1. In-process guard: se un thread in questo processo è già in polling, evita duplicati
        if getattr(sys, "_voice_caddy_bot_polling_active", False):
            logging.warning("⚠️ Polling già attivo in un altro thread dello stesso processo. Avvio duplicato ignorato.")
            return

        # 2. Process-level guard: lock via socket locale
        if not self._acquire_instance_lock():
            logging.warning("⚠️ Un'altra istanza o processo del bot Telegram è già attivo su questo PC. Avvio duplicato ignorato per prevenire risposte multiple.")
            return

        setattr(sys, "_voice_caddy_bot_polling_active", True)
        self.is_running = True
        offset = 0

        # Cache deduplicazione update condivisa
        if not hasattr(sys, "_voice_caddy_processed_updates"):
            setattr(sys, "_voice_caddy_processed_updates", set())
        processed_updates: set = getattr(sys, "_voice_caddy_processed_updates")

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

        # 3. Allinea l'offset iniziale saltando i vecchi messaggi non confermati per evitare replay flood
        try:
            flush_res = self._api_request("getUpdates", {"offset": -1, "timeout": 0})
            if flush_res.get("ok") and flush_res.get("result"):
                last_u = flush_res["result"][-1]
                offset = last_u["update_id"] + 1
                logging.info(f"Offset Telegram sincronizzato: {offset}")
        except Exception as e_flush:
            logging.debug(f"Info sync offset iniziale: {e_flush}")

        try:
            while self.is_running:
                try:
                    res = self._api_request("getUpdates", {"offset": offset, "timeout": 15})
                    if res.get("ok"):
                        for update in res.get("result", []):
                            u_id = update["update_id"]
                            offset = u_id + 1

                            # Deduplicazione immediata: se già elaborato, scarta
                            if u_id in processed_updates:
                                continue
                            processed_updates.add(u_id)
                            if len(processed_updates) > 3000:
                                processed_updates.clear()
                                processed_updates.add(u_id)

                            # 0. Callback Query (Click su pulsanti inline)
                            if "callback_query" in update:
                                self.handle_callback_query(update["callback_query"])
                                continue

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

                            elif text:
                                if text.startswith("/"):
                                    self.handle_command(chat_id, text)
                                else:
                                    self.process_text_message(chat_id, text)
                    else:
                        err_desc = str(res.get("description", ""))
                        if "conflict" in err_desc.lower() or res.get("error_code") == 409:
                            logging.warning("Avviso Telegram Bot: un'altra istanza è già attiva (409 Conflict). In attesa...")
                            time.sleep(8)
                        else:
                            time.sleep(2)

                    time.sleep(0.5)
                except KeyboardInterrupt:
                    logging.info("Interruzione manuale del bot.")
                    self.stop()
                    break
                except Exception as e:
                    logging.error(f"Errore loop polling Telegram: {e}")
                    time.sleep(3)
        finally:
            setattr(sys, "_voice_caddy_bot_polling_active", False)
            self._release_instance_lock()
            self.is_running = False

    def stop(self):
        self.is_running = False
        import sys
        setattr(sys, "_voice_caddy_bot_polling_active", False)
        self._release_instance_lock()


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
