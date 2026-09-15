import os
import tempfile
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from core.audio import VoiceCaddyAudioEngine
from core.parser import parse_golf_audio_transcript
from core.metrics import GolfMetricsCalculator
from core.schemas import GolfRoundData
from core.db import DatabaseManager
from core.strokes_gained import StrokesGainedBenchmarkEngine
from core.pdf_export import PDFReportGenerator
from core.course import CourseRegistry, CONERO_GOLF_CLUB, GolfCourse
from core.user_profile import UserProfile, PlayerCategory, parse_user_setup_transcript, ClubDetail, ShaftFlex
from core.visualizer import GolfHoleVisualizer


st.set_page_config(
    page_title="Voice Caddy | Golf Performance Analyzer",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
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
course_registry = CourseRegistry()

# Default initial equipment setup
DEFAULT_BAG = [
    ClubDetail(club_name="Driver", brand="TaylorMade", model_type="Qi10 / Stealth 2", shaft_flex=ShaftFlex.STIFF, carry_meters=220),
    ClubDetail(club_name="Legno 3", brand="Callaway", model_type="Paradym Ai Smoke", shaft_flex=ShaftFlex.STIFF, carry_meters=195),
    ClubDetail(club_name="Ibrido 4", brand="Ping", model_type="G430", shaft_flex=ShaftFlex.REGULAR, carry_meters=175),
    ClubDetail(club_name="Ferro 5", brand="Titleist", model_type="T200", shaft_flex=ShaftFlex.STIFF, carry_meters=160),
    ClubDetail(club_name="Ferro 7", brand="Titleist", model_type="T200", shaft_flex=ShaftFlex.STIFF, carry_meters=145),
    ClubDetail(club_name="Ferro 9", brand="Titleist", model_type="T200", shaft_flex=ShaftFlex.STIFF, carry_meters=125),
    ClubDetail(club_name="Pitching Wedge", brand="Titleist", model_type="Vokey SM9", shaft_flex=ShaftFlex.STIFF, carry_meters=110),
    ClubDetail(club_name="Sand Wedge (56°)", brand="Titleist", model_type="Vokey SM9", shaft_flex=ShaftFlex.STIFF, carry_meters=85),
    ClubDetail(club_name="Putter", brand="Scotty Cameron", model_type="Phantom X", shaft_flex=ShaftFlex.REGULAR, carry_meters=0)
]

# Session State Initialization
if "round_data" not in st.session_state:
    st.session_state.round_data = None
if "transcript" not in st.session_state:
    st.session_state.transcript = None
if "user_profile" not in st.session_state:
    st.session_state.user_profile = UserProfile(
        player_name="Giocatore Conero",
        handicap=14.0,
        category=PlayerCategory.CATEGORY_2,
        preferred_ball="Titleist Pro V1",
        clubs_in_bag=DEFAULT_BAG
    )
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

    styled_df = df.style.applymap(color_status, subset=["Status"])
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

    st.caption(f"📌 **{active_course.name}** ({active_course.city}) — Par Totale {active_course.total_par}")

    st.markdown("---")
    st.subheader("📁 Carica Note Vocali Partita")
    uploaded_files = st.file_uploader(
        "Seleziona file audio (.m4a, .mp3, .wav, .opus)",
        type=["m4a", "mp3", "wav", "aac", "opus", "ogg", "3gp", "amr"],
        accept_multiple_files=True
    )

    whisper_model = st.selectbox(
        "Modello Whisper",
        options=["medium", "small", "base", "large-v3"],
        index=0
    )

    process_btn = st.button("⚡ Analizza Partita Ora", type="primary", use_container_width=True, disabled=not uploaded_files)


# Process Audio Pipeline
if process_btn and uploaded_files:
    if not os.environ.get("OPENAI_API_KEY"):
        st.error("Inserisci la tua OpenAI API Key nella barra laterale.")
        st.stop()

    temp_paths = []
    try:
        progress_bar = st.progress(0)
        status_text = st.empty()

        status_text.info("🎙️ Conversione audio ed eliminazione rumori di fondo (ffmpeg)...")
        progress_bar.progress(20)

        for file in uploaded_files:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.name}")
            temp_file.write(file.read())
            temp_file.close()
            temp_paths.append(temp_file.name)

        status_text.info(f"🧠 Trascrizione speech-to-text in corso ({whisper_model})...")
        progress_bar.progress(45)

        audio_engine = VoiceCaddyAudioEngine(model_size=whisper_model)
        if len(temp_paths) == 1:
            transcript_text, meta = audio_engine.transcribe(temp_paths[0])
        else:
            transcript_text, meta = audio_engine.transcribe_multiple(temp_paths)

        st.session_state.transcript = transcript_text

        status_text.info(f"🧩 Analisi semantica NLU adattata a {st.session_state.user_profile.category.value} su {active_course.name}...")
        progress_bar.progress(70)

        raw_round_data = parse_golf_audio_transcript(
            transcript_text=transcript_text,
            user_profile=st.session_state.user_profile,
            course=active_course
        )

        status_text.info("📊 Riconciliazione matematica deterministica...")
        progress_bar.progress(90)

        validated_data = GolfMetricsCalculator.recompute_and_reconcile(raw_round_data)
        st.session_state.round_data = validated_data

        # Auto-save to SQLite DB
        db.save_round(validated_data)

        progress_bar.progress(100)
        status_text.success("✅ Partita analizzata e salvata!")

    except Exception as e:
        st.error(f"Errore durante l'elaborazione: {str(e)}")
    finally:
        for p in temp_paths:
            if os.path.exists(p):
                os.remove(p)


# Navigation Tabs
nav_tab1, nav_tab2, nav_tab3, nav_tab4 = st.tabs([
    "⛳ Dashboard & Diagnosi PGA",
    "👤 Scheda Profilo & Attrezzatura Sacca",
    "📈 Storico Giri & Trend",
    "🎯 Benchmark & Strokes Gained"
])


# TAB 1: LIVE DASHBOARD & PGA DIAGNOSIS
with nav_tab1:
    if st.session_state.round_data:
        data: GolfRoundData = st.session_state.round_data
        summary = data.performance_summary
        diag = summary.professional_diagnosis
        rel_par = GolfMetricsCalculator.calculate_score_relation_to_par(data.holes)
        rel_par_str = f"+{rel_par}" if rel_par > 0 else ("Par" if rel_par == 0 else f"{rel_par}")

        col_head, col_btn = st.columns([4, 1])
        with col_head:
            st.title(f"⛳ {data.round_info.course_name or active_course.name}")
            cat_val = st.session_state.user_profile.category.value
            cat_badge = f"🔥 Tono IA: {cat_val}"
            st.caption(f"Partita di {data.round_info.holes_played} Buche • Data: {data.round_info.date or 'Oggi'} • {cat_badge}")

        with col_btn:
            html_rep = PDFReportGenerator.generate_html_report(data)
            st.download_button(
                label="📄 Scarica Report PDF / HTML",
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

        # Professional Diagnosis Box
        st.markdown(f"""
            <div class="diag-card">
                <h3 style="margin-top: 0; color: #2ECC71;">🧠 Diagnosi Caddie PGA — ({st.session_state.user_profile.category.value})</h3>
                <p><b>Sintesi Giro:</b> {diag.executive_narrative}</p>
                <p><b>Dispersion Leak Principale:</b> {diag.biggest_stroke_leak}</p>
                <p><b>Analisi Esecuzione Tecnica vs Tattica:</b> {diag.technical_vs_tactical_split}</p>
            </div>
        """, unsafe_allow_html=True)

        sub_tab_overview, sub_tab_holes, sub_tab_drills, sub_tab_transcript = st.tabs([
            "📋 Scorecard Ufficiale",
            "🗺️ Mappa Vettoriale & Target Landing",
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
                st.markdown("### 🎯 Ripartizione Colpi Persi (Strokes Lost)")
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
                            verdict_color = "#2ECC71" if "Bravo" in t_an.tactical_verdict or "Ottimo" in t_an.tactical_verdict or "Vincente" in t_an.tactical_verdict else "#E67E22"
                            st.markdown(f"""
                                <div class="target-box" style="border-left: 4px solid {verdict_color};">
                                    <span style="color: {verdict_color}; font-weight: bold; font-size: 0.95rem;">
                                        {t_an.tactical_verdict}
                                    </span>
                                    <p style="margin-top: 5px; margin-bottom: 3px; font-size: 0.9rem;">🎯 <b>Target Ideale per HCP {st.session_state.user_profile.handicap}:</b> {t_an.ideal_target_zone}</p>
                                    <p style="margin-bottom: 3px; font-size: 0.9rem;">📍 <b>Atterraggio Reale Palla:</b> {t_an.actual_landing_zone}</p>
                                    <p style="color: #B0B3B8; font-size: 0.85rem; margin-top: 5px;"><i>💡 Note Caddie: {t_an.caddie_tactical_note}</i></p>
                                </div>
                            """, unsafe_allow_html=True)

                        st.write(f"**GIR:** {'Sì' if h.gir else 'No'} | **Fairway Hit:** {'Sì' if h.fairway_hit else ('No' if h.fairway_hit is False else 'N/A')}")
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
            drill_cols = st.columns(len(summary.training_drills_recommended))
            for idx, drill in enumerate(summary.training_drills_recommended):
                with drill_cols[idx]:
                    st.markdown(f"""
                        <div class="drill-box">
                            <div class="drill-target">{drill.target_area}</div>
                            <h4 style="margin-top: 5px; margin-bottom: 8px;">{drill.drill_name}</h4>
                            <p style="color: #48C9B0; font-size: 0.85rem; margin-bottom: 8px;"><b>Obiettivo:</b> {drill.objective}</p>
                            <p style="color: #B0B3B8; font-size: 0.9rem; line-height: 1.4;">{drill.setup_and_execution}</p>
                            <div style="background: #262B36; padding: 8px; border-radius: 5px; margin-top: 10px; color: #E67E22; font-size: 0.85rem; font-weight: bold;">
                                🎯 Target: {drill.success_benchmark}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

        with sub_tab_transcript:
            st.markdown("### 🎙️ Trascrizione Vocale Estratta")
            st.text_area("Testo completo generato da Whisper:", value=st.session_state.transcript, height=250)

    else:
        st.info("👈 Carica una nota vocale dal pannello laterale per iniziare l'analisi del tuo giro.")


# TAB 2: USER PROFILE & MANUAL EQUIPMENT FORM
with nav_tab2:
    st.subheader("👤 Scheda Profilo Giocatore & Attrezzatura Sacca")
    st.caption("Compila o modifica i tuoi dati anagrafici, l'Handicap e la composizione completa della tua sacca da golf (Marca, Modello, Shaft e Distanze).")

    prof = st.session_state.user_profile

    col_prof_l, col_prof_r = st.columns([2, 3])

    with col_prof_l:
        st.markdown("### 📝 Dati Giocatore & Handicap")
        m_name = st.text_input("Nome & Cognome Giocatore", value=prof.player_name)
        m_hcp = st.number_input("Handicap Ufficiale (HCP)", min_value=0.0, max_value=54.0, value=float(prof.handicap), step=0.1)
        m_ball = st.text_input("Palla Preferita / In Uso", value=prof.preferred_ball or "Titleist Pro V1")

        new_cat = UserProfile.determine_category(m_hcp)
        st.info(f"**Categoria Assegnata:** {new_cat.value}")

        st.markdown("---")
        st.markdown("### 🎙️ In alternativa: Importa Profilo da Nota Vocale")
        setup_audio_file = st.file_uploader("Carica Audio Presentazione Sacca", type=["m4a", "mp3", "wav", "opus", "aac"])
        if st.button("🧠 Estrarre Profilo da Audio", type="primary", disabled=not setup_audio_file):
            if not os.environ.get("OPENAI_API_KEY"):
                st.error("Inserisci la tua OpenAI API Key nella barra laterale.")
                st.stop()

            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{setup_audio_file.name}") as tmp_s:
                tmp_s.write(setup_audio_file.read())
                tmp_s_path = tmp_s.name

            try:
                audio_eng = VoiceCaddyAudioEngine(model_size="medium")
                setup_transcript, _ = audio_eng.transcribe(tmp_s_path)
                parsed_profile = parse_user_setup_transcript(setup_transcript)
                st.session_state.user_profile = parsed_profile
                st.success(f"✅ Profilo estratto con successo! Handicap: {parsed_profile.handicap}")
                st.rerun()
            except Exception as e:
                st.error(f"Errore estrazione profilo: {e}")
            finally:
                if os.path.exists(tmp_s_path):
                    os.remove(tmp_s_path)

    with col_prof_r:
        st.markdown("### 🏌️ Composizione Sacca Bastoni (Modifica Manuale)")

        # Display Editable Form for Bag
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

        if st.button("💾 Salva Scheda Profilo & Sacca", type="primary", use_container_width=True):
            updated_clubs = []
            for _, row in edited_df.iterrows():
                if pd.notna(row["Mazza"]):
                    # Match ShaftFlex enum
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

            st.success("✅ Scheda Profilo e Sacca aggiornate con successo! L'IA utilizzerà queste impostazioni precise per le prossime analisi.")


# TAB 3: HISTORICAL ROUNDS & TRENDS
with nav_tab3:
    st.subheader("📈 Storico Parti & Progressioni nel Tempo")
    rounds_list = db.get_all_rounds()

    if not rounds_list:
        st.info("Nessuna partita ancora registrata nel database. Carica e analizza la tua prima partita!")
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
