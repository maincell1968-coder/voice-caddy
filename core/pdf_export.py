from __future__ import annotations

from core.schemas import GolfRoundData
from core.metrics import GolfMetricsCalculator


class PDFReportGenerator:
    """
    Generates printable HTML & PDF performance reports for Voice Caddy.
    Allows golfers to export their round scorecard, PGA professional diagnosis, and training plan.
    """

    @staticmethod
    def generate_html_report(round_data: GolfRoundData) -> str:
        summary = round_data.performance_summary
        info = round_data.round_info
        diag = summary.professional_diagnosis
        rel_par = GolfMetricsCalculator.calculate_score_relation_to_par(round_data.holes)
        rel_par_str = f"+{rel_par}" if rel_par > 0 else ("Par" if rel_par == 0 else f"{rel_par}")
        matrix = GolfMetricsCalculator.get_scorecard_matrix(round_data.holes)

        scorecard_rows = ""
        for r in matrix:
            bg_color = "#2c3e50"
            if r["Status"] == "Eagle or Better":
                bg_color = "#1b4d3e"
            elif r["Status"] == "Birdie":
                bg_color = "#27ae60"
            elif r["Status"] == "Bogey":
                bg_color = "#d35400"
            elif r["Status"] == "Double+ Bogey":
                bg_color = "#c0392b"

            scorecard_rows += f"""
            <tr>
                <td style="text-align:center;"><b>{r['Buca']}</b></td>
                <td style="text-align:center;">{r['Par']}</td>
                <td style="text-align:center; background-color:{bg_color}; color:#ffffff; font-weight:bold;">{r['Score']} ({r['+/-']})</td>
                <td style="text-align:center;">{r['FIR']}</td>
                <td style="text-align:center;">{r['GIR']}</td>
                <td style="text-align:center;">{r['Putts']}</td>
                <td>{r['Dettaglio Errore']}</td>
            </tr>
            """

        drills_html = ""
        for d in summary.training_drills_recommended:
            drills_html += f"""
            <div style="background:#f8f9fa; border-left:4px solid #2ecc71; padding:12px; margin-bottom:12px; border-radius:4px;">
                <span style="color:#27ae60; font-weight:bold; font-size:11px; text-transform:uppercase;">{d.target_area}</span>
                <h4 style="margin:4px 0 6px 0; color:#2c3e50;">{d.drill_name}</h4>
                <p style="margin:0 0 6px 0; color:#444; font-size:13px;"><b>Obiettivo:</b> {d.objective}</p>
                <p style="margin:0 0 6px 0; color:#555; font-size:13px; line-height:1.4;">{d.setup_and_execution}</p>
                <p style="margin:0; color:#d35400; font-size:12px; font-weight:bold;">🎯 Target Misurabile: {d.success_benchmark}</p>
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="utf-8">
    <title>Voice Caddy - Report Partita PGA</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; margin: 30px; background: #fff; line-height: 1.5; }}
        .header {{ border-bottom: 3px solid #2ecc71; padding-bottom: 15px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; color: #1e2b37; font-size: 24px; }}
        .header p {{ margin: 5px 0 0 0; color: #7f8c8d; font-size: 13px; }}
        .kpi-container {{ display: flex; justify-content: space-between; margin-bottom: 20px; background: #f4f6f7; padding: 12px; border-radius: 8px; }}
        .kpi-card {{ text-align: center; flex: 1; border-right: 1px solid #ddd; }}
        .kpi-card:last-child {{ border-right: none; }}
        .kpi-val {{ font-size: 20px; font-weight: bold; color: #2c3e50; margin-top: 4px; }}
        .kpi-lbl {{ font-size: 10px; text-transform: uppercase; color: #7f8c8d; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 12px; }}
        th {{ background: #2c3e50; color: white; padding: 8px; text-align: center; }}
        td {{ padding: 6px; border-bottom: 1px solid #eee; }}
        .section-title {{ font-size: 16px; color: #2c3e50; border-bottom: 2px solid #ecf0f1; padding-bottom: 6px; margin-top: 25px; margin-bottom: 12px; }}
        .diag-box {{ background: #fdfefe; border: 1px solid #e1e8ed; padding: 15px; border-radius: 6px; margin-bottom: 15px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⛳ Voice Caddy — Analisi Prestazionale PGA</h1>
        <p><b>Campo:</b> {info.course_name or 'Non specificato'} | <b>Buche:</b> {info.holes_played} | <b>Data:</b> {info.date or 'Oggi'}</p>
    </div>

    <div class="kpi-container">
        <div class="kpi-card">
            <div class="kpi-lbl">Score Finale</div>
            <div class="kpi-val">{summary.total_score} ({rel_par_str})</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-lbl">Fairway Hit (FIR)</div>
            <div class="kpi-val">{summary.fairway_accuracy_pct}%</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-lbl">Green in Reg. (GIR)</div>
            <div class="kpi-val">{summary.gir_pct}%</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-lbl">Course Mgmt Score</div>
            <div class="kpi-val">{diag.course_management_score}/100</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-lbl">Scrambling</div>
            <div class="kpi-val">{summary.scrambling_pct}%</div>
        </div>
    </div>

    <div class="section-title">🧠 Diagnosi Professionale del Caddie</div>
    <div class="diag-box">
        <p><b>Sintesi Giro:</b> {diag.executive_narrative}</p>
        <p><b>Dispersion Leak Principale:</b> {diag.biggest_stroke_leak}</p>
        <p><b>Analisi Esecuzione Tecnica vs Tattica:</b> {diag.technical_vs_tactical_split}</p>
    </div>

    <div class="section-title">📋 Scorecard Dettagliata</div>
    <table>
        <thead>
            <tr>
                <th>Buca</th>
                <th>Par</th>
                <th>Score</th>
                <th>FIR</th>
                <th>GIR</th>
                <th>Putt</th>
                <th>Dettaglio Errore / Note</th>
            </tr>
        </thead>
        <tbody>
            {scorecard_rows}
        </tbody>
    </table>

    <div class="section-title">🎯 Piano di Allenamento Personalizzato</div>
    {drills_html}

    <div style="margin-top:35px; padding-top:15px; border-top:1px solid #e2e8f0; text-align:center; font-size:11px; color:#718096;">
        <b>Voice Caddy Pro</b> &bull; Concept, Architettura &copy; 2025-2026 <b>Stefano Pirani</b> &bull; Generato da Voice Caddy AI Performance Engine
    </div>
</body>
</html>
"""
        return html_content
