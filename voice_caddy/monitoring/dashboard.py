from __future__ import annotations

import sys
import json
import time
from pathlib import Path
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# Setup path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VOICE_CADDY_DIR = PROJECT_ROOT / "voice_caddy"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(VOICE_CADDY_DIR) not in sys.path:
    sys.path.insert(0, str(VOICE_CADDY_DIR))

try:
    from monitoring.runner import MonitoringOrchestrator
except ImportError:
    from voice_caddy.monitoring.runner import MonitoringOrchestrator

from core.auth import AuthManager
from core.db import DatabaseManager
from core.advanced_golf_stats import AdvancedGolfStatsEngine

st.set_page_config(
    page_title="Voice Caddy Pro — Zero-Cost Telemetry (Admin)",
    page_icon="👑",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for rich aesthetics and dark mode
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.01));
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        backdrop-filter: blur(8px);
        margin-bottom: 12px;
    }
    .metric-val {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.5px;
    }
    .metric-lbl {
        font-size: 0.85rem;
        text-transform: uppercase;
        color: #94a3b8;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .badge-zero {
        background: linear-gradient(90deg, #10b981, #059669);
        color: white;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        display: inline-block;
    }
    .badge-active {
        background: linear-gradient(90deg, #3b82f6, #2563eb);
        color: white;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        display: inline-block;
    }
    .admin-header-pill {
        background: linear-gradient(90deg, #1e293b, #0f172a);
        border: 1px solid #f59e0b;
        padding: 8px 16px;
        border-radius: 25px;
        display: inline-flex;
        align-items: center;
        gap: 10px;
        color: #f59e0b;
        font-weight: 700;
        font-size: 0.95rem;
    }
</style>
""", unsafe_allow_html=True)

auth_mgr = AuthManager()
db_mgr = DatabaseManager()

# =====================================================================
# GATE DI SICUREZZA: ACCESSO ESCLUSIVO AMMINISTRATORE (STEFANO)
# =====================================================================
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

if not st.session_state.admin_logged_in:
    col_l1, col_l2, col_l3 = st.columns([1, 1.8, 1])
    with col_l2:
        st.markdown("""
            <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                        border: 2px solid #f59e0b; border-radius: 16px; padding: 30px; margin-top: 50px;
                        box-shadow: 0 10px 30px rgba(0,0,0,0.5); text-align: center;">
                <span style="font-size: 3rem;">👑</span>
                <h2 style="color: #f59e0b; margin-top: 10px;">Ambiente di Monitoraggio & Golf Intelligence</h2>
                <p style="color: #94a3b8; font-size: 0.95rem;">
                    Questo ambiente di osservabilità e telemetria è <b>riservato esclusivamente all'Amministratore di Sistema</b>.
                    Inserisci la password di amministrazione per sbloccare la console.
                </p>
            </div>
        """, unsafe_allow_html=True)

        with st.form("form_admin_monitoring_login"):
            admin_pwd = st.text_input("Password Amministratore (Stefano):", type="password", placeholder="Inserisci password")
            submit_login = st.form_submit_button("🔓 Accedi alla Console Riservata", type="primary", use_container_width=True)

            if submit_login:
                ok_auth, user_rec, msg = auth_manager_attempt = auth_mgr.authenticate_strafatti("Stefano", admin_pwd)
                if ok_auth and user_rec.is_admin:
                    st.session_state.admin_logged_in = True
                    st.session_state.admin_user = user_rec
                    st.success("✅ Autenticazione Amministratore riuscita!")
                    st.rerun()
                else:
                    st.error("⛔ Accesso negato: password amministratore non valida.")

        st.caption("🔒 *Conforme alla SafeVault Policy e alle regole di accesso deny-by-default.*")
    st.stop()


# =====================================================================
# CONSOLE AMMINISTRATORE ATTIVA (AUTENTICATA)
# =====================================================================
@st.cache_resource
def get_orchestrator():
    """Inizializza una volta l'orchestratore per il monitoraggio zero-cost."""
    db_path = VOICE_CADDY_DIR / "voice_caddy.db"
    return MonitoringOrchestrator(db_path=db_path, exporter_port=9102, cycle_interval_seconds=15)


orchestrator = get_orchestrator()

# Header Amministratore
col_h1, col_h2, col_h3 = st.columns([2.5, 1.2, 0.8])
with col_h1:
    st.title("🛡️ Console di Monitoraggio & Golf Intelligence")
    st.markdown('<span class="admin-header-pill">👑 Ambiente Esclusivo Amministratore — Stefano Pirani</span>', unsafe_allow_html=True)
    st.caption("Salute dei server, funnel Telegram ➡️ Browser e analisi statistica avanzata a costo token zero (Zero LLM Tokens)")
with col_h2:
    st.markdown("<div style='text-align: right; padding-top: 15px;'>", unsafe_allow_html=True)
    if st.button("🔄 Aggiorna Telemetria", use_container_width=True):
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
with col_h3:
    st.markdown("<div style='text-align: right; padding-top: 15px;'>", unsafe_allow_html=True)
    if st.button("🚪 Esci", use_container_width=True):
        st.session_state.admin_logged_in = False
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# Esegui scansione telemetrica real-time
telemetry = orchestrator.run_single_iteration()
server_res = telemetry["server"]
tg_res = telemetry["telegram"]
brw_res = telemetry["browser"]
adv_res = telemetry["advisor"]

# Top KPI Row
k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    is_up = server_res.get("server_up", False)
    stat_color = "#10b981" if is_up else "#ef4444"
    stat_text = "ONLINE" if is_up else "OFFLINE"
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-lbl">Stato Server (Port 8501)</div>
        <div class="metric-val" style="color: {stat_color};">{stat_text}</div>
        <div style="font-size: 0.8rem; color: #94a3b8;">Latenza: <b>{server_res.get('latency_ms', 0)} ms</b></div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    st.markdown("""
    <div class="metric-card">
        <div class="metric-lbl">Costo Token LLM</div>
        <div class="metric-val" style="color: #10b981;">0 Tokens</div>
        <div><span class="badge-zero">100% GRATUITO (0.00€)</span></div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    rate = brw_res.get("completion_rate_pct", 0.0)
    rate_col = "#10b981" if rate >= 50 else ("#f59e0b" if rate >= 20 else "#ef4444")
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-lbl">Tasso Completamento Funnel</div>
        <div class="metric-val" style="color: {rate_col};">{rate}%</div>
        <div style="font-size: 0.8rem; color: #94a3b8;">Telegram ➡️ Browser</div>
    </div>
    """, unsafe_allow_html=True)

with k4:
    active_now = tg_res.get("active_now", 0)
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-lbl">Giocatori Attivi su Telegram</div>
        <div class="metric-val" style="color: #3b82f6;">{active_now}</div>
        <div><span class="badge-active">In Campo Live</span></div>
    </div>
    """, unsafe_allow_html=True)

with k5:
    brw_total = brw_res.get("browser_completed", 0)
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-lbl">Giri Consolidati a DB</div>
        <div class="metric-val" style="color: #a855f7;">{brw_total}</div>
        <div style="font-size: 0.8rem; color: #94a3b8;">Scorecard Salvate</div>
    </div>
    """, unsafe_allow_html=True)

# Main Navigation Tabs nell'ambiente dedicato
tab_stats_golf, tab_funnel, tab_server, tab_agents_ecosystem, tab_telemetry = st.tabs([
    "📊 Analisi Statistica Golf Intelligence",
    "🏌️ Funnel Telegram ➡️ Browser",
    "⚡ Monitoraggio Server & Errori",
    "🤖 Suite Agenti Funzionali & Gratuiti",
    "🔍 Telemetria & Lifecycle Hooks"
])

# ----------------- TAB 1: ANALISI STATISTICA GOLF INTELLIGENCE -----------------
with tab_stats_golf:
    st.subheader("⛳ Analisi Statistica Avanzata (Dati Elaborati dall'Esperto di Golf)")
    st.caption("Calcolo deterministico a costo token zero basato sui giri storici e sui dati telemetrici delle partite.")

    # Filtro Giocatore
    all_users = auth_mgr.get_all_users()
    user_options = ["Tutti i Giocatori (Aggregato Circolo)"] + [f"{u.first_name} {u.last_name} ({u.user_id})" for u in all_users]
    selected_user_str = st.selectbox("Seleziona il bacino di analisi statistica:", options=user_options, index=0)

    # Carica giri reali dal database
    selected_uid = None
    if selected_user_str != "Tutti i Giocatori (Aggregato Circolo)":
        selected_uid = selected_user_str.split("(")[-1].replace(")", "").strip()

    rounds_records = db_mgr.get_all_rounds(user_id=selected_uid)
    loaded_rounds = []
    for r in rounds_records:
        rd = db_mgr.get_round_by_id(r["id"])
        if rd:
            loaded_rounds.append(rd)

    stats_engine = AdvancedGolfStatsEngine()
    player_hcp = 18.0
    if selected_uid:
        try:
            from core.user_profile import UserProfile
            prof = UserProfile.load_for_user(selected_uid)
            player_hcp = prof.handicap
        except Exception:
            player_hcp = 18.0

    report = stats_engine.compile_full_player_report(loaded_rounds, player_handicap=player_hcp)
    holes_analyzed = report.get("total_holes_analyzed", 0)

    if holes_analyzed == 0:
        st.warning("⚠️ Nessuna buca registrata per il filtro selezionato. Registra partite da Telegram per visualizzare le metriche balistiche.")
    else:
        st.success(f"✅ Analisi condotta su **{len(loaded_rounds)} giri storici** e **{holes_analyzed} buche complessive** (Handicap di riferimento: **{player_hcp}**).")

        # Visualizzazione delle 8 Aree Statistiche in Griglia
        st.markdown("---")
        g_row1_c1, g_row1_c2 = st.columns(2)

        # 1. DISPERSIONE OFF-THE-TEE
        with g_row1_c1:
            st.markdown("#### 1. 🎯 Ellisse di Dispersione & Miss-Side (Tee Shot)")
            disp = report["dispersion"]
            m_tend = disp["miss_tendency"]

            fig_disp = go.Figure(data=[go.Pie(
                labels=["Miss Sinistra (Hook/Pull)", "Centro Fairway", "Miss Destra (Slice/Push)"],
                values=[m_tend["left_pct"], m_tend["center_fairway_pct"], m_tend["right_pct"]],
                hole=.45,
                marker_colors=["#ef4444", "#10b981", "#3b82f6"]
            )])
            fig_disp.update_layout(
                title=f"Distribuzione Tee Shots: {disp['primary_bias']}",
                margin=dict(l=10, r=10, t=40, b=10),
                height=260,
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_disp, use_container_width=True)
            st.markdown(f"""
            - **Distanza Media Partenze:** `{disp['avg_distance_m']} m`
            - **Dispersione Laterale Stimata (±):** `{disp['dispersion_lateral_std_m']} m`
            - 💡 **Consiglio Tattico:** *{disp['tactical_advice']}*
            """)

        # 2. LIE-TO-GIR MATRIX
        with g_row1_c2:
            st.markdown("#### 2. 🌿 Lie-to-GIR Conversion Matrix (Approcci)")
            ltg = report["lie_to_gir"]
            c_mat = ltg["conversion_matrix"]

            lies = ["Fairway", "Rough", "Bunker", "Tee (Par 3)"]
            rates = [
                c_mat.get("fairway", {}).get("gir_pct", 0),
                c_mat.get("rough", {}).get("gir_pct", 0),
                c_mat.get("bunker", {}).get("gir_pct", 0),
                c_mat.get("tee", {}).get("gir_pct", 0)
            ]

            fig_gir = go.Figure(data=[go.Bar(
                x=lies,
                y=rates,
                marker_color=["#10b981", "#f59e0b", "#d97706", "#3b82f6"],
                text=[f"{r}%" for r in rates],
                textposition="auto"
            )])
            fig_gir.update_layout(
                title="Green Presi in Regolazione (GIR %) per Tipologia di Lie",
                yaxis=dict(range=[0, 100]),
                margin=dict(l=10, r=10, t=40, b=10),
                height=260,
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_gir, use_container_width=True)
            st.info(f"💡 **Impatto del Lie:** {ltg['key_finding']} (Penalità Rough: -{ltg['lie_penalty_rough_vs_fairway']}%)")

        st.markdown("---")
        g_row2_c1, g_row2_c2 = st.columns(2)

        # 3. STROKES GAINED 4-WAY
        with g_row2_c1:
            st.markdown("#### 3. 📈 Strokes Gained 4-Way (Metodo Broadie)")
            sg = report["strokes_gained"]

            categories = ["Off-The-Tee", "Approach", "Around-Green", "Putting"]
            sg_vals = [sg["sg_off_the_tee"], sg["sg_approach"], sg["sg_around_green"], sg["sg_putting"]]
            colors = ["#10b981" if v >= 0 else "#ef4444" for v in sg_vals]

            fig_sg = go.Figure(data=[go.Bar(
                x=categories,
                y=sg_vals,
                marker_color=colors,
                text=[f"{v:+.2f}" for v in sg_vals],
                textposition="auto"
            )])
            fig_sg.update_layout(
                title=f"Strokes Gained vs Handicap {player_hcp} (Totale: {sg['sg_total']:+.2f})",
                margin=dict(l=10, r=10, t=40, b=10),
                height=260,
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_sg, use_container_width=True)
            st.warning(f"⚠️ **Settore più debole:** {sg['recommendation']}")

        # 4. RESILIENZA MENTALE (BOUNCE-BACK)
        with g_row2_c2:
            st.markdown("#### 4. 🧠 Bounce-Back Factor (Resilienza Mentale)")
            bb = report["bounce_back"]

            b_rate = bb.get("bounce_back_rate_pct", 0)
            fig_bb = go.Figure(go.Indicator(
                mode="gauge+number",
                value=b_rate,
                title={'text': "Tasso di Recupero Post-Double Bogey (%)"},
                gauge={
                    'axis': {'range': [0, 100]},
                    'bar': {'color': "#a855f7"},
                    'steps': [
                        {'range': [0, 25], 'color': "rgba(239, 68, 68, 0.3)"},
                        {'range': [25, 50], 'color': "rgba(245, 158, 11, 0.3)"},
                        {'range': [50, 100], 'color': "rgba(16, 185, 129, 0.3)"}
                    ]
                }
            ))
            fig_bb.update_layout(height=260, margin=dict(l=10, r=10, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_bb, use_container_width=True)
            st.markdown(f"""
            - **Opportunità di Rimbalzo:** `{bb.get('opportunities', 0)} buche`
            - **Par o Birdie Immediati:** `{bb.get('recovered_holes', 0)} buche`
            - 💡 **Diagnosi Psicologica:** *{bb.get('mental_diagnosis', 'N/D')}*
            """)

        st.markdown("---")
        g_row3_c1, g_row3_c2 = st.columns(2)

        # 5. PUTTING PER FASCE DI DISTANZA
        with g_row3_c1:
            st.markdown("#### 5. ⛳ Putting Performance per Fasce di Distanza")
            pz = report["putting_zones"]
            c_p1, c_p2, c_p3 = st.columns(3)
            c_p1.metric("Media Putt / Giro", f"{pz.get('avg_putts_per_round_18', 0)}")
            c_p2.metric("Pressure Putts (<1.5m)", f"{pz.get('pressure_putts_less_than_1_5m_pct', 0)}%")
            c_p3.metric("3-Putt Avoidance", f"{pz.get('three_putt_avoidance_pct', 0)}%")

            st.write(f"• **1-Putt Conversion:** `{pz.get('one_putt_pct', 0)}%` delle buche.")
            st.write(f"• **2-Putt Regolari:** `{pz.get('two_putt_pct', 0)}%` delle buche.")
            st.write(f"• **Valutazione Lag Putting (>7m):** *{pz.get('lag_putting_rating', 'Buono')}*")

        # 6. CADDY COMPLIANCE & FATIGUE
        with g_row3_c2:
            st.markdown("#### 6. 🛡️ Caddy Compliance ROI & Curva Affaticamento")
            cc = report["caddy_compliance"]
            fc = report["fatigue_curve"]

            st.markdown(f"""
            <div style="background:#131d2a; border-left:4px solid #10b981; border-radius:8px; padding:12px; margin-bottom:12px;">
                <b>🎯 Valore Strategico dell'IA (Caddy Compliance):</b><br>
                Seguendo il bastone e il bersaglio conservativo raccomandato, il giocatore risparmia in media 
                <b style="color:#10b981;">{cc.get('strokes_saved_by_caddy_discipline', 0.8)} colpi a buca</b> 
                rispetto a quando forza la giocata in direzione di ostacoli.
            </div>
            """, unsafe_allow_html=True)

            if fc.get("has_18_holes"):
                st.write(f"• **Front 9 (Buche 1-9):** {fc['front_9_score_to_par']:+d} dal par ({fc['front_gir_count']} GIR)")
                st.write(f"• **Back 9 (Buche 10-18):** {fc['back_9_score_to_par']:+d} dal par ({fc['back_gir_count']} GIR)")
                st.info(f"💡 **Diagnosi Ritmo/Fisico:** {fc['fatigue_diagnosis']}")
            else:
                st.caption(f"ℹ️ *{fc.get('note')}*")

# ----------------- TAB 2: FUNNEL TELEGRAM -> BROWSER -----------------
with tab_funnel:
    st.subheader("Tracciamento del Doppio Flusso Utente (Telegram ➡️ Browser)")
    st.info(f"**Diagnosi Funnel:** {brw_res.get('funnel_diagnosis', 'In analisi')}")

    f_col1, f_col2 = st.columns([1, 1])

    with f_col1:
        t_start = tg_res.get("sessions_started", 0)
        t_done = tg_res.get("sessions_completed", 0)
        b_done = brw_res.get("browser_completed", 0)

        fig_funnel = go.Figure(go.Funnel(
            y=["1. Avvio Partita su Telegram", "2. Conclusione 18 Buche su Telegram", "3. Revisione & Salvataggio su Browser"],
            x=[t_start, t_done, b_done],
            textinfo="value+percent initial",
            marker={
                "color": ["#3b82f6", "#06b6d4", "#10b981"],
                "line": {"width": [1, 1, 1], "color": ["#1e3a8a", "#0891b2", "#047857"]}
            }
        ))
        fig_funnel.update_layout(
            title="Funnel di Conversione Utente (Volumi & Tassi di Drop-off)",
            margin=dict(l=20, r=20, t=50, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#f8fafc")
        )
        st.plotly_chart(fig_funnel, use_container_width=True)

    with f_col2:
        st.markdown("### Dettaglio Tappe del Percorso")
        breakdown_df = pd.DataFrame([
            {"Fase": "1. Avvio su Telegram", "Descrizione": "Giocatore invia /start o /nuovogiro, seleziona circolo e tee", "Volumi": t_start, "Stato": "Inizio"},
            {"Fase": "2. Conclusione Telegram", "Descrizione": "Completamento buche, emissione score finale su bot", "Volumi": t_done, "Stato": "Giro Concluso"},
            {"Fase": "3. Completamento Browser", "Descrizione": "Accesso alla dashboard web Streamlit, visualizzazione 3D, export PDF", "Volumi": b_done, "Stato": "Consolidato a DB"},
        ])
        st.dataframe(breakdown_df, use_container_width=True, hide_index=True)

        st.markdown("### Monitoraggio Sessioni in Stallo (Drop-out)")
        stalled_count = tg_res.get("stalled_count", 0)
        if stalled_count > 0:
            st.warning(f"⚠️ Attenzione: {stalled_count} sessione/i risultano in stallo (nessun colpo registrato da oltre 45 minuti).")
        else:
            st.success("✅ Nessun giocatore in stallo anomalo sul percorso.")

# ----------------- TAB 3: MONITORAGGIO SERVER & ERRORI -----------------
with tab_server:
    st.subheader("Disponibilità dell'Infrastruttura (ServerMonitorAgent)")
    s1, s2, s3 = st.columns(3)

    with s1:
        st.markdown(f"**Target URL:** `{orchestrator.server_agent.target_url}`")
        st.markdown(f"**Uptime Stimato:** `{server_res.get('uptime_seconds', 0)} secondi`")
    with s2:
        st.markdown(f"**Porta Streamlit (8501):** `{'APERTA (IN ASCOLTO)' if orchestrator.server_agent.state.get('port_8501_open') else 'CHIUSA'}`")
        st.markdown(f"**Porta Prometheus (9102):** `{'APERTA' if orchestrator.exporter.is_running else 'CHIUSA'}`")
    with s3:
        st.markdown(f"**Errori 5xx Rilevati:** `{server_res.get('errors_5xx', 0)}`")
        u_cfg = orchestrator.server_agent.uptimerobot_api_key != ""
        st.markdown(f"**UptimeRobot API:** `{'CONFIGURATA' if u_cfg else 'MODALITÀ PROBE LOCALE'}`")

    # Gauge Latenza
    fig_lat = go.Figure(go.Indicator(
        mode="gauge+number",
        value=server_res.get("latency_ms", 0),
        title={'text': "Latenza Risposta HTTP (ms)"},
        gauge={
            'axis': {'range': [0, 800]},
            'bar': {'color': "#38bdf8"},
            'steps': [
                {'range': [0, 150], 'color': "rgba(16, 185, 129, 0.4)"},
                {'range': [150, 400], 'color': "rgba(245, 158, 11, 0.4)"},
                {'range': [400, 800], 'color': "rgba(239, 68, 68, 0.4)"}
            ]
        }
    ))
    fig_lat.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=20), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_lat, use_container_width=True)

# ----------------- TAB 4: SUITE AGENTI FUNZIONALI -----------------
with tab_agents_ecosystem:
    st.subheader("Suite di Agenti Specializzati e Gratuiti per Voice Caddy Pro")
    st.caption("Progettata dall'agente GolfIntelligenceAdvisorAgent per estendere le funzionalità senza costi di inferenza.")

    agents_data = orchestrator.advisor_agent.execute_tool("suggest_free_specialized_agents_suite")
    for ag in agents_data["suite_agenti_specializzati_gratuiti"]:
        with st.container():
            st.markdown(f"""
            <div class="metric-card" style="margin-bottom: 15px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h4 style="margin: 0; color: #38bdf8;">🛡️ {ag['nome_agente']}</h4>
                    <span class="badge-zero">{ag['natura']}</span>
                </div>
                <p style="margin-top: 8px; color: #cbd5e1; font-size: 0.95rem;">{ag['ruolo']}</p>
                <div style="font-size: 0.85rem; color: #10b981;"><b>🎯 Utilità Progetto:</b> {ag['utilità']}</div>
            </div>
            """, unsafe_allow_html=True)

# ----------------- TAB 5: TELEMETRIA & LIFECYCLE HOOKS -----------------
with tab_telemetry:
    st.subheader("Ispezione Telemetria in Tempo Reale (Lifecycle Hooks)")
    
    t_c1, t_c2 = st.columns(2)
    with t_c1:
        st.markdown("### Endpoint Prometheus Scraped (/metrics)")
        st.code(orchestrator.prom_hook.render_prometheus_text(), language="text")

    with t_c2:
        st.markdown("### Ultimi Eventi Intercettati dagli Hook")
        all_m = orchestrator.prom_hook.get_all_metrics()
        recent = all_m.get("recent_events", [])
        if recent:
            st.dataframe(pd.DataFrame(recent), use_container_width=True)
        else:
            st.write("Nessun evento recente in memoria.")

    st.markdown("### Stato Persistente Locale (.state JSON)")
    states_col1, states_col2, states_col3 = st.columns(3)
    with states_col1:
        st.caption("ServerMonitorAgent State")
        st.json(orchestrator.server_agent.state)
    with states_col2:
        st.caption("TelegramSessionAgent State")
        st.json(orchestrator.tg_agent.state)
    with states_col3:
        st.caption("BrowserCompletionAgent State")
        st.json(orchestrator.browser_agent.state)
