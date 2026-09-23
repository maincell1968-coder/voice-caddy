"""
Mobile PDF Report Generator (Voice Caddy Pro)
=============================================
Genera un report PDF professionale e compatto, ottimizzato sia per la stampa A4
che per la condivisione rapida su WhatsApp e Telegram (visualizzazione da smartphone).

Include:
1. Intestazione & Dati Giocatore (HCP WHS, Data, Circolo)
2. Il Circuito dei 4 Campi (Conero, Torrenova, Perugia, Riviera)
3. Scorecard Ufficiale di Gara (Lordo & Netto, Stableford & Colpi)
4. Analisi Balistica & Dispersione (Benchmark di Categoria, Distanze, Fairway Accuracy)
5. Il Giudizio del Maestro PGA (Regola Aurea, Buca Migliore, Errori Chiave)
6. Top 3 Drill di Allenamento con Benchmark Misurabili
"""

from __future__ import annotations

import io
import warnings
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

warnings.filterwarnings("ignore", category=DeprecationWarning)

from fpdf import FPDF
from fpdf.enums import MethodReturnValue
from core.schemas import GolfRoundData
from core.metrics import GolfMetricsCalculator
from core.whs_rules import generate_tournament_summary_data
from core.course import CourseRegistry


class VoiceCaddyPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        # Font predefiniti Helvetica sicuri e universali

    @staticmethod
    def _sanitize(text: Any) -> str:
        if text is None:
            return ""
        s = str(text)
        replacements = {
            "\u2013": "-",   # en-dash
            "\u2014": "--",  # em-dash
            "\u2018": "'",   # left single quote
            "\u2019": "'",   # right single quote
            "\u201c": '"',   # left double quote
            "\u201d": '"',   # right double quote
            "\u2026": "...", # ellipsis
            "\u2022": "*",   # bullet
            "\u00a0": " ",   # non-breaking space
            "\u20ac": "EUR", # euro
        }
        for orig, rep in replacements.items():
            s = s.replace(orig, rep)
        return s.encode("latin-1", errors="replace").decode("latin-1")

    def cell(self, *args, **kwargs):
        if "text" in kwargs:
            kwargs["text"] = self._sanitize(kwargs["text"])
        elif "txt" in kwargs:
            kwargs["txt"] = self._sanitize(kwargs["txt"])
        elif len(args) >= 3 and isinstance(args[2], (str, int, float)):
            args_list = list(args)
            args_list[2] = self._sanitize(args_list[2])
            args = tuple(args_list)
        return super().cell(*args, **kwargs)

    def multi_cell(self, *args, **kwargs):
        if "text" in kwargs:
            kwargs["text"] = self._sanitize(kwargs["text"])
        elif "txt" in kwargs:
            kwargs["txt"] = self._sanitize(kwargs["txt"])
        elif len(args) >= 3 and isinstance(args[2], (str, int, float)):
            args_list = list(args)
            args_list[2] = self._sanitize(args_list[2])
            args = tuple(args_list)
        return super().multi_cell(*args, **kwargs)

    def header(self):
        # Header banner scuro elegante
        self.set_fill_color(15, 23, 42)  # #0f172a
        self.rect(0, 0, 210, 18, style="F")
        self.set_text_color(46, 204, 113)  # Emerald #2ecc71
        self.set_font("Helvetica", "B", 10)
        self.set_xy(10, 5)
        self.cell(100, 8, "VOICE CADDY PRO | PGA PERFORMANCE & CLUB REPORT", align="L")
        self.set_text_color(148, 163, 184)
        self.set_font("Helvetica", "", 8)
        self.set_xy(140, 5)
        self.cell(60, 8, "Ottimizzato per Telegram & WhatsApp", align="R")
        self.ln(15)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 8, f"Pagina {self.page_no()} | Voice Caddy Pro - Documento Ufficiale Circolo & Giocatore", align="C")


def generate_showcase_mobile_pdf(
    round_data: Optional[GolfRoundData] = None,
    player_name: str = "Stefano Pirani",
    handicap: float = 18.0,
    active_course_id: str = "conero_golf_club"
) -> bytes:
    """
    Genera il PDF completo di riepilogo e anteprima per i 4 campi e per il giro giocato.
    Ritorna i byte raw del file PDF.
    """
    if round_data is None:
        from core.demo_data import get_demo_golf_round
        round_data = get_demo_golf_round()

    # Assicura sempre riconciliazione metrica e diagnostica completa
    round_data = GolfMetricsCalculator.recompute_and_reconcile(round_data)

    summary = round_data.performance_summary
    diag = summary.professional_diagnosis if summary else None
    matrix = GolfMetricsCalculator.get_scorecard_matrix(round_data.holes)
    t_data = generate_tournament_summary_data(round_data)

    registry = CourseRegistry()
    active_course = registry.get_course(active_course_id) or registry.get_default_course()
    all_courses = registry.list_courses()

    pdf = VoiceCaddyPDF()
    pdf.add_page()

    # ---------------------------------------------------------
    # 1. HERO TITLE & PLAYER PROFILE
    # ---------------------------------------------------------
    pdf.set_fill_color(24, 32, 47)
    pdf.rect(10, 22, 190, 24, style="F")

    pdf.set_xy(14, 24)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(110, 7, f"GIOCATORE: {player_name.upper()}", ln=0)

    pdf.set_text_color(46, 204, 113)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(70, 7, f"HCP WHS: {handicap:.1f} | Playing HCP: {t_data.get('playing_hcp', 18)}", ln=1, align="R")

    pdf.set_xy(14, 32)
    pdf.set_text_color(203, 213, 225)
    pdf.set_font("Helvetica", "", 9)
    date_str = datetime.now().strftime("%d/%m/%Y")
    pdf.cell(110, 6, f"Campo Attivo: {active_course.name} ({active_course.city}) - Par {active_course.total_par}", ln=0)

    pdf.set_text_color(241, 196, 15)  # Gold
    pdf.cell(70, 6, f"Data Report: {date_str}", ln=1, align="R")

    # ---------------------------------------------------------
    # 2. SEZIONE A: IL CIRCUITO DEI 4 CAMPI ATTIVI
    # ---------------------------------------------------------
    pdf.set_xy(10, 50)
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 6, "1. I 4 CAMPI UFFICIALI DEL CIRCUITO (PREVIEW & COMPATIBILITA)", ln=1)

    pdf.set_fill_color(241, 245, 249)
    pdf.set_draw_color(203, 213, 225)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(71, 85, 105)

    col_w = [48, 48, 24, 22, 48]
    headers = ["Circolo / Campo", "Localita", "Buche / Par", "Tee Attivi", "Caratteristiche"]
    for w, h in zip(col_w, headers):
        pdf.cell(w, 6, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(30, 41, 59)

    course_infos = [
        ("Conero Golf Club", "Sirolo (AN)", "18 Buche / Par 71", "Bianchi/Gialli/Rossi", "Collinare tecnico con pendenze"),
        ("Torrenova Golf", "P. Potenza Picena (MC)", "9 Buche / Par 34", "Gialli/Rossi", "Pianeggiante, ideale per scoring"),
        ("Golf Club Perugia", "Santa Sabina (PG)", "18 Buche / Par 72", "Gialli/Rossi", "Storico alberato, green ondulati"),
        ("Riviera Golf Cattolica", "S. Giovanni Marignano (RN)", "18 Buche / Par 70", "Bianchi/Gialli/Rossi", "Championship resort, Graham Cooke")
    ]

    for c_name, c_city, c_holes, c_tees, c_notes in course_infos:
        # Evidenzia il campo attivo
        is_active = (c_name.lower() in active_course.name.lower())
        if is_active:
            pdf.set_fill_color(236, 253, 245)  # Verde chiarissimo
            pdf.set_text_color(6, 95, 70)
            pdf.set_font("Helvetica", "B", 7.5)
        else:
            pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(30, 41, 59)
            pdf.set_font("Helvetica", "", 7.5)

        pdf.cell(col_w[0], 5.5, f"{'* ' if is_active else ''}{c_name}", border=1, fill=is_active)
        pdf.cell(col_w[1], 5.5, c_city, border=1, fill=is_active)
        pdf.cell(col_w[2], 5.5, c_holes, border=1, fill=is_active, align="C")
        pdf.cell(col_w[3], 5.5, c_tees, border=1, fill=is_active, align="C")
        pdf.cell(col_w[4], 5.5, c_notes, border=1, fill=is_active)
        pdf.ln()

    # ---------------------------------------------------------
    # 3. SEZIONE B: RIEPILOGO GARA UFFICIALE (LORDO & NETTO)
    # ---------------------------------------------------------
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(190, 6, "2. RIEPILOGO GARA UFFICIALE (REGOLA 21.1 STABLEFORD & STROKE PLAY)", ln=1)

    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(10, pdf.get_y(), 190, 18, style="DF")

    curr_y = pdf.get_y() + 2
    pdf.set_xy(12, curr_y)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(30, 4, "COLPI LORDI", align="C")
    pdf.cell(30, 4, "COLPI NETTI", align="C")
    pdf.cell(32, 4, "STABLEFORD LORDO", align="C")
    pdf.cell(32, 4, "STABLEFORD NETTO", align="C")
    pdf.cell(32, 4, "FAIRWAY (FIR)", align="C")
    pdf.cell(32, 4, "GREEN (GIR)", align="C")

    pdf.set_xy(12, curr_y + 5)
    pdf.set_font("Helvetica", "B", 13)

    # Colpi Lordi
    pdf.set_text_color(15, 23, 42)
    pdf.cell(30, 8, f"{t_data.get('total_gross', 82)}", align="C")

    # Colpi Netti
    pdf.set_text_color(37, 99, 235)
    pdf.cell(30, 8, f"{t_data.get('total_net', 64)}", align="C")

    # Stableford Lordo
    pdf.set_text_color(147, 51, 234)
    pdf.cell(32, 8, f"{t_data.get('total_stableford_gross', 26)} pt", align="C")

    # Stableford Netto
    pdf.set_text_color(16, 185, 129)
    pdf.cell(32, 8, f"{t_data.get('total_stableford_net', 44)} pt", align="C")

    # FIR %
    pdf.set_text_color(15, 23, 42)
    pdf.set_font("Helvetica", "B", 11)
    fir_val = f"{summary.fairway_accuracy_pct:.0f}%" if (summary and summary.fairway_accuracy_pct is not None) else "71%"
    pdf.cell(32, 8, fir_val, align="C")

    # GIR %
    gir_val = f"{summary.gir_pct:.0f}%" if (summary and summary.gir_pct is not None) else "50%"
    pdf.cell(32, 8, gir_val, align="C")

    pdf.ln(12)

    # ---------------------------------------------------------
    # 4. SEZIONE C: SCORECARD DETTAGLIATA (BUCA PER BUCA)
    # ---------------------------------------------------------
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(190, 5, "3. SCORECARD DI GARA (LORDO, NETTO, STABLEFORD & PUTT)", ln=1)

    s_col_w = [14, 12, 12, 14, 18, 16, 20, 20, 16, 16, 14, 18]
    s_headers = ["Buca", "Par", "SI", "HCP", "Lordo", "Netto", "Stb.Lor", "Stb.Net", "FIR", "GIR", "Putt", "Voto"]

    pdf.set_fill_color(226, 232, 240)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(51, 65, 85)
    for w, h in zip(s_col_w, s_headers):
        pdf.cell(w, 5, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 7)
    for r in matrix[:18]:
        buca_num = r["Buca"]
        h_obj = next((h for h in round_data.holes if h.hole_number == buca_num), None)
        c_eval = getattr(h_obj, "coach_evaluation", {}) if h_obj else {}
        rating_str = f"{c_eval.get('rating', '-')}/10" if c_eval else "-"

        # Colore sfondo in base al punteggio lordo
        status = r.get("Status", "")
        if "Birdie" in status or "Eagle" in status:
            pdf.set_fill_color(209, 250, 229)  # Verde chiaro
            pdf.set_text_color(6, 95, 70)
        elif "Bogey" in status and "Double" not in status:
            pdf.set_fill_color(254, 243, 199)  # Giallo chiaro
            pdf.set_text_color(146, 64, 14)
        elif "Double" in status:
            pdf.set_fill_color(254, 226, 226)  # Rosso chiaro
            pdf.set_text_color(153, 27, 27)
        else:
            pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(30, 41, 59)

        pdf.cell(s_col_w[0], 4.2, str(r["Buca"]), border=1, align="C")
        pdf.cell(s_col_w[1], 4.2, str(r["Par"]), border=1, align="C")
        pdf.cell(s_col_w[2], 4.2, str(r.get("SI", "-")), border=1, align="C")
        pdf.cell(s_col_w[3], 4.2, f"+{r.get('HCP', 0)}", border=1, align="C")
        pdf.cell(s_col_w[4], 4.2, f"{r['Score']} ({r.get('+/-', '')})", border=1, fill=True, align="C")
        pdf.cell(s_col_w[5], 4.2, str(r.get("Score Netto", r["Score"])), border=1, align="C")
        pdf.cell(s_col_w[6], 4.2, f"{r.get('Stabl. Lordo', '-')} pt", border=1, align="C")
        pdf.cell(s_col_w[7], 4.2, f"{r.get('Stabl. Netto', '-')} pt", border=1, align="C")
        pdf.cell(s_col_w[8], 4.2, str(r.get("FIR", "-")), border=1, align="C")
        pdf.cell(s_col_w[9], 4.2, str(r.get("GIR", "-")), border=1, align="C")
        pdf.cell(s_col_w[10], 4.2, str(r.get("Putts", "-")), border=1, align="C")
        pdf.cell(s_col_w[11], 4.2, rating_str, border=1, align="C")
        pdf.ln()

    # ---------------------------------------------------------
    # PAGINA 2: MAESTRO PGA, DISPERSIONE & TOP 3 DRILL
    # ---------------------------------------------------------
    pdf.add_page()

    # ---------------------------------------------------------
    # 5. SEZIONE D: IL GIUDIZIO DEL MAESTRO PGA (REGOLA AUREA)
    # ---------------------------------------------------------
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(190, 6, "4. IL GIUDIZIO DEL MAESTRO PGA (REGOLA AUREA: DOVE, COME & PERCHE)", ln=1)

    s4_start_y = pdf.get_y()
    diag_score = diag.course_management_score if (diag and diag.course_management_score is not None) else 80
    score_txt = f"GIUDIZIO COMPLESSIVO (Punteggio Strategia: {diag_score}/100)"

    exec_narrative = (diag.executive_narrative if (diag and diag.executive_narrative) else "Giro analizzato secondo la Regola Aurea PGA. Solida tenuta nei colpi e buona regolarità generale.")
    exec_p = f"{exec_narrative[:280]}..." if len(exec_narrative) > 280 else exec_narrative

    leak_val = diag.biggest_stroke_leak if (diag and diag.biggest_stroke_leak) else "Dispersione standard di colpi."
    leak_txt = f"Dispersione Primaria di Colpi: {leak_val}"

    split_val = diag.technical_vs_tactical_split if (diag and diag.technical_vs_tactical_split) else "Approccio equilibrato tra esecuzione tecnica e strategia di gioco."
    split_txt = f"Quadro Tecnico vs Tattico: {split_val}"

    pdf.set_font("Helvetica", "B", 9)
    h_score = pdf.multi_cell(182, 4.6, score_txt, dry_run=True, output=MethodReturnValue.HEIGHT)
    pdf.set_font("Helvetica", "", 8)
    h_narrative = pdf.multi_cell(182, 4.0, exec_p, dry_run=True, output=MethodReturnValue.HEIGHT)
    pdf.set_font("Helvetica", "B", 8)
    h_leak = pdf.multi_cell(182, 4.0, leak_txt, dry_run=True, output=MethodReturnValue.HEIGHT)
    pdf.set_font("Helvetica", "I", 8)
    h_split = pdf.multi_cell(182, 4.0, split_txt, dry_run=True, output=MethodReturnValue.HEIGHT)

    top_pad_s4 = 2.5
    bot_pad_s4 = 2.5
    s4_card_h = top_pad_s4 + h_score + 1.2 + h_narrative + 1.2 + h_leak + 1.0 + h_split + bot_pad_s4

    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(203, 213, 225)
    pdf.rect(10, s4_start_y, 190, s4_card_h, style="DF")
    pdf.set_fill_color(16, 185, 129)
    pdf.rect(10, s4_start_y, 2.5, s4_card_h, style="F")

    pdf.set_xy(14, s4_start_y + top_pad_s4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(15, 23, 42)
    pdf.multi_cell(182, 4.6, score_txt)

    pdf.set_x(14)
    pdf.ln(1.2)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(182, 4.0, exec_p)

    pdf.set_x(14)
    pdf.ln(1.2)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(225, 29, 72)
    pdf.multi_cell(182, 4.0, leak_txt)

    pdf.set_x(14)
    pdf.ln(1.0)
    pdf.set_x(14)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(37, 99, 235)
    pdf.multi_cell(182, 4.0, split_txt)

    pdf.set_y(s4_start_y + s4_card_h + 3.0)

    # ---------------------------------------------------------
    # 6. SEZIONE E: ANALISI BALISTICA & DISPERSIONE DEI COLPI
    # ---------------------------------------------------------
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(190, 6, "5. ANALISI BALISTICA & DISPERSIONE (CRUSCOTTO TRACKMAN / GAUGE 0M)", ln=1)

    pdf.set_fill_color(241, 245, 249)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(71, 85, 105)

    b_cols = [30, 30, 30, 35, 35, 30]
    b_headers = ["Bastone", "Distanza Media", "Benchmark Cat.", "Dispersione Lat.", "Esito Tipico", "Valutazione"]
    for w, h in zip(b_cols, b_headers):
        pdf.cell(w, 6, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(30, 41, 59)

    bal_rows = [
        ("Driver", "220 m", "205 - 230 m", "+8 m a destra", "Fairway centro-dx", "OTTIMALE"),
        ("Legno 3", "190 m", "180 - 200 m", "-4 m a sinistra", "Fairway pieno", "IN MEDIA"),
        ("Ferro 7", "148 m", "135 - 150 m", "+2 m a destra", "Green centrato", "ECCELLENTE"),
        ("Pitching Wedge", "110 m", "100 - 115 m", "0 m centro perfetto", "Pin Hunter (3m)", "OTTIMALE"),
        ("Sand Wedge 56°", "68 m", "65 - 80 m", "-6 m a sinistra", "Avangreen / Bunker", "MIGLIORABILE")
    ]

    for b_club, b_dist, b_bench, b_disp, b_lie, b_verdict in bal_rows:
        v_col = (16, 185, 129) if "OTTIMALE" in b_verdict or "ECCELLENTE" in b_verdict else (217, 119, 6)
        pdf.cell(b_cols[0], 5.2, b_club, border=1)
        pdf.cell(b_cols[1], 5.2, b_dist, border=1, align="C")
        pdf.cell(b_cols[2], 5.2, b_bench, border=1, align="C")
        pdf.cell(b_cols[3], 5.2, b_disp, border=1, align="C")
        pdf.cell(b_cols[4], 5.2, b_lie, border=1)
        pdf.set_text_color(*v_col)
        pdf.set_font("Helvetica", "B", 7.5)
        pdf.cell(b_cols[5], 5.2, b_verdict, border=1, align="C")
        pdf.set_text_color(30, 41, 59)
        pdf.set_font("Helvetica", "", 8)
        pdf.ln()

    # ---------------------------------------------------------
    # 7. SEZIONE F: TOP 3 DRILL DI ALLENAMENTO (PRESCRITTI)
    # ---------------------------------------------------------
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(190, 6, "6. TOP 3 ESERCIZI DI ALLENAMENTO SUL CAMPO PRATICA (BENCHMARK MISURABILI)", ln=1)

    drills = summary.training_drills_recommended if (summary and summary.training_drills_recommended) else []
    if not drills:
        from core.schemas import TrainingDrill
        drills = [
            TrainingDrill(
                target_area="DRIVING",
                drill_name="Controllo Corridoio di Partenza",
                objective="Mantenere la palla in gioco dal tee",
                setup_and_execution="10 drive consecutivi con tee basso mirando a un corridoio virtuale di 25 metri.",
                success_benchmark="> 70% in corridoio"
            ),
            TrainingDrill(
                target_area="APPROACH",
                drill_name="Precisione Target 100m",
                objective="Controllo della profondità sui colpi al green",
                setup_and_execution="10 colpi di wedge da 100m con swing 3/4 compatto verso il target.",
                success_benchmark="> 65% entro 6 metri"
            ),
            TrainingDrill(
                target_area="PUTTING",
                drill_name="Clock Drill Salva-Par (1.5m)",
                objective="Solidità ed eliminazione dei 3-putt",
                setup_and_execution="6 palline a cerchio attorno alla buca a 1.5 metri, imbucare tutta la serie.",
                success_benchmark="85% di putt imbucati"
            )
        ]

    for idx, d in enumerate(drills[:3], 1):
        d_start_y = pdf.get_y()

        # Normalizzazione Titolo Drill (evita duplicazioni se target_area coincide col nome)
        t_area = (d.target_area or "").strip()
        d_name = (d.drill_name or "").strip()
        if not d_name:
            d_name = t_area or f"Drill #{idx}"

        if t_area.lower() == d_name.lower() or d_name.lower().startswith(t_area.lower()):
            title_text = f"DRILL #{idx}: {d_name.upper()}"
        elif len(t_area) <= 20:
            title_text = f"DRILL #{idx} [{t_area.upper()}]: {d_name}"
        else:
            title_text = f"DRILL #{idx}: {d_name}"

        bench_text = f"TARGET BENCHMARK: {d.success_benchmark.strip()}"
        obj_text = f"Obiettivo: {d.objective.strip()}"
        exec_text = f"Esecuzione: {d.setup_and_execution.strip()}"
        exec_p = exec_text[:280] + "..." if len(exec_text) > 280 else exec_text

        # Calcolo altezze esatte con dry_run=True (nessuna sovrapposizione possibile)
        pdf.set_font("Helvetica", "B", 8.5)
        h_title = pdf.multi_cell(182, 4.3, title_text, dry_run=True, output=MethodReturnValue.HEIGHT)

        pdf.set_font("Helvetica", "B", 8)
        h_bench = pdf.multi_cell(182, 4.0, bench_text, dry_run=True, output=MethodReturnValue.HEIGHT)

        pdf.set_font("Helvetica", "", 7.5)
        h_obj = pdf.multi_cell(182, 3.8, obj_text, dry_run=True, output=MethodReturnValue.HEIGHT)

        pdf.set_font("Helvetica", "I", 7.5)
        h_exec = pdf.multi_cell(182, 3.6, exec_p, dry_run=True, output=MethodReturnValue.HEIGHT)

        top_pad = 2.0
        bot_pad = 2.0
        card_h = top_pad + h_title + 0.8 + h_bench + 0.8 + h_obj + 0.8 + h_exec + bot_pad

        # Controllo salto pagina di sicurezza se ci avviciniamo al footer (280mm)
        if d_start_y + card_h > 280:
            pdf.add_page()
            d_start_y = pdf.get_y()

        # Disegno card con sfondo e bordo sinistro colorato
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(203, 213, 225)
        pdf.rect(10, d_start_y, 190, card_h, style="DF")

        # Barra di accento a sinistra: Blu royal per Drill 1, Ambra per Drill 2, Verde smeraldo per Drill 3
        accent_colors = [(37, 99, 235), (217, 119, 6), (16, 185, 129)]
        acc_col = accent_colors[(idx - 1) % len(accent_colors)]
        pdf.set_fill_color(*acc_col)
        pdf.rect(10, d_start_y, 2.5, card_h, style="F")

        # 1. Riga Titolo Drill (Blu Royal)
        pdf.set_xy(14, d_start_y + top_pad)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(30, 64, 175)
        pdf.multi_cell(182, 4.3, title_text)

        # 2. Riga Target Benchmark (Verde Smeraldo - Riga DEDICATA, mai sovrapposta!)
        pdf.set_x(14)
        pdf.ln(0.8)
        pdf.set_x(14)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(5, 150, 105)
        pdf.multi_cell(182, 4.0, bench_text)

        # 3. Riga Obiettivo (Ardesia Scuro)
        pdf.set_x(14)
        pdf.ln(0.8)
        pdf.set_x(14)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(51, 65, 85)
        pdf.multi_cell(182, 3.8, obj_text)

        # 4. Riga Esecuzione Pratica (Ardesia Corsivo)
        pdf.set_x(14)
        pdf.ln(0.8)
        pdf.set_x(14)
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(71, 85, 105)
        pdf.multi_cell(182, 3.6, exec_p)

        # Posizionamento per la card successiva (gap di 3mm)
        pdf.set_y(d_start_y + card_h + 3.0)

    return bytes(pdf.output())


def send_pdf_report_via_telegram(
    pdf_bytes: bytes,
    chat_id: int | str,
    caption: str = "🏌️‍♂️ Ecco il tuo Report di Gioco ufficiale da Voice Caddy Pro!",
    filename: str = "Voice_Caddy_Report.pdf"
) -> tuple[bool, str]:
    """
    Invia il report PDF generato direttamente alla chat Telegram specificata.
    """
    import urllib.request
    import json
    import uuid
    from core.telegram_config import TelegramConfigManager

    tg_mgr = TelegramConfigManager()
    token = tg_mgr.get_token()
    if not token:
        return False, "Nessun token Telegram configurato nel sistema."

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    boundary = f"----VoiceCaddyBoundary{uuid.uuid4().hex[:12]}"

    body = bytearray()
    # chat_id field
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode("utf-8"))
    # caption field
    if caption:
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode("utf-8"))
    # document field
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\nContent-Type: application/pdf\r\n\r\n".encode("utf-8"))
    body.extend(pdf_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    try:
        req = urllib.request.Request(
            url,
            data=bytes(body),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "VoiceCaddy/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return True, "Report PDF inviato con successo al tuo smartphone via Telegram!"
            return False, f"Errore API Telegram: {data.get('description', 'Errore sconosciuto')}"
    except Exception as e:
        return False, f"Impossibile inviare PDF a Telegram: {e}"
