"""
==============================================================================
VOICE CADDY GOLF — RULES ACADEMY (MODULO DIDATTICO AUTONOMO)
==============================================================================
Modulo indipendente dedicato allo studio, consultazione e ripasso delle
Regole Ufficiali del Golf R&A / USGA (Edizione 2023-2026).

Caratteristiche:
1. Consultazione Rapida & Ricerca per parole chiave e categorie
2. Quiz Interattivo con casi reali da torneo, correzione immediata e punteggio
3. Zero impatto sul core di Voice Caddy
4. Avviabile autonomamente (streamlit run golf_rules_module.py)
   oppure integrabile in app.py con 2-3 righe di codice.
==============================================================================
"""

import os
import json
from pathlib import Path
import streamlit as st

# Path di riferimento per il database delle regole
MODULE_DIR = Path(__file__).resolve().parent
DB_PATH = MODULE_DIR / "data" / "golf_rules_db.json"

# ============================================================================
# DATI FALLBACK (Garantisce che il modulo funzioni anche se il file JSON manca)
# ============================================================================
FALLBACK_RULES_DATA = {
    "rules": [
        {
            "id": "rule_17_penalty_areas",
            "rule_number": "Regola 17",
            "title": "Aree di Penalità (Paletti Rossi e Gialli)",
            "category": "Aree di Penalità",
            "icon": "🔴",
            "short_summary": "Opzioni di gioco e di ovvio quando la palla entra in un'area d'acqua o penalità.",
            "official_principle": "Puoi giocare la palla dove si trova senza penalità oppure procedere con l'ovvio (+1 colpo).",
            "practical_steps": [
                "Puoi giocare la palla nell'area di penalità: puoi toccare terra o acqua e rimuovere foglie senza penalità.",
                "Se prendi l'ovvio (+1 colpo), individua il punto esatto di ingresso nell'area (Punto di Riferimento).",
                "Paletti Gialli = 2 opzioni (Colpo e Distanza oppure Linea all'indietro). Paletti Rossi = 3 opzioni (include 2 bastoni laterali)."
            ],
            "relief_options": [
                {"name": "Colpo e Distanza", "penalty": "+1 colpo", "details": "Rigioca dal punto del colpo precedente."},
                {"name": "Ovvio all'Indietro sulla Linea", "penalty": "+1 colpo", "details": "Arretra in linea retta buca-punto d'ingresso quanto desideri."},
                {"name": "Ovvio Laterale (Solo Paletti ROSSI)", "penalty": "+1 colpo", "details": "Droppa entro 2 bastoni dal punto di ingresso, non più vicino alla buca."}
            ],
            "common_mistakes": [
                "Droppare lateralmente a 2 bastoni con paletti GIALLI (vietato!).",
                "Misurare dal punto in cui la palla è finita nell'acqua invece che da dove ha varcato il margine."
            ]
        }
    ],
    "quizzes": [
        {
            "id": 1,
            "rule_ref": "Regola 12.2b",
            "category": "Bunker",
            "scenario": "Mario è in bunker. Toglie una foglia secca vicino alla palla senza muoverla, poi tocca la sabbia con il ferro durante lo swing di prova. Qual è la decisione?",
            "options": [
                "Nessuna penalità: entrambe le azioni sono permesse dal 2019.",
                "2 colpi di penalità per aver toccato la sabbia durante lo swing di prova; rimuovere la foglia era legale.",
                "1 colpo di penalità per la foglia secca.",
                "4 colpi di penalità."
            ],
            "correct_index": 1,
            "explanation": "Secondo la Regola 12.2, rimuovere foglie dal bunker è lecito, ma toccare la sabbia nello swing di prova comporta 2 colpi di penalità.",
            "pro_tip": "Tieni sempre il bastone a mezz'aria durante lo swing di prova in bunker!"
        }
    ]
}


def load_rules_data():
    """Carica i dati dal file JSON dedicato con fallback di sicurezza."""
    if DB_PATH.exists():
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "rules" in data and "quizzes" in data:
                    return data
        except Exception:
            pass
    return FALLBACK_RULES_DATA


# ============================================================================
# STILI CSS INTEGRATI (Coerenti con la Luxury Dark Aesthetics di Voice Caddy)
# ============================================================================
def inject_academy_styles():
    st.markdown("""
        <style>
            /* Stili Principali Rules Academy */
            .academy-hero {
                background: linear-gradient(135deg, #0d1724 0%, #172a3a 50%, #0d1e1a 100%);
                border: 1px solid rgba(46, 204, 113, 0.35);
                border-radius: 14px;
                padding: 24px;
                margin-bottom: 22px;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
            }
            .academy-title {
                font-size: 2.1rem;
                font-weight: 800;
                background: linear-gradient(90deg, #FFFFFF, #2ECC71, #F1C40F);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 6px;
            }
            .academy-subtitle {
                font-size: 0.98rem;
                color: #CBD5E1;
                margin-bottom: 0;
            }
            .rule-card {
                background-color: #141C2A;
                border: 1px solid #28374D;
                border-left: 5px solid #2ECC71;
                border-radius: 10px;
                padding: 18px 20px;
                margin-bottom: 18px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
                transition: border-color 0.2s ease;
            }
            .rule-card:hover {
                border-color: #2ECC71;
            }
            .rule-header-title {
                color: #F8FAFC;
                font-size: 1.25rem;
                font-weight: 700;
                margin-bottom: 4px;
            }
            .rule-category-pill {
                display: inline-block;
                background: rgba(46, 204, 113, 0.15);
                color: #2ECC71;
                border: 1px solid rgba(46, 204, 113, 0.35);
                padding: 2px 10px;
                border-radius: 14px;
                font-size: 0.78rem;
                font-weight: 600;
                margin-right: 6px;
            }
            .rule-ref-pill {
                display: inline-block;
                background: rgba(241, 196, 15, 0.15);
                color: #F1C40F;
                border: 1px solid rgba(241, 196, 15, 0.35);
                padding: 2px 10px;
                border-radius: 14px;
                font-size: 0.78rem;
                font-weight: 700;
            }
            .relief-box {
                background: #0f1622;
                border: 1px solid #223247;
                border-radius: 8px;
                padding: 12px 14px;
                margin-top: 10px;
                margin-bottom: 10px;
            }
            .pitfall-box {
                background: rgba(231, 76, 60, 0.1);
                border-left: 4px solid #E74C3C;
                border-radius: 6px;
                padding: 10px 14px;
                margin-top: 10px;
                font-size: 0.88rem;
                color: #FCA5A5;
            }
            .quiz-container {
                background: linear-gradient(145deg, #121A27 0%, #182335 100%);
                border: 1px solid #2C3E5D;
                border-radius: 12px;
                padding: 24px;
                margin-bottom: 20px;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
            }
            .quiz-scenario-text {
                font-size: 1.12rem;
                line-height: 1.6;
                color: #F1F5F9;
                font-weight: 500;
                margin-bottom: 20px;
                background: #0D1420;
                padding: 16px;
                border-radius: 8px;
                border-left: 4px solid #38BDF8;
            }
            .quiz-feedback-correct {
                background: rgba(46, 204, 113, 0.15);
                border: 1px solid #2ECC71;
                border-radius: 8px;
                padding: 16px;
                margin-top: 16px;
                color: #E2E8F0;
            }
            .quiz-feedback-wrong {
                background: rgba(231, 76, 60, 0.15);
                border: 1px solid #E74C3C;
                border-radius: 8px;
                padding: 16px;
                margin-top: 16px;
                color: #E2E8F0;
            }
            .protip-badge {
                display: inline-block;
                background: rgba(241, 196, 15, 0.2);
                color: #FCD34D;
                padding: 3px 8px;
                border-radius: 4px;
                font-weight: 700;
                font-size: 0.8rem;
                margin-bottom: 6px;
            }
            .score-card-box {
                background: linear-gradient(135deg, #13241b 0%, #0e1713 100%);
                border: 2px solid #2ECC71;
                border-radius: 12px;
                padding: 24px;
                text-align: center;
                margin-bottom: 20px;
            }
        </style>
    """, unsafe_allow_html=True)


# ============================================================================
# VISTA 1: CONSULTAZIONE REGOLE
# ============================================================================
def render_rules_explorer(rules: list):
    st.markdown("### 📖 Sfoglia & Cerca nel Regolamento R&A")
    st.caption("Consulta le regole ufficiali del golf con spiegazioni pratiche, opzioni di ovvio e consigli salva-colpi.")

    # Filtri di ricerca
    col_search, col_cat = st.columns([3, 2])
    with col_search:
        search_query = st.text_input(
            "🔍 Cerca per parola chiave:",
            placeholder="es. bunker, ginocchio, provvisoria, asta, penalità...",
            key="rules_search_query"
        ).strip().lower()

    # Categorie disponibili
    categories = ["Tutte le Categorie"] + sorted(list(set(r.get("category", "Altro") for r in rules)))
    with col_cat:
        selected_cat = st.selectbox("📂 Filtra per Argomento:", options=categories, key="rules_selected_cat")

    # Filtraggio
    filtered_rules = []
    for r in rules:
        matches_cat = (selected_cat == "Tutte le Categorie") or (r.get("category") == selected_cat)
        
        matches_search = True
        if search_query:
            text_corpus = (
                r.get("rule_number", "") + " " +
                r.get("title", "") + " " +
                r.get("category", "") + " " +
                r.get("short_summary", "") + " " +
                r.get("official_principle", "") + " " +
                " ".join(r.get("practical_steps", [])) + " " +
                " ".join(r.get("common_mistakes", [])) + " " +
                " ".join(opt.get("name", "") + " " + opt.get("details", "") for opt in r.get("relief_options", []))
            ).lower()
            matches_search = search_query in text_corpus

        if matches_cat and matches_search:
            filtered_rules.append(r)

    # Conteggio risultati
    st.markdown(f"<div style='margin-bottom: 14px; font-size: 0.88rem; color: #94A3B8;'>Trovate <b>{len(filtered_rules)}</b> regole corrispondenti.</div>", unsafe_allow_html=True)

    if not filtered_rules:
        st.info("Nessuna regola trovata con i filtri selezionati. Prova un altro termine di ricerca!")
        return

    # Visualizzazione delle regole
    for rule in filtered_rules:
        icon = rule.get("icon", "⛳")
        r_num = rule.get("rule_number", "Regola")
        title = rule.get("title", "")
        cat = rule.get("category", "")
        summary = rule.get("short_summary", "")
        principle = rule.get("official_principle", "")
        steps = rule.get("practical_steps", [])
        relief_options = rule.get("relief_options", [])
        mistakes = rule.get("common_mistakes", [])

        st.markdown(f"""
            <div class="rule-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div>
                        <span class="rule-ref-pill">{r_num}</span>
                        <span class="rule-category-pill">{cat}</span>
                    </div>
                    <span style="font-size: 1.4rem;">{icon}</span>
                </div>
                <div class="rule-header-title">{title}</div>
                <p style="color: #94A3B8; font-size: 0.92rem; margin-bottom: 10px;">{summary}</p>
                <div style="background: #0D131D; border-left: 3px solid #F1C40F; padding: 8px 12px; border-radius: 4px; font-size: 0.88rem; color: #E2E8F0; margin-bottom: 12px;">
                    <b>📜 Principio Ufficiale:</b> <i>{principle}</i>
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.expander(f"🔍 Dettagli Operativi & Procedure per {r_num} — {title}", expanded=False):
            if steps:
                st.markdown("##### 🚶‍♂️ Procedura Pratica in Campo:")
                for s in steps:
                    st.markdown(f"- {s}")

            if relief_options:
                st.markdown("##### 📏 Opzioni di Ovvio Previste:")
                for opt in relief_options:
                    p_badge = opt.get("penalty", "")
                    p_color = "#2ECC71" if "Zero" in p_badge else "#F59E0B"
                    st.markdown(f"""
                        <div class="relief-box">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <b style="color: #38BDF8;">{opt.get('name')}</b>
                                <span style="background: rgba(0,0,0,0.4); border: 1px solid {p_color}; color: {p_color}; font-size: 0.76rem; font-weight: bold; padding: 2px 8px; border-radius: 10px;">{p_badge}</span>
                            </div>
                            <div style="font-size: 0.88rem; color: #CBD5E1;">{opt.get('details')}</div>
                        </div>
                    """, unsafe_allow_html=True)

            if mistakes:
                st.markdown("##### ⚠️ Errori Tipici da Evitare in Gara:")
                st.markdown("""
                    <div class="pitfall-box">
                """, unsafe_allow_html=True)
                for m in mistakes:
                    st.markdown(f"• {m}")
                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)


# ============================================================================
# VISTA 2: QUIZ & RIPASSO INTERATTIVO
# ============================================================================
def render_rules_quiz(quizzes: list):
    st.markdown("### 🎯 Quiz & Ripasso: Mettiti alla Prova!")
    st.caption("Affronta situazioni di gioco realistiche tratte da gare ufficiali. Verifica la tua risposta con il commento degli arbitri R&A.")

    if not quizzes:
        st.warning("Nessun quiz disponibile al momento.")
        return

    # Inizializzazione dello Stato di Sessione per il Quiz
    if "quiz_idx" not in st.session_state:
        st.session_state.quiz_idx = 0
    if "quiz_answers" not in st.session_state:
        st.session_state.quiz_answers = {}  # {q_id: selected_index}
    if "quiz_submitted" not in st.session_state:
        st.session_state.quiz_submitted = {}  # {q_id: bool}

    total_q = len(quizzes)
    curr_idx = min(st.session_state.quiz_idx, total_q - 1)
    q = quizzes[curr_idx]
    q_id = q["id"]

    # Barra di avanzamento e barra statistiche
    answered_count = len(st.session_state.quiz_submitted)
    correct_count = 0
    for q_item in quizzes:
        item_id = q_item["id"]
        if st.session_state.quiz_submitted.get(item_id):
            if st.session_state.quiz_answers.get(item_id) == q_item["correct_index"]:
                correct_count += 1

    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.metric("Domanda", f"{curr_idx + 1} di {total_q}")
    with col_stat2:
        st.metric("Risposte Date", f"{answered_count} / {total_q}")
    with col_stat3:
        pct = int((correct_count / answered_count * 100)) if answered_count > 0 else 0
        st.metric("Precisione Corrente", f"{correct_count} corrette ({pct}%)")

    st.progress((curr_idx + 1) / total_q)
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # Box Domanda
    is_submitted = st.session_state.quiz_submitted.get(q_id, False)
    user_selection = st.session_state.quiz_answers.get(q_id, None)

    st.markdown(f"""
        <div class="quiz-container">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span class="rule-ref-pill">{q.get('rule_ref', 'R&A Rule')}</span>
                <span class="rule-category-pill">{q.get('category', 'Generale')}</span>
            </div>
            <div class="quiz-scenario-text">
                {q['scenario']}
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Opzioni di risposta (Radio selection)
    options = q["options"]
    radio_key = f"quiz_radio_{q_id}"
    selected_option = st.radio(
        "Seleziona la tua risposta:",
        options=options,
        index=user_selection if user_selection is not None else 0,
        disabled=is_submitted,
        key=radio_key
    )

    selected_idx = options.index(selected_option)

    # Azioni del Quiz
    col_btn_prev, col_btn_action, col_btn_next = st.columns([1, 2, 1])

    with col_btn_prev:
        if st.button("⬅️ Precedente", disabled=(curr_idx == 0), use_container_width=True):
            st.session_state.quiz_idx = max(0, curr_idx - 1)
            st.rerun()

    with col_btn_action:
        if not is_submitted:
            if st.button("✅ Conferma e Verifica Risposta", type="primary", use_container_width=True):
                st.session_state.quiz_answers[q_id] = selected_idx
                st.session_state.quiz_submitted[q_id] = True
                st.rerun()
        else:
            if st.button("🔄 Cambia Risposta", use_container_width=True):
                st.session_state.quiz_submitted[q_id] = False
                st.rerun()

    with col_btn_next:
        if st.button("Successiva ➡️", disabled=(curr_idx == total_q - 1), use_container_width=True):
            st.session_state.quiz_idx = min(total_q - 1, curr_idx + 1)
            st.rerun()

    # Feedback Immediato se la risposta è stata verificata
    if is_submitted:
        is_correct = (user_selection == q["correct_index"])
        if is_correct:
            st.markdown(f"""
                <div class="quiz-feedback-correct">
                    <h4 style="color: #2ECC71; margin-top: 0;">🎉 Risposta Esatta!</h4>
                    <p style="margin-bottom: 8px;"><b>Motivazione Ufficiale ({q.get('rule_ref')}):</b></p>
                    <p style="font-size: 0.95rem; line-height: 1.55;">{q['explanation']}</p>
                    <div style="margin-top: 10px;">
                        <span class="protip-badge">💡 PRO TIP</span>
                        <div style="color: #FCD34D; font-size: 0.9rem;">{q.get('pro_tip', '')}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            correct_text = options[q["correct_index"]]
            st.markdown(f"""
                <div class="quiz-feedback-wrong">
                    <h4 style="color: #E74C3C; margin-top: 0;">❌ Risposta Non Corretta</h4>
                    <p style="margin-bottom: 6px;">La risposta corretta è:</p>
                    <div style="background: rgba(0,0,0,0.3); padding: 8px 12px; border-radius: 6px; color: #38BDF8; font-weight: bold; margin-bottom: 10px;">
                        👉 {correct_text}
                    </div>
                    <p style="margin-bottom: 8px;"><b>Spiegazione Regola R&A ({q.get('rule_ref')}):</b></p>
                    <p style="font-size: 0.95rem; line-height: 1.55;">{q['explanation']}</p>
                    <div style="margin-top: 10px;">
                        <span class="protip-badge">💡 PRO TIP</span>
                        <div style="color: #FCD34D; font-size: 0.9rem;">{q.get('pro_tip', '')}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    # Riepilogo Finale se tutte le domande sono completate
    if answered_count == total_q:
        st.markdown("---")
        score_pct = int((correct_count / total_q) * 100)
        badge_title = "🏌️‍♂️ Neofita delle Regole"
        badge_desc = "Continua a ripassare per evitare colpi persi inutili sul campo!"
        if score_pct >= 90:
            badge_title = "🏆 Arbitro Federale R&A"
            badge_desc = "Padronanza assoluta delle regole! Sei la guida del tuo flight."
        elif score_pct >= 70:
            badge_title = "⛳ Giocatore di Categoria Superiore"
            badge_desc = "Ottima conoscenza delle regole! Sai come trarre il massimo vantaggio legale da ogni situazione."
        elif score_pct >= 50:
            badge_title = "🏌️‍♂️ Giocatore Consapevole"
            badge_desc = "Buone basi, ma attenzione ai dettagli sulle ostruzioni e sul green."

        st.markdown(f"""
            <div class="score-card-box">
                <h2 style="color: #2ECC71; margin-top: 0;">🎓 Quiz Completato!</h2>
                <div style="font-size: 2.5rem; font-weight: 800; color: #FFFFFF; margin-bottom: 4px;">
                    {correct_count} / {total_q}
                </div>
                <div style="font-size: 1.2rem; color: #F1C40F; font-weight: bold; margin-bottom: 12px;">
                    {score_pct}% — {badge_title}
                </div>
                <p style="color: #CBD5E1; max-width: 600px; margin: 0 auto 16px auto;">
                    {badge_desc}
                </p>
            </div>
        """, unsafe_allow_html=True)

        if st.button("🔁 Ricomincia il Quiz da Capo", use_container_width=True):
            st.session_state.quiz_idx = 0
            st.session_state.quiz_answers = {}
            st.session_state.quiz_submitted = {}
            st.rerun()


# ============================================================================
# ENTRY POINT PRINCIPALE DEL MODULO
# ============================================================================
def render_rules_academy(is_standalone: bool = False):
    """
    Funzione principale da richiamare per visualizzare il modulo Rules Academy.
    Può essere richiamata all'interno di un Tab di app.py oppure in standalone.
    """
    inject_academy_styles()
    data = load_rules_data()
    rules = data.get("rules", [])
    quizzes = data.get("quizzes", [])

    # Header Visivo del Modulo
    st.markdown("""
        <div class="academy-hero">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <div class="academy-title">🎓 Rules Academy — Regole del Golf R&A</div>
                    <div class="academy-subtitle">
                        Guida ufficiale interattiva alle Regole del Golf per non perdere mai colpi preziosi e giocare con sicurezza da vero professionista.
                    </div>
                </div>
                <div style="font-size: 3rem; margin-left: 20px;">⛳</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Navigazione interna tra Consultazione e Quiz
    sub_tab_consult, sub_tab_quiz = st.tabs([
        "📚 Consultazione & Ricerca Regole",
        "🎯 Quiz & Ripasso Interattivo"
    ])

    with sub_tab_consult:
        render_rules_explorer(rules)

    with sub_tab_quiz:
        render_rules_quiz(quizzes)


# ============================================================================
# ESECUZIONE STANDALONE
# ============================================================================
if __name__ == "__main__":
    # Configurazione della pagina autonoma quando il modulo viene eseguito da solo
    st.set_page_config(
        page_title="Rules Academy | Voice Caddy Golf",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    render_rules_academy(is_standalone=True)
