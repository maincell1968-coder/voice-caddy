import os
import tempfile
import json
import base64
import urllib.request
import urllib.parse
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from core.audio import VoiceCaddyAudioEngine, AudioProcessingError
from core.parser import parse_golf_audio_transcript
from core.metrics import GolfMetricsCalculator
from core.schemas import GolfRoundData
import importlib
import core.db
importlib.reload(core.db)
from core.db import DatabaseManager
from core.strokes_gained import StrokesGainedBenchmarkEngine
from core.pdf_export import PDFReportGenerator
from core.course import CourseRegistry, CONERO_GOLF_CLUB, GolfCourse
from core.user_profile import UserProfile, PlayerCategory, parse_user_setup_transcript, ClubDetail, ShaftFlex, get_default_bag, sort_clubs_by_distance
from core.visualizer import GolfHoleVisualizer
from core.caddy_personality import CaddyTone, CaddyPersonalityEngine
from core.demo_data import get_demo_golf_round
from core.auth import AuthManager, AIUserConfig, UserRecord, STRAFATTI_INITIAL_MEMBERS
from datetime import datetime
from core.ai_provider import test_ai_connection, AIProviderError
from core.telegram_config import TelegramConfigManager
from core.telegram_service import get_telegram_service
from core.elevation_service import elevation_service, haversine_distance, calculate_plays_like
from core.live_session import LiveSessionManager
from core.backup_manager import backup_manager
from golf_rules_module import render_rules_academy
from core.club_distance_service import ClubDistanceService
from core.admin_inbox import AdminInboxManager
from core.mobile_pdf_report import generate_showcase_mobile_pdf, send_pdf_report_via_telegram
from golf_strategy_ai import (
    load_hole_geometry_from_geojson,
    analyze_hole_strategy,
    render_hole_map_html,
    estimate_category_from_handicap,
    HoleGeometry,
    GeoPoint,
    HoleStrategyAgent,
    render_view_a_map_html,
    render_view_b_benchmark_html,
    render_view_c_green_radar_html
)

PROJECT_ROOT = Path(__file__).resolve().parent
live_session_mgr = LiveSessionManager()

def get_asset_base64(filename: str) -> str:
    path = PROJECT_ROOT / "assets" / filename
    if path.exists():
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

_icon_path = PROJECT_ROOT / "assets" / "voice_caddy_golfer_icon.png"
_page_icon = str(_icon_path) if _icon_path.exists() else "⛳"

st.set_page_config(
    page_title="Voice Caddy Pro | Club & Performance Portal",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium Styling & Luxury Aesthetics
st.markdown("""
    <style>
        /* Modern Dark & Gold/Emerald Accents */
        .landing-hero {
            background: linear-gradient(135deg, #0d131f 0%, #172338 50%, #0c1724 100%);
            border: 1px solid rgba(46, 204, 113, 0.25);
            border-radius: 16px;
            padding: 35px 25px;
            text-align: center;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
        }
        .landing-title {
            font-size: 2.6rem;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #FFFFFF, #2ECC71, #F1C40F);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        .landing-subtitle {
            font-size: 0.98rem;
            color: #CBD5E1;
            letter-spacing: 1px;
            font-weight: 600;
            margin-bottom: 0;
        }
        /* Voice Caddy Philosophy & Thought Banner */
        .thought-banner {
            background: linear-gradient(135deg, rgba(14, 23, 38, 0.95) 0%, rgba(20, 32, 48, 0.92) 50%, rgba(13, 29, 26, 0.95) 100%);
            border: 1px solid rgba(212, 175, 55, 0.35);
            border-left: 5px solid #D4AF37;
            border-radius: 14px;
            padding: 20px 24px;
            margin: 0 auto 26px auto;
            box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4), 0 0 20px rgba(212, 175, 55, 0.08);
            position: relative;
            overflow: hidden;
        }
        .thought-banner::before {
            content: "";
            position: absolute;
            top: 0;
            right: 0;
            width: 180px;
            height: 100%;
            background: radial-gradient(circle at top right, rgba(46, 204, 113, 0.08) 0%, transparent 70%);
            pointer-events: none;
        }
        .thought-quote-line {
            font-size: 1.1rem;
            font-weight: 700;
            color: #F1C40F;
            letter-spacing: -0.2px;
            line-height: 1.45;
            margin-bottom: 8px;
        }
        .thought-body-line {
            font-size: 0.95rem;
            color: #CBD5E1;
            line-height: 1.6;
            margin-bottom: 12px;
        }
        .thought-cta-box {
            background: rgba(46, 204, 113, 0.1);
            border: 1px solid rgba(46, 204, 113, 0.3);
            border-radius: 8px;
            padding: 10px 16px;
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            font-size: 0.92rem;
            line-height: 1.5;
        }
        .thought-cta-badge {
            color: #2ECC71;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            white-space: nowrap;
        }
        .thought-cta-text {
            color: #E2E8F0;
        }
        .group-card-strafatti {
            background: linear-gradient(160deg, #13241b 0%, #0e1713 100%);
            border: 2px solid #27ae60;
            border-radius: 14px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 8px 24px rgba(39, 174, 96, 0.2);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }
        .group-card-strafatti:hover {
            border-color: #2ecc71;
            transform: translateY(-2px);
        }
        .group-card-amici {
            background: linear-gradient(160deg, #121e33 0%, #0b1424 100%);
            border: 2px solid #2980b9;
            border-radius: 14px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 8px 24px rgba(41, 128, 185, 0.2);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }
        .group-card-amici:hover {
            border-color: #3498db;
            transform: translateY(-2px);
        }
        .badge-strafatti {
            display: inline-block;
            background-color: rgba(46, 204, 113, 0.2);
            color: #2ECC71;
            border: 1px solid #2ECC71;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 12px;
        }
        .badge-amici {
            display: inline-block;
            background-color: rgba(52, 152, 219, 0.2);
            color: #3498DB;
            border: 1px solid #3498DB;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 12px;
        }
        .user-header-pill {
            background-color: #141c2a;
            border: 1px solid #2b3952;
            padding: 8px 16px;
            border-radius: 25px;
            display: inline-flex;
            align-items: center;
            gap: 10px;
            font-size: 0.95rem;
        }
        .ai-status-card {
            background-color: #151a24;
            border: 1px solid #2d3748;
            border-radius: 10px;
            padding: 14px;
            margin-bottom: 15px;
        }
        .drill-box {
            background-color: #1E222B;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 15px;
            border: 1px solid #313745;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
        }
        .drill-target {
            color: #2ECC71;
            font-weight: 700;
            text-transform: uppercase;
            font-size: 0.85rem;
            letter-spacing: 1px;
        }
        .diag-card {
            background-color: #141822;
            border-left: 5px solid #2ECC71;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .target-box {
            background-color: #1A1F2C;
            border: 1px solid #2C354A;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 12px;
        }
        .stMetric {
            background-color: #161A23;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid #292F3D;
        }
        .legal-disclaimer-box {
            background: linear-gradient(145deg, #101622 0%, #162234 100%);
            border: 1px solid rgba(241, 196, 15, 0.4);
            border-left: 5px solid #F1C40F;
            border-radius: 12px;
            padding: 22px 24px;
            margin: 0 auto 30px auto;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }
        .disclaimer-title {
            color: #F1C40F;
            font-size: 1.05rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }
        .disclaimer-text {
            color: #CBD5E1;
            font-size: 0.92rem;
            line-height: 1.65;
            margin-bottom: 0;
        }
        .disclaimer-pill {
            display: inline-block;
            background: rgba(241, 196, 15, 0.12);
            color: #F1C40F;
            border: 1px solid rgba(241, 196, 15, 0.35);
            border-radius: 16px;
            padding: 3px 12px;
            font-size: 0.78rem;
            font-weight: 600;
            margin-right: 6px;
            margin-top: 6px;
        }
        /* Guide & Onboarding Banner */
        .guide-box {
            background: linear-gradient(145deg, #0d1522 0%, #131f33 100%);
            border: 1px solid rgba(52, 152, 219, 0.35);
            border-left: 5px solid #3498DB;
            border-radius: 14px;
            padding: 26px 28px;
            margin: 0 auto 30px auto;
            box-shadow: 0 8px 26px rgba(0, 0, 0, 0.45);
        }
        .guide-header-title {
            font-size: 1.35rem;
            font-weight: 800;
            letter-spacing: -0.2px;
            background: linear-gradient(90deg, #FFFFFF 0%, #68D391 50%, #F6E05E 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .guide-header-subtitle {
            font-size: 0.95rem;
            color: #CBD5E1;
            line-height: 1.5;
            margin-bottom: 22px;
        }
        .guide-columns {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .guide-card-phase1 {
            background: rgba(18, 30, 51, 0.75);
            border: 1px solid rgba(52, 152, 219, 0.35);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .guide-card-phase2 {
            background: rgba(19, 36, 27, 0.75);
            border: 1px solid rgba(46, 204, 113, 0.35);
            border-radius: 12px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .guide-phase-title-1 {
            color: #3498DB;
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 1px solid rgba(52, 152, 219, 0.25);
            padding-bottom: 8px;
        }
        .guide-phase-title-2 {
            color: #2ECC71;
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 1px solid rgba(46, 204, 113, 0.25);
            padding-bottom: 8px;
        }
        .guide-step-item {
            margin-bottom: 14px;
            display: flex;
            align-items: flex-start;
            gap: 12px;
        }
        .guide-step-num {
            background: rgba(255, 255, 255, 0.12);
            color: #FFFFFF;
            font-weight: 700;
            font-size: 0.8rem;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            margin-top: 1px;
        }
        .guide-step-content {
            font-size: 0.90rem;
            color: #CBD5E1;
            line-height: 1.5;
        }
        .guide-step-content b {
            color: #FFFFFF;
        }
        .guide-phase-footer {
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            font-size: 0.88rem;
            font-weight: 600;
        }
        .guide-benefits-strip {
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(241, 196, 15, 0.25);
            border-radius: 10px;
            padding: 16px 20px;
        }
        .guide-benefits-title {
            color: #F1C40F;
            font-size: 0.92rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .guide-benefits-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 12px;
        }
        .guide-benefit-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.88rem;
            color: #E2E8F0;
        }
        .guide-benefit-item b {
            color: #F1C40F;
        }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Core Services & Session State Initialization
# ---------------------------------------------------------
auth_manager = AuthManager()
db = DatabaseManager()
course_registry = CourseRegistry(storage_dir=PROJECT_ROOT / "courses")
tg_manager = TelegramConfigManager()
bot_service = get_telegram_service()
inbox_mgr = AdminInboxManager()

# Avvio automatico in background del Bot Telegram se il token è presente
if tg_manager.get_token() and not bot_service.is_alive():
    try:
        bot_service.start()
    except Exception:
        pass

# SafeVault: Snapshot di sicurezza automatico all'avvio sessione
if "startup_backup_done" not in st.session_state:
    try:
        backup_manager.create_startup_snapshot()
        st.session_state.startup_backup_done = True
    except Exception:
        pass

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

if "selected_group" not in st.session_state:
    st.session_state.selected_group = "strafatti"

if "changing_pw_user_id" not in st.session_state:
    st.session_state.changing_pw_user_id = None

if "round_data" not in st.session_state:
    st.session_state.round_data = None

if "transcript" not in st.session_state:
    st.session_state.transcript = None

if "selected_course_id" not in st.session_state:
    st.session_state.selected_course_id = CONERO_GOLF_CLUB.course_id


def inject_autofill_cleaner(username_val: str = ""):
    """
    Disabilita in modo categorico l'autofill e la memorizzazione automatica delle password
    da parte dei browser (Chrome, Edge, Firefox, Safari) e password manager esterni.
    Svuota attivamente qualsiasi valore auto-iniettato da Chrome/Edge finché l'utente non digita manualmente.
    """
    components.html("""
        <script>
            (function() {
                try {
                    const parentDoc = window.parent.document;

                    // Rimuove eventuali campi nascosti legacy
                    const oldUserField = parentDoc.getElementById('vc_autofill_username');
                    if (oldUserField) {
                        oldUserField.remove();
                    }

                    function sanitizePasswordInputs() {
                        const forms = parentDoc.querySelectorAll('form');
                        forms.forEach(f => {
                            f.setAttribute('autocomplete', 'off');
                        });

                        const pwInputs = parentDoc.querySelectorAll('input[type="password"]');
                        pwInputs.forEach(input => {
                            input.setAttribute('autocomplete', 'new-password');
                            input.setAttribute('data-lpignore', 'true');
                            input.setAttribute('data-1p-ignore', 'true');
                            input.setAttribute('data-bwignore', 'true');
                            input.setAttribute('data-form-type', 'other');
                            input.setAttribute('autocapitalize', 'off');
                            input.setAttribute('autocorrect', 'off');
                            input.setAttribute('spellcheck', 'false');

                            // Se l'utente non ha interagito manualmente, svuota qualsiasi valore autofillato
                            if (!input.dataset.userTyped && parentDoc.activeElement !== input) {
                                if (input.value && input.value.length > 0) {
                                    input.value = '';
                                    input.dispatchEvent(new Event('input', { bubbles: true }));
                                    input.dispatchEvent(new Event('change', { bubbles: true }));
                                }
                            }

                            // Registra evento digitazione manuale dell'utente
                            if (!input.dataset.listenerAttached) {
                                input.dataset.listenerAttached = 'true';
                                input.addEventListener('input', function() {
                                    this.dataset.userTyped = 'true';
                                });
                                input.addEventListener('keydown', function() {
                                    this.dataset.userTyped = 'true';
                                });
                                input.addEventListener('focus', function() {
                                    // Se il campo conteneva già caratteri prima del focus ed è un autofill, azzera
                                    if (!this.dataset.userTyped && this.value.length > 20) {
                                        this.value = '';
                                    }
                                });
                            }
                        });
                    }

                    sanitizePasswordInputs();
                    setTimeout(sanitizePasswordInputs, 50);
                    setTimeout(sanitizePasswordInputs, 200);
                    setTimeout(sanitizePasswordInputs, 600);
                    setTimeout(sanitizePasswordInputs, 1200);

                    if (!window._vc_clean_observer) {
                        window._vc_clean_observer = true;
                        const observer = new MutationObserver(() => sanitizePasswordInputs());
                        observer.observe(parentDoc.body, { childList: true, subtree: true });
                    }
                } catch (e) {}
            })();
        </script>
    """, height=0, width=0)


def _render_contact_form(current_user, inbox_mgr, key_suffix="home"):
    with st.form(f"contact_admin_form_{key_suffix}", clear_on_submit=True):
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            contact_sender_name = st.text_input(
                "Tuo Nome & Cognome *",
                value=f"{current_user.first_name} {current_user.last_name}",
                help="Nome del mittente visibile all'amministratore",
                key=f"cs_name_{key_suffix}"
            )
            contact_category = st.selectbox(
                "Categoria della richiesta",
                options=[
                    "Assistenza / Supporto Tecnico",
                    "Segnalazione Anomalia / Bug",
                    "Regole di Golf & Handicap",
                    "Proposta Nuova Funzionalità",
                    "Altro"
                ],
                key=f"cs_cat_{key_suffix}"
            )
        with c_col2:
            contact_reply_to = st.text_input(
                "Recapito per risposta (Email o Telefono)",
                placeholder="es. mario.rossi@email.it oppure 333 1234567",
                help="Inserisci la tua email o numero telefonico per consentire all'amministratore di ricontattarti",
                key=f"cs_reply_{key_suffix}"
            )
            contact_subject = st.text_input(
                "Oggetto del messaggio *",
                placeholder="es. Chiarimento su calcolo Stableford buca 7",
                key=f"cs_subj_{key_suffix}"
            )

        contact_body = st.text_area(
            "Testo del messaggio *",
            placeholder="Descrivi dettagliatamente la tua richiesta, segnalazione o domanda per Stefano...",
            height=130,
            key=f"cs_body_{key_suffix}"
        )

        submit_contact = st.form_submit_button("🚀 Invia Messaggio a Stefano", type="primary", use_container_width=True)
        if submit_contact:
            if not contact_subject.strip() or not contact_body.strip():
                st.error("⚠️ Inserisci sia l'oggetto che il testo del messaggio prima di inviare.")
            else:
                ok_send, send_msg = inbox_mgr.send_message(
                    sender_user_id=current_user.user_id,
                    sender_name=contact_sender_name.strip() or f"{current_user.first_name} {current_user.last_name}",
                    sender_contact=contact_reply_to.strip(),
                    subject=contact_subject.strip(),
                    body=contact_body.strip(),
                    category=contact_category
                )
                if ok_send:
                    st.success(f"✅ {send_msg}")
                    st.balloons()
                else:
                    st.error(f"❌ {send_msg}")


def _render_inbox_messages(current_user, inbox_mgr, key_suffix="home"):
    all_inbox_msgs = inbox_mgr.get_messages()
    unread_inbox_count = inbox_mgr.get_unread_count()

    col_h1, col_h2, col_h3 = st.columns([2, 1, 1])
    col_h1.markdown(f"**Totale Messaggi:** {len(all_inbox_msgs)} | **Da Leggere:** :red[{unread_inbox_count}]")
    with col_h2:
        filter_unread = st.checkbox("Mostra solo non letti", value=False, key=f"filter_unread_{key_suffix}")
    with col_h3:
        if unread_inbox_count > 0:
            if st.button("✔️ Segna tutti letti", key=f"btn_mark_all_read_{key_suffix}", use_container_width=True):
                inbox_mgr.mark_all_as_read()
                st.success("Tutti i messaggi sono stati contrassegnati come letti.")
                st.rerun()

    displayed_msgs = inbox_mgr.get_messages(unread_only=filter_unread)

    if not displayed_msgs:
        st.info("📭 Nessun messaggio presente nella casella." if not filter_unread else "✅ Non ci sono nuovi messaggi da leggere.")
    else:
        for msg in displayed_msgs:
            msg_id = msg.get("id")
            is_unread = not msg.get("is_read", False)
            status_icon = "🔴 NUOVO" if is_unread else "⚪ Letto"
            badge_bg = "rgba(231, 76, 60, 0.12)" if is_unread else "rgba(148, 163, 184, 0.08)"
            border_color = "#E74C3C" if is_unread else "#334155"

            with st.expander(f"{'🔔 ' if is_unread else ''}{msg.get('timestamp', '')} — {msg.get('sender_name', '')} | {msg.get('subject', '')} [{msg.get('category', '')}]", expanded=is_unread):
                st.markdown(f"""
                    <div style="background:{badge_bg}; border-left:4px solid {border_color}; border-radius:6px; padding:12px 16px; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                            <span style="font-weight:bold; font-size:1.05rem; color:#FFFFFF;">📌 {msg.get('subject')}</span>
                            <span style="font-size:0.8rem; font-weight:bold; color:{'#E74C3C' if is_unread else '#94A3B8'};">{status_icon}</span>
                        </div>
                        <div style="font-size:0.85rem; color:#94A3B8; margin-bottom:8px;">
                            👤 <b>Mittente:</b> {msg.get('sender_name')} (ID: <code>{msg.get('sender_user_id')}</code>)<br>
                            🏷️ <b>Categoria:</b> {msg.get('category')}<br>
                            📞 <b>Recapito:</b> {msg.get('sender_contact') or '<i>Nessun recapito fornito</i>'}<br>
                            🕒 <b>Data & Ora:</b> {msg.get('timestamp')}
                        </div>
                        <div style="background:#0b111e; border:1px solid #1e293b; border-radius:6px; padding:12px; font-size:0.92rem; color:#E2E8F0; white-space:pre-wrap; line-height:1.5;">{msg.get('body')}</div>
                    </div>
                """, unsafe_allow_html=True)

                btn_c1, btn_c2, _ = st.columns([1.5, 1.5, 3])
                with btn_c1:
                    if is_unread:
                        if st.button("👁️ Segna come letto", key=f"read_{key_suffix}_{msg_id}"):
                            inbox_mgr.mark_as_read(msg_id)
                            st.rerun()
                with btn_c2:
                    if st.button("🗑️ Elimina messaggio", key=f"del_{key_suffix}_{msg_id}"):
                        inbox_mgr.delete_message(msg_id)
                        st.success("Messaggio eliminato.")
                        st.rerun()


def render_contact_and_inbox(current_user, inbox_mgr, key_suffix="home"):
    st.markdown("""
        <div style="background: linear-gradient(135deg, #0d1a2d 0%, #152744 50%, #0d1a2d 100%);
                    border: 1px solid rgba(52, 152, 219, 0.4); border-radius: 12px; padding: 16px 20px;
                    margin-bottom: 14px; box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);">
            <div style="display:flex; align-items:center; gap: 12px;">
                <span style="font-size: 1.8rem;">📬</span>
                <div>
                    <span style="font-size: 1.15rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.2px;">
                        CONTATTA L'AMMINISTRATORE & CASELLA DI POSTA
                    </span>
                    <div style="font-size: 0.85rem; color: #94A3B8; margin-top: 2px;">
                        Hai bisogno di assistenza tecnica, chiarimenti su handicap e regole o vuoi inviare un suggerimento a <b>Stefano Pirani</b>?<br>
                        Invia il tuo messaggio qui sotto: verrà recapitato direttamente nella sua casella e notificato in tempo reale su Telegram!
                    </div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if current_user.is_admin:
        tab_inbox, tab_write = st.tabs(["📬 Casella di Posta (Ricevuti)", "✍️ Invia Messaggio"])
        with tab_inbox:
            _render_inbox_messages(current_user, inbox_mgr, key_suffix=key_suffix)
        with tab_write:
            _render_contact_form(current_user, inbox_mgr, key_suffix=f"{key_suffix}_admin")
    else:
        tab_write, tab_history = st.tabs(["✍️ Invia Messaggio all'Amministratore", "📬 I Miei Messaggi Inviati"])
        with tab_write:
            _render_contact_form(current_user, inbox_mgr, key_suffix=f"{key_suffix}_user")
        with tab_history:
            user_msgs = [m for m in inbox_mgr.get_messages() if m.get("sender_user_id") == current_user.user_id]
            if not user_msgs:
                st.info("Non hai ancora inviato alcun messaggio all'amministratore.")
            else:
                for m in user_msgs:
                    st_read = "🟢 Letto da Stefano" if m.get("is_read", False) else "🟡 In attesa di lettura"
                    with st.expander(f"📌 {m.get('timestamp', '')} — {m.get('subject', '')} ({st_read})"):
                        st.markdown(f"**Categoria:** {m.get('category', '')}")
                        if m.get('sender_contact'):
                            st.markdown(f"**Recapito fornito:** {m.get('sender_contact')}")
                        st.markdown(f"**Messaggio:**\n\n{m.get('body', '')}")


def render_footer():
    golfer_b64 = get_asset_base64("voice_caddy_golfer_icon.png")
    if golfer_b64:
        icon_html = f'<img src="data:image/png;base64,{golfer_b64}" style="height: 18px; vertical-align: middle; margin-right: 6px; filter: drop-shadow(0 1px 4px rgba(212,175,55,0.5));">'
    else:
        icon_html = "⛳ "
    st.markdown(f"""
        <div style="margin-top: 55px; padding: 25px 15px; border-top: 1px solid rgba(255, 255, 255, 0.08); text-align: center;">
            <div style="font-size: 0.95rem; font-weight: 700; color: #E2E8F0; letter-spacing: 0.5px; margin-bottom: 6px;">
                {icon_html}VOICE CADDY PRO &bull; PGA Performance Analytics & Live GPS Caddie
            </div>
            <div style="font-size: 0.85rem; color: #CBD5E1; margin-bottom: 6px;">
                Concept, Architettura e Proprietà Intellettuale &copy; 2025-2026 <b>Stefano Pirani</b> &bull; Tutti i diritti riservati
            </div>
            <div style="font-size: 0.78rem; color: #64748B;">
                Ideato e sviluppato per finalità sportive e ricreative
            </div>
        </div>
    """, unsafe_allow_html=True)


# =========================================================
# SCREEN 1: ACCESS GATE & LOGIN / PASSWORD CHANGE FLOW
# =========================================================
if st.session_state.auth_user is None:
    logo_full_b64 = get_asset_base64("voice_caddy_logo_full.png")
    if logo_full_b64:
        hero_brand_html = f'<img src="data:image/png;base64,{logo_full_b64}" alt="Voice Caddy Pro" style="max-height: 135px; width: auto; max-width: 92%; margin-bottom: 14px; filter: drop-shadow(0 8px 24px rgba(212,175,55,0.38));">'
    else:
        hero_brand_html = '<div class="landing-title">⛳ VOICE CADDY PRO</div>'
    st.markdown(f"""
        <div class="landing-hero" style="text-align: center; padding: 32px 20px 26px 20px;">
            {hero_brand_html}
            <div class="landing-subtitle">Performance Analysis Portal</div>
        </div>
        <div class="thought-banner">
            <div class="thought-quote-line">
                « Lo score è la fine di una giornata di golf. Voice Caddy ti racconta perché. »
            </div>
            <div class="thought-body-line">
                Non siamo professionisti che sbagliano un paio di colpi a giro: il nostro gioco è la somma di tanti piccoli errori che vanno compresi.
            </div>
            <div class="thought-cta-box">
                <span class="thought-cta-badge">💬 Chatta con Voice Caddy :</span>
                <span class="thought-cta-text">l'IA analizza ogni buca per darti la vera consapevolezza di come sei arrivato a quel risultato e come diventare un giocatore migliore</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("""
<div class="guide-box">
    <div class="guide-header-title">
        ⛳ Il tuo caddie digitale, in 2 fasi
    </div>
    <div class="guide-header-subtitle">
        Bastano pochi minuti di configurazione. Poi in campo ci pensa il bot Telegram: tu giochi, lui raccoglie dati, distanze e statistiche.
    </div>
    <div class="guide-columns">
        <div class="guide-card-phase1">
            <div>
                <div class="guide-phase-title-1">
                    🛠️ Fase 1 – Configura il tuo profilo (una volta sola)
                </div>
                <div class="guide-step-item">
                    <div class="guide-step-num">1</div>
                    <div class="guide-step-content">
                        <b>Accedi:</b> Inserisci o seleziona il tuo <b>nome</b> e, come password iniziale, il tuo <b>cognome</b>.
                    </div>
                </div>
                <div class="guide-step-item">
                    <div class="guide-step-num">2</div>
                    <div class="guide-step-content">
                        <b>Personalizza la password:</b> Al primo accesso imposta la tua <b>nuova password personale e riservata</b> (minimo 4 caratteri): sarà quella che userai d'ora in avanti.
                    </div>
                </div>
                <div class="guide-step-item">
                    <div class="guide-step-num">3</div>
                    <div class="guide-step-content">
                        <b>Componi la tua sacca:</b> Inserisci le mazze che usi abitualmente. Più è precisa la sacca, più saranno accurate le statistiche e i consigli.
                    </div>
                </div>
                <div class="guide-step-item">
                    <div class="guide-step-num">4</div>
                    <div class="guide-step-content">
                        <b>Attiva il bot Telegram:</b> Apri Telegram, inquadra il <b>QR Code</b> nel tuo profilo (oppure tocca il link di avvio rapido) e il bot si collegherà automaticamente al tuo account.
                    </div>
                </div>
            </div>
            <div class="guide-phase-footer" style="color: #60A5FA;">
                ✅ <b>Fatto.</b> Da questo momento il bot è il tuo assistente personale in campo.
            </div>
        </div>
        <div class="guide-card-phase2">
            <div>
                <div class="guide-phase-title-2">
                    ⛳ Fase 2 – In campo, buca dopo buca
                </div>
                <div class="guide-step-item">
                    <div class="guide-step-num">1</div>
                    <div class="guide-step-content">
                        <b>Al tee della buca 1:</b> Dì al bot se stai giocando in <b>Training</b> o in <b>Gara</b>. Puoi scrivere un messaggio o inviare un vocale.
                    </div>
                </div>
                <div class="guide-step-item">
                    <div class="guide-step-num">2</div>
                    <div class="guide-step-content">
                        <b>Prima di ogni colpo:</b> Comunica la <b>mazza che stai usando</b> (es. <em>"Ferro 7"</em>). Poi gioca normalmente il tuo colpo.
                    </div>
                </div>
                <div class="guide-step-item">
                    <div class="guide-step-num">3</div>
                    <div class="guide-step-content">
                        <b>Dopo il colpo:</b> Raggiungi la palla e invia la tua <b>posizione</b> al bot (icona 📎 <em>Posizione</em> di Telegram). Ti risponderà subito con la distanza percorsa e le indicazioni per arrivare al green.
                    </div>
                </div>
                <div class="guide-step-item">
                    <div class="guide-step-num">4</div>
                    <div class="guide-step-content">
                        <b>Sul green:</b> Comunica il <b>numero di putt</b> (es. <em>"2 putt"</em>). La buca è registrata e chiusa!
                    </div>
                </div>
            </div>
            <div class="guide-phase-footer" style="color: #4ADE80;">
                🔄 <b>Ripeti dalla 1 alla 18.</b> Nessun taccuino, nessun calcolo: al bot basta un messaggio o un vocale.
            </div>
        </div>
    </div>
    <div class="guide-benefits-strip">
        <div class="guide-benefits-title">
            ⭐ Perché ti conviene
        </div>
        <div class="guide-benefits-grid">
            <div class="guide-benefit-item">
                <span>📏</span> <span><b>Distanze reali:</b> calcolo metrico GPS dopo ogni colpo, senza telemetri o orologi dedicati</span>
            </div>
            <div class="guide-benefit-item">
                <span>🏌️</span> <span><b>Statistiche per mazza:</b> scopri quanto tiri davvero con ogni ferro</span>
            </div>
            <div class="guide-benefit-item">
                <span>📊</span> <span><b>Storico di partite:</b> archivio allenamenti e gare sempre a portata di mano sul portale</span>
            </div>
            <div class="guide-benefit-item">
                <span>🎙️</span> <span><b>Zero attrito:</b> un vocale o un messaggio rapido, e sei già al colpo successivo</span>
            </div>
        </div>
        <div style="text-align: right; margin-top: 10px; font-size: 0.92rem; font-weight: 700; color: #2ECC71;">
            🏌️‍♂️ Buon golf!
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

    st.markdown(f"""
        <div class="legal-disclaimer-box">
            <div class="disclaimer-title">
                ⚖️ Note Legali, Origine del Software & Esonero di Responsabilità
            </div>
            <div class="disclaimer-text">
                Il presente applicativo <b>Voice Caddy Pro</b> nasce da un'idea originale e dal concept funzionale ideato dall'<b>Amministratore di Sistema</b>, ed è stato interamente sviluppato, strutturato e codificato tramite l'ausilio di tecnologie di <b>Intelligenza Artificiale (IA)</b>.
                <br><br>
                Il programma <b>non persegue alcuna finalità commerciale o di lucro</b>, essendo destinato a scopi <b>esclusivamente ludici, amatoriali, ricreativi e sportivi</b> per la condivisione e l'analisi non agonistica delle sessioni di golf tra amici e compagni di circolo.
                <br><br>
                Tutti i contenuti, i calcoli, le metriche statistiche e i suggerimenti tattici generati sono forniti nello stato di fatto e di diritto in cui si trovano (<em>"as-is"</em>), a puro titolo di intrattenimento personale. <b>L'Amministratore di Sistema e l'ideatore del software sono espressamente e totalmente sollevati da qualsiasi conseguenza legale</b>, responsabilità civile, penale o onere risarcitorio diretto o indiretto derivante dall'uso o dal mancato funzionamento dell'applicazione.
            </div>
            <div style="margin-top: 14px;">
                <span class="disclaimer-pill">💡 Ideato dall'Amministratore</span>
                <span class="disclaimer-pill">🤖 Sviluppato da Intelligenza Artificiale</span>
                <span class="disclaimer-pill">🎯 Scopo Esclusivamente Ludico e Ricreativo</span>
                <span class="disclaimer-pill">🛡️ Esonero Totale da Responsabilità Legale</span>
            </div>
        </div>
        <div class="legal-disclaimer-box" style="border-left: 5px solid #2ECC71; border-color: rgba(46, 204, 113, 0.4); margin-top: -10px;">
            <div class="disclaimer-title" style="color: #2ECC71;">
                💡 Trasparenza Totale: Zero Token a Pagamento & Nessun Costo Condiviso
            </div>
            <div class="disclaimer-text">
                Per la massima tutela e serenità di tutti i soci e dell'Amministratore, l'architettura è strutturata a <b>costo zero assoluto</b>:
                <br><br>
                • <b>🎙️ Trascrizione Audio a ZERO TOKEN:</b> La conversione da voce a testo (da Telegram o web) usa il motore <em>Faster-Whisper locale</em>. Non impiega gettoni/token a pagamento ed è gratuita al 100% (0,00€).
                <br>
                • <b>⚡ Analisi Partita Gratuita con Groq Cloud (Llama 3.3):</b> Il motore cloud predefinito sfrutta il piano gratuito di <b>Groq Cloud</b> con modelli open-source Llama 3.3. È gratuito al 100%, <b>non richiede carta di credito</b> e non genera alcun costo né per l'Amministratore né per i giocatori.
                <br>
                • <b>💻 Alternativa Ollama Locale:</b> Chi gioca da PC può utilizzare il proprio Ollama offline senza connessione internet.
                <br>
                • <b>🛡️ Nessun Costo Condiviso (L'Amministratore non paga token per nessuno):</b> Nessun conto o carta è condiviso. Se un giocatore desidera utilizzare modelli a pagamento OpenAI, deve inserire la propria chiave personale; nessun utente può consumare le risorse o i crediti di altri.
            </div>
            <div style="margin-top: 14px;">
                <span class="disclaimer-pill" style="color: #2ECC71; border-color: rgba(46, 204, 113, 0.35); background: rgba(46, 204, 113, 0.12);">🎙️ Trascrizione Vocale = 0 Token</span>
                <span class="disclaimer-pill" style="color: #2ECC71; border-color: rgba(46, 204, 113, 0.35); background: rgba(46, 204, 113, 0.12);">⚡ Groq Cloud 100% Gratuito (No Carta)</span>
                <span class="disclaimer-pill" style="color: #2ECC71; border-color: rgba(46, 204, 113, 0.35); background: rgba(46, 204, 113, 0.12);">🛡️ Zero Costi Condivisi</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Sub-flow: Mandatory Password Change Modal
    if st.session_state.changing_pw_user_id:
        u_temp = auth_manager.get_user_by_id(st.session_state.changing_pw_user_id)
        st.markdown(f"""
            <div style="background-color: #1a2233; border: 2px solid #f39c12; border-radius: 12px; padding: 24px; max-width: 650px; margin: 0 auto 30px auto;">
                <h3 style="color: #f39c12; margin-top: 0;">🔒 Primo Accesso — Imposta la tua Nuova Password Personale</h3>
                <p style="color: #e2e8f0; font-size: 1rem;">
                    Benvenuto <b>{u_temp.first_name} {u_temp.last_name}</b>! Per garantire la massima privacy e riservatezza,
                    al primo accesso è obbligatorio sostituire la password iniziale temporanea (<b>{u_temp.last_name}</b>)
                    con una tua nuova password segreta e personale.
                </p>
            </div>
        """, unsafe_allow_html=True)

        col_pw1, col_pw2, col_pw3 = st.columns([1, 2, 1])
        with col_pw2:
            with st.form("form_change_initial_pw"):
                inject_autofill_cleaner()
                new_pw = st.text_input("Nuova Password Personale", type="password", help="Almeno 4 caratteri")
                new_pw_confirm = st.text_input("Conferma Nuova Password", type="password")
                submit_pw = st.form_submit_button("💾 Salva Nuova Password ed Entra nel Dashboard", type="primary", use_container_width=True)

                if submit_pw:
                    if not new_pw or len(new_pw) < 4:
                        st.error("La password deve contenere almeno 4 caratteri.")
                    elif new_pw != new_pw_confirm:
                        st.error("Le due password inserite non coincidono.")
                    elif new_pw.lower() == u_temp.last_name.lower():
                        st.error("La nuova password non può essere uguale al tuo cognome!")
                    else:
                        ok, msg = auth_manager.change_password(u_temp.user_id, new_pw)
                        if ok:
                            # Re-fetch updated user and authenticate session
                            updated_user = auth_manager.get_user_by_id(u_temp.user_id)
                            st.session_state.auth_user = updated_user
                            tg_manager.notify_admin(
                                f"🔒 <b>Primo Accesso PC (Web)</b>\n"
                                f"👤 <b>Utente:</b> {updated_user.first_name} {updated_user.last_name}\n"
                                f"🏷️ <b>Gruppo:</b> {updated_user.group.upper()}\n"
                                f"🔑 Ha impostato la sua password personale ed è entrato nel portale."
                            )
                            st.session_state.changing_pw_user_id = None
                            st.success("✅ Password aggiornata con successo! Accesso completato.")
                            st.rerun()
                        else:
                            st.error(f"Errore cambio password: {msg}")

            if st.button("⬅️ Annulla e Torna alla Selezione Ingressi"):
                st.session_state.changing_pw_user_id = None
                st.rerun()

        st.stop()

    # Main Entrance Choice
    st.markdown("### 🔑 Scegli il tuo Portale d'Ingresso")
    col_strafatti, col_amici = st.columns(2, gap="large")

    with col_strafatti:
        st.markdown("""
            <div class="group-card-strafatti">
                <div class="badge-strafatti">🏆 Membri Fondatori Esclusivi</div>
                <h2 style="color: #2ECC71; margin-top: 5px;">Gruppo Strafatti</h2>
                <p style="color: #cbd5e0; font-size: 0.95rem;">
                    Ingresso riservato ai membri ufficiali del team. Solo per gli 8 giocatori designati con password iniziale pari al proprio cognome.
                </p>
            </div>
        """, unsafe_allow_html=True)
        if st.button("👉 Accedi come Strafatti", key="btn_sel_strafatti", use_container_width=True, type="primary" if st.session_state.selected_group == "strafatti" else "secondary"):
            st.session_state.selected_group = "strafatti"
            st.rerun()

    with col_amici:
        st.markdown("""
            <div class="group-card-amici">
                <div class="badge-amici">🤝 Compagni di Circolo & Ospiti</div>
                <h2 style="color: #3498DB; margin-top: 5px;">Gruppo Amici</h2>
                <p style="color: #cbd5e0; font-size: 0.95rem;">
                    Ingresso per compagni di gioco, amici del club e ospiti. Primo accesso con Nome e Cognome, con immediata richiesta di password privata.
                </p>
            </div>
        """, unsafe_allow_html=True)
        if st.button("👉 Accedi come Amico", key="btn_sel_amici", use_container_width=True, type="primary" if st.session_state.selected_group == "amici" else "secondary"):
            st.session_state.selected_group = "amici"
            st.rerun()

    st.markdown("---")

    # Login Form based on selected group
    col_form_l, col_form_c, col_form_r = st.columns([1, 2, 1])

    with col_form_c:
        if st.session_state.selected_group == "strafatti":
            st.markdown("""
                <div style="text-align: center; margin-bottom: 20px;">
                    <h3 style="color: #2ECC71; margin-bottom: 4px;">🏌️‍♂️ Login Riservato: Gruppo Strafatti</h3>
                    <p style="color: #94A3B8; font-size: 0.9rem;">
                        Gli unici autorizzati sono: Stefano, Giorgio, Marco S, Marco F, Gianluca, Alessandro, Renzo, Luca.
                    </p>
                </div>
            """, unsafe_allow_html=True)

            if "strafatti_login_error" in st.session_state:
                st.error(st.session_state.pop("strafatti_login_error"))

            with st.form("form_login_strafatti"):
                member_names = [
                    "Stefano",
                    "Giorgio",
                    "Marco S",
                    "Marco F",
                    "Gianluca",
                    "Alessandro",
                    "Renzo",
                    "Luca"
                ]
                strafatti_user_input = st.selectbox(
                    "Seleziona il tuo Profilo Utente:",
                    options=member_names,
                    index=0,
                    key="strafatti_user_select"
                )
                inject_autofill_cleaner(strafatti_user_input)

                pw_ver = st.session_state.get("strafatti_pw_version", 0)
                strafatti_pw_input = st.text_input(
                    "Password (al primo accesso inserisci il tuo Cognome):",
                    type="password",
                    placeholder="Inserisci la tua password...",
                    key=f"strafatti_pw_{strafatti_user_input}_{pw_ver}"
                )
                st.caption("🔒 *Autofill disattivato: il campo rimane sempre vuoto per evitare errori di compilazione.*")
                submit_strafatti = st.form_submit_button("🚀 Entra nel Club Strafatti", type="primary", use_container_width=True)

                if submit_strafatti:
                    ok, user, msg = auth_manager.authenticate_strafatti(strafatti_user_input, strafatti_pw_input)
                    if ok:
                        if user.must_change_password:
                            st.session_state.changing_pw_user_id = user.user_id
                            st.info("🔒 Rilevato primo accesso! Imposta ora la tua nuova password personale.")
                            st.rerun()
                        else:
                            st.session_state.auth_user = user
                            tg_manager.notify_admin(
                                f"💻 <b>Accesso PC (Web)</b>\n"
                                f"👤 <b>Utente:</b> {user.first_name} {user.last_name}\n"
                                f"🏷️ <b>Gruppo:</b> STRAFATTI (Membro Ufficiale)\n"
                                f"🕒 Accesso alla Dashboard completato."
                            )
                            st.success(f"Bentornato {user.first_name}!")
                            st.rerun()
                    else:
                        st.session_state["strafatti_login_error"] = f"⛔ {msg}"
                        # Incrementa versione: al rerun il campo password sarà immediatamente vuoto
                        st.session_state["strafatti_pw_version"] = pw_ver + 1
                        st.rerun()

        else:
            st.markdown("""
                <div style="text-align: center; margin-bottom: 20px;">
                    <h3 style="color: #3498DB; margin-bottom: 4px;">🤝 Login Riservato: Gruppo Amici</h3>
                    <p style="color: #94A3B8; font-size: 0.9rem;">
                        Inserisci il tuo Nome di battesimo e la Password (se è la prima volta, scrivi il tuo Cognome).
                    </p>
                </div>
            """, unsafe_allow_html=True)

            if "amici_login_error" in st.session_state:
                st.error(st.session_state.pop("amici_login_error"))

            with st.form("form_login_amici"):
                amici_name_input = st.text_input("Il tuo Nome:", placeholder="es. Mario", key="amici_name_input")
                inject_autofill_cleaner(amici_name_input)

                amici_pw_ver = st.session_state.get("amici_pw_version", 0)
                amici_pw_input = st.text_input(
                    "Password (al primo accesso inserisci il tuo Cognome):",
                    type="password",
                    placeholder="es. Rossi",
                    key=f"amici_pw_{amici_pw_ver}"
                )
                st.caption("🔒 *Autofill disattivato: il campo rimane sempre vuoto per evitare errori di compilazione.*")
                submit_amici = st.form_submit_button("🚀 Accedi come Amico", type="primary", use_container_width=True)

                if submit_amici:
                    if not amici_name_input or not amici_pw_input:
                        st.error("Compila sia il Nome che la Password.")
                    else:
                        ok, user, msg = auth_manager.authenticate_amici(amici_name_input, amici_pw_input)
                        if ok:
                            if user.must_change_password:
                                st.session_state.changing_pw_user_id = user.user_id
                                st.info("🔒 Rilevato primo accesso! Imposta ora la tua password personale.")
                                st.rerun()
                            else:
                                st.session_state.auth_user = user
                                tg_manager.notify_admin(
                                    f"💻 <b>Accesso PC (Web)</b>\n"
                                    f"👤 <b>Utente:</b> {user.first_name} {user.last_name}\n"
                                    f"🏷️ <b>Gruppo:</b> AMICI & OSPITI\n"
                                    f"🕒 Accesso alla Dashboard completato."
                                )
                                st.success(f"Bentornato {user.first_name}!")
                                st.rerun()
                        else:
                            st.session_state["amici_login_error"] = f"⛔ {msg}"
                            st.session_state["amici_pw_version"] = amici_pw_ver + 1
                            st.rerun()

    # Visualizza footer di copyright anche sulla schermata di accesso
    render_footer()

    # Stop rendering remainder of the app until authenticated
    st.stop()


current_user: UserRecord = st.session_state.auth_user
inject_autofill_cleaner(current_user.first_name)

# Assicura retrocompatibilità totale con oggetti session_state precedenti
if not hasattr(current_user, "ai_config") or current_user.ai_config is None:
    current_user.ai_config = AIUserConfig()
else:
    if not hasattr(current_user.ai_config, "groq_api_key"):
        setattr(current_user.ai_config, "groq_api_key", "")
    if not hasattr(current_user.ai_config, "groq_model"):
        setattr(current_user.ai_config, "groq_model", "llama-3.3-70b-versatile")

# Load Per-User Golf Profile (handicap, bag, ball)
if "user_profile" not in st.session_state or st.session_state.user_profile.player_name != f"{current_user.first_name} {current_user.last_name}":
    st.session_state.user_profile = UserProfile.load_for_user(
        user_id=current_user.user_id,
        default_name=f"{current_user.first_name} {current_user.last_name}"
    )

# Auto-ripristino trasparente dell'ultima partita registrata nel database se non ancora in memoria
if st.session_state.round_data is None:
    try:
        if hasattr(db, "get_latest_round"):
            latest_saved = db.get_latest_round(user_id=current_user.user_id)
        elif hasattr(db, "get_all_rounds") and hasattr(db, "get_round_by_id"):
            all_r = db.get_all_rounds(user_id=current_user.user_id)
            latest_saved = db.get_round_by_id(all_r[0]["id"]) if all_r else None
        else:
            latest_saved = None
        if latest_saved:
            st.session_state.round_data = latest_saved
    except Exception:
        pass

# Header Bar with User Badge, Info Popover & Logout
header_left, header_info, header_right = st.columns([3, 1.3, 1])
with header_left:
    group_label = "🏆 Gruppo Strafatti" if current_user.group == "strafatti" else "🤝 Gruppo Amici"
    group_color = "#2ECC71" if current_user.group == "strafatti" else "#3498DB"
    admin_badge = '<span style="color: #F1C40F; font-weight: bold; border-left: 1px solid #3b4963; padding-left: 10px;">👑 Amministratore di Sistema</span>' if current_user.is_admin else f'<span style="color: {group_color}; font-weight: bold; border-left: 1px solid #3b4963; padding-left: 10px;">{group_label}</span>'
    st.markdown(f"""
        <div class="user-header-pill">
            <span>🏌️‍♂️ Connesso: <b>{current_user.first_name} {current_user.last_name}</b></span>
            {admin_badge}
        </div>
    """, unsafe_allow_html=True)

with header_info:
    with st.popover("💡 Info Consumi & Token", use_container_width=True):
        st.markdown("""
            <h4 style="color:#2ECC71; margin-top:0;">🎙️ Trascrizione Vocale: ZERO TOKEN</h4>
            <p style="font-size:0.88rem; line-height:1.5; color:#CBD5E1;">
                La conversione della voce in testo (Speech-to-Text per note vocali su Telegram o caricate sul sito) usa il motore <b>Faster-Whisper locale</b> direttamente sul computer.
                <br><b>Non consuma alcun token/credito OpenAI (Costo: 0,00€).</b>
            </p>
            <h4 style="color:#F1C40F; margin-top:12px;">⚡ Analisi Partita: 100% Gratuita (Groq Cloud)</h4>
            <p style="font-size:0.88rem; line-height:1.5; color:#CBD5E1;">
                Per consentire a tutti di giocare senza costi e senza bruciare token:
                <br>• <b>Groq Cloud (Llama 3.3):</b> Gratuito al 100%, <b>nessuna carta di credito richiesta</b>, velocità ultra-rapida.
                <br>• <b>Ollama Locale:</b> Gratuito al 100% offline sul proprio PC.
                <br>• <b>OpenAI Personale:</b> Chi desidera usare GPT-4o inserisce la propria chiave personale.
            </p>
            <h4 style="color:#3498DB; margin-top:12px;">🛡️ L'Amministratore non paga token per gli altri</h4>
            <p style="font-size:0.88rem; line-height:1.5; color:#CBD5E1;">
                Grazie all'architettura <b>Bring Your Own AI</b>, i profili sono separati ermeticamente: nessun credito è condiviso e ciascun giocatore gestisce la propria configurazione senza intaccare le risorse di nessun altro.
            </p>
        """, unsafe_allow_html=True)

with header_right:
    if st.button("🚪 Esci (Logout)", use_container_width=True):
        st.session_state.auth_user = None
        st.session_state.round_data = None
        st.session_state.transcript = None
        st.rerun()

st.markdown("---")


# =========================================================
# SIDEBAR SETUP (BYO-AI & Analysis Controls)
# =========================================================
with st.sidebar:
    logo_full_b64 = get_asset_base64("voice_caddy_logo_full.png")
    if logo_full_b64:
        st.markdown(f"""
            <div style="text-align: center; margin-bottom: 8px; padding: 4px 0;">
                <img src="data:image/png;base64,{logo_full_b64}" alt="Voice Caddy Pro" style="max-height: 48px; max-width: 95%; filter: drop-shadow(0 3px 10px rgba(212,175,55,0.3));">
            </div>
        """, unsafe_allow_html=True)
    else:
        st.title("⛳ Voice Caddy Pro")
    st.caption("AI Caddie & PGA Performance Analytics Engine")

    # ---------------------------------------------------------
    # BRING YOUR OWN AI (Zero Shared Tokens Architecture)
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("🤖 Il Tuo Motore IA Personale")
    st.caption("Ciascun giocatore utilizza esclusivamente la propria IA (Ollama locale gratuito o token personali).")

    user_ai = current_user.ai_config
    if not hasattr(user_ai, "groq_api_key"):
        setattr(user_ai, "groq_api_key", "")
    if not hasattr(user_ai, "groq_model") or getattr(user_ai, "groq_model") == "llama-3.3-70b-versatile":
        setattr(user_ai, "groq_model", "groq/compound-mini")

    provider_options = [
        "Groq Cloud (100% Gratuito - Consigliato)",
        "Ollama (Locale Offline su PC)",
        "OpenAI (Chiave Personale)",
        "Custom (DeepSeek, Together)"
    ]
    curr_prov = getattr(user_ai, "provider", "groq")
    current_idx = 0
    if curr_prov == "openai":
        current_idx = 2
    elif curr_prov == "custom":
        current_idx = 3
    elif curr_prov == "ollama" and st.session_state.get("explicit_ollama_choice"):
        current_idx = 1
    else:
        current_idx = 0  # Groq Cloud è sempre il default a indice 0!

    chosen_provider_label = st.selectbox(
        "Provider IA Attivo:",
        options=provider_options,
        index=current_idx
    )

    new_provider = "groq"
    if "Ollama" in chosen_provider_label:
        new_provider = "ollama"
        st.session_state["explicit_ollama_choice"] = True
    elif "OpenAI" in chosen_provider_label:
        new_provider = "openai"
    elif "Custom" in chosen_provider_label:
        new_provider = "custom"

    if new_provider == "groq":
        from core.ai_provider import get_default_groq_key
        club_groq_key = os.environ.get("GROQ_API_KEY", "")
        if not club_groq_key:
            try:
                if hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets:
                    club_groq_key = st.secrets["GROQ_API_KEY"]
            except Exception:
                pass
        if not club_groq_key:
            club_groq_key = get_default_groq_key()

        groq_key_val = getattr(user_ai, "groq_api_key", "") or club_groq_key
        groq_api_key = st.text_input(
            "Chiave API Groq Gratuita:",
            type="password",
            value=groq_key_val,
            help="100% gratuita senza carta di credito. Generala su https://console.groq.com/keys"
        )
        groq_model_options = [
            "groq/compound-mini",
            "qwen/qwen3.8-27b",
            "groq/compound",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b"
        ]
        cur_groq_model = getattr(user_ai, "groq_model", "groq/compound-mini")
        if cur_groq_model not in groq_model_options:
            cur_groq_model = "groq/compound-mini"
        model_idx = groq_model_options.index(cur_groq_model)
        groq_model = st.selectbox(
            "Modello Groq Gratuito:",
            options=groq_model_options,
            index=model_idx
        )
        st.caption("💡 *Groq Cloud è 100% gratuito per sempre: non richiede carta di credito e non costa nulla.*")
        st.markdown("[👉 **Ottieni la tua chiave gratuita Groq in 10 secondi su console.groq.com**](https://console.groq.com/keys)")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if st.button("🔌 Test Groq Cloud", use_container_width=True):
                effective_key = groq_api_key or club_groq_key or get_default_groq_key()
                test_cfg = AIUserConfig(provider="groq", groq_api_key=effective_key, groq_model=groq_model)
                ok, msg = test_ai_connection(test_cfg)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
        with col_t2:
            if st.button("💾 Salva IA", key="save_groq_btn", use_container_width=True):
                effective_key = groq_api_key or club_groq_key or get_default_groq_key()
                user_ai.provider = "groq"
                setattr(user_ai, "groq_api_key", effective_key)
                setattr(user_ai, "groq_model", groq_model)
                auth_manager.update_user_ai_config(current_user.user_id, user_ai)
                st.success("Configurazione salvata con successo!")
                st.rerun()

    elif new_provider == "ollama":
        ollama_url = st.text_input("URL Server Ollama:", value=user_ai.ollama_url or "http://localhost:11434")

        # Rileva automaticamente i modelli installati localmente su Ollama
        installed_models = []
        try:
            req_models = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/tags", headers={"User-Agent": "VoiceCaddy/1.0"})
            with urllib.request.urlopen(req_models, timeout=2) as resp_m:
                m_data = json.loads(resp_m.read().decode("utf-8"))
                installed_models = [m.get("name", "") for m in m_data.get("models", []) if m.get("name")]
        except Exception:
            pass

        if installed_models:
            preferred = user_ai.ollama_model if user_ai.ollama_model in installed_models else (
                "llama3:latest" if "llama3:latest" in installed_models else installed_models[0]
            )
            idx_m = installed_models.index(preferred) if preferred in installed_models else 0
            ollama_model = st.selectbox(
                "Modello Ollama Rilevato sul tuo PC:",
                options=installed_models,
                index=idx_m,
                help="Modelli già scaricati e pronti all'uso sul tuo computer."
            )
        else:
            ollama_model = st.text_input(
                "Nome Modello Ollama:",
                value=user_ai.ollama_model or "llama3",
                help="es. llama3, mistral, qwen2.5, phi4"
            )
        st.caption("💡 *Ollama è 100% gratuito, offline e non consuma alcun gettone.*")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if st.button("🔌 Test Ollama", use_container_width=True):
                test_cfg = AIUserConfig(provider="ollama", ollama_url=ollama_url, ollama_model=ollama_model)
                ok, msg = test_ai_connection(test_cfg)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
        with col_t2:
            if st.button("💾 Salva IA", key="save_ollama_btn", use_container_width=True):
                user_ai.provider = "ollama"
                user_ai.ollama_url = ollama_url
                user_ai.ollama_model = ollama_model
                auth_manager.update_user_ai_config(current_user.user_id, user_ai)
                st.success("Configurazione salvata!")
                st.rerun()

    elif new_provider == "openai":
        openai_key = st.text_input("La tua OpenAI API Key:", type="password", value=user_ai.openai_api_key or os.environ.get("OPENAI_API_KEY", ""))
        openai_model = st.selectbox("Modello OpenAI:", options=["gpt-4o", "gpt-4o-mini", "o3-mini", "o1"], index=0 if user_ai.openai_model == "gpt-4o" else 1)
        st.caption("🔒 *La tua chiave viene memorizzata in sicurezza solo per il tuo account.*")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if st.button("🔌 Test OpenAI", use_container_width=True):
                test_cfg = AIUserConfig(provider="openai", openai_api_key=openai_key, openai_model=openai_model)
                ok, msg = test_ai_connection(test_cfg)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
        with col_t2:
            if st.button("💾 Salva IA", key="save_openai_btn", use_container_width=True):
                user_ai.provider = "openai"
                user_ai.openai_api_key = openai_key
                user_ai.openai_model = openai_model
                auth_manager.update_user_ai_config(current_user.user_id, user_ai)
                st.success("Configurazione salvata!")
                st.rerun()

    else:
        custom_base = st.text_input("Base URL:", value=user_ai.custom_base_url or "https://api.groq.com/openai/v1")
        custom_key = st.text_input("Chiave API Custom:", type="password", value=user_ai.custom_api_key or "")
        custom_model = st.text_input("Nome Modello Custom:", value=user_ai.custom_model or "llama-3.3-70b-versatile")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if st.button("🔌 Test Endpoint", use_container_width=True):
                test_cfg = AIUserConfig(provider="custom", custom_base_url=custom_base, custom_api_key=custom_key, custom_model=custom_model)
                ok, msg = test_ai_connection(test_cfg)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
        with col_t2:
            if st.button("💾 Salva IA", key="save_custom_btn", use_container_width=True):
                user_ai.provider = "custom"
                user_ai.custom_base_url = custom_base
                user_ai.custom_api_key = custom_key
                user_ai.custom_model = custom_model
                auth_manager.update_user_ai_config(current_user.user_id, user_ai)
                st.success("Configurazione salvata!")
                st.rerun()

    st.markdown("---")
    st.subheader("⛳ Campo da Gioco")
    all_courses = course_registry.list_courses()
    course_options = {c.name: c.course_id for c in all_courses}

    selected_course_name = st.selectbox(
        "Campo attivo:",
        options=list(course_options.keys()),
        index=0,
        help="Conero Golf Club pre-impostato per la fase di test."
    )
    st.session_state.selected_course_id = course_options[selected_course_name]
    active_course = course_registry.get_course(st.session_state.selected_course_id) or CONERO_GOLF_CLUB

    st.caption(f"📍 **{active_course.name}** ({active_course.city}) — Par Totale {active_course.total_par}")
    terrain_desc = getattr(active_course, "terrain_description", "")
    if terrain_desc:
        st.markdown(f"<div style='font-size:0.8rem; color:#94A3B8; margin-top:-6px; margin-bottom:10px;'>⛰️ <i>{terrain_desc}</i></div>", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("🎮 Prova Rapida & Anteprima")
    col_demo1, col_demo2 = st.columns(2)
    with col_demo1:
        if st.button("Carica Giro Demo PGA", use_container_width=True):
            demo_round = get_demo_golf_round()
            st.session_state.round_data = demo_round
            st.session_state.transcript = "Trascrizione generata per il Giro Dimostrativo PGA a 18 buche al Conero Golf Club."
            db.save_round(demo_round, user_id=current_user.user_id, group_name=current_user.group)
            st.success("✅ Giro Demo caricato nel tuo profilo con successo!")
            st.rerun()
    with col_demo2:
        if st.button("🌟 ANTEPRIMA 4 CAMPI", type="primary", use_container_width=True):
            st.session_state.show_4courses_showcase = not st.session_state.get("show_4courses_showcase", False)
            st.rerun()

    st.markdown("---")
    st.subheader("🎙️ Carica Note Vocali Partita")
    uploaded_files = st.file_uploader(
        "Seleziona file audio (.m4a, .mp3, .wav, .opus)",
        type=["m4a", "mp3", "wav", "aac", "opus", "ogg", "3gp", "amr"],
        accept_multiple_files=True
    )

    whisper_engine = st.radio(
        "Motore Speech-to-Text:",
        options=["Groq Whisper Turbo (Consigliato, Gratuito & Istantaneo)", "OpenAI Whisper Cloud (Usa tua API Key)", "Faster-Whisper Locale"],
        index=0
    )

    whisper_model_local = "base"
    if "Faster-Whisper" in whisper_engine:
        whisper_model_local = st.selectbox(
            "Modello Whisper Locale:",
            options=["base", "small", "medium"],
            index=0
        )

    process_btn = st.button("🚀 Analizza Partita con la Tua IA", type="primary", use_container_width=True, disabled=not uploaded_files)

    # ---------------------------------------------------------
    # TELEGRAM BOT LIVE IN CAMPO (Smart Pairing & Zero-Friction)
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📱 Bot Telegram (Live in Campo)")
    st.caption("Registra o scrivi i colpi buca per buca durante la partita dallo smartphone.")

    curr_token = tg_manager.get_token()
    bot_username = tg_manager.get_bot_username() or "VoiceCaddyGolf_bot"
    linked_chat_id = tg_manager.get_chat_id_for_user(current_user.user_id, current_user.first_name)

    # 2. Sezione Giocatore: Connesso vs Da Connettere
    if linked_chat_id:
        # GIOCATORE CONNESSO
        st.markdown(f"""
            <div style="background: linear-gradient(135deg, #0d2818 0%, #081a10 100%); border: 1px solid #10B981; border-radius: 10px; padding: 14px; margin-bottom: 12px; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.15);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
                    <span style="font-size:0.85rem; font-weight:bold; color:#F1F5F9;">📱 Smartphone:</span>
                    <span style="font-size:0.75rem; font-weight:bold; color:#10B981; background:rgba(16,185,129,0.18); padding:2px 8px; border-radius:4px;">🟢 Collegato & Pronto</span>
                </div>
                <div style="font-size:1.10rem; font-weight:bold; color:#6EE7B7; margin-bottom: 6px;">
                    👤 {current_user.first_name} {current_user.last_name}
                </div>
                <div style="font-size:0.82rem; color:#CBD5E1; line-height:1.5; margin-bottom: 8px; background:#041009; padding:8px; border-radius:6px;">
                    💬 <b>Chat Telegram:</b> <code>#{linked_chat_id}</code><br>
                    🏌️ <b>Sacca Personale:</b> 14 Bastoni sincronizzati<br>
                    ⛳ <b>Percorso:</b> {active_course.name}
                </div>
                <div style="text-align:center; font-size:0.75rem; color:#94A3B8;">
                    🤖 Bot: <b>@{bot_username}</b>
                </div>
            </div>
        """, unsafe_allow_html=True)

        col_act_p1, col_act_p2 = st.columns([3, 2])
        with col_act_p1:
            if st.button("🧪 Invia Test a Smartphone", key="test_tg_ping_btn", use_container_width=True, help="Invia un messaggio di prova istantaneo al tuo cellulare"):
                ok_msg, resp_msg = tg_manager.send_direct_message(
                    linked_chat_id,
                    f"⛳ <b>Voice Caddy Pro</b>: Ciao {current_user.first_name}! Connessione attiva. Sacca e profilo sincronizzati con il PC. Buon gioco!"
                )
                if ok_msg:
                    st.success("✅ Messaggio di prova inviato con successo al tuo cellulare!")
                else:
                    st.error(f"❌ Errore invio: {resp_msg}")
        with col_act_p2:
            if st.button("❌ Scollega", key="unlink_tg_btn", use_container_width=True, help="Scollega questo dispositivo"):
                tg_manager.unlink_user(current_user.user_id)
                st.info("Dispositivo scollegato.")
                st.rerun()

    else:
        # GIOCATORE: PAIRING SMART A 1-CLIC + QR CODE
        deep_link = f"https://t.me/{bot_username}?start=link_{current_user.user_id}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(deep_link)}"

        st.markdown(f"""
            <div style="background: linear-gradient(135deg, #182234 0%, #0d131f 100%); border: 1px solid #2C3E5D; border-radius: 10px; padding: 14px; margin-bottom: 8px;">
                <div style="font-size:0.95rem; font-weight:bold; color:#38BDF8; margin-bottom: 4px;">
                    👤 {current_user.first_name} {current_user.last_name}
                </div>
                <div style="font-size:0.82rem; color:#CBD5E1; margin-bottom: 4px;">
                    Inquadra il QR Code con lo smartphone per sincronizzare la sacca:
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Riquadro QR Code nativo Streamlit
        col_qr1, col_qr2, col_qr3 = st.columns([1, 4, 1])
        with col_qr2:
            st.image(qr_url, caption="📷 Inquadra con la fotocamera", width=170)

        st.caption("Sul telefono si aprirà Telegram: tocca semplicemente **[ AVVIA ]** per sincronizzare la sacca.")

        # Pulsante nativo per apertura chat diretta 1-clic su Desktop
        st.link_button(
            f"👉 Apri Chat con @{bot_username}",
            deep_link,
            type="primary",
            use_container_width=True,
            help="Apre Telegram con il comando di collegamento preimpostato"
        )
        if st.button("🔄 Verifica Connessione Smartphone", key="check_tg_link_btn", use_container_width=True, help="Rileva immediatamente il collegamento avvenuto dal cellulare"):
            st.rerun()
        st.markdown(f"""
            <div style="text-align:center; font-size:0.75rem; color:#94A3B8; margin-top:6px; margin-bottom:12px;">
                🤖 Bot: <b>@{bot_username}</b>
            </div>
        """, unsafe_allow_html=True)

    # Guida passo-passo chiara
    with st.expander("ℹ️ Come funziona l'uso in campo e il salvataggio automatico", expanded=False):
        st.markdown(f"""
            <div style="font-size:0.82rem; color:#CBD5E1; line-height:1.6;">
                <b>1. Collega lo smartphone in 2 secondi:</b><br>
                Inquadra il QR Code con la fotocamera del tuo cellulare oppure clicca il pulsante blu su questo PC. Si aprirà Telegram con il bot <b>@{bot_username}</b>: premi semplicemente <b>[ AVVIA ]</b>. Il tuo profilo e la tua sacca da golf sono immediatamente sincronizzati!<br><br>
                <b>2. Durante il gioco sul percorso:</b><br>
                Sul telefono avrai il grande tasto <code>[ 📍 Calcola Distanza & Plays Like ]</code> per avere subito la distanza al green, il dislivello orografico e il bastone consigliato dalla tua sacca. Dopo il colpo puoi inviare una breve nota vocale (es. <i>"Ferro 7 dal fairway, finita a 3 metri dal green"</i>).<br><br>
                <b>3. Salvataggio 100% Automatico sul PC:</b><br>
                Non devi esportare o caricare file a mano: il bot Telegram e questo sito condividono lo stesso database locale. I colpi e le metriche finiscono direttamente nel tuo profilo sul PC!
            </div>
        """, unsafe_allow_html=True)



# ---------------------------------------------------------
# AUDIO & TELEGRAM PIPELINE (REUSABLE FOR SIDEBAR & MAIN DASHBOARD)
# ---------------------------------------------------------
def execute_audio_round_pipeline(
    files_or_paths,
    whisper_engine="Groq Whisper Turbo (Consigliato, Gratuito & Istantaneo)",
    whisper_model_local="base",
    additional_text=""
):
    if user_ai.provider == "openai" and not user_ai.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        st.error("⚠️ Inserisci la tua OpenAI API Key personale nella barra laterale prima di avviare l'analisi.")
        return

    temp_paths = []
    json_texts = []
    try:
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.info("⚙️ Preparazione e caricamento note vocali e dati di testo...")
        progress_bar.progress(15)

        for item in (files_or_paths or []):
            if hasattr(item, "read"):
                fname = getattr(item, "name", "audio.ogg").lower()
                if fname.endswith(".json"):
                    try:
                        raw_bytes = item.read()
                        tg_data = json.loads(raw_bytes.decode("utf-8"))
                        if isinstance(tg_data, dict) and "messages" in tg_data:
                            user_texts = []
                            for m in tg_data["messages"]:
                                # Skip bot responses
                                if m.get("from") == "Voice Caddy Pro" or "bot" in str(m.get("from_id", "")):
                                    continue
                                txt_obj = m.get("text", "")
                                if isinstance(txt_obj, list):
                                    t_parts = []
                                    for p in txt_obj:
                                        if isinstance(p, dict):
                                            t_parts.append(p.get("text", ""))
                                        elif isinstance(p, str):
                                            t_parts.append(p)
                                    m_txt = "".join(t_parts).strip()
                                else:
                                    m_txt = str(txt_obj).strip()
                                d_str = m.get("date", "")
                                if m_txt:
                                    user_texts.append(f"[{d_str}] {m_txt}")
                            if user_texts:
                                json_texts.append("\n".join(user_texts))
                    except Exception:
                        pass
                elif fname.endswith(".html") or fname.endswith(".htm"):
                    try:
                        raw_bytes = item.read()
                        html_content = raw_bytes.decode("utf-8", errors="ignore")
                        import re
                        from html import unescape
                        msg_blocks = re.findall(r'<div class="message default clearfix[^"]*"[^>]*>(.*?)</div>\s*</div>', html_content, re.DOTALL)
                        user_texts = []
                        for block in msg_blocks:
                            from_match = re.search(r'<div class="from_name">\s*(.*?)\s*</div>', block)
                            author = from_match.group(1).strip() if from_match else ""
                            if "Voice Caddy" in author or "bot" in author.lower():
                                continue
                            date_match = re.search(r'<div class="date details" title="([^"]+)"', block)
                            d_str = date_match.group(1) if date_match else ""
                            text_match = re.search(r'<div class="text">\s*(.*?)\s*</div>', block, re.DOTALL)
                            if text_match:
                                clean_t = re.sub(r'<[^>]+>', ' ', text_match.group(1))
                                clean_t = unescape(clean_t).strip()
                                if clean_t:
                                    user_texts.append(f"[{d_str}] {clean_t}" if d_str else clean_t)
                        if user_texts:
                            json_texts.append("\n".join(user_texts))
                    except Exception:
                        pass
                else:
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{fname}")
                    temp_file.write(item.read())
                    temp_file.close()
                    temp_paths.append(temp_file.name)
            elif isinstance(item, (str, Path)) and os.path.exists(str(item)):
                temp_paths.append(str(item))

        # Check if we have anything to process
        has_audio = bool(temp_paths)
        has_text = bool(json_texts or (additional_text and additional_text.strip()))

        if not has_audio and not has_text:
            st.error("⚠️ Nessun file audio o testo valido trovato per l'elaborazione.")
            return

        transcript_parts = []

        if has_audio:
            status_text.info(f"🎙️ Trascrizione speech-to-text in corso ({whisper_engine})...")
            progress_bar.progress(40)

            if "Groq" in whisper_engine:
                engine_mode = "groq"
            elif "Cloud" in whisper_engine or "OpenAI" in whisper_engine:
                engine_mode = "cloud"
            else:
                engine_mode = "local"

            audio_engine = VoiceCaddyAudioEngine(model_size=whisper_model_local)
            whisper_api_key = user_ai.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
            groq_api_key = user_ai.groq_api_key or os.environ.get("GROQ_API_KEY", "")
            if not groq_api_key:
                try:
                    if hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets:
                        groq_api_key = st.secrets["GROQ_API_KEY"]
                except Exception:
                    pass
            if not groq_api_key:
                try:
                    from core.ai_provider import get_default_groq_key
                    groq_api_key = get_default_groq_key()
                except Exception:
                    pass

            if len(temp_paths) == 1:
                t_text, _ = audio_engine.transcribe(
                    temp_paths[0], engine_mode=engine_mode, api_key=whisper_api_key, groq_api_key=groq_api_key
                )
            else:
                t_text, _ = audio_engine.transcribe_multiple(
                    temp_paths, engine_mode=engine_mode, api_key=whisper_api_key, groq_api_key=groq_api_key
                )
            if t_text:
                transcript_parts.append(t_text)

        if json_texts:
            transcript_parts.append("[Messaggi di Testo dalla Chat Telegram]:\n" + "\n\n".join(json_texts))

        if additional_text and additional_text.strip():
            if not has_audio and not json_texts:
                transcript_parts.append(additional_text.strip())
            else:
                transcript_parts.append("[Note e Messaggi Scritti dal Giocatore]:\n" + additional_text.strip())

        transcript_text = "\n\n".join(transcript_parts)
        st.session_state.transcript = transcript_text

        ai_desc = f"Ollama ({user_ai.ollama_model})" if user_ai.provider == "ollama" else (
            f"Groq ({user_ai.groq_model})" if user_ai.provider == "groq" else f"OpenAI ({user_ai.openai_model})"
        )
        status_text.info(f"🧠 Analisi semantica NLU tramite la tua IA ({ai_desc}) per {st.session_state.user_profile.category.value} su {active_course.name}...")
        progress_bar.progress(70)

        import importlib
        import core.parser
        import core.ai_provider
        import core.metrics
        importlib.reload(core.parser)
        importlib.reload(core.ai_provider)
        importlib.reload(core.metrics)

        raw_round_data = core.parser.parse_golf_audio_transcript(
            transcript_text=transcript_text,
            user_profile=st.session_state.user_profile,
            course=active_course,
            ai_config=user_ai
        )

        status_text.info("📊 Riconciliazione matematica e calcolo metriche balistiche...")
        progress_bar.progress(90)

        validated_data = core.metrics.GolfMetricsCalculator.recompute_and_reconcile(raw_round_data)
        st.session_state.round_data = validated_data

        # Save round tagged with current user ID and group
        db.save_round(validated_data, user_id=current_user.user_id, group_name=current_user.group)

        progress_bar.progress(100)
        status_text.success("✅ Partita analizzata e salvata nel tuo archivio personale con successo!")
        st.rerun()

    except AudioProcessingError as ape:
        st.error(f"Errore Audio: {ape}")
    except AIProviderError as aie:
        st.error(f"Errore IA Personale: {aie}")
    except Exception as e:
        st.error(f"Si è verificato un errore durante l'elaborazione: {e}")
    finally:
        for p in temp_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def sync_telegram_data_to_round(user_id: str, chat_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Controlla e scarica note vocali recenti o colpi registrati su Telegram,
    elaborando e salvando il round aggiornato.
    """
    token = tg_manager.get_token()
    resolved_cid = str(chat_id or tg_manager.get_chat_id_for_user(user_id) or "")
    if not resolved_cid and (user_id == "strafatti_stefano_pirani" or "stefano" in str(user_id).lower()):
        resolved_cid = tg_manager.get_admin_chat_id()

    # 1. Verifica aggiornamenti audio in arrivo su Telegram
    if token:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    updates = data.get("result", [])
                    audio_msgs = []
                    max_u_id = 0
                    for u in updates:
                        u_id = u.get("update_id", 0)
                        if u_id > max_u_id:
                            max_u_id = u_id
                        msg = u.get("message", {})
                        c_id = str(msg.get("chat", {}).get("id", ""))
                        if resolved_cid and c_id != resolved_cid:
                            continue
                        if msg.get("voice") or msg.get("audio"):
                            audio_msgs.append(msg)

                    if audio_msgs:
                        downloaded = []
                        for m in audio_msgs:
                            f_obj = m.get("voice") or m.get("audio")
                            f_id = f_obj.get("file_id")
                            if f_id:
                                req_f = urllib.request.Request(f"https://api.telegram.org/bot{token}/getFile?file_id={f_id}")
                                with urllib.request.urlopen(req_f, timeout=8) as r_f:
                                    f_info = json.loads(r_f.read().decode("utf-8"))
                                    if f_info.get("ok"):
                                        fp = f_info["result"]["file_path"]
                                        ext = os.path.splitext(fp)[1] or ".ogg"
                                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                                        tmp_path = tmp.name
                                        tmp.close()
                                        urllib.request.urlretrieve(f"https://api.telegram.org/file/bot{token}/{fp}", tmp_path)
                                        downloaded.append(tmp_path)

                        # Conferma lettura a Telegram
                        if max_u_id > 0:
                            try:
                                urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates?offset={max_u_id + 1}", timeout=5)
                            except Exception:
                                pass

                        if downloaded:
                            execute_audio_round_pipeline(downloaded)
                            return True, f"Scaricati ed elaborati con successo {len(downloaded)} file vocali da Telegram!"
        except Exception:
            pass

    # 2. Verifica sessione live e colpi già memorizzati su database locale
    if resolved_cid:
        scorecard = live_session_mgr.get_round_scorecard(resolved_cid)
        comp_holes = scorecard.get("completed_holes", [])
        if comp_holes:
            try:
                from core.schemas import HoleData, Shot, RoundInfo, GolfRoundData, LieType, ShotResult, ShotIntent
                holes_list = []
                for h in comp_holes:
                    h_num = int(h.get("hole_number", 1))
                    shots_raw = live_session_mgr.get_hole_shots(resolved_cid, h_num)
                    s_list = []
                    for s_idx, s in enumerate(shots_raw, 1):
                        lie_str = str(s.get("lie", "fairway")).lower()
                        try:
                            lie_val = LieType(lie_str)
                        except Exception:
                            lie_val = LieType.FAIRWAY

                        dist_cov = s.get("distance_covered")
                        raw_d = s.get("raw_distance_to_green")
                        pl_d = s.get("plays_like_distance")
                        elev_d = s.get("elevation_diff")

                        s_list.append(Shot(
                            shot_index=s_idx,
                            club=s.get("club") or "Bastone",
                            lie=lie_val,
                            result=ShotResult.GOOD,
                            intent=ShotIntent.FULL_SHOT,
                            distance_meters=float(dist_cov) if dist_cov is not None else None,
                            raw_distance=float(raw_d) if raw_d is not None else None,
                            plays_like_distance=float(pl_d) if pl_d is not None else None,
                            elevation_diff=float(elev_d) if elev_d is not None else None,
                            notes=s.get("notes") or ""
                        ))

                    h_par = int(h.get("par", 4))
                    h_score = int(h.get("gross_strokes") or h.get("score") or 4)
                    h_putts = int(h.get("putts", 2))
                    shots_to_green = h_score - h_putts
                    calc_gir = (shots_to_green <= (h_par - 2)) if h_score >= h_putts else False

                    holes_list.append(HoleData(
                        hole_number=h_num,
                        par=h_par,
                        score=h_score,
                        putts=h_putts,
                        gir=calc_gir,
                        fairway_hit=None if h_par == 3 else True,
                        received_strokes=int(h.get("received_strokes") or 0),
                        stroke_index=int(h.get("stroke_index")) if h.get("stroke_index") is not None else None,
                        shots=s_list
                    ))

                user_prof = st.session_state.get("user_profile")
                hcp_val = getattr(user_prof, "handicap", 23.9) if user_prof else 23.9
                p_name = "Stefano Pirani"
                if hasattr(current_user, "first_name") and hasattr(current_user, "last_name"):
                    p_name = f"{current_user.first_name} {current_user.last_name}"

                raw_round = GolfRoundData(
                    round_info=RoundInfo(
                        date=datetime.now().strftime("%d %B %Y"),
                        course_name=active_course.name,
                        holes_played=len(holes_list),
                        game_format="stableford",
                        player_name=p_name,
                        exact_hcp=hcp_val,
                        playing_hcp=int(round(hcp_val)),
                        category="Singolo Stableford"
                    ),
                    holes=holes_list
                )
                validated = GolfMetricsCalculator.recompute_and_reconcile(raw_round)
                st.session_state.round_data = validated
                db.save_round(validated, user_id=current_user.user_id, group_name=current_user.group)
                return True, f"Sincronizzate {len(holes_list)} buche registrate in campo dal Bot Telegram con successo!"
            except Exception as e_sync:
                return False, f"Errore durante l'elaborazione dei colpi della sessione live: {e_sync}"


    return False, (
        f"🟢 Smartphone associato con successo a @{tg_manager.get_bot_username()} (Chat ID: `{resolved_cid}`)!\n\n"
        "ℹ️ Al momento non sono presenti nuovi file audio in arrivo sui server Telegram (le note vocali restano sul server Telegram per 24h se non inviate di recente).\n\n"
        "👉 **Cosa fare adesso per elaborare la gara di ieri:**\n"
        "• **Se hai le note vocali salvate sul computer o telefono:** trascinale direttamente nel riquadro verde a fianco *(Opzione 2)* e premi **[ 🚀 TRASCRIVI ED ELABORA LA GARA ORA ]**!\n"
        "• **Oppure inoltra/invia ora** gli audio della gara nella chat di **@VoiceCaddyGolf_bot** su Telegram, poi torna qui e riclicca questo pulsante!"
    )


if process_btn and uploaded_files:
    execute_audio_round_pipeline(uploaded_files, whisper_engine=whisper_engine, whisper_model_local=whisper_model_local)


# =========================================================
# HELPER FUNCTIONS FOR RENDERING
# =========================================================
def render_scorecard_table(holes_data: list):
    matrix = GolfMetricsCalculator.get_scorecard_matrix(holes_data)
    df = pd.DataFrame(matrix)

    def color_status(val):
        colors = {
            "Eagle or Better": "background-color: #1b4d3e; color: #ffffff; font-weight: bold;",
            "Birdie": "background-color: #27ae60; color: #ffffff; font-weight: bold;",
            "Par": "background-color: #2c3e50; color: #ffffff;",
            "Bogey": "background-color: #d35400; color: #ffffff;",
            "Double+ Bogey": "background-color: #c0392b; color: #ffffff; font-weight: bold;"
        }
        return colors.get(val, "")

    styled_df = df.style.map(color_status, subset=["Status"]) if hasattr(df.style, "map") else df.style.applymap(color_status, subset=["Status"])
    st.dataframe(styled_df, use_container_width=True, hide_index=True)


def render_strokes_lost_radar(strokes_lost):
    categories = ["Dal Tee (Driver)", "Approcci (>50m)", "Gioco Corto (<50m)", "Putting", "Penalità"]
    values = [
        strokes_lost.tee_shots,
        strokes_lost.approach_shots,
        strokes_lost.short_game_around_green,
        strokes_lost.putting,
        strokes_lost.penalties
    ]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values + [values[0]],
        theta=categories + [categories[0]],
        fill='toself',
        fillcolor='rgba(231, 76, 60, 0.3)',
        line=dict(color='#E74C3C', width=2)
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, max(values + [1]) + 0.5])),
        showlegend=False,
        margin=dict(l=40, r=40, t=30, b=30),
        height=320,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    st.plotly_chart(fig, use_container_width=True)


# =========================================================
# MAIN DASHBOARD TABS
# =========================================================
tab_titles = [
    "📊 Live Dashboard & Diagnosi PGA",
    "💬 Chat con il Caddie",
    "📍 Pin Position & Plays Like GPS",
    "🏌️‍♂️ Profilo Personale & Sacca Mazze",
    "📈 Storico Partite & Trend",
    "🎯 Benchmark & Strokes Gained",
    "🎓 Rules Academy"
]
if current_user.is_admin:
    unread_admin_cnt = inbox_mgr.get_unread_count()
    admin_badge = f" ({unread_admin_cnt} nuovi)" if unread_admin_cnt > 0 else ""
    tab_titles.append(f"👑 Amministrazione & Utenti{admin_badge}")

all_tabs = st.tabs(tab_titles)
nav_tab1 = all_tabs[0]
nav_chat = all_tabs[1]
nav_pin_gps = all_tabs[2]
nav_tab2 = all_tabs[3]
nav_tab3 = all_tabs[4]
nav_tab4 = all_tabs[5]
nav_rules = all_tabs[6]
nav_admin = all_tabs[7] if current_user.is_admin else None


# ---------------------------------------------------------
# TAB 1: LIVE DASHBOARD & PGA DIAGNOSIS
# ---------------------------------------------------------
with nav_tab1:
    # ---------------------------------------------------------
    # ANTEPRIMA & SHOWCASE: I 4 CAMPI, VISTE TATTICHE & REPORT PDF
    # ---------------------------------------------------------
    show_showcase_default = st.session_state.get("show_4courses_showcase", False)
    with st.expander("🌟 ANTEPRIMA COMPLETA: I 4 Campi, Viste Tattiche & Report WhatsApp/Telegram", expanded=show_showcase_default):
        st.markdown("""
            <div style="background: linear-gradient(135deg, #0b1320 0%, #15253b 50%, #0c1626 100%);
                        border: 2px solid #38BDF8; border-radius: 12px; padding: 18px 22px; margin-bottom: 20px;">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
                    <div>
                        <span style="font-size: 1.3rem; font-weight: 800; color: #FFFFFF;">
                            🏌️‍♂️ PANORAMICA DEL PROGRAMMA SUI 4 CAMPI UFFICIALI
                        </span>
                        <div style="font-size: 0.88rem; color: #94A3B8; margin-top: 4px;">
                            Voice Caddy Pro unifica l'esperienza di gioco su tutti i percorsi: raccoglie i colpi da Telegram,
                            proietta le <b>3 Viste Tattiche Balistiche</b> (Mappa Satellitare, Dispersione Trackman e Green Radar),
                            applica il <b>Metodo del Maestro PGA</b> ed esporta il <b>Report PDF pronto per WhatsApp e Telegram</b>.
                        </div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # 1. I 4 CAMPI ATTIVI
        st.markdown("#### ⛳ I 4 Campi del Circuito Attualmente Attivi")
        c_cols = st.columns(4)
        c_data = [
            ("Conero Golf Club", "Sirolo (AN)", "18 Buche / Par 71", "Bianchi, Gialli, Verdi, Rossi", "Collinare tecnico con pendenze orografiche e dislivelli."),
            ("Torrenova Golf", "P. Potenza Picena (MC)", "9 Buche / Par 34", "Gialli, Rossi", "Pianeggiante veloce, ideale per scoring e precisione."),
            ("Golf Club Perugia", "Santa Sabina (PG)", "18 Buche / Par 72", "Gialli, Rossi", "Storico collinare del 1959 con fairway alberati e green mossi."),
            ("Riviera Golf Cattolica", "S. Giovanni Marignano (RN)", "18 Buche / Par 70", "Bianchi, Gialli, Rossi", "Championship resort Graham Cooke lungo il fiume Ventena.")
        ]
        for idx, (c_n, c_loc, c_par, c_tees, c_desc) in enumerate(c_data):
            with c_cols[idx]:
                st.markdown(f"""
                    <div style="background:#131d2a; border:1px solid #334155; border-radius:8px; padding:12px; height:180px;">
                        <span style="color:#38BDF8; font-weight:bold; font-size:0.95rem;">{c_n}</span><br>
                        <span style="color:#94A3B8; font-size:0.8rem;">📍 {c_loc}</span><br>
                        <span style="color:#2ECC71; font-weight:bold; font-size:0.85rem;">{c_par}</span><br>
                        <span style="color:#CBD5E1; font-size:0.75rem;"><b>Tee:</b> {c_tees}</span><br>
                        <p style="color:#94A3B8; font-size:0.75rem; margin-top:6px; line-height:1.3;"><i>{c_desc}</i></p>
                    </div>
                """, unsafe_allow_html=True)

        st.markdown("---")

        # 2. SIMULATORE TATTICO BUCA-TIPO
        st.markdown("#### 🎯 Simulazione Dinamica Buca-Tipo & Viste Tattiche")
        sim_course_choice = st.selectbox(
            "Seleziona il campo per simulare la visualizzazione buca:",
            options=["Conero Golf Club", "Torrenova Golf", "Golf Club Perugia", "Riviera Golf Cattolica"],
            key="sim_course_select"
        )

        sim_col_l, sim_col_r = st.columns([1.2, 1])
        with sim_col_l:
            st.markdown(f"""
                <div style="background:#0f172a; border-left:4px solid #10B981; border-radius:8px; padding:12px; margin-bottom:12px;">
                    <span style="color:#34D399; font-weight:bold;">🎙️ Sequenza Vocale Telegram (Esempio Reale):</span><br>
                    <span style="color:#E2E8F0; font-size:0.88rem; font-style:italic;">
                        "Buca 1 a {sim_course_choice}: drive lungo in centro fairway a 220 metri, secondo colpo ferro 7 a 6 metri dalla bandiera, primo putt di avvicinamento a 40 centimetri e tap-in per il Par."
                    </span>
                </div>
            """, unsafe_allow_html=True)

            # Mostra le viste tattiche per la buca simulata
            sim_agent = HoleStrategyAgent()
            sim_h = st.session_state.round_data.holes[0] if st.session_state.round_data else None
            # Crea geometria buca basata sul campo selezionato
            c_obj = next((c for c in all_courses if c.name == sim_course_choice), active_course)
            c_h1 = c_obj.get_hole(1) if hasattr(c_obj, "get_hole") else None
            h_coords = getattr(c_h1, "coordinates", None) if c_h1 else None

            if h_coords:
                sim_geom = HoleGeometry(
                    course_id=c_obj.course_id,
                    hole_number=1,
                    par=getattr(c_h1, "par", 4),
                    length_m=float(getattr(c_h1, "distance_meters", 350)),
                    stroke_index=int(getattr(c_h1, "handicap_index", 1) or 1),
                    tee=GeoPoint(lat=h_coords.tee_lat, lon=h_coords.tee_lon, alt_m=h_coords.tee_altitude),
                    green_center=GeoPoint(lat=h_coords.target_lat, lon=h_coords.target_lon, alt_m=h_coords.target_altitude)
                )
            else:
                sim_geom = None

            sim_view_mode = st.radio(
                "Modalità Vista Tattica:",
                options=["🗺️ Vista A (Mappa Satellitare)", "📊 Vista B (Dispersione Trackman)", "🎯 Vista C (Green Radar)"],
                horizontal=True,
                key="sim_view_mode_radio"
            )

            if sim_geom and sim_h:
                perf_eval = sim_agent.evaluate_played_hole(sim_geom, sim_h.shots, user_handicap=st.session_state.user_profile.handicap, score=sim_h.score, putts=sim_h.putts)
                if sim_view_mode == "🗺️ Vista A (Mappa Satellitare)":
                    html_code = render_view_a_map_html(sim_geom, perf_eval=perf_eval, height="380px")
                    components.html(html_code, height=400)
                elif sim_view_mode == "📊 Vista B (Dispersione Trackman)":
                    html_code = render_view_b_benchmark_html(perf_eval=perf_eval)
                    st.markdown(html_code, unsafe_allow_html=True)
                else:
                    html_code = render_view_c_green_radar_html(sim_geom, app_eval=perf_eval.green_evaluation, height="380px")
                    components.html(html_code, height=400)

        with sim_col_r:
            st.markdown(f"""
                <div style="background:#0f172a; border-left:4px solid #38BDF8; border-radius:8px; padding:12px; margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                        <span style="color:#38BDF8; font-weight:bold; font-size:0.95rem;">👨‍🏫 Analisi del Maestro PGA (Regola Aurea)</span>
                        <span style="background:#0369A1; color:#E0F2FE; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;">Voto Buca: 9.0/10</span>
                    </div>
                    <div style="font-size:0.85rem; color:#CBD5E1; margin-bottom:4px;">
                        <b>1. Sintesi:</b> Buca condotta con regolarità ed eccellente tenuta tattica, senza sbavature dal tee al green.<br>
                        <b>2. Colpo chiave:</b> L'approccio con Ferro 7: ha centrato la superficie lasciando un comodo putt per il par.<br>
                        <b>3. Valutazione tecnica:</b> Contatto solido e traiettoria controllata in asse (+2m scostamento dal centro).<br>
                        <b>4. Valutazione strategica:</b> Scelta del bastone e orientamento del bersaglio perfettamente coerenti con l'HCP.<br>
                        <b>5. Consiglio del Maestro:</b> <i>"Ottima esecuzione. Mantieni questa routine e lavora sul primo putt per attaccare il birdie."</i>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # Scorecard sintetica
            st.markdown("<b>Scorecard Ufficiale (Regola 21.1):</b>", unsafe_allow_html=True)
            sc_demo_df = pd.DataFrame([
                {"Buca": 1, "Par": 4, "SI": 5, "HCP": "+1", "Lordo": 4, "Netto": 3, "Stb. Lordo": "2 pt", "Stb. Netto": "3 pt", "FIR": "Sì", "GIR": "Sì", "Putts": 2}
            ])
            st.dataframe(sc_demo_df, use_container_width=True, hide_index=True)

        st.markdown("---")

        # 3. ESPORTAZIONE E INVIO REPORT PDF (WHATSAPP & TELEGRAM)
        st.markdown("#### 📄 Esportazione Report PDF Ufficiale (Condivisione WhatsApp & Telegram)")
        st.caption("Il report PDF compatto sintetizza l'intero giro, la scorecard lordo/netto, l'analisi del maestro e i drill prescritti in un formato grafico ad alta risoluzione, perfetto da visualizzare su smartphone.")

        pdf_bytes = None
        try:
            pdf_bytes = generate_showcase_mobile_pdf(
                round_data=st.session_state.round_data,
                player_name=f"{current_user.first_name} {current_user.last_name}",
                handicap=float(st.session_state.user_profile.handicap),
                active_course_id=active_course.course_id
            )
        except Exception as e:
            print(f"[PDF ERROR] Errore generazione showcase PDF: {e}")
            st.warning(f"⚠️ Impossibile generare l'anteprima PDF: {e}")

        if pdf_bytes:
            col_pdf1, col_pdf2 = st.columns(2)
            with col_pdf1:
                st.download_button(
                    label="📥 Scarica Report PDF (per WhatsApp & Stampa)",
                    data=pdf_bytes,
                    file_name=f"Voice_Caddy_Report_{current_user.last_name}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary"
                )

            with col_pdf2:
                linked_cid = tg_manager.get_chat_id_for_user(current_user.user_id, current_user.first_name)
                if not linked_cid and (current_user.user_id == "strafatti_stefano_pirani" or getattr(current_user, "is_admin", False)):
                    linked_cid = tg_manager.get_admin_chat_id()

                if st.button("📲 Invia Report PDF su Telegram al mio Bot", use_container_width=True):
                    if not linked_cid:
                        st.warning("⚠️ Non hai ancora collegato la tua chat Telegram. Premi 'Collega Telegram' nella barra laterale o avvia @VoiceCaddyGolf_bot.")
                    else:
                        with st.spinner("Invio del documento PDF su Telegram in corso..."):
                            ok_tg, msg_tg = send_pdf_report_via_telegram(
                                pdf_bytes=pdf_bytes,
                                chat_id=linked_cid,
                                caption=f"🏌️‍♂️ <b>Report Ufficiale Voice Caddy Pro</b>\nGiocatore: {current_user.first_name} {current_user.last_name} (HCP {st.session_state.user_profile.handicap})\nCampo: {active_course.name}",
                                filename=f"Report_{active_course.course_id}.pdf"
                            )
                            if ok_tg:
                                st.success(f"✅ {msg_tg}")
                            else:
                                st.error(f"❌ {msg_tg}")

    # ---------------------------------------------------------
    # CONTATTA L'AMMINISTRATORE & CASELLA DI POSTA (INBOX)
    # ---------------------------------------------------------
    unread_admin_cnt = inbox_mgr.get_unread_count() if current_user.is_admin else 0
    inbox_badge = f" 🔴 ({unread_admin_cnt} nuovi messaggi)" if unread_admin_cnt > 0 else ""
    with st.expander(f"📬 CONTATTA L'AMMINISTRATORE & CASELLA DI POSTA (INBOX){inbox_badge}", expanded=(unread_admin_cnt > 0)):
        render_contact_and_inbox(current_user, inbox_mgr, key_suffix="home")

    # ---------------------------------------------------------
    # HERO ACTION HUB: SCARICA ED ELABORA GARA DI IERI (TELEGRAM / AUDIO)
    # ---------------------------------------------------------
    if "show_sync_panel" not in st.session_state:
        st.session_state.show_sync_panel = True

    if st.session_state.show_sync_panel:
        st.markdown("""
            <div style="background: linear-gradient(135deg, #0f1e16 0%, #162a20 50%, #0c1824 100%);
                        border: 2px solid #2ECC71; border-radius: 14px; padding: 22px 26px;
                        margin-bottom: 24px; box-shadow: 0 10px 30px rgba(46, 204, 113, 0.25);">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; margin-bottom: 14px;">
                    <div style="display:flex; align-items:center; gap: 12px;">
                        <span style="font-size: 2rem;">📥</span>
                        <div>
                            <span style="font-size: 1.3rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.3px;">
                                SCARICA & ELABORA LA GARA DI IERI / ALLENAMENTO
                            </span>
                            <div style="font-size: 0.9rem; color: #A0AEC0; margin-top: 3px;">
                                Trasferisci e processa le note vocali e i colpi da Telegram, oppure trascina qui i file audio registrati.
                            </div>
                        </div>
                    </div>
                    <span style="background: rgba(46, 204, 113, 0.2); border: 1px solid #2ECC71; color: #2ECC71;
                                 padding: 5px 14px; border-radius: 20px; font-size: 0.85rem; font-weight: 700;">
                        ⚡ AZIONE RAPIDA 1-CLIC
                    </span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        col_sync_tg, col_sync_files = st.columns([1, 1], gap="large")

        with col_sync_tg:
            st.markdown("""
                <div style="background: #131d2a; border: 1px solid #38BDF8; border-radius: 10px; padding: 16px; margin-bottom: 12px;">
                    <div style="display:flex; align-items:center; gap: 8px; margin-bottom: 6px;">
                        <span style="font-size: 1.3rem;">📲</span>
                        <span style="font-weight: bold; font-size: 1.05rem; color: #38BDF8;">OPZIONE 1: Da Bot Telegram</span>
                    </div>
                    <p style="font-size: 0.85rem; color: #CBD5E1; line-height: 1.5; margin-bottom: 4px;">
                        Se durante o dopo la gara hai inviato note vocali o registrato colpi al bot Telegram <b>@VoiceCaddyGolf_bot</b>, clicca il pulsante qui sotto per scaricarli e processarli subito.
                    </p>
                </div>
            """, unsafe_allow_html=True)

            linked_cid = tg_manager.get_chat_id_for_user(current_user.user_id, current_user.first_name)
            if not linked_cid and (current_user.user_id == "strafatti_stefano_pirani" or getattr(current_user, "is_admin", False)):
                linked_cid = tg_manager.get_admin_chat_id()
            bot_uname = tg_manager.get_bot_username() or "VoiceCaddyGolf_bot"

            if linked_cid:
                st.caption(f"🟢 Collegato: **@{bot_uname}** (Chat ID: `{linked_cid}`)")
            else:
                st.caption(f"⚠️ Smartphone non ancora associato a @{bot_uname}")

            if st.button("🔄 Scarica ed Elabora Ultimi Dati da Telegram", key="btn_sync_tg_hero", type="primary", use_container_width=True):
                with st.spinner("Connessione a Telegram e controllo aggiornamenti in corso..."):
                    ok_sync, msg_sync = sync_telegram_data_to_round(current_user.user_id, linked_cid)
                    if ok_sync:
                        st.success(msg_sync)
                        st.rerun()
                    else:
                        st.warning(msg_sync)

            deep_link_hero = f"https://t.me/{bot_uname}"
            st.link_button("👉 Apri Chat con @VoiceCaddyGolf_bot su Telegram", deep_link_hero, use_container_width=True)

            st.markdown("<div style='margin-top: 14px; margin-bottom: 6px; font-weight: bold; color: #38BDF8; font-size: 0.88rem;'>☁️ Oppure Recupera Gara Archiviata in Cloud per Data:</div>", unsafe_allow_html=True)

            if not hasattr(db, "get_telegram_archived_dates"):
                import importlib
                import core.db
                importlib.reload(core.db)
                db = core.db.DatabaseManager()

            archived_dates = db.get_telegram_archived_dates(chat_id=linked_cid, user_id=current_user.user_id) if hasattr(db, "get_telegram_archived_dates") else []
            date_options = [d["round_date"] for d in archived_dates]

            from datetime import date, timedelta
            default_d = date.today() - timedelta(days=1)

            col_date, col_btn = st.columns([1.1, 1], gap="small")
            with col_date:
                if date_options:
                    selected_date = st.selectbox(
                        "Data del Giro:",
                        options=date_options,
                        format_func=lambda d: f"{d} ({next((x['total_count'] for x in archived_dates if x['round_date'] == d), 0)} note)",
                        key="sb_archive_date"
                    )
                else:
                    selected_date = str(st.date_input("Data del Giro:", value=default_d, key="di_archive_date"))

            with col_btn:
                st.write("")  # alignment spacing
                if st.button("🚀 Elabora da Cloud", key="btn_elabora_data_cloud", type="secondary", use_container_width=True):
                    with st.spinner(f"Recupero ed elaborazione cronologica dati del {selected_date} dal Cloud..."):
                        if not hasattr(db, "get_telegram_messages_for_date"):
                            import importlib
                            import core.db
                            importlib.reload(core.db)
                            db = core.db.DatabaseManager()

                        msgs = db.get_telegram_messages_for_date(selected_date, chat_id=linked_cid, user_id=current_user.user_id) if hasattr(db, "get_telegram_messages_for_date") else []
                        if msgs:
                            # Ordina rigorosamente in sequenza cronologica
                            msgs = sorted(msgs, key=lambda m: (m.get("timestamp") or "", m.get("id") or 0))

                            whisper_choice = st.session_state.get("hero_whisper_choice", "Groq Whisper Turbo (Consigliato, Gratuito & Istantaneo)")
                            engine_mode = "groq" if "Groq" in whisper_choice else ("cloud" if "Cloud" in whisper_choice or "OpenAI" in whisper_choice else "local")
                            audio_engine = VoiceCaddyAudioEngine(model_size="base")
                            whisper_api_key = user_ai.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
                            groq_api_key = user_ai.groq_api_key or os.environ.get("GROQ_API_KEY", "")
                            if not groq_api_key:
                                try:
                                    from core.ai_provider import get_default_groq_key
                                    groq_api_key = get_default_groq_key()
                                except Exception:
                                    pass

                            timeline_lines = []
                            for m in msgs:
                                m_type = m.get("message_type", "text")
                                f_path = m.get("file_path")
                                c_text = m.get("content_text")
                                ts_short = m.get("timestamp", "")[11:16]
                                is_audio_msg = m_type in ("voice", "audio", "video_note") or bool(f_path)
                                is_dummy_name = bool(c_text and any(c_text.strip().lower().endswith(ext) for ext in ('.ogg', '.mp3', '.wav', '.m4a', '.opus', '.aac', '.3gp', '.amr')))
                                needs_transcription = is_audio_msg and (not c_text or is_dummy_name)

                                if needs_transcription and f_path:
                                    full_p = Path(f_path) if os.path.isabs(f_path) else (PROJECT_ROOT / f_path)
                                    if full_p.exists():
                                        try:
                                            t_text, _ = audio_engine.transcribe(
                                                full_p, engine_mode=engine_mode, api_key=whisper_api_key, groq_api_key=groq_api_key
                                            )
                                            if t_text:
                                                c_text = t_text
                                                m["content_text"] = t_text
                                                if hasattr(db, "update_telegram_message_text") and m.get("id"):
                                                    db.update_telegram_message_text(m["id"], t_text)
                                        except Exception as tx_err:
                                            logger.warning(f"Errore trascrizione audio {f_path}: {tx_err}")

                                if c_text and not any(c_text.strip().lower().endswith(ext) for ext in ('.ogg', '.mp3', '.wav', '.m4a', '.opus', '.aac', '.3gp', '.amr')):
                                    line = f"[{ts_short}] {c_text.strip()}" if ts_short else c_text.strip()
                                    timeline_lines.append(line)

                            unified_transcript = "\n".join(timeline_lines)
                            if unified_transcript.strip():
                                execute_audio_round_pipeline(
                                    [],
                                    whisper_engine=whisper_choice,
                                    additional_text=unified_transcript
                                )
                            else:
                                st.warning("Nessun contenuto testuale o vocale valido trovato per questa data.")
                        else:
                            st.info(f"Nessun dato registrato in cloud per la data {selected_date}. Se hai salvato il file sul PC, usa l'Opzione 2 a fianco!")

            with st.expander("ℹ️ Come inviare gli audio di ieri tramite Telegram", expanded=False):
                st.markdown(f"""
                    <div style="font-size:0.82rem; color:#CBD5E1; line-height:1.5;">
                        <b>1.</b> Apri Telegram sul cellulare o PC e cerca <b>@{bot_uname}</b>.<br>
                        <b>2.</b> Inoltra o invia le note vocali della gara direttamente al bot.<br>
                        <b>3.</b> Torna qui e premi <b>[ 🔄 Scarica ed Elabora Ultimi Dati da Telegram ]</b>: il sistema li trascriverà e calcolerà all'istante la scorecard e tutte le statistiche PGA!
                    </div>
                """, unsafe_allow_html=True)

        with col_sync_files:
            st.markdown("""
                <div style="background: #112217; border: 1px solid #2ECC71; border-radius: 10px; padding: 16px; margin-bottom: 12px;">
                    <div style="display:flex; align-items:center; gap: 8px; margin-bottom: 6px;">
                        <span style="font-size: 1.3rem;">🎙️</span>
                        <span style="font-weight: bold; font-size: 1.05rem; color: #2ECC71;">OPZIONE 2: Trascina o Carica File Audio</span>
                    </div>
                    <p style="font-size: 0.85rem; color: #CBD5E1; line-height: 1.5; margin-bottom: 4px;">
                        Hai i file audio salvati sul PC o scaricati da Telegram? Selezionali o trascinali direttamente qui:
                    </p>
                </div>
            """, unsafe_allow_html=True)

            hero_uploaded_files = st.file_uploader(
                "File audio (.m4a, .mp3, .wav, .opus, .ogg) o esportazione Telegram (result.json, messages.html)",
                type=["m4a", "mp3", "wav", "aac", "opus", "ogg", "3gp", "amr", "json", "html", "htm"],
                accept_multiple_files=True,
                key="hero_uploader_files_box"
            )

            hero_text_notes = st.text_area(
                "📝 Note o Messaggi di Testo della Gara (Opzionale):",
                placeholder="Hai scritto alcune buche o colpi come messaggi di testo in chat? Incollali qui...",
                help="Se durante il giro hai alternato vocali e messaggi di testo scritti, incolla qui il testo. Verrà unito in automatico alle note vocali per un'analisi completa a 18 buche!",
                height=90,
                key="hero_text_notes_area"
            )

            hero_whisper = st.radio(
                "Motore Whisper Trascrizione:",
                options=["Groq Whisper Turbo (Consigliato, Gratuito & Istantaneo)", "OpenAI Whisper Cloud (Usa tua API Key)", "Faster-Whisper Locale"],
                index=0,
                key="hero_whisper_choice",
                horizontal=False
            )

            can_process = bool(hero_uploaded_files or (hero_text_notes and hero_text_notes.strip()))

            if st.button("🚀 TRASCRIVI ED ELABORA LA GARA ORA", key="btn_hero_process_audio", type="primary", use_container_width=True, disabled=not can_process):
                execute_audio_round_pipeline(
                    hero_uploaded_files or [],
                    whisper_engine=hero_whisper,
                    whisper_model_local="base",
                    additional_text=hero_text_notes.strip() if hero_text_notes else ""
                )

            with st.expander("💡 Come gestire audio + messaggi scritti o esportazione Telegram", expanded=False):
                st.markdown("""
                    <div style="font-size:0.82rem; color:#CBD5E1; line-height:1.5;">
                        <b>• Se hai vocali e messaggi di testo:</b> trascina i file vocali nel riquadro sopra e fai <i>Copia & Incolla</i> dei messaggi di testo nel box «Note o Messaggi di Testo». Il sistema unirà tutto in automatico!<br>
                        <b>• Se hai esportato la chat da Telegram Desktop:</b> puoi trascinare direttamente il file <code>result.json</code> nel riquadro: Voice Caddy estrarrà i tuoi messaggi e li elaborerà all'istante!<br>
                        <b>• Per salvare i singoli vocali da Telegram:</b> tasto destro sul vocale ➔ «Salva con nome...» ➔ trascinalo qui.
                    </div>
                """, unsafe_allow_html=True)

        st.markdown("---")

    data = st.session_state.round_data

    if data:
        summary = data.performance_summary
        diag = summary.professional_diagnosis

        rel_par = GolfMetricsCalculator.calculate_score_relation_to_par(data.holes)
        rel_par_str = f"+{rel_par}" if rel_par > 0 else ("Par" if rel_par == 0 else f"{rel_par}")

        r_info = data.round_info
        c_name = getattr(r_info, "course_name", None) or active_course.name
        h_played = getattr(r_info, "holes_played", len(data.holes) if data.holes else 18)
        r_date = getattr(r_info, "date", None) or "Oggi"

        col_head, col_sync_btn, col_btn = st.columns([2.6, 1.4, 1.0])
        with col_head:
            st.title(f"⛳ {c_name}")
            cat_val = st.session_state.user_profile.category.value
            cat_badge = f"🎭 Tono IA: {cat_val}"
            st.caption(f"Giocatore: **{st.session_state.user_profile.player_name}** • Partita di {h_played} Buche • Data: {r_date} • {cat_badge}")

        with col_sync_btn:
            lbl_toggle = "🔼 Nascondi Pannello Sync" if st.session_state.show_sync_panel else "📥 Sincronizza Gara di Ieri"
            if st.button(lbl_toggle, key="toggle_sync_btn_hdr", use_container_width=True, help="Mostra o nasconde il pannello di sincronizzazione con Telegram e caricamento audio"):
                st.session_state.show_sync_panel = not st.session_state.show_sync_panel
                st.rerun()

        with col_btn:
            html_rep = PDFReportGenerator.generate_html_report(data)
            st.download_button(
                label="📥 Scarica Report PDF / HTML",
                data=html_rep,
                file_name=f"VoiceCaddy_{current_user.first_name}_{r_date}.html",
                mime="text/html",
                use_container_width=True
            )

        # Top KPI Metrics Cards (Lordo, Netto, Stableford WHS)
        g_format = getattr(r_info, "game_format", None) or "stableford"
        is_stbl = "stableford" in g_format.lower()
        kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
        stbl_net = getattr(summary, "total_stableford_points", None)
        stbl_gross = getattr(summary, "total_stableford_gross_points", None)
        sc_net = getattr(summary, "total_score_net", None)

        if is_stbl:
            kpi1.metric("Stableford Netto", f"{stbl_net or 0} pt", f"{stbl_gross or 0} pt Lordo")
            kpi2.metric("Colpi Lordi / Netti", f"{summary.total_score} L / {sc_net or summary.total_score} N", f"Rel. Par {rel_par_str}")
        else:
            kpi1.metric("Colpi Lordi", f"{summary.total_score} ({rel_par_str})")
            kpi2.metric("Colpi Netti", f"{sc_net or summary.total_score}")

        phcp = getattr(r_info, "playing_hcp", None)
        ehcp = getattr(r_info, "exact_hcp", None)
        phcp_display = f"{phcp}" if phcp is not None else "-"
        ehcp_display = f"{ehcp}" if ehcp is not None else str(st.session_state.user_profile.handicap)
        kpi3.metric("Playing HCP", f"{phcp_display} colpi", f"Exact: {ehcp_display}")
        kpi4.metric("Fairway Presi (FIR)", f"{summary.fairway_accuracy_pct}%")
        kpi5.metric("Green in Reg. (GIR)", f"{summary.gir_pct}%")
        kpi6.metric("Course Mgmt", f"{diag.course_management_score}/100")

        st.markdown("---")

        # Valutazione del Maestro (Regola Aurea & coach_analysis_rules.md)
        c_rep = getattr(summary, "coach_report", None)
        if c_rep:
            sc = c_rep.get("technical_scores", {})
            cat_str = c_rep.get("player_category", "seconda").title()
            st.markdown(f"""
                <div style="background: linear-gradient(135deg, #131b2a 0%, #17263c 100%); border: 1px solid #3B82F6; border-radius: 10px; padding: 14px 18px; margin-top: 10px; margin-bottom: 15px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; margin-bottom:10px;">
                        <span style="font-size:1.1rem; font-weight:bold; color:#60A5FA;">🏌️ Metodo del Maestro: Valutazione Tecnica ({cat_str} Categoria)</span>
                        <span style="background:#1E3A8A; color:#93C5FD; padding:4px 12px; border-radius:15px; font-weight:bold; font-size:0.95rem;">Voto Globale: {sc.get('overall', '-')}/10</span>
                    </div>
                    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:10px; text-align:center;">
                        <div style="background:#0F172A; border:1px solid #1E293B; border-radius:8px; padding:8px;">
                            <span style="font-size:0.75rem; color:#94A3B8; text-transform:uppercase;">Tee Game</span><br>
                            <span style="font-size:1.15rem; font-weight:bold; color:#38BDF8;">{sc.get('tee_game', '-')}/10</span>
                        </div>
                        <div style="background:#0F172A; border:1px solid #1E293B; border-radius:8px; padding:8px;">
                            <span style="font-size:0.75rem; color:#94A3B8; text-transform:uppercase;">Approcci</span><br>
                            <span style="font-size:1.15rem; font-weight:bold; color:#34D399;">{sc.get('approach_game', '-')}/10</span>
                        </div>
                        <div style="background:#0F172A; border:1px solid #1E293B; border-radius:8px; padding:8px;">
                            <span style="font-size:0.75rem; color:#94A3B8; text-transform:uppercase;">Gioco Corto</span><br>
                            <span style="font-size:1.15rem; font-weight:bold; color:#FBBF24;">{sc.get('short_game', '-')}/10</span>
                        </div>
                        <div style="background:#0F172A; border:1px solid #1E293B; border-radius:8px; padding:8px;">
                            <span style="font-size:0.75rem; color:#94A3B8; text-transform:uppercase;">Putting</span><br>
                            <span style="font-size:1.15rem; font-weight:bold; color:#A78BFA;">{sc.get('putting', '-')}/10</span>
                        </div>
                        <div style="background:#0F172A; border:1px solid #1E293B; border-radius:8px; padding:8px;">
                            <span style="font-size:0.75rem; color:#94A3B8; text-transform:uppercase;">Strategia</span><br>
                            <span style="font-size:1.15rem; font-weight:bold; color:#2DD4BF;">{sc.get('strategy', '-')}/10</span>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        # PGA Coach Executive Diagnosis Box
        st.markdown(f"""
            <div class="diag-card">
                <h3 style="margin-top:0; color:#2ECC71;">🧠 Diagnosi Strategica del Caddie PGA</h3>
                <p style="font-size: 1.05rem; line-height: 1.6;">{diag.executive_narrative}</p>
                <hr style="border-color:#2C354A;">
                <p><b>Dispersion Leak Principale:</b> {diag.biggest_stroke_leak}</p>
                <p><b>Analisi Esecuzione Tecnica vs Tattica:</b> {diag.technical_vs_tactical_split}</p>
            </div>
        """, unsafe_allow_html=True)

        # Course Management Stats Box (Layup, Recovery, Bump & Run)
        cm = getattr(summary, "course_management_stats", None)
        if cm:
            st.markdown(f"""
                <div style="background:#131824; border:1px solid #2ECC71; border-radius:10px; padding:14px 18px; margin-top:12px; margin-bottom:15px; color:#E2E8F0;">
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
                        <span style="color:#2ECC71; font-weight:bold; font-size:1.05rem;">🧠 Gestione del Percorso & Scelte Tattiche: <i>{cm.course_management_rating}</i></span>
                        <span style="font-size:0.88rem; color:#A0AEC0;">Tasso Successo Recovery: <b style="color:#2ECC71;">{cm.recovery_success_rate}%</b></span>
                    </div>
                    <div style="display:flex; gap:25px; margin-top:10px; font-size:0.92rem; flex-wrap:wrap;">
                        <span>🎯 <b>Piazzamenti Tattici (Layup):</b> {cm.layups_count}</span>
                        <span>🌳 <b>Salvataggi da Difficoltà (Recovery):</b> {cm.recoveries_count}</span>
                        <span>👟 <b>Approcci a Correre (Bump & Run):</b> {cm.bump_and_runs_count}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        sub_tab_overview, sub_tab_holes, sub_tab_drills, sub_tab_transcript = st.tabs([
            "📋 Scorecard Ufficiale",
            "🎯 Mappa Vettoriale & Target Landing",
            "🏋️ Piano di Allenamento Mirato",
            "🎙️ Trascrizione Vocale"
        ])

        with sub_tab_overview:
            left_col, right_col = st.columns([3, 2])
            with left_col:
                st.markdown(f"### 📋 Scorecard Ufficiale — {active_course.name}")
                render_scorecard_table(data.holes)
                if summary.three_putt_holes:
                    st.warning(f"⚠️ 3-Putt riscontrati alle buche: {', '.join(map(str, summary.three_putt_holes))}")

            with right_col:
                st.markdown("### 📊 Ripartizione Colpi Persi (Strokes Lost)")
                render_strokes_lost_radar(summary.strokes_lost_breakdown)
                st.info(f"**Tendenza errore principale:** {summary.primary_miss_tendency}")

        with sub_tab_holes:
            st.markdown("### 🎯 Target Landing Area & Analisi Tattica per Buca")
            st.caption(f"Valutazione strategica tarata sull'Handicap personale ({st.session_state.user_profile.handicap}): Target Ideale vs Atterraggio Reale.")

            for h in data.holes:
                c_hole = next((ch for ch in active_course.holes if ch.hole_number == h.hole_number), None)
                slope_label = f" — ⛰️ {c_hole.slope_elevation_profile}" if (c_hole and hasattr(c_hole, 'slope_elevation_profile') and c_hole.slope_elevation_profile != "In pianura") else ""
                with st.expander(f"Buca {h.hole_number} — Par {h.par} | Score: {h.score} | Putt: {h.putts}{slope_label}"):
                    map_col, table_col = st.columns([2, 3])

                    with map_col:
                        map_mode = st.radio(
                            "Visualizzazione Buca:",
                            [
                                "🗺️ Vista A (Mappa ①②③ & Asse)",
                                "📊 Vista B (Benchmark & Dispersione)",
                                "🎯 Vista C (Green Radar & Pin)",
                                "📐 Grafico Traiettoria"
                            ],
                            horizontal=True,
                            key=f"map_mode_{h.hole_number}"
                        )
                        geojson_p = PROJECT_ROOT / "golf_strategy_ai" / "data" / f"conero_hole{h.hole_number}.geojson"
                        hole_geom = None
                        if geojson_p.exists():
                            try:
                                hole_geom = load_hole_geometry_from_geojson(geojson_p)
                            except Exception:
                                hole_geom = None

                        if not hole_geom and c_hole and hasattr(c_hole, 'coordinates') and c_hole.coordinates:
                            try:
                                hc = c_hole.coordinates
                                hole_geom = HoleGeometry(
                                    hole_number=h.hole_number,
                                    par=h.par,
                                    length_m=float(getattr(c_hole, 'distance_meters', 350.0)),
                                    stroke_index=int(getattr(c_hole, 'handicap_index', 1) or 1),
                                    tee=GeoPoint(lat=hc.tee_lat, lon=hc.tee_lon, alt_m=hc.tee_altitude),
                                    green_center=GeoPoint(lat=hc.target_lat, lon=hc.target_lon, alt_m=hc.target_altitude)
                                )
                            except Exception:
                                hole_geom = None

                        agent = HoleStrategyAgent()
                        user_hcp = getattr(st.session_state.user_profile, "handicap", 18.0)

                        if hole_geom and map_mode == "🗺️ Vista A (Mappa ①②③ & Asse)":
                            perf_eval = agent.evaluate_played_hole(hole_geom, h.shots, user_handicap=user_hcp, score=h.score, putts=h.putts)
                            html_code = render_view_a_map_html(hole_geom, perf_eval=perf_eval, height="420px")
                            components.html(html_code, height=440)
                        elif hole_geom and map_mode == "📊 Vista B (Benchmark & Dispersione)":
                            perf_eval = agent.evaluate_played_hole(hole_geom, h.shots, user_handicap=user_hcp, score=h.score, putts=h.putts)
                            html_code = render_view_b_benchmark_html(perf_eval=perf_eval)
                            st.markdown(html_code, unsafe_allow_html=True)
                        elif hole_geom and map_mode == "🎯 Vista C (Green Radar & Pin)":
                            perf_eval = agent.evaluate_played_hole(hole_geom, h.shots, user_handicap=user_hcp, score=h.score, putts=h.putts)
                            html_code = render_view_c_green_radar_html(hole_geom, app_eval=perf_eval.green_evaluation, height="420px")
                            components.html(html_code, height=440)
                        else:
                            fig_map = GolfHoleVisualizer.create_hole_trajectory_map(
                                h,
                                course_id=active_course.course_id if active_course else None
                            )
                            st.plotly_chart(fig_map, use_container_width=True)

                    with table_col:
                        if hole_geom:
                            perf_eval = agent.evaluate_played_hole(hole_geom, h.shots, user_handicap=user_hcp, score=h.score, putts=h.putts)
                            if perf_eval.tactical_verdict:
                                st.markdown(f"""
                                    <div style="background:#131d2a; border-left:4px solid #3498DB; border-radius:6px; padding:8px 12px; margin-bottom:8px; font-size:0.88rem;">
                                        <b>🧠 Valutazione Agente Strategico:</b> {perf_eval.tactical_verdict}<br>
                                        <span style="color:#A0AEC0; font-size:0.82rem;"><i>{perf_eval.caddy_advice_retrospective}</i></span>
                                    </div>
                                """, unsafe_allow_html=True)
                        if c_hole and hasattr(c_hole, 'slope_elevation_profile'):
                            slope_badge_bg = "#1e293b" if c_hole.slope_elevation_profile == "In pianura" else "#1e3a5f"
                            st.markdown(f"""
                                <div style="background:{slope_badge_bg}; border:1px solid #3b82f6; border-radius:6px; padding:6px 10px; margin-bottom:10px; font-size:0.83rem; color:#93C5FD;">
                                    ⛰️ <b>Profilo Altimetrico:</b> {c_hole.slope_elevation_profile}
                                </div>
                            """, unsafe_allow_html=True)
                        c_eval = getattr(h, "coach_evaluation", None)
                        if c_eval:
                            st.markdown(f"""
                                <div style="background:#0f172a; border-left:4px solid #10B981; border-radius:8px; padding:10px 14px; margin-bottom:12px; font-size:0.88rem; color:#E2E8F0;">
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                                        <span style="color:#34D399; font-weight:bold; font-size:0.95rem;">👨‍🏫 Analisi del Maestro (Regola Aurea)</span>
                                        <span style="background:#064E3B; color:#A7F3D0; padding:2px 8px; border-radius:10px; font-size:0.8rem; font-weight:bold;">Voto Buca: {c_eval.get('rating', '-')}/10</span>
                                    </div>
                                    <div style="margin-bottom:4px;"><b>1. Sintesi:</b> {c_eval.get('summary', '')}</div>
                                    <div style="margin-bottom:4px;"><b>2. Colpo chiave:</b> {c_eval.get('key_shot', '')}</div>
                                    <div style="margin-bottom:4px;"><b>3. Valutazione tecnica:</b> {c_eval.get('technical_assessment', '')}</div>
                                    <div style="margin-bottom:4px;"><b>4. Valutazione strategica:</b> {c_eval.get('strategic_assessment', '')}</div>
                                    <div style="margin-top:6px; padding-top:6px; border-top:1px dashed #334155; color:#93C5FD;">
                                        <b>5. Cosa avrebbe detto il maestro:</b> <i>{c_eval.get('coach_advice', '')}</i>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)

                        t_an = h.target_landing_analysis
                        if t_an:
                            verdict_color = "#2ECC71" if any(w in t_an.tactical_verdict for w in ["Bravo", "Ottimo", "Vincente", "Perfetto"]) else "#E67E22"
                            st.markdown(f"""
                                <div class="target-box" style="border-left: 4px solid {verdict_color};">
                                    <span style="color: {verdict_color}; font-weight: bold; font-size: 0.95rem;">
                                        {t_an.tactical_verdict}
                                    </span>
                                    <p style="margin-top: 5px; margin-bottom: 3px; font-size: 0.9rem;">🎯 <b>Target Ideale per HCP {st.session_state.user_profile.handicap}:</b> {t_an.ideal_target_zone}</p>
                                    <p style="margin-bottom: 3px; font-size: 0.9rem;">📍 <b>Atterraggio Reale Palla:</b> {t_an.actual_landing_zone}</p>
                                    <p style="color: #B0B3B8; font-size: 0.85rem; margin-top: 5px;"><i>🗣️ Note Caddie: {t_an.caddie_tactical_note}</i></p>
                                </div>
                            """, unsafe_allow_html=True)

                        gir_str = "Sì" if h.gir else "No"
                        fir_str = "Sì" if h.fairway_hit is True else ("No" if h.fairway_hit is False else "N/A")
                        st.write(f"**GIR:** {gir_str} | **Fairway Hit:** {fir_str}")
                        if h.root_cause_error:
                            st.caption(f"**Causa errore:** {h.root_cause_error}")

                        shot_df = pd.DataFrame([
                            {
                                "Colpo #": s.shot_index,
                                "Bastone": s.club or "N/D",
                                "Distanza (m)": s.distance_meters if s.distance_meters else "-",
                                "Posizione Palla": s.lie.value if hasattr(s.lie, 'value') else str(s.lie),
                                "Esito": s.result.value if hasattr(s.result, 'value') else str(s.result),
                                "Note": s.notes
                            } for s in h.shots
                        ])
                        st.dataframe(shot_df, use_container_width=True, hide_index=True)

        with sub_tab_drills:
            st.markdown("### 🏋️ Esercizi Prescritti dal Caddie PGA")
            st.caption("Drill biomeccanici e di course management con benchmark misurabili per il campo di pratica.")

            for drill in summary.training_drills_recommended:
                st.markdown(f"""
                    <div class="drill-box">
                        <div class="drill-target">AREA FOCUS: {drill.target_area}</div>
                        <h4 style="margin-top: 5px; color: #FFFFFF;">{drill.drill_name}</h4>
                        <p><b>🎯 Obiettivo:</b> {drill.objective}</p>
                        <p style="line-height: 1.5; color: #D1D5DB;"><b>📋 Istruzioni sul campo pratica:</b><br>{drill.setup_and_execution}</p>
                        <div style="background-color: #12151C; padding: 10px; border-radius: 6px; border-left: 3px solid #2ECC71;">
                            <b>🎯 Benchmark di Successo:</b> {drill.success_benchmark}
                        </div>
                    </div>
                """, unsafe_allow_html=True)

        with sub_tab_transcript:
            st.markdown("### 🎙️ Trascrizione Integrale Note Vocali")
            st.text_area("Testo completo trascritto:", value=st.session_state.transcript or "Nessuna trascrizione disponibile.", height=250)

    else:
        st.info("🏌️‍♂️ Carica una nota vocale dal pannello laterale oppure clicca su 'Carica Giro Demo PGA' per iniziare l'analisi.")




# ---------------------------------------------------------
# TAB: CHAT CON IL CADDIE (CLOUD AI & PERSONALITÀ)
# ---------------------------------------------------------
with nav_chat:
    st.subheader("💬 Chat con il tuo Caddie Personale (Cloud AI)")
    st.caption("Consulenza strategica e caddie virtuale in tempo reale: chiedi consigli sui bastoni da tirare, gestione del vento, strategie di percorso o supporto mentale.")

    if "caddy_chat_history" not in st.session_state:
        st.session_state.caddy_chat_history = []
    if "active_chat_tone" not in st.session_state:
        st.session_state.active_chat_tone = getattr(st.session_state.user_profile, "caddy_tone", "professionale") or "professionale"

    # Tone Selector Bar (Pill buttons)
    top_col1, top_col2 = st.columns([3.2, 0.8])
    with top_col1:
        st.markdown("<div style='font-size:0.85rem; font-weight:bold; color:#94A3B8; margin-bottom:4px;'>🎭 PERSONALITÀ ATTIVA DEL CADDIE:</div>", unsafe_allow_html=True)
        tone_cols = st.columns(4)
        for idx, t_enum in enumerate(CaddyTone):
            is_active = (st.session_state.active_chat_tone == t_enum.value)
            btn_type = "primary" if is_active else "secondary"
            with tone_cols[idx]:
                if st.button(t_enum.short_label, key=f"chat_tone_btn_{t_enum.value}", type=btn_type, use_container_width=True):
                    st.session_state.active_chat_tone = t_enum.value
                    # Welcome reaction in new tone
                    phrase = CaddyPersonalityEngine.get_instance().get_phrase(
                        "START_ROUND",
                        tone=t_enum.value,
                        buca="1",
                        nome=st.session_state.user_profile.player_name
                    )
                    st.session_state.caddy_chat_history.append({
                        "role": "assistant",
                        "content": f"🎭 <i>Personalità impostata su {t_enum.display_name}</i>\n\n«{phrase}»",
                        "tone": t_enum.value
                    })
                    st.rerun()

    with top_col2:
        st.write("")
        st.write("")
        if st.button("🧹 Pulisci", key="btn_clear_caddy_chat", use_container_width=True):
            st.session_state.caddy_chat_history = []
            st.rerun()

    active_tone_enum = CaddyTone(st.session_state.active_chat_tone)
    st.markdown(f"""
        <div style="background:#1E293B; border-left:4px solid {active_tone_enum.badge_color}; border-radius:6px; padding:8px 12px; margin-bottom:14px; font-size:0.85rem; color:#CBD5E1;">
            <b style="color:{active_tone_enum.badge_color};">{active_tone_enum.display_name}</b> — <i>{active_tone_enum.description}</i>
        </div>
    """, unsafe_allow_html=True)

    # Quick Suggestion Chips
    st.markdown("<div style='font-size:0.82rem; color:#94A3B8; margin-bottom:6px;'>⚡ <i>Domande rapide:</i></div>", unsafe_allow_html=True)
    q_col1, q_col2, q_col3, q_col4 = st.columns(4)
    quick_prompt = None
    with q_col1:
        if st.button("🏌️ Bastone da 145m?", key="qp_dist", use_container_width=True):
            quick_prompt = "Ho 145 metri alla bandiera in leggera salita con un po' di vento contrario. Quale bastone mi consigli dalla mia sacca?"
    with q_col2:
        if st.button("⛳ Strategia Buca 1", key="qp_h1", use_container_width=True):
            quick_prompt = f"Dammi la strategia di gioco migliore per affrontare la buca 1 di {active_course.name} considerando il mio handicap."
    with q_col3:
        if st.button("🌊 Palla in Acqua", key="qp_water", use_container_width=True):
            quick_prompt = "Ho appena mandato la palla in acqua dal tee! Come affronto il colpo successivo per limitare i danni ed evitare il disastro?"
    with q_col4:
        if st.button("🧘 Focus Mentale", key="qp_zen", use_container_width=True):
            quick_prompt = "Sento tensione prima di questo tee shot delicato. Dammi un consiglio mentale per ritrovare ritmo, fiducia e calma."

    # Initial Welcome message if history is empty
    if not st.session_state.caddy_chat_history:
        welcome_phrase = CaddyPersonalityEngine.get_instance().get_phrase(
            "START_ROUND",
            tone=st.session_state.active_chat_tone,
            buca="1",
            nome=st.session_state.user_profile.player_name
        )
        st.session_state.caddy_chat_history.append({
            "role": "assistant",
            "content": welcome_phrase,
            "tone": st.session_state.active_chat_tone
        })

    # Render chat messages
    for msg in st.session_state.caddy_chat_history:
        if msg["role"] == "user":
            with st.chat_message("user", avatar="🏌️‍♂️"):
                st.markdown(msg["content"])
        else:
            msg_tone = msg.get("tone", st.session_state.active_chat_tone)
            tone_avatar = {
                "professionale": "👔",
                "arrabbiato": "🤬",
                "spensierato": "🍻",
                "psicologo": "🧘"
            }.get(msg_tone, "⛳")
            with st.chat_message("assistant", avatar=tone_avatar):
                st.markdown(msg["content"])

    # Chat Input Box
    user_input = st.chat_input("Scrivi al caddie (es. 'che bastone tiro da 130m?', 'come gioco questa buca?')...")
    prompt_to_process = quick_prompt or user_input

    if prompt_to_process:
        st.session_state.caddy_chat_history.append({"role": "user", "content": prompt_to_process})
        with st.spinner(f"Il caddie ({active_tone_enum.short_label}) sta valutando..."):
            reply = CaddyPersonalityEngine.get_instance().chat_with_caddy(
                message=prompt_to_process,
                tone=st.session_state.active_chat_tone,
                history=[{"role": m["role"], "content": m["content"]} for m in st.session_state.caddy_chat_history[:-1]],
                user_profile=st.session_state.user_profile,
                ai_config=user_ai,
                active_course=active_course
            )
        st.session_state.caddy_chat_history.append({
            "role": "assistant",
            "content": reply,
            "tone": st.session_state.active_chat_tone
        })
        st.rerun()


# ---------------------------------------------------------
# TAB: PIN POSITION & PLAYS LIKE GPS
# ---------------------------------------------------------
with nav_pin_gps:
    st.subheader("📍 Pin Position, Altimetria & Balistica Plays Like (Live GPS)")
    st.caption("Tracciamento delle distanze cieche, dislivello altimetrico con Open-Meteo & Open-Elevation, e calcolo balistico Plays Like con suggerimento bastone.")

    col_pin_l, col_pin_r = st.columns([1.5, 2.5])

    with col_pin_l:
        st.markdown(f"### ⛳ {active_course.name}")
        st.caption(f"Città: {active_course.city} | Buche: {active_course.holes_count} | Par: {active_course.total_par}")
        if hasattr(active_course, "terrain_description") and active_course.terrain_description:
            st.info(f"⛰️ **Orografia del campo:** {active_course.terrain_description}")

        hole_nums = [h.hole_number for h in active_course.holes]
        selected_h_num = st.selectbox(
            "Seleziona la Buca da visualizzare/calcolare:",
            options=hole_nums,
            index=0,
            format_func=lambda n: f"Buca {n} (Par {active_course.get_hole(n).par if active_course.get_hole(n) else 4} — {active_course.get_hole(n).distance_meters if active_course.get_hole(n) else 'N/D'}m)"
        )
        h_info = active_course.get_hole(selected_h_num)

        if h_info:
            h_coords = h_info.coordinates
            slope_color = "#E67E22" if "salita" in h_info.slope_elevation_profile.lower() else ("#3498DB" if "discesa" in h_info.slope_elevation_profile.lower() else "#2ECC71")

            st.markdown(f"""
                <div style="background-color: #141d2b; border: 1px solid #28374f; border-radius: 10px; padding: 16px; margin-top: 10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:1.1rem; font-weight:bold; color:#FFFFFF;">Buca {h_info.hole_number}</span>
                        <span style="background-color:rgba(46,204,113,0.15); color:#2ECC71; padding:2px 8px; border-radius:12px; font-weight:bold;">Par {h_info.par}</span>
                    </div>
                    <div style="color:#94A3B8; font-size:0.85rem; margin-top:4px;">
                        • Distanza Scorecard: <b>{h_info.distance_meters}m</b><br>
                        • Indice di Difficoltà (HCP): <b>{h_info.handicap_index or 'N/D'}</b><br>
                        • Pendenza dichiarata: <b style="color:{slope_color};">{h_info.slope_elevation_profile}</b>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            if h_coords:
                st.markdown("#### 🌐 Coordinate GPS & Quote Altimetriche")
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown(f"""
                        <div style="background:#0e1622; border:1px solid #1f2d42; border-radius:8px; padding:10px; font-size:0.82rem;">
                            <b style="color:#38BDF8;">🏌️‍♂️ Tee di Partenza:</b><br>
                            Lat: <code>{h_coords.tee_lat:.4f}</code><br>
                            Lon: <code>{h_coords.tee_lon:.4f}</code><br>
                            Quota: <b>{int(h_coords.tee_altitude) if h_coords.tee_altitude else 'N/D'}m s.l.m.</b>
                        </div>
                    """, unsafe_allow_html=True)
                with col_c2:
                    st.markdown(f"""
                        <div style="background:#0e1622; border:1px solid #1f2d42; border-radius:8px; padding:10px; font-size:0.82rem;">
                            <b style="color:#2ECC71;">🎯 Centro Green / Pin:</b><br>
                            Lat: <code>{h_coords.target_lat:.4f}</code><br>
                            Lon: <code>{h_coords.target_lon:.4f}</code><br>
                            Quota: <b>{int(h_coords.target_altitude) if h_coords.target_altitude else 'N/D'}m s.l.m.</b>
                        </div>
                    """, unsafe_allow_html=True)

                # Mappa Tattica Satellitare Esri HD per la buca selezionata
                geojson_p = PROJECT_ROOT / "golf_strategy_ai" / "data" / f"conero_hole{selected_h_num}.geojson"
                hole_geom = None
                if geojson_p.exists():
                    try:
                        hole_geom = load_hole_geometry_from_geojson(geojson_p)
                    except Exception:
                        hole_geom = None

                if not hole_geom and h_coords:
                    try:
                        hole_geom = HoleGeometry(
                            hole_number=selected_h_num,
                            par=h_info.par,
                            length_m=float(h_info.distance_meters),
                            stroke_index=int(h_info.handicap_index or 1),
                            tee=GeoPoint(lat=h_coords.tee_lat, lon=h_coords.tee_lon, alt_m=h_coords.tee_altitude),
                            green_center=GeoPoint(lat=h_coords.target_lat, lon=h_coords.target_lon, alt_m=h_coords.target_altitude)
                        )
                    except Exception:
                        hole_geom = None

                if hole_geom:
                    st.markdown("#### 🛰️ Mappa Tattica Satellitare (Tour Esri HD)")
                    user_hcp = getattr(st.session_state.user_profile, "handicap", 18.0)
                    cat = estimate_category_from_handicap(user_hcp)
                    strategy = analyze_hole_strategy(hole_geom, cat, course_id=active_course.course_id if active_course else "course")
                    html_code = render_hole_map_html(hole_geom, strategy=strategy, height="360px")
                    components.html(html_code, height=380)

    with col_pin_r:
        st.markdown("### 🧮 Calcolatore Balistico Plays Like Distance")
        st.caption("Simula la posizione della palla dal tee o dal fairway e calcola l'effetto reale della pendenza.")

        calc_mode = st.radio(
            "Modalità di calcolo:",
            options=["Distanza Metrica & Dislivello Altimetrico", "Coordinate GPS Reali (Lat/Lon)"],
            horizontal=True
        )

        target_coords = h_info.coordinates if (h_info and h_info.coordinates) else None

        if calc_mode == "Distanza Metrica & Dislivello Altimetrico":
            default_dist = float(h_info.distance_meters if h_info and h_info.distance_meters else 150)
            sim_dist = st.slider("Distanza orizzontale in linea d'aria verso la bandiera (metri):", min_value=20.0, max_value=500.0, value=min(default_dist, 140.0), step=1.0)

            default_elev = 0.0
            if target_coords and target_coords.tee_altitude and target_coords.green_altitude:
                default_elev = float(target_coords.green_altitude - target_coords.tee_altitude)

            sim_elev = st.slider("Dislivello altimetrico Δh (metri tra palla e green):", min_value=-40.0, max_value=40.0, value=default_elev, step=1.0, help="Positivo (+) per salita, negativo (-) per discesa.")

            c_factor = st.slider("Coefficiente balistico c (standard golf ~1.0):", min_value=0.8, max_value=1.2, value=1.0, step=0.05, help="10m di salita equivalgono solitamente a ~10m in più di bastone.")

            plays_like_val = calculate_plays_like(sim_dist, sim_elev, c_factor)
            rec_club = st.session_state.user_profile.recommend_club_for_distance(plays_like_val)
            rec_str = f"{rec_club.club_name} ({int(rec_club.carry_meters)}m)" if rec_club else "N/D"

            sign_s = "+" if sim_elev > 0 else ""
            status_text = "In salita" if sim_elev > 1 else ("In discesa" if sim_elev < -1 else "In pianura")

            col_res1, col_res2, col_res3 = st.columns(3)
            col_res1.metric("📏 Distanza Reale (Laser)", f"{int(sim_dist)}m")
            col_res2.metric(f"⛰️ Dislivello ({status_text})", f"{sign_s}{int(sim_elev)}m")
            col_res3.metric("🎯 Plays Like Distance", f"~{int(plays_like_val)}m", delta=f"{sign_s}{int(plays_like_val - sim_dist)}m")

            st.markdown(f"""
                <div style="background: linear-gradient(135deg, #13271d 0%, #0d1a14 100%); border: 2px solid #2ECC71; border-radius: 12px; padding: 18px; margin-top: 15px; text-align: center;">
                    <span style="font-size: 0.95rem; color: #A7F3D0; text-transform: uppercase; font-weight: bold; letter-spacing: 1px;">🏌️ Raccomandazione Caddie PGA per {st.session_state.user_profile.player_name}:</span>
                    <div style="font-size: 1.8rem; font-weight: 800; color: #FFFFFF; margin: 8px 0;">
                        Bastone Consigliato: <span style="color: #F1C40F;">{rec_str}</span>
                    </div>
                    <div style="font-size: 0.88rem; color: #CBD5E1;">
                        Un colpo di <b>{int(sim_dist)}m</b> con <b>{sign_s}{int(sim_elev)}m</b> di pendenza richiede la stessa potenza e traiettoria di un colpo in piano da <b>~{int(plays_like_val)}m</b>.
                    </div>
                </div>
            """, unsafe_allow_html=True)

        else:
            default_lat = target_coords.tee_lat if target_coords else 43.5228
            default_lon = target_coords.tee_lon if target_coords else 13.6060
            c_lat1, c_lat2 = st.columns(2)
            with c_lat1:
                b_lat = st.number_input("Latitudine Palla:", value=float(default_lat), format="%.5f")
            with c_lat2:
                b_lon = st.number_input("Longitudine Palla:", value=float(default_lon), format="%.5f")

            if st.button("📡 Calcola con API Open-Meteo & Open-Elevation", type="primary", use_container_width=True):
                with st.spinner("Interrogazione modelli di elevazione digitale..."):
                    t_lat = target_coords.target_lat if target_coords else 43.5199
                    t_lon = target_coords.target_lon if target_coords else 13.6072
                    t_alt = target_coords.target_altitude if target_coords else 110.0

                    approach = elevation_service.calculate_hole_approach(
                        ball_lat=b_lat, ball_lon=b_lon,
                        target_lat=t_lat, target_lon=t_lon,
                        target_altitude=t_alt
                    )

                    rec_club = st.session_state.user_profile.recommend_club_for_distance(approach["plays_like_distance"])
                    rec_str = f"{rec_club.club_name} ({int(rec_club.carry_meters)}m)" if rec_club else "N/D"

                    col_r1, col_r2, col_r3 = st.columns(3)
                    col_r1.metric("📏 Distanza Haversine", f"{int(approach['raw_distance'])}m")
                    col_r2.metric(f"⛰️ Dislivello ({approach['slope_label']})", f"{int(approach['elevation_diff'])}m")
                    col_r3.metric("🎯 Plays Like Distance", f"~{int(approach['plays_like_distance'])}m")

                    st.success(f"🏌️ **Bastone Suggerito dalla tua sacca:** {rec_str}")
                    st.caption(f"Quota Palla: {approach['ball_altitude']}m s.l.m. | Quota Green: {approach['target_altitude']}m s.l.m.")

        st.markdown("---")
        st.markdown("### 📱 Guida in 3 Passaggi: Come giocare in campo senza rallentare il gioco")
        st.markdown(f"""
            <div style="background: linear-gradient(135deg, #111e30 0%, #0d1522 100%); border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 10px; padding: 18px; margin-bottom: 15px;">
                <div style="font-size: 1rem; font-weight: bold; color: #38BDF8; margin-bottom: 12px;">
                    ⚡ 3 Semplici Passaggi: Zero Distrazioni, Zero Rallentamenti per il Team
                </div>
                <div style="font-size: 0.88rem; line-height: 1.6; color: #E2E8F0;">
                    <b>1️⃣ SUL TEE DI PARTENZA:</b><br>
                    Tocca il pulsante rapido <code>⏩ Prossima Buca</code> sulla tastiera Telegram (o digita <code>/buca 1</code>). Tira il tuo colpo dal tee.<br><br>
                    <b>2️⃣ QUANDO ARRIVI SULLA PALLA (1 Solo Tocco):</b><br>
                    Tira fuori lo smartphone e tocca l'unico grande pulsante in basso:<br>
                    <span style="display:inline-block; background:#0284C7; color:#FFFFFF; padding:4px 10px; border-radius:6px; font-weight:bold; margin: 4px 0;">📍 Calcola Distanza & Plays Like</span><br>
                    <i>In meno di 1 secondo ricevi: Distanza reale al green, Dislivello altimetrico (+/- metri), Plays Like effettivo e Bastone consigliato dalla tua sacca!</i><br><br>
                    <b>3️⃣ DOPO IL COLPO (Mentre cammini):</b><br>
                    Mentre cammini verso il green o verso la palla successiva, tieni premuto il microfono di Telegram per 2 secondi: <i>'Ferro 7 dal fairway'</i>.<br>
                    Il bot archivia il colpo nel database senza che tu debba fermarti o digitare nulla.<br><br>
                    <span style="color:#94A3B8; font-size:0.8rem;">💡 <b>Giocatore collegato al Bot:</b> {current_user.first_name} {current_user.last_name} &bull; <b>Campo attivo:</b> {active_course.name}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------
# TAB 2: USER PROFILE & PERSONAL EQUIPMENT
# ---------------------------------------------------------
with nav_tab2:
    st.subheader(f"🏌️‍♂️ Scheda Profilo di {current_user.first_name} & Attrezzatura Sacca")
    st.caption("I dati del tuo profilo e la composizione della tua sacca sono memorizzati in modo permanente e isolato per il tuo account.")

    if current_user.is_admin:
        unread_admin_msgs = inbox_mgr.get_unread_count()
        if unread_admin_msgs > 0:
            st.info(f"📬 **Hai {unread_admin_msgs} nuovi messaggi dagli utenti!** Vai alla scheda **👑 Amministrazione & Utenti** per leggerli e gestire la casella.")

    prof = st.session_state.user_profile

    col_prof_l, col_prof_r = st.columns([2, 3])

    with col_prof_l:
        st.markdown("### 👤 Dati Giocatore & Handicap")
        m_name = st.text_input("Nome & Cognome Giocatore", value=prof.player_name)
        m_hcp = st.number_input("Handicap Ufficiale (HCP)", min_value=0.0, max_value=54.0, value=float(prof.handicap), step=0.1)
        m_ball = st.text_input("Palla Preferita / In Uso", value=prof.preferred_ball or "Titleist Pro V1")

        new_cat = UserProfile.determine_category(m_hcp)
        st.info(f"**Categoria Assegnata:** {new_cat.value}")

        st.markdown("---")
        st.markdown("### 🎭 Personalità & Tono del Caddie")
        st.caption("Scegli come il tuo caddie si relazionerà con te durante il giro e nelle chat.")
        tone_options = [t.value for t in CaddyTone]
        curr_tone = getattr(prof, "caddy_tone", "professionale") or "professionale"
        curr_idx = tone_options.index(curr_tone) if curr_tone in tone_options else 0
        m_caddy_tone = st.selectbox(
            "Stile Predefinito Caddie",
            options=tone_options,
            format_func=lambda k: CaddyTone(k).display_name,
            index=curr_idx,
            key="profile_caddy_tone_select"
        )
        sel_enum = CaddyTone(m_caddy_tone)
        st.markdown(f"""
            <div style="background:#1E293B; border-left:4px solid {sel_enum.badge_color}; border-radius:6px; padding:10px 14px; margin-top:6px; margin-bottom:12px; font-size:0.85rem; color:#CBD5E1;">
                <b style="color:{sel_enum.badge_color};">{sel_enum.display_name}</b><br>
                <i>{sel_enum.description}</i><br>
                <span style="color:#94A3B8; font-size:0.80rem; margin-top:4px; display:inline-block;">{sel_enum.sample_quote}</span>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 🎙️ In alternativa: Importa Profilo da Nota Vocale")
        setup_audio_file = st.file_uploader("Carica Audio Presentazione Sacca", type=["m4a", "mp3", "wav", "opus", "aac"])
        if st.button("🪄 Estrai Profilo da Audio", type="primary", disabled=not setup_audio_file):
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{setup_audio_file.name}") as tmp_s:
                tmp_s.write(setup_audio_file.read())
                tmp_s_path = tmp_s.name

            try:
                audio_eng = VoiceCaddyAudioEngine()
                setup_transcript, _ = audio_eng.transcribe(tmp_s_path, engine_mode="local")
                parsed_profile = parse_user_setup_transcript(setup_transcript, ai_config=user_ai)
                parsed_profile.save_for_user(current_user.user_id)
                st.session_state.user_profile = parsed_profile
                st.success(f"✅ Profilo estratto e salvato nel tuo account! Handicap: {parsed_profile.handicap}")
                st.rerun()
            except Exception as e:
                st.error(f"Errore estrazione profilo: {e}")
            finally:
                if os.path.exists(tmp_s_path):
                    try:
                        os.remove(tmp_s_path)
                    except OSError:
                        pass

    with col_prof_r:
        st.markdown("### 🎒 Composizione Sacca Bastoni Personale")
        st.caption("⚡ I bastoni salvati si allineano automaticamente in base alla distanza: dal Driver più lungo fino al Putter.")

        if "bag_save_success" in st.session_state:
            st.success(st.session_state.pop("bag_save_success"))

        sorted_bag = sort_clubs_by_distance(prof.clubs_in_bag)
        clubs_data = []
        for idx, c in enumerate(sorted_bag):
            clubs_data.append({
                "Mazza": c.club_name,
                "Marca": c.brand or "Generica",
                "Modello / Tipo": c.model_type or "",
                "Shaft": c.shaft_flex.value if hasattr(c.shaft_flex, 'value') else str(c.shaft_flex),
                "Distanza Carry (m)": int(c.carry_meters)
            })

        df_bag = pd.DataFrame(clubs_data)
        edited_df = st.data_editor(
            df_bag,
            key=f"bag_editor_{current_user.user_id}",
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Mazza": st.column_config.SelectboxColumn("Mazza", options=["Driver", "Legno 3", "Legno 5", "Ibrido 3", "Ibrido 4", "Ferro 4", "Ferro 5", "Ferro 6", "Ferro 7", "Ferro 8", "Ferro 9", "Pitching Wedge", "Approach Wedge (AW)", "Gap Wedge (50°/52°)", "Sand Wedge (56°)", "Lob Wedge (60°)", "Putter"], required=True),
                "Marca": st.column_config.SelectboxColumn("Marca", options=["TaylorMade", "Callaway", "Titleist", "Ping", "Cobra", "Mizuno", "Wilson", "Cleveland", "PXG", "Srixon", "Generica"]),
                "Modello / Tipo": st.column_config.TextColumn("Modello / Tipo"),
                "Shaft": st.column_config.SelectboxColumn("Shaft", options=["Regular", "Stiff", "Extra Stiff (X-Stiff)", "Senior / Lite", "Ladies"]),
                "Distanza Carry (m)": st.column_config.NumberColumn("Distanza Carry (m)", min_value=0, max_value=350, step=5)
            }
        )

        if st.button("💾 Salva Scheda Profilo & Sacca", type="primary", use_container_width=True):
            updated_clubs = []
            for _, row in edited_df.iterrows():
                if pd.notna(row["Mazza"]):
                    s_flex = ShaftFlex.REGULAR
                    for sf in ShaftFlex:
                        if sf.value == row["Shaft"]:
                            s_flex = sf
                            break

                    updated_clubs.append(ClubDetail(
                        club_name=str(row["Mazza"]),
                        brand=str(row["Marca"]) if pd.notna(row["Marca"]) else "Generica",
                        model_type=str(row["Modello / Tipo"]) if pd.notna(row["Modello / Tipo"]) else "",
                        shaft_flex=s_flex,
                        carry_meters=float(row["Distanza Carry (m)"]) if pd.notna(row["Distanza Carry (m)"]) else 0.0
                    ))

            # Allinea automaticamente le voci inserite in base alla distanza: dal driver più lungo fino al putt
            updated_clubs = sort_clubs_by_distance(updated_clubs)

            st.session_state.user_profile.player_name = m_name
            st.session_state.user_profile.handicap = m_hcp
            st.session_state.user_profile.category = new_cat
            st.session_state.user_profile.preferred_ball = m_ball
            st.session_state.user_profile.clubs_in_bag = updated_clubs
            st.session_state.user_profile.caddy_tone = m_caddy_tone

            st.session_state.user_profile.save_for_user(current_user.user_id)
            st.session_state["bag_save_success"] = f"✅ Profilo e Sacca di {current_user.first_name} salvati e riordinati con successo dal Driver al Putter!"
            st.rerun()

        col_sb1, col_sb2 = st.columns([1, 1])
        with col_sb1:
            st.download_button(
                "⬇️ Scarica la mia Sacca (File JSON)",
                data=prof.model_dump_json(indent=2),
                file_name=f"sacca_{current_user.user_id}.json",
                mime="application/json",
                use_container_width=True,
                help="Scarica una copia istantanea della tua sacca sul tuo dispositivo per conservarla sempre al sicuro da qualsiasi aggiornamento cloud."
            )
        with col_sb2:
            with st.popover("📥 Ricarica da File JSON", use_container_width=True):
                st.caption("Se la tua sacca si è resettata dopo un aggiornamento cloud, ricarica qui il tuo file JSON per ripristinarla in 1 secondo:")
                uploaded_bag_json = st.file_uploader("Seleziona file JSON sacca:", type=["json"], key="restore_bag_json_pop")
                if uploaded_bag_json is not None:
                    if st.button("🚀 Ripristina Subito", type="primary", use_container_width=True, key="btn_apply_uploaded_bag"):
                        try:
                            raw_data = json.loads(uploaded_bag_json.read().decode("utf-8"))
                            restored_prof = UserProfile.model_validate(raw_data)
                            restored_prof.save_for_user(current_user.user_id)
                            st.session_state.user_profile = restored_prof
                            st.success("✅ Sacca ripristinata con successo!")
                            st.rerun()
                        except Exception as e_rst:
                            st.error(f"Errore lettura file JSON: {e_rst}")

        # ---------------------------------------------------------
        # 🎯 Sincronizza Sacca: Allenamento vs Gara sull'Erba
        # ---------------------------------------------------------
        st.markdown("---")
        st.markdown("### 🎯 Sincronizza Sacca: Allenamento vs Gara sull'Erba")
        st.caption("Confronta le distanze nominali impostate in allenamento/campo pratica con la media reale dei colpi misurati su erba via GPS durante le gare.")

        grass_stats = ClubDistanceService.get_club_grass_performance(
            db_path=db.db_path,
            user_id=current_user.user_id
        )

        # Allinea temporaneamente per calcolare la sintesi (senza sovrascrivere il carry)
        prof.sync_with_grass_statistics(grass_stats, update_carry=False)
        comparison_list = prof.get_club_comparison_summary()

        has_grass_data = any(item["grass_meters"] is not None for item in comparison_list)

        comp_rows = []
        for item in comparison_list:
            c_name = item["club_name"]
            train_m = f"{int(item['training_meters'])} m"
            if item["grass_meters"] is not None:
                g_m = f"{int(item['grass_meters'])} m"
                delta_val = int(item["delta_meters"])
                delta_str = f"{'+' if delta_val > 0 else ''}{delta_val} m"
                cnt = item["shots_count"]
                if abs(delta_val) <= 5:
                    status = "🎯 Allineato (±5m)"
                elif delta_val > 5:
                    status = f"🚀 Su erba vola più lungo (+{delta_val}m)"
                else:
                    status = f"⚠️ Su erba vola più corto ({delta_val}m)"
            else:
                g_m = "—"
                delta_str = "—"
                cnt = 0
                status = "Dati in attesa (nessun colpo su erba)"

            comp_rows.append({
                "Bastone": c_name,
                "Allenamento (m)": train_m,
                "Media Erba (m)": g_m,
                "Differenza (Delta)": delta_str,
                "Colpi Misurati": cnt,
                "Analisi Performance": status
            })

        df_comp = pd.DataFrame(comp_rows)
        st.dataframe(df_comp, use_container_width=True, hide_index=True)

        col_sync1, col_sync2 = st.columns([2, 1])
        with col_sync1:
            if has_grass_data:
                st.info("💡 **Consiglio Tattico:** Se i colpi misurati su erba sono attendibili (es. > 3 colpi per bastone), puoi sincronizzare la sacca per permettere al caddie di suggerire i bastoni in base alla tua reale resa sul campo da golf.")
            else:
                st.info("ℹ️ **Nessun colpo ancora rilevato su erba:** Registra i colpi via GPS con il Bot Telegram durante la gara per popolare automaticamente questo confronto.")

        with col_sync2:
            if st.button("🔄 Sincronizza Sacca con i Colpi su Erba", type="secondary", use_container_width=True, disabled=not has_grass_data, key="sync_grass_bag_btn"):
                prof.sync_with_grass_statistics(grass_stats, update_carry=True, user_id=current_user.user_id)
                st.session_state.user_profile = prof
                st.success("✅ Sacca sincronizzata con successo con le distanze reali su erba!")
                st.rerun()

        # ---------------------------------------------------------
        # SAFEVAULT: Protezione Dati, Esportazione & Ripristino 1-Clic
        # ---------------------------------------------------------
        st.markdown("---")
        st.subheader("🛡️ Cassaforte Dati & Backup Personale (Anti-Perdita)")
        st.caption("Scarica una copia di sicurezza certificata dei tuoi dati (Sacca, HCP, Distanze e Gare) o ripristina uno snapshot precedente.")

        col_bk1, col_bk2 = st.columns(2)
        with col_bk1:
            st.markdown("<b>💾 Esporta Copia di Sicurezza:</b>", unsafe_allow_html=True)
            st.caption("Scarica un pacchetto compresso ZIP contenente tutti i tuoi dati da conservare al sicuro.")
            backup_bytes = backup_manager.export_full_backup_bytes()
            ts_str = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                label=f"⬇️ Scarica Backup Completo ({current_user.first_name})",
                data=backup_bytes,
                file_name=f"VoiceCaddy_Backup_{current_user.user_id}_{ts_str}.zip",
                mime="application/zip",
                use_container_width=True,
                type="secondary"
            )

        with col_bk2:
            st.markdown("<b>📥 Ripristina da Backup (ZIP):</b>", unsafe_allow_html=True)
            uploaded_bk = st.file_uploader("Carica file ZIP di backup:", type=["zip"], key="upload_user_backup_zip")
            if uploaded_bk is not None:
                if st.button("🚀 Conferma e Ripristina Dati", key="confirm_restore_user_btn", type="primary", use_container_width=True):
                    ok_rst, msg_rst = backup_manager.restore_from_zip(uploaded_bk.getvalue())
                    if ok_rst:
                        st.success(msg_rst)
                        st.rerun()
                    else:
                        st.error(msg_rst)

        # Snapshot locali rotativi automatici
        snapshots = backup_manager.list_snapshots()
        if snapshots:
            with st.expander(f"🕒 Cronologia Snapshot Automatici ({len(snapshots)} disponibili)", expanded=False):
                st.caption("Voice Caddy crea automaticamente uno snapshot di sicurezza rotativo ad ogni sessione.")
                col_sn1, col_sn2 = st.columns([3, 1])
                with col_sn1:
                    snap_options = {s["filename"]: f"{s['filename']} — {s['date_str']} ({s['size_kb']} KB)" for s in snapshots}
                    selected_snap = st.selectbox(
                        "Seleziona snapshot da ripristinare:",
                        options=list(snap_options.keys()),
                        format_func=lambda x: snap_options[x],
                        key="selected_snapshot_to_restore"
                    )
                with col_sn2:
                    st.write("")
                    st.write("")
                    if st.button("🔄 Ripristina Snapshot", key="btn_apply_snapshot", use_container_width=True):
                        ok_snap, msg_snap = backup_manager.restore_from_snapshot(selected_snap)
                        if ok_snap:
                            st.success(f"Snapshot '{selected_snap}' ripristinato con successo!")
                            st.rerun()
                        else:
                            st.error(msg_snap)


# ---------------------------------------------------------
# TAB 3: HISTORICAL ROUNDS & TRENDS (PER-USER ISOLATION)
# ---------------------------------------------------------
with nav_tab3:
    col_hist_title, col_hist_filter = st.columns([3, 2])
    with col_hist_title:
        st.subheader(f"📈 Storico Partite di {current_user.first_name}")
    with col_hist_filter:
        show_all_club = st.checkbox("Mostra partite di tutti i membri del circolo", value=False)

    filter_user_id = None if show_all_club else current_user.user_id
    rounds_list = db.get_all_rounds(user_id=filter_user_id)

    if not rounds_list:
        st.info("Nessuna partita ancora registrata per questo account. Carica una nota vocale o clicca su 'Carica Giro Demo PGA'!")
    else:
        hist_stats = db.get_historical_stats(user_id=filter_user_id)

        stat1, stat2, stat3, stat4, stat5 = st.columns(5)
        stat1.metric("Giri Registrati", hist_stats["total_rounds"])
        stat2.metric("Score Medio", hist_stats["avg_score"])
        stat3.metric("Media FIR %", f"{hist_stats['avg_fairway_pct']}%")
        stat4.metric("Media GIR %", f"{hist_stats['avg_gir_pct']}%")
        stat5.metric("Media Putt", hist_stats["avg_putts"])

        st.markdown("---")
        df_rounds = pd.DataFrame(rounds_list)

        fig_score = px.line(
            df_rounds, x="created_at", y="total_score",
            title="Progressione Score Totale (Giri Storici)",
            markers=True, color_discrete_sequence=["#2ECC71"]
        )
        st.plotly_chart(fig_score, use_container_width=True)

        st.markdown("### 📂 Gestione Giri Registrati")
        selected_round_id = st.selectbox(
            "Seleziona un giro per visualizzarlo o gestirlo:",
            options=[r["id"] for r in rounds_list],
            format_func=lambda x: next(f"ID #{r['id']} — {r['course_name']} ({r['date_played']}) — Score: {r['total_score']} [{r.get('group_name', 'strafatti').upper()}]" for r in rounds_list if r["id"] == x)
        )

        col_load, col_del = st.columns(2)
        with col_load:
            if st.button("📂 Carica nel Dashboard Attivo", use_container_width=True):
                loaded_round = db.get_round_by_id(selected_round_id)
                if loaded_round:
                    st.session_state.round_data = loaded_round
                    st.success(f"✅ Giro #{selected_round_id} caricato nel Dashboard!")
                    st.rerun()

        with col_del:
            if st.button("🗑️ Elimina Giro dal Database", type="secondary", use_container_width=True):
                if db.delete_round(selected_round_id):
                    st.success(f"Giro #{selected_round_id} eliminato con successo.")
                    st.rerun()


# ---------------------------------------------------------
# TAB 4: BENCHMARK & STROKES GAINED
# ---------------------------------------------------------
with nav_tab4:
    st.subheader("🎯 Confronto Benchmark Strokes Gained vs Handicap Target")

    if not st.session_state.round_data:
        st.info("Carica o analizza una partita per sbloccare l'analisi dei benchmark di handicap.")
    else:
        target_hcp = st.selectbox(
            "Seleziona il tuo Handicap Target di confronto:",
            options=list(StrokesGainedBenchmarkEngine.HANDICAP_BASELINES.keys()),
            index=2
        )

        comparison = StrokesGainedBenchmarkEngine.compare_with_target(st.session_state.round_data, target_hcp)
        player_m = comparison["player_metrics"]
        base_m = comparison["baseline"]
        diffs = comparison["differentials"]

        st.markdown(f"### Confronto con il target: **{target_hcp}**")

        b1, b2, b3, b4 = st.columns(4)
        b1.metric("GIR %", f"{player_m['gir_pct']}%", delta=f"{diffs['gir_diff']}% vs Target")
        b2.metric("Fairway Hit %", f"{player_m['fairway_pct']}%", delta=f"{diffs['fairway_diff']}% vs Target")
        b3.metric("Media Putt (18b eq)", f"{player_m['putts_18h_equivalent']}", delta=f"{diffs['putts_diff']} putt", delta_color="normal")
        st.markdown("---")
        st.markdown(f"**Dispersione Maggiore Identificata:** `{comparison['biggest_bottleneck']}` (+{comparison['max_strokes_lost']} colpi persi stimati)")


# ---------------------------------------------------------
# TAB 6: RULES ACADEMY (STUDIO REGOLE R&A & QUIZ)
# ---------------------------------------------------------
with nav_rules:
    render_rules_academy()


# ---------------------------------------------------------
# TAB 7: ADMIN & USERS MANAGEMENT (EXCLUSIVE FOR STEFANO)
# ---------------------------------------------------------
if current_user.is_admin and nav_admin:
    with nav_admin:
        st.subheader("👑 Pannello di Controllo Amministratore (Stefano)")
        st.caption("Pannello riservato all'Amministratore di Sistema per visualizzare tutti i membri, reimpostare password e monitorare il circolo.")

        all_users = auth_manager.get_all_users()

        col_a1, col_a2, col_a3 = st.columns(3)
        col_a1.metric("Membri Totali Iscritti", len(all_users))
        strafatti_count = sum(1 for u in all_users if u.group == "strafatti")
        amici_count = sum(1 for u in all_users if u.group == "amici")
        col_a2.metric("Membri Gruppo Strafatti", strafatti_count)
        col_a3.metric("Membri Gruppo Amici", amici_count)

        st.markdown("---")
        st.markdown("### 📋 Registro Membri & Credenziali")

        users_table_data = []
        for u in all_users:
            role_tag = "👑 Admin" if u.is_admin else "Membro"
            status_tag = "⚠️ Primo Accesso (In Attesa)" if u.must_change_password else "✅ Password Attiva"
            users_table_data.append({
                "User ID": u.user_id,
                "Nome": u.first_name,
                "Cognome": u.last_name,
                "Gruppo": "Strafatti" if u.group == "strafatti" else "Amici",
                "Ruolo": role_tag,
                "Stato Password": status_tag,
                "Provider IA": u.ai_config.provider.upper()
            })

        st.dataframe(pd.DataFrame(users_table_data), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### 🔧 Gestione Credenziali & Azioni Rapide")

        target_user_id = st.selectbox(
            "Seleziona l'utente su cui intervenire:",
            options=[u.user_id for u in all_users],
            format_func=lambda uid: next(f"{u.first_name} {u.last_name} ({u.group}) — ID: {u.user_id}" for u in all_users if u.user_id == uid)
        )

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.button("🔄 Reimposta Password Utente", use_container_width=True, help="Reimposta la password al valore iniziale del Cognome"):
                ok_rst, msg_rst = auth_manager.admin_reset_user_password(target_user_id)
                if ok_rst:
                    st.success(msg_rst)
                    st.rerun()
                else:
                    st.error(msg_rst)

        with col_act2:
            if st.button("🗑️ Elimina Utente (Non Amministratore)", type="secondary", use_container_width=True):
                ok_del, msg_del = auth_manager.admin_delete_user(target_user_id)
                if ok_del:
                    st.success(msg_del)
                    st.rerun()
                else:
                    st.error(msg_del)

        st.markdown("---")
        st.markdown("### 🤖 Configurazione & Chat Telegram del Circolo")
        st.caption("Stato globale del server Telegram e associazioni chat dei membri.")

        col_tadmin1, col_tadmin2 = st.columns([3, 2])
        with col_tadmin1:
            admin_tok = tg_manager.get_token()
            new_admin_tok = st.text_input("TELEGRAM_BOT_TOKEN globale:", value=admin_tok, type="password", key="admin_tg_tok_input")
            if st.button("💾 Salva Token Globale", key="admin_save_tg_btn"):
                tg_manager.set_token(new_admin_tok)
                bot_service.restart(token=new_admin_tok)
                st.success("Token salvato e Bot Server aggiornato!")
                st.rerun()

            ok_adm, msg_adm, adm_uname = tg_manager.test_token(new_admin_tok)
            if ok_adm:
                st.success(f"✅ Bot Telegram Operativo: **@{adm_uname}**")
                st.markdown(f"[👉 **Apri Bot su Telegram (@{adm_uname})**](https://t.me/{adm_uname})")
            elif new_admin_tok:
                st.warning(f"Verifica connessione: {msg_adm}")

        with col_tadmin2:
            st.markdown("<b>Chat Collegate:</b>", unsafe_allow_html=True)
            users_map = tg_manager.load_users_map()
            if not users_map:
                st.info("Nessun membro ha ancora collegato la propria chat Telegram. I membri possono collegarsi istantaneamente tramite QR Code o cliccando sul pulsante nella barra laterale.")
            else:
                for cid, data in users_map.items():
                    st.markdown(f"• Chat ID <code>{cid}</code> ➔ <b>{data.get('first_name')}</b> ({data.get('group_name', '').upper()}) — Campo: <i>{data.get('active_course_name')}</i>", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 📬 Casella Messaggi Utenti & Assistenza (Inbox)")
        st.caption("Messaggi inviati dagli utenti tramite il modulo 'Contatta l'Amministratore' presente nella Home Page.")
        _render_inbox_messages(current_user, inbox_mgr, key_suffix="admin")


# =========================================================
# GLOBAL FOOTER & INTELLECTUAL PROPERTY
# =========================================================
render_footer()
