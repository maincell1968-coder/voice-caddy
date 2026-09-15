import os
import tempfile
from pathlib import Path
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from core.audio import VoiceCaddyAudioEngine, AudioProcessingError
from core.parser import parse_golf_audio_transcript
from core.metrics import GolfMetricsCalculator
from core.schemas import GolfRoundData
from core.db import DatabaseManager
from core.strokes_gained import StrokesGainedBenchmarkEngine
from core.pdf_export import PDFReportGenerator
from core.course import CourseRegistry, CONERO_GOLF_CLUB, GolfCourse
from core.user_profile import UserProfile, PlayerCategory, parse_user_setup_transcript, ClubDetail, ShaftFlex, get_default_bag, sort_clubs_by_distance
from core.visualizer import GolfHoleVisualizer
from core.demo_data import get_demo_golf_round
from core.auth import AuthManager, AIUserConfig, UserRecord, STRAFATTI_INITIAL_MEMBERS
from core.ai_provider import test_ai_connection, AIProviderError

PROJECT_ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Voice Caddy Pro | Club & Performance Portal",
    page_icon="⛳",
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
            font-size: 1.15rem;
            color: #A0AEC0;
            margin-bottom: 0;
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
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Core Services & Session State Initialization
# ---------------------------------------------------------
auth_manager = AuthManager()
db = DatabaseManager()
course_registry = CourseRegistry(storage_dir=PROJECT_ROOT / "courses")

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


# =========================================================
# SCREEN 1: ACCESS GATE & LOGIN / PASSWORD CHANGE FLOW
# =========================================================
if st.session_state.auth_user is None:
    st.markdown("""
        <div class="landing-hero">
            <div class="landing-title">⛳ VOICE CADDY PRO</div>
            <div class="landing-subtitle">PGA Tour Performance Analytics & Club Portal • Accesso Riservato</div>
        </div>
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
                        Gli unici autorizzati sono: Stefano, Giorgio, Marco (Sebastianelli/Fiorani), Gianluca, Alessandro, Renzo, Luca.
                    </p>
                </div>
            """, unsafe_allow_html=True)

            with st.form("form_login_strafatti"):
                # Autocomplete / Selector or custom text
                member_names = [
                    "Stefano",
                    "Giorgio",
                    "Marco Sebastianelli",
                    "Marco Fiorani",
                    "Gianluca",
                    "Alessandro",
                    "Renzo",
                    "Luca"
                ]
                strafatti_user_input = st.selectbox(
                    "Seleziona il tuo Profilo Utente:",
                    options=member_names,
                    index=0
                )
                strafatti_pw_input = st.text_input(
                    "Password (al primo accesso per Stefano: Amministratore1968, per gli altri: Cognome):",
                    type="password",
                    help="Per Stefano inserisci Amministratore1968 al primo accesso, per gli altri il proprio Cognome."
                )
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
                            st.success(f"Bentornato {user.first_name}!")
                            st.rerun()
                    else:
                        st.error(f"⛔ {msg}")

        else:
            st.markdown("""
                <div style="text-align: center; margin-bottom: 20px;">
                    <h3 style="color: #3498DB; margin-bottom: 4px;">🤝 Login Riservato: Gruppo Amici</h3>
                    <p style="color: #94A3B8; font-size: 0.9rem;">
                        Inserisci il tuo Nome di battesimo e la Password (se è la prima volta, scrivi il tuo Cognome).
                    </p>
                </div>
            """, unsafe_allow_html=True)

            with st.form("form_login_amici"):
                amici_name_input = st.text_input("Il tuo Nome:", placeholder="es. Mario")
                amici_pw_input = st.text_input(
                    "Password (al primo accesso inserisci il tuo Cognome):",
                    type="password",
                    placeholder="es. Rossi"
                )
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
                                st.success(f"Bentornato {user.first_name}!")
                                st.rerun()
                        else:
                            st.error(f"⛔ {msg}")

    # Stop rendering remainder of the app until authenticated
    st.stop()


# =========================================================
# SCREEN 2: AUTHENTICATED USER DASHBOARD
# =========================================================
current_user: UserRecord = st.session_state.auth_user

# Load Per-User Golf Profile (handicap, bag, ball)
if "user_profile" not in st.session_state or st.session_state.user_profile.player_name != f"{current_user.first_name} {current_user.last_name}":
    st.session_state.user_profile = UserProfile.load_for_user(
        user_id=current_user.user_id,
        default_name=f"{current_user.first_name} {current_user.last_name}"
    )

# Header Bar with User Badge & Logout
header_left, header_right = st.columns([4, 1])
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
    st.title("⛳ Voice Caddy Pro")
    st.caption("AI Caddie & PGA Performance Analytics Engine")

    # ---------------------------------------------------------
    # BRING YOUR OWN AI (Zero Shared Tokens Architecture)
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("🤖 Il Tuo Motore IA Personale")
    st.caption("Ciascun giocatore utilizza esclusivamente la propria IA (Ollama locale gratuito o token personali).")

    user_ai = current_user.ai_config

    provider_options = ["Ollama (Locale Gratuito)", "OpenAI (Chiave Personale)", "Custom (Groq, DeepSeek, Together)"]
    current_idx = 0
    if user_ai.provider == "openai":
        current_idx = 1
    elif user_ai.provider == "custom":
        current_idx = 2

    chosen_provider_label = st.selectbox(
        "Provider IA Attivo:",
        options=provider_options,
        index=current_idx
    )

    new_provider = "ollama"
    if "OpenAI" in chosen_provider_label:
        new_provider = "openai"
    elif "Custom" in chosen_provider_label:
        new_provider = "custom"

    if new_provider == "ollama":
        ollama_url = st.text_input("URL Server Ollama:", value=user_ai.ollama_url or "http://localhost:11434")
        ollama_model = st.text_input("Nome Modello Ollama:", value=user_ai.ollama_model or "llama3.1", help="es. llama3.1, mistral, qwen2.5, phi4, deepseek-r1")
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

    st.markdown("---")
    st.subheader("🎮 Prova Rapida (Giro Demo)")
    if st.button("Carica Giro Demo PGA (18 Buche)", use_container_width=True):
        demo_round = get_demo_golf_round()
        st.session_state.round_data = demo_round
        st.session_state.transcript = "Trascrizione generata per il Giro Dimostrativo PGA a 18 buche al Conero Golf Club."
        db.save_round(demo_round, user_id=current_user.user_id, group_name=current_user.group)
        st.success("✅ Giro Demo caricato nel tuo profilo con successo!")
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
        options=["Faster-Whisper Locale (Offline Gratuito)", "OpenAI Whisper Cloud (Usa tua API Key)"],
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
# PROCESS AUDIO PIPELINE (Using User's Configured AI)
# ---------------------------------------------------------
if process_btn and uploaded_files:
    # Validate user AI configuration before consuming
    if user_ai.provider == "openai" and not user_ai.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        st.error("⚠️ Inserisci la tua OpenAI API Key personale nella barra laterale prima di avviare l'analisi.")
        st.stop()

    temp_paths = []
    try:
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.info("⚙️ Preparazione e caricamento note vocali...")
        progress_bar.progress(15)

        for file in uploaded_files:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.name}")
            temp_file.write(file.read())
            temp_file.close()
            temp_paths.append(temp_file.name)

        status_text.info(f"🎙️ Trascrizione speech-to-text in corso ({whisper_engine})...")
        progress_bar.progress(40)

        is_cloud = "Cloud" in whisper_engine
        engine_mode = "cloud" if is_cloud else "local"
        audio_engine = VoiceCaddyAudioEngine(model_size=whisper_model_local)

        whisper_api_key = user_ai.openai_api_key or os.environ.get("OPENAI_API_KEY", "")

        if len(temp_paths) == 1:
            transcript_text, meta = audio_engine.transcribe(
                temp_paths[0], engine_mode=engine_mode, api_key=whisper_api_key
            )
        else:
            transcript_text, meta = audio_engine.transcribe_multiple(
                temp_paths, engine_mode=engine_mode, api_key=whisper_api_key
            )

        st.session_state.transcript = transcript_text

        ai_desc = f"Ollama ({user_ai.ollama_model})" if user_ai.provider == "ollama" else f"OpenAI ({user_ai.openai_model})"
        status_text.info(f"🧠 Analisi semantica NLU tramite la tua IA ({ai_desc}) per {st.session_state.user_profile.category.value} su {active_course.name}...")
        progress_bar.progress(70)

        raw_round_data = parse_golf_audio_transcript(
            transcript_text=transcript_text,
            user_profile=st.session_state.user_profile,
            course=active_course,
            ai_config=user_ai
        )

        status_text.info("📊 Riconciliazione matematica e calcolo metriche balistiche...")
        progress_bar.progress(90)

        validated_data = GolfMetricsCalculator.recompute_and_reconcile(raw_round_data)
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
    "🏌️‍♂️ Profilo Personale & Sacca Mazze",
    "📈 Storico Partite & Trend",
    "🎯 Benchmark & Strokes Gained"
]
if current_user.is_admin:
    tab_titles.append("👑 Amministrazione & Utenti")

all_tabs = st.tabs(tab_titles)
nav_tab1, nav_tab2, nav_tab3, nav_tab4 = all_tabs[0], all_tabs[1], all_tabs[2], all_tabs[3]
nav_admin = all_tabs[4] if current_user.is_admin else None


# ---------------------------------------------------------
# TAB 1: LIVE DASHBOARD & PGA DIAGNOSIS
# ---------------------------------------------------------
with nav_tab1:
    data = st.session_state.round_data

    if data:
        summary = data.performance_summary
        diag = summary.professional_diagnosis

        rel_par = GolfMetricsCalculator.calculate_score_relation_to_par(data.holes)
        rel_par_str = f"+{rel_par}" if rel_par > 0 else ("Par" if rel_par == 0 else f"{rel_par}")

        col_head, col_btn = st.columns([4, 1])
        with col_head:
            st.title(f"⛳ {data.round_info.course_name or active_course.name}")
            cat_val = st.session_state.user_profile.category.value
            cat_badge = f"🎭 Tono IA: {cat_val}"
            st.caption(f"Giocatore: **{st.session_state.user_profile.player_name}** • Partita di {data.round_info.holes_played} Buche • Data: {data.round_info.date or 'Oggi'} • {cat_badge}")

        with col_btn:
            html_rep = PDFReportGenerator.generate_html_report(data)
            st.download_button(
                label="📥 Scarica Report PDF / HTML",
                data=html_rep,
                file_name=f"VoiceCaddy_{current_user.first_name}_{data.round_info.date or 'Round'}.html",
                mime="text/html",
                use_container_width=True
            )

        # Top KPI Metrics Cards
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("Score Finale", f"{summary.total_score} ({rel_par_str})")
        kpi2.metric("Fairway Presi (FIR)", f"{summary.fairway_accuracy_pct}%")
        kpi3.metric("Green in Regulation", f"{summary.gir_pct}%")
        kpi4.metric("Course Mgmt Score", f"{diag.course_management_score}/100")
        kpi5.metric("Scrambling %", f"{summary.scrambling_pct}%")

        st.markdown("---")

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
                with st.expander(f"Buca {h.hole_number} — Par {h.par} | Score: {h.score} | Putt: {h.putts}"):
                    map_col, table_col = st.columns([2, 3])

                    with map_col:
                        fig_map = GolfHoleVisualizer.create_hole_trajectory_map(h)
                        st.plotly_chart(fig_map, use_container_width=True)

                    with table_col:
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
# TAB 2: USER PROFILE & PERSONAL EQUIPMENT
# ---------------------------------------------------------
with nav_tab2:
    st.subheader(f"🏌️‍♂️ Scheda Profilo di {current_user.first_name} & Attrezzatura Sacca")
    st.caption("I dati del tuo profilo e la composizione della tua sacca sono memorizzati in modo permanente e isolato per il tuo account.")

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
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "Mazza": st.column_config.SelectboxColumn("Mazza", options=["Driver", "Legno 3", "Legno 5", "Ibrido 3", "Ibrido 4", "Ferro 4", "Ferro 5", "Ferro 6", "Ferro 7", "Ferro 8", "Ferro 9", "Pitching Wedge", "Gap Wedge (50°/52°)", "Sand Wedge (56°)", "Lob Wedge (60°)", "Putter"], required=True),
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

            st.session_state.user_profile.save_for_user(current_user.user_id)
            st.session_state["bag_save_success"] = f"✅ Profilo e Sacca di {current_user.first_name} salvati e riordinati con successo dal Driver al Putter!"
            st.rerun()


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
# TAB 5: ADMIN & USERS MANAGEMENT (EXCLUSIVE FOR STEFANO)
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
