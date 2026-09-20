from __future__ import annotations

from core.schemas import GolfRoundData
from core.metrics import GolfMetricsCalculator
from core.whs_rules import generate_tournament_summary_data


class PDFReportGenerator:
    """
    Generates printable HTML & PDF performance reports for Voice Caddy.
    Integrates official tournament rules (R&A/USGA Rule 21.1 and Rule 3):
    - Always displays both Gross and Net results (strokes and Stableford points).
    - Distinguishes between Stableford (95% WHS) and Stroke Play / Medal (100%).
    - Generates full tournament summary sections (A to G).
    """

    @staticmethod
    def generate_html_report(round_data: GolfRoundData) -> str:
        summary = round_data.performance_summary
        info = round_data.round_info
        diag = summary.professional_diagnosis
        rel_par = GolfMetricsCalculator.calculate_score_relation_to_par(round_data.holes)
        rel_par_str = f"+{rel_par}" if rel_par > 0 else ("Par" if rel_par == 0 else f"{rel_par}")
        matrix = GolfMetricsCalculator.get_scorecard_matrix(round_data.holes)

        # Estrazione dati ufficiali di gara (Sezioni A-G)
        t_data = generate_tournament_summary_data(round_data)
        is_stableford = t_data["is_stableford"]

        # Righe Scorecard Dettagliata
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

            si_val = r.get("SI", "-")
            hcp_val = r.get("HCP", 0)
            net_val = r.get("Score Netto", r["Score"])
            stbl_g = r.get("Stabl. Lordo", "-")
            stbl_n = r.get("Stabl. Netto", "-")

            scorecard_rows += f"""
            <tr>
                <td style="text-align:center;"><b>{r['Buca']}</b></td>
                <td style="text-align:center;">{r['Par']}</td>
                <td style="text-align:center; color:#7f8c8d;">{si_val}</td>
                <td style="text-align:center; color:#2980b9; font-weight:bold;">+{hcp_val}</td>
                <td style="text-align:center; background-color:{bg_color}; color:#ffffff; font-weight:bold;">{r['Score']} ({r['+/-']})</td>
                <td style="text-align:center; font-weight:bold; color:#2c3e50;">{net_val}</td>
                <td style="text-align:center; font-weight:bold; color:#8e44ad;">{stbl_g} pt</td>
                <td style="text-align:center; font-weight:bold; color:#27ae60;">{stbl_n} pt</td>
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

        # Sezione D: Anomalie o note di validazione
        anomalies_html = ""
        if t_data["anomalies"]:
            items = "".join([f"<li>⚠️ {a}</li>" for a in t_data["anomalies"]])
            anomalies_html = f"""
            <div style="background:#fef9e7; border-left:4px solid #f39c12; padding:10px 14px; margin-bottom:14px; border-radius:4px; font-size:12px; color:#7d6608;">
                <b>Dati da verificare o completare:</b>
                <ul style="margin:4px 0 0 0; padding-left:18px;">{items}</ul>
            </div>
            """
        else:
            anomalies_html = """
            <div style="background:#eafaf1; border-left:4px solid #2ecc71; padding:8px 12px; margin-bottom:14px; border-radius:4px; font-size:12px; color:#1e8449;">
                ✅ <b>Validazione Dati Completata:</b> Tutti i parametri di gara (Par, Stroke Index, Colpi Lordi e Handicap di Gioco) risultano validi e verificati.
            </div>
            """

        # Sezione C: Tabella Risultati Ufficiale
        if is_stableford:
            results_table_header = """
            <tr>
                <th>Giocatore</th>
                <th>HCP Index</th>
                <th>Playing HCP</th>
                <th>Colpi Lordi</th>
                <th>Colpi Netti</th>
                <th>Punti Stableford Lordi</th>
                <th>Punti Stableford Netti</th>
                <th>Posizione Lorda</th>
                <th>Posizione Netta</th>
                <th>Note</th>
            </tr>
            """
            results_table_row = f"""
            <tr>
                <td style="text-align:center; font-weight:bold;">{t_data['player_name']}</td>
                <td style="text-align:center;">{t_data['hcp_index']}</td>
                <td style="text-align:center; font-weight:bold; color:#2980b9;">{t_data['playing_hcp']}</td>
                <td style="text-align:center; font-weight:bold;">{t_data['total_gross']} ({rel_par_str})</td>
                <td style="text-align:center; font-weight:bold; color:#27ae60;">{t_data['total_net']}</td>
                <td style="text-align:center; font-weight:bold; color:#8e44ad;">{t_data['total_stableford_gross']} pt</td>
                <td style="text-align:center; font-weight:bold; color:#2ecc71; font-size:13px;">{t_data['total_stableford_net']} pt</td>
                <td style="text-align:center; font-weight:bold;">{t_data['leaderboard_gross']['posizione']}</td>
                <td style="text-align:center; font-weight:bold; color:#27ae60;">{t_data['leaderboard_net']['posizione']}</td>
                <td style="text-align:center; font-size:11px; color:#7f8c8d;">Giro Regolare</td>
            </tr>
            """
        else:
            results_table_header = """
            <tr>
                <th>Giocatore</th>
                <th>HCP Index</th>
                <th>Playing HCP</th>
                <th>Colpi Lordi</th>
                <th>Colpi Netti</th>
                <th>Posizione Lorda</th>
                <th>Posizione Netta</th>
                <th>Note</th>
            </tr>
            """
            results_table_row = f"""
            <tr>
                <td style="text-align:center; font-weight:bold;">{t_data['player_name']}</td>
                <td style="text-align:center;">{t_data['hcp_index']}</td>
                <td style="text-align:center; font-weight:bold; color:#2980b9;">{t_data['playing_hcp']}</td>
                <td style="text-align:center; font-weight:bold;">{t_data['total_gross']} ({rel_par_str})</td>
                <td style="text-align:center; font-weight:bold; color:#27ae60; font-size:13px;">{t_data['total_net']}</td>
                <td style="text-align:center; font-weight:bold;">{t_data['leaderboard_gross']['posizione']}</td>
                <td style="text-align:center; font-weight:bold; color:#27ae60;">{t_data['leaderboard_net']['posizione']}</td>
                <td style="text-align:center; font-size:11px; color:#7f8c8d;">Giro Regolare</td>
            </tr>
            """

        # KPI Cards differenziate
        if is_stableford:
            kpi_primary_val = f"{t_data['total_stableford_net']} pt <span style='font-size:13px; color:#7f8c8d; font-weight:normal;'>({t_data['total_stableford_gross']} Lordi)</span>"
            kpi_primary_lbl = "Stableford (Netto / Lordo)"
            kpi_strokes_val = f"{t_data['total_gross']} L / {t_data['total_net']} N"
            kpi_strokes_lbl = "Colpi (Lordo / Netto)"
        else:
            kpi_primary_val = f"{t_data['total_gross']} ({rel_par_str})"
            kpi_primary_lbl = "Colpi Lordi"
            kpi_strokes_val = f"{t_data['total_net']} Colpi"
            kpi_strokes_lbl = f"Colpi Netti (HCP {t_data['playing_hcp']})"

        html_content = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="utf-8">
    <title>Voice Caddy - Report Ufficiale di Gara PGA</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; margin: 30px; background: #fff; line-height: 1.5; }}
        .header {{ border-bottom: 3px solid #2ecc71; padding-bottom: 15px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; color: #1e2b37; font-size: 24px; }}
        .header p {{ margin: 5px 0 0 0; color: #7f8c8d; font-size: 13px; }}
        .kpi-container {{ display: flex; justify-content: space-between; margin-bottom: 20px; background: #f4f6f7; padding: 12px; border-radius: 8px; }}
        .kpi-card {{ text-align: center; flex: 1; border-right: 1px solid #ddd; }}
        .kpi-card:last-child {{ border-right: none; }}
        .kpi-val {{ font-size: 18px; font-weight: bold; color: #2c3e50; margin-top: 4px; }}
        .kpi-lbl {{ font-size: 10px; text-transform: uppercase; color: #7f8c8d; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 12px; }}
        th {{ background: #2c3e50; color: white; padding: 8px; text-align: center; font-size: 11px; }}
        td {{ padding: 6px; border-bottom: 1px solid #eee; }}
        .section-title {{ font-size: 16px; color: #2c3e50; border-bottom: 2px solid #ecf0f1; padding-bottom: 6px; margin-top: 25px; margin-bottom: 12px; }}
        .diag-box {{ background: #fdfefe; border: 1px solid #e1e8ed; padding: 15px; border-radius: 6px; margin-bottom: 15px; }}
        .summary-box {{ background: #fcfcfc; border: 1px solid #dcdde1; border-radius: 6px; padding: 14px; margin-bottom: 20px; }}
        .summary-header {{ display: flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 8px; }}
        .badge-format {{ background: #2980b9; color: white; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }}
        .leaderboard-grid {{ display: flex; gap: 15px; margin-top: 10px; margin-bottom: 10px; }}
        .leaderboard-card {{ flex: 1; background: #fff; border: 1px solid #e1e8ed; padding: 10px 14px; border-radius: 6px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>⛳ Voice Caddy — Analisi Prestazionale & Riepilogo Ufficiale di Gara</h1>
        <p>
            <b>Giocatore:</b> {t_data['player_name']} | 
            <b>Campo:</b> {info.course_name or 'Non specificato'} | 
            <b>Buche:</b> {info.holes_played} | 
            <b>Data:</b> {info.date or 'Oggi'} | 
            <b>Formula:</b> <span class="badge-format">{t_data['format_name']}</span>
        </p>
    </div>

    <!-- Top KPI Cards -->
    <div class="kpi-container">
        <div class="kpi-card">
            <div class="kpi-lbl">{kpi_primary_lbl}</div>
            <div class="kpi-val">{kpi_primary_val}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-lbl">{kpi_strokes_lbl}</div>
            <div class="kpi-val">{kpi_strokes_val}</div>
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

    <!-- Sezione Ufficiale Riepilogo Gara (A - G) -->
    <div class="section-title">🏆 Riepilogo Ufficiale di Gara (Lordo e Netto)</div>
    <div class="summary-box">
        <div class="summary-header">
            <div><b>A. Formula di Gara:</b> {t_data['format_name']}</div>
            <div><b>Playing HCP applicato:</b> {t_data['playing_hcp']} (Exact HCP: {t_data['hcp_index']})</div>
        </div>
        <p style="font-size:12px; color:#555; margin:0 0 12px 0;">
            <b>B. Metodo di Calcolo Utilizzato:</b> {t_data['calc_method']}
        </p>

        <!-- D. Validazioni e Anomalie -->
        {anomalies_html}

        <!-- C. Tabella Risultati -->
        <p style="font-size:13px; font-weight:bold; margin:10px 0 6px 0; color:#2c3e50;">C. Tabella Risultati Ufficiale</p>
        <table>
            <thead>
                {results_table_header}
            </thead>
            <tbody>
                {results_table_row}
            </tbody>
        </table>

        <!-- E & F. Classifiche Netta e Lorda -->
        <div class="leaderboard-grid">
            <div class="leaderboard-card">
                <div style="font-size:11px; text-transform:uppercase; color:#7f8c8d;">E. Classifica Netta Ufficiale</div>
                <div style="font-size:18px; font-weight:bold; color:#27ae60; margin-top:2px;">
                    {t_data['leaderboard_net']['posizione']} — {t_data['leaderboard_net']['valore']}
                </div>
                <div style="font-size:11px; color:#555; margin-top:2px;">Criterio: {t_data['leaderboard_net']['criterio']}</div>
            </div>
            <div class="leaderboard-card">
                <div style="font-size:11px; text-transform:uppercase; color:#7f8c8d;">F. Classifica Lorda Ufficiale</div>
                <div style="font-size:18px; font-weight:bold; color:#2c3e50; margin-top:2px;">
                    {t_data['leaderboard_gross']['posizione']} — {t_data['leaderboard_gross']['valore']}
                </div>
                <div style="font-size:11px; color:#555; margin-top:2px;">Criterio: {t_data['leaderboard_gross']['criterio']}</div>
            </div>
        </div>

        <!-- G. Nota finale di conformità -->
        <div style="margin-top:12px; font-size:12px; color:#2c3e50; font-weight:500;">
            <b>G. Nota Finale:</b> {t_data['compliance_note']}
        </div>
    </div>

    <!-- Diagnosi Caddie -->
    <div class="section-title">🧠 Diagnosi Professionale del Caddie</div>
    <div class="diag-box">
        <p><b>Sintesi Giro:</b> {diag.executive_narrative}</p>
        <p><b>Dispersion Leak Principale:</b> {diag.biggest_stroke_leak}</p>
        <p><b>Analisi Esecuzione Tecnica vs Tattica:</b> {diag.technical_vs_tactical_split}</p>
    </div>

    <!-- Scorecard Dettagliata -->
    <div class="section-title">📋 Scorecard Dettagliata Buca per Buca</div>
    <table>
        <thead>
            <tr>
                <th>Buca</th>
                <th>Par</th>
                <th>SI</th>
                <th>HCP</th>
                <th>Colpi Lordi</th>
                <th>Colpi Netti</th>
                <th>Stabl. Lordo</th>
                <th>Stabl. Netto</th>
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

    <!-- Piano di Allenamento -->
    <div class="section-title">🎯 Piano di Allenamento Personalizzato</div>
    {drills_html}

    <div style="margin-top:35px; padding-top:15px; border-top:1px solid #e2e8f0; text-align:center; font-size:11px; color:#718096;">
        <b>Voice Caddy Pro</b> &bull; Concept, Architettura &copy; 2025-2026 <b>Stefano Pirani</b> &bull; Generato da Voice Caddy AI Performance Engine
    </div>
</body>
</html>
"""
        return html_content

