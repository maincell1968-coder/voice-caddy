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
from core.user_profile import UserProfile, PlayerCategory, parse_user_setup_transcript, ClubDetail, ShaftFlex, get_default_bag
from core.visualizer import GolfHoleVisualizer
from core.demo_data import get_demo_golf_round

PROJECT_ROOT = Path(__file__).resolve().parent
PROFILE_PATH = PROJECT_ROOT / "user_profile.json"

st.set_page_config(
    page_title="Voice Caddy | Golf Performance Analyzer",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium Styling
st.markdown("""
    <style>
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
    </style>
""", unsafe_allow_html=True)

# Registries and DB
db = DatabaseManager()
course_registry = CourseRegistry(storage_dir=PROJECT_ROOT / "courses")

# Load persistent profile or fallback
saved_profile = UserProfile.load_from_file(PROFILE_PATH)
if "user_profile" not in st.session_state:
    st.session_state.user_profile = saved_profile or UserProfile(
        player_name="Giocatore Conero",
        handicap=14.0,
        category=PlayerCategory.CATEGORY_2,
        preferred_ball="Titleist Pro V1",
        clubs_in_bag=get_default_bag()
    )

if "round_data" not in st.session_state:
    st.session_state.round_data = None
if "transcript" not in st.session_state:
    st.session_state.transcript = None
if "selected_course_id" not in st.session_state:
    st.session_state.selected_course_id = CONERO_GOLF_CLUB.course_id


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


# Sidebar Setup
with st.sidebar:
    st.title("⛳ Voice Caddy")
    st.caption("AI Caddie & PGA Performance Analytics Engine")

    api_key = st.text_input("OpenAI API Key", type="password", value=os.environ.get("OPENAI_API_KEY", ""))
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key

    st.markdown("---")
    st.subheader("⛳ Selezione Campo da Gioco")
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
    st.subheader("🎮 Prova Rapida (Senza Audio)")
    if st.button("Carica Giro Demo (18 Buche Conero)", use_container_width=True):
        demo_round = get_demo_golf_round()
        st.session_state.round_data = demo_round
        st.session_state.transcript = "Trascrizione generata per il Giro Dimostrativo PGA a 18 buche al Conero Golf Club."
        db.save_round(demo_round)
        st.success("✅ Giro Demo caricato e registrato con successo!")
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
        options=["OpenAI Whisper Cloud (Consigliato)", "Faster-Whisper Locale (Offline)"],
        index=0
    )

    whisper_model_local = "base"
    if "Locale" in whisper_engine:
        whisper_model_local = st.selectbox(
            "Modello Locale:",
            options=["base", "small", "medium"],
            index=0
        )

    ai_model_name = st.selectbox(
        "Modello LLM Coach:",
        options=["gpt-4o", "gpt-4o-mini"],
        index=0
    )

    process_btn = st.button("🚀 Analizza Partita Ora", type="primary", use_container_width=True, disabled=not uploaded_files)


# Process Audio Pipeline
if process_btn and uploaded_files:
    if not os.environ.get("OPENAI_API_KEY"):
        st.error("Inserisci la tua OpenAI API Key nella barra laterale.")
        st.stop()

    temp_paths = []
    try:
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.info("⚙️ Preparazione e caricamento note vocali...")
        progress_bar.progress(20)

        for file in uploaded_files:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.name}")
            temp_file.write(file.read())
            temp_file.close()
            temp_paths.append(temp_file.name)

        status_text.info(f"🎙️ Trascrizione speech-to-text in corso ({whisper_engine})...")
        progress_bar.progress(45)

        is_cloud = "Cloud" in whisper_engine
        engine_mode = "cloud" if is_cloud else "local"
        audio_engine = VoiceCaddyAudioEngine(model_size=whisper_model_local)

        if len(temp_paths) == 1:
            transcript_text, meta = audio_engine.transcribe(
                temp_paths[0], engine_mode=engine_mode, api_key=os.environ.get("OPENAI_API_KEY")
            )
        else:
            transcript_text, meta = audio_engine.transcribe_multiple(
                temp_paths, engine_mode=engine_mode, api_key=os.environ.get("OPENAI_API_KEY")
            )

        st.session_state.transcript = transcript_text

        status_text.info(f"🧠 Analisi semantica NLU ({ai_model_name}) per {st.session_state.user_profile.category.value} su {active_course.name}...")
        progress_bar.progress(70)

        raw_round_data = parse_golf_audio_transcript(
            transcript_text=transcript_text,
            user_profile=st.session_state.user_profile,
            course=active_course,
            model_name=ai_model_name
        )

        status_text.info("📊 Riconciliazione matematica e calcolo metriche balistiche...")
        progress_bar.progress(90)

        validated_data = GolfMetricsCalculator.recompute_and_reconcile(raw_round_data)
        st.session_state.round_data = validated_data

        db.save_round(validated_data)

        progress_bar.progress(100)
        status_text.success("✅ Partita analizzata e salvata nello storico con successo!")
        st.rerun()

    except AudioProcessingError as ape:
        st.error(f"Errore Audio: {ape}")
    except Exception as e:
        st.error(f"Si è verificato un errore durante l'elaborazione: {e}")
    finally:
        for p in temp_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


# Navigation Tabs
nav_tab1, nav_tab2, nav_tab3, nav_tab4 = st.tabs([
    "📊 Live Dashboard & Diagnosi PGA",
    "🏌️‍♂️ Profilo Giocatore & Sacca Mazze",
    "📈 Storico Partite & Trend",
    "🎯 Benchmark & Strokes Gained"
])


# TAB 1: LIVE DASHBOARD & PGA DIAGNOSIS
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
            st.caption(f"Partita di {data.round_info.holes_played} Buche • Data: {data.round_info.date or 'Oggi'} • {cat_badge}")

        with col_btn:
            html_rep = PDFReportGenerator.generate_html_report(data)
            st.download_button(
                label="📥 Scarica Report PDF / HTML",
                data=html_rep,
                file_name=f"VoiceCaddy_Report_{data.round_info.date or 'Round'}.html",
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
            st.caption(f"Valutazione strategica tarata sull'Handicap del giocatore ({st.session_state.user_profile.handicap}): Target Ideale vs Atterraggio Reale.")

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
        st.info("🏌️‍♂️ Carica una nota vocale dal pannello laterale oppure clicca su 'Carica Giro Demo' per iniziare.")


# TAB 2: USER PROFILE & MANUAL EQUIPMENT FORM
with nav_tab2:
    st.subheader("🏌️‍♂️ Scheda Profilo Giocatore & Attrezzatura Sacca")
    st.caption("I dati del profilo e la composizione della sacca vengono salvati in modo permanente su disco per tutte le future sessioni.")

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
            if not os.environ.get("OPENAI_API_KEY"):
                st.error("Inserisci la tua OpenAI API Key nella barra laterale.")
                st.stop()

            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{setup_audio_file.name}") as tmp_s:
                tmp_s.write(setup_audio_file.read())
                tmp_s_path = tmp_s.name

            try:
                audio_eng = VoiceCaddyAudioEngine()
                setup_transcript, _ = audio_eng.transcribe(tmp_s_path, engine_mode="cloud", api_key=os.environ.get("OPENAI_API_KEY"))
                parsed_profile = parse_user_setup_transcript(setup_transcript)
                parsed_profile.save_to_file(PROFILE_PATH)
                st.session_state.user_profile = parsed_profile
                st.success(f"✅ Profilo estratto e salvato su disco! Handicap: {parsed_profile.handicap}")
                st.rerun()
            except Exception as e:
                st.error(f"Errore estrazione profilo: {e}")
            finally:
                if os.path.exists(tmp_s_path):
                    os.remove(tmp_s_path)

    with col_prof_r:
        st.markdown("### 🎒 Composizione Sacca Bastoni (Modifica Manuale)")

        clubs_data = []
        for idx, c in enumerate(prof.clubs_in_bag):
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

        if st.button("💾 Salva Scheda Profilo & Sacca (Permanente)", type="primary", use_container_width=True):
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

            st.session_state.user_profile.player_name = m_name
            st.session_state.user_profile.handicap = m_hcp
            st.session_state.user_profile.category = new_cat
            st.session_state.user_profile.preferred_ball = m_ball
            st.session_state.user_profile.clubs_in_bag = updated_clubs

            st.session_state.user_profile.save_to_file(PROFILE_PATH)
            st.success("✅ Scheda Profilo e Sacca salvate in modo permanente su disco!")


# TAB 3: HISTORICAL ROUNDS & TRENDS
with nav_tab3:
    st.subheader("📈 Storico Partite & Progressioni nel Tempo")
    rounds_list = db.get_all_rounds()

    if not rounds_list:
        st.info("Nessuna partita ancora registrata nel database. Carica una nota vocale o clicca su 'Carica Giro Demo' per iniziare!")
    else:
        hist_stats = db.get_historical_stats()

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
            format_func=lambda x: next(f"ID #{r['id']} — {r['course_name']} ({r['date_played']}) — Score: {r['total_score']}" for r in rounds_list if r["id"] == x)
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


# TAB 4: BENCHMARK & STROKES GAINED
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
        b4.metric("Scrambling %", f"{player_m['scrambling_pct']}%", delta=f"{diffs['scrambling_diff']}% vs Target")

        st.markdown("---")
        st.markdown(f"**Dispersione Maggiore Identificata:** `{comparison['biggest_bottleneck']}` (+{comparison['max_strokes_lost']} colpi persi stimati)")
