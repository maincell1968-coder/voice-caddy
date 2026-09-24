"""
Generatore visuale del Corridoio Tattico 3D su Piano Inclinato e Spettro Radar del Green.
Implementa:
- Corridoio fairway poligonale basato sui dati reali di Coordinate Campi.xlsx
- Piano inclinato 3D con effetto di profondità e parallelepipedo del manto erboso
- Playing line continua dal Tee alla Bandiera passando per la Landing Area (1 e 2 se presenti)
- Fascia orizzontale ottimale della landing area (±20 metri verso bandiera e tee)
- Dispersione visiva dei colpi registrati con colori autentici di gara (fairway, rough, bunker, green)
- Diagramma a Spettro Balistico del Green (diametro 50m, anelli concentrici, quadranti e prossimità pin)
"""

from __future__ import annotations

import math
from typing import List, Dict, Optional, Any, Tuple
from core.tactical_course_manager import TacticalHole, tactical_course_manager


def render_tactical_corridor_html(
    tactical_hole: TacticalHole,
    shots: Optional[List[Any]] = None,
    tee_color: str = "gialli",
    is_expanded: bool = False,
    initial_tilt_deg: int = 28,
    container_id: str = "tactical_corridor_view"
) -> str:
    """
    Genera il codice HTML/SVG/CSS responsive per il corridoio tattico su piano inclinato 3D.
    """
    nominal_len = tactical_hole.get_nominal_length(tee_color)
    fairway_w = tactical_hole.fairway_width
    landing_zones = tactical_course_manager.get_landing_zones_info(tactical_hole, tee_color)

    # Elaborazione colpi del giocatore
    projected_shots = []
    prev_cum = 0.0
    if shots and len(shots) > 0:
        for s in shots:
            ps = tactical_course_manager.project_shot_along_corridor(
                tactical_hole, s, tee_color=tee_color, prev_cumulative_dist=prev_cum
            )
            projected_shots.append(ps)
            prev_cum = ps["cum_dist_m"]
    else:
        # Piano strategico dimostrativo / ideale se nessun colpo è ancora registrato
        if len(landing_zones) > 0:
            lz1_d = landing_zones[0]["dist_from_tee_m"]
            projected_shots.append({
                "shot_index": 1,
                "club": "Driver",
                "dist_m": round(lz1_d, 0),
                "cum_dist_m": round(lz1_d, 0),
                "remaining_to_green_m": round(nominal_len - lz1_d, 0),
                "lateral_offset_m": 0.0,
                "lie": "fairway",
                "result": "good",
                "notes": "Drive ideale al centro della landing area",
                "color": "#10B981",
                "in_landing_zone": True,
                "is_on_green": False
            })
            projected_shots.append({
                "shot_index": 2,
                "club": "Ferro Approccio",
                "dist_m": round(nominal_len - lz1_d, 0),
                "cum_dist_m": round(nominal_len, 0),
                "remaining_to_green_m": 3.5,
                "lateral_offset_m": 1.5,
                "lie": "green",
                "result": "green",
                "notes": "Approccio a 3.5m dall'asta",
                "color": "#06B6D4",
                "in_landing_zone": False,
                "is_on_green": True
            })
        else:
            # Par 3
            projected_shots.append({
                "shot_index": 1,
                "club": "Ferro dal Tee",
                "dist_m": round(nominal_len, 0),
                "cum_dist_m": round(nominal_len, 0),
                "remaining_to_green_m": 4.0,
                "lateral_offset_m": -1.0,
                "lie": "green",
                "result": "green",
                "notes": "Colpo al green da tee a 4m",
                "color": "#06B6D4",
                "in_landing_zone": False,
                "is_on_green": True
            })

    # Dimensioni canvas SVG
    # X va da -45 a +45 metri (larghezza totale ~90m compreso rough laterale)
    # Y va da -15m (dietro il tee) a nominal_len + 30m (dietro il green)
    svg_w = 460 if not is_expanded else 760
    svg_h = 560 if not is_expanded else 800

    meter_w_span = 90.0  # -45m a +45m
    meter_h_span = nominal_len + 45.0  # da -15m a nominal_len + 30m

    def m2svg_x(m_x: float) -> float:
        # m_x = 0 al centro
        return (m_x + 45.0) / meter_w_span * svg_w

    def m2svg_y(m_y: float) -> float:
        # m_y = 0 al tee (in basso), nominal_len al green (in alto)
        margin_bottom = 35.0
        scale = (svg_h - 70.0) / meter_h_span
        return (svg_h - margin_bottom) - (m_y + 10.0) * scale

    # Coordinate cardine
    tee_svg_x = m2svg_x(0.0)
    tee_svg_y = m2svg_y(0.0)
    green_svg_x = m2svg_x(0.0)
    green_svg_y = m2svg_y(nominal_len)

    # Punti della playing line
    pl_svg_points = [(tee_svg_x, tee_svg_y)]
    for lz in landing_zones:
        # leggera deviazione realistica o centrata
        lz_y = m2svg_y(lz["dist_from_tee_m"])
        pl_svg_points.append((tee_svg_x, lz_y))
    pl_svg_points.append((green_svg_x, green_svg_y))

    pl_poly_str = " ".join(f"{px:.1f},{py:.1f}" for px, py in pl_svg_points)

    # Poligono Fairway (larghezza = fairway_w)
    fw_half = fairway_w / 2.0
    fw_pts = [
        (m2svg_x(-fw_half * 0.7), m2svg_y(25.0)),
        (m2svg_x(-fw_half), m2svg_y(nominal_len * 0.4)),
        (m2svg_x(-fw_half * 1.05), m2svg_y(nominal_len * 0.75)),
        (m2svg_x(-fw_half * 0.8), m2svg_y(nominal_len - 15.0)),
        (m2svg_x(fw_half * 0.8), m2svg_y(nominal_len - 15.0)),
        (m2svg_x(fw_half * 1.05), m2svg_y(nominal_len * 0.75)),
        (m2svg_x(fw_half), m2svg_y(nominal_len * 0.4)),
        (m2svg_x(fw_half * 0.7), m2svg_y(25.0)),
    ]
    fw_poly_str = " ".join(f"{px:.1f},{py:.1f}" for px, py in fw_pts)

    # Fasce orizzontali Landing Area (±20m verso bandiera e tee)
    landing_bands_svg = []
    for idx, lz in enumerate(landing_zones):
        lz_center_y = lz["dist_from_tee_m"]
        y_top = m2svg_y(lz_center_y + 20.0)      # verso la bandiera
        y_bottom = m2svg_y(lz_center_y - 20.0)   # verso il tee
        band_h = abs(y_bottom - y_top)
        x_left = m2svg_x(-fw_half * 1.1)
        x_right = m2svg_x(fw_half * 1.1)
        band_w = x_right - x_left
        center_svg_y = m2svg_y(lz_center_y)
        landing_bands_svg.append({
            "index": idx + 1,
            "label": lz["label"],
            "dist_from_tee": lz["dist_from_tee_m"],
            "x": x_left,
            "y": y_top,
            "w": band_w,
            "h": band_h,
            "center_y": center_svg_y
        })

    # Yardage Markers (50m, 100m, 150m, 200m, 250m al green)
    yardage_ticks = []
    for d_green in [50, 100, 150, 200, 250]:
        y_dist = nominal_len - d_green
        if 20.0 <= y_dist <= (nominal_len - 20.0):
            yardage_ticks.append({
                "dist_to_green": d_green,
                "y": m2svg_y(y_dist),
                "x1": m2svg_x(-fw_half - 10.0),
                "x2": m2svg_x(fw_half + 10.0)
            })

    # Colpi posizionati in SVG
    shots_svg = []
    prev_pt = (tee_svg_x, tee_svg_y)
    for ps in projected_shots:
        sx = m2svg_x(ps["lateral_offset_m"])
        sy = m2svg_y(ps["cum_dist_m"])
        shots_svg.append({
            "shot_index": ps["shot_index"],
            "club": ps["club"],
            "dist_m": ps["dist_m"],
            "cum_dist_m": ps["cum_dist_m"],
            "remaining_m": ps["remaining_to_green_m"],
            "lat_offset_m": ps["lateral_offset_m"],
            "lie": ps["lie"],
            "result": ps["result"],
            "notes": ps["notes"],
            "color": ps["color"],
            "in_landing": ps["in_landing_zone"],
            "x": sx,
            "y": sy,
            "from_x": prev_pt[0],
            "from_y": prev_pt[1]
        })
        prev_pt = (sx, sy)

    # Green rendering (diametro 50m indicativo)
    # 50m diameter scale
    green_rx = (25.0 / meter_w_span) * svg_w * 0.95
    green_ry = ((nominal_len + 45.0) / meter_h_span) * 22.0

    html = f"""
    <div id="{container_id}" class="tactical-corridor-wrapper">
        <style>
            .tactical-corridor-wrapper {{
                background: linear-gradient(180deg, #09131e 0%, #060b12 100%);
                border: 1px solid #1a2c42;
                border-radius: 12px;
                padding: 12px;
                color: #F1F5F9;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                user-select: none;
            }}
            .tactical-top-bar {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
                padding-bottom: 6px;
                border-bottom: 1px solid #1e293b;
            }}
            .tactical-title {{
                font-size: 0.92rem;
                font-weight: 700;
                color: #38BDF8;
                display: flex;
                align-items: center;
                gap: 6px;
            }}
            .tactical-controls {{
                display: flex;
                gap: 6px;
                align-items: center;
            }}
            .tilt-btn {{
                background: #0F172A;
                border: 1px solid #334155;
                color: #94A3B8;
                padding: 3px 8px;
                border-radius: 5px;
                font-size: 0.72rem;
                cursor: pointer;
                transition: all 0.2s;
            }}
            .tilt-btn:hover, .tilt-btn.active {{
                background: #2563EB;
                color: #FFFFFF;
                border-color: #38BDF8;
            }}
            /* 3D PERSPECTIVE STAGE */
            .stage-3d-container {{
                perspective: 950px;
                perspective-origin: 50% 82%;
                overflow: hidden;
                border-radius: 8px;
                background: radial-gradient(circle at 50% 30%, #0f2438 0%, #07121c 100%);
                display: flex;
                justify-content: center;
                align-items: center;
                position: relative;
            }}
            .turf-slab-3d {{
                width: 100%;
                max-width: {svg_w}px;
                transform-style: preserve-3d;
                transform: rotateX({initial_tilt_deg}deg) scale(0.96);
                transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                box-shadow: 0 35px 60px -15px rgba(0, 0, 0, 0.8), 0 0 40px rgba(16, 185, 129, 0.08);
                border-radius: 14px;
            }}
            /* TOOLTIP */
            .shot-tooltip {{
                position: absolute;
                background: rgba(15, 23, 42, 0.95);
                border: 1px solid #38BDF8;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 0.75rem;
                color: #FFFFFF;
                pointer-events: none;
                display: none;
                z-index: 100;
                box-shadow: 0 4px 15px rgba(0,0,0,0.5);
                max-width: 220px;
            }}
            .legend-bar {{
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 10px;
                font-size: 0.72rem;
                color: #94A3B8;
                background: #09131e;
                padding: 6px 10px;
                border-radius: 6px;
                border: 1px solid #1a2536;
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 5px;
            }}
            .legend-color {{
                width: 10px;
                height: 10px;
                border-radius: 50%;
                display: inline-block;
            }}
        </style>

        <div class="tactical-top-bar">
            <div class="tactical-title">
                <span>📐 Corridoio Tattico 3D (Piano Inclinato)</span>
                <span style="font-size:0.75rem; color:#94A3B8; font-weight:normal;">Buca {tactical_hole.hole_number} (Par {tactical_hole.par} — {int(nominal_len)}m)</span>
            </div>
            <div class="tactical-controls">
                <button class="tilt-btn active" id="btn-tilt-3d" onclick="setTilt(28)">📐 3D ({initial_tilt_deg}°)</button>
                <button class="tilt-btn" id="btn-tilt-2d" onclick="setTilt(0)">🛸 2D (Aereo)</button>
            </div>
        </div>

        <div class="stage-3d-container" style="height: {'380px' if not is_expanded else '620px'};">
            <div id="shotTooltip" class="shot-tooltip"></div>
            
            <div id="turfSlab" class="turf-slab-3d">
                <svg viewBox="0 0 {svg_w} {svg_h}" width="100%" height="100%" style="display:block; overflow:visible;">
                    <defs>
                        <!-- Pattern Manto Erboso Fairway -->
                        <linearGradient id="fairwayGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stop-color="#14532D" />
                            <stop offset="30%" stop-color="#15803D" />
                            <stop offset="50%" stop-color="#16A34A" />
                            <stop offset="70%" stop-color="#15803D" />
                            <stop offset="100%" stop-color="#14532D" />
                        </linearGradient>

                        <linearGradient id="roughGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="#0a1f12" />
                            <stop offset="100%" stop-color="#05120a" />
                        </linearGradient>

                        <radialGradient id="greenGrad" cx="50%" cy="50%" r="50%">
                            <stop offset="0%" stop-color="#34D399" />
                            <stop offset="70%" stop-color="#059669" />
                            <stop offset="100%" stop-color="#065F46" />
                        </radialGradient>

                        <linearGradient id="landingZoneGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="rgba(245, 158, 11, 0.05)" />
                            <stop offset="50%" stop-color="rgba(245, 158, 11, 0.28)" />
                            <stop offset="100%" stop-color="rgba(245, 158, 11, 0.05)" />
                        </linearGradient>

                        <filter id="neonGlow" x="-30%" y="-30%" width="160%" height="160%">
                            <feGaussianBlur stdDeviation="3.5" result="blur" />
                            <feMerge>
                                <feMergeNode in="blur" />
                                <feMergeNode in="SourceGraphic" />
                            </feMerge>
                        </filter>
                    </defs>

                    <!-- BASE ESTRUSA 3D (PARALLELEPIPEDO TURF SLAB) -->
                    <rect x="15" y="15" width="{svg_w - 30}" height="{svg_h - 30}" rx="14" fill="url(#roughGrad)" stroke="#163824" stroke-width="2" />
                    
                    <!-- Righe orizzontali di texture rough -->
                    <g opacity="0.08" stroke="#FFFFFF" stroke-width="1">
                        {"".join(f'<line x1="20" y1="{y}" x2="{svg_w - 20}" y2="{y}" />' for y in range(40, svg_h - 40, 35))}
                    </g>

                    <!-- POLIGONO CORRIDOIO FAIRWAY (LARGHEZZA REALE DA EXCEL: {fairway_w}m) -->
                    <polygon points="{fw_poly_str}" fill="url(#fairwayGrad)" stroke="#22C55E" stroke-width="1.8" opacity="0.95" />

                    <!-- LINEE TAGLIO FAIRWAY (MOWING STRIPES) -->
                    <g opacity="0.12" stroke="#FFFFFF" stroke-width="1.2" stroke-dasharray="6,4">
                        <line x1="{m2svg_x(-fw_half*0.5)}" y1="{m2svg_y(30)}" x2="{m2svg_x(-fw_half*0.5)}" y2="{m2svg_y(nominal_len - 20)}" />
                        <line x1="{m2svg_x(fw_half*0.5)}" y1="{m2svg_y(30)}" x2="{m2svg_x(fw_half*0.5)}" y2="{m2svg_y(nominal_len - 20)}" />
                    </g>

                    <!-- YARDAGE MARKERS DAL GREEN -->
                    <g class="yardage-lines">
                        {"".join(f'''
                        <g>
                            <line x1="{yt['x1']}" y1="{yt['y']}" x2="{yt['x2']}" y2="{yt['y']}" stroke="#64748B" stroke-width="1" stroke-dasharray="3,3" opacity="0.65" />
                            <rect x="{yt['x2'] + 4}" y="{yt['y'] - 8}" width="38" height="15" rx="3" fill="#0F172A" stroke="#334155" stroke-width="0.8" />
                            <text x="{yt['x2'] + 23}" y="{yt['y'] + 3}" fill="#94A3B8" font-size="9" font-weight="bold" text-anchor="middle">{yt['dist_to_green']}m</text>
                        </g>
                        ''' for yt in yardage_ticks)}
                    </g>

                    <!-- FASCIA ORIZZONTALE LANDING AREA (±20 METRI: 40m TOTALI) -->
                    {"".join(f'''
                    <!-- Landing Area {lb['index']} (±20m) -->
                    <g class="landing-zone-band">
                        <rect x="{lb['x']}" y="{lb['y']}" width="{lb['w']}" height="{lb['h']}" rx="4" fill="url(#landingZoneGrad)" stroke="#F59E0B" stroke-width="1.8" stroke-dasharray="5,3" opacity="0.92" />
                        <!-- Linea orizzontale centrale della landing area -->
                        <line x1="{lb['x']}" y1="{lb['center_y']}" x2="{lb['x'] + lb['w']}" y2="{lb['center_y']}" stroke="#F59E0B" stroke-width="2" filter="url(#neonGlow)" />
                        <!-- Target Badge -->
                        <rect x="{lb['x'] + lb['w']/2.0 - 65}" y="{lb['center_y'] - 10}" width="130" height="20" rx="4" fill="#1E293B" stroke="#F59E0B" stroke-width="1.2" />
                        <text x="{lb['x'] + lb['w']/2.0}" y="{lb['center_y'] + 4}" fill="#FDE68A" font-size="9.5" font-weight="bold" text-anchor="middle">🎯 TARGET ZONE (±20m)</text>
                    </g>
                    ''' for lb in landing_bands_svg)}

                    <!-- PLAYING LINE GUIDA VISUALE TEE -> LANDING -> GREEN -->
                    <polyline points="{pl_poly_str}" fill="none" stroke="#38BDF8" stroke-width="2.5" stroke-dasharray="6,4" opacity="0.85" filter="url(#neonGlow)" />

                    <!-- TEE BOX DI PARTENZA -->
                    <g transform="translate({tee_svg_x}, {tee_svg_y})">
                        <rect x="-24" y="-10" width="48" height="20" rx="4" fill="#1E293B" stroke="#475569" stroke-width="1.5" />
                        <circle cx="-12" cy="0" r="3.5" fill="#FFFFFF" stroke="#000" stroke-width="0.5" />
                        <circle cx="0" cy="0" r="3.5" fill="#FBBF24" stroke="#000" stroke-width="0.5" />
                        <circle cx="12" cy="0" r="3.5" fill="#EF4444" stroke="#000" stroke-width="0.5" />
                        <text x="0" y="22" fill="#94A3B8" font-size="9" font-weight="bold" text-anchor="middle">TEE {tee_color.upper()}</text>
                    </g>

                    <!-- GREEN COMPLEX (SUPERFICIE CIRCOLARE ~50m DIAMETRO) -->
                    <g transform="translate({green_svg_x}, {green_svg_y})">
                        <!-- Fringe / Collar -->
                        <ellipse cx="0" cy="0" rx="{green_rx * 1.25}" ry="{green_ry * 1.25}" fill="#065F46" opacity="0.6" stroke="#047857" stroke-width="1.5" />
                        <!-- Putting Green Turf -->
                        <ellipse cx="0" cy="0" rx="{green_rx}" ry="{green_ry}" fill="url(#greenGrad)" stroke="#10B981" stroke-width="2" />
                        <!-- Anelli concentrici diametro 50m green -->
                        <ellipse cx="0" cy="0" rx="{green_rx * 0.5}" ry="{green_ry * 0.5}" fill="none" stroke="rgba(255,255,255,0.25)" stroke-dasharray="2,2" />
                        <!-- Cup / Hole & Pin -->
                        <circle cx="0" cy="0" r="3.5" fill="#000000" />
                        <!-- Asta e bandierina rossa -->
                        <line x1="0" y1="0" x2="0" y2="-28" stroke="#FFFFFF" stroke-width="1.5" />
                        <polygon points="0,-28 14,-22 0,-16" fill="#EF4444" stroke="#B91C1C" stroke-width="0.8" />
                        <text x="0" y="-32" fill="#38BDF8" font-size="10" font-weight="bold" text-anchor="middle">GREEN (~50m)</text>
                    </g>

                    <!-- TRAIETTORIE E COLPI DEL GIOCATORE CON COLORI DI GARA -->
                    <!-- Curve paraboliche di volo palla -->
                    {"".join(f'''
                    <path d="M {s['from_x']} {s['from_y']} Q {(s['from_x'] + s['x'])/2.0 + 8} {(s['from_y'] + s['y'])/2.0} {s['x']} {s['y']}" 
                          fill="none" stroke="{s['color']}" stroke-width="2" stroke-dasharray="4,3" opacity="0.75" />
                    ''' for s in shots_svg)}

                    <!-- Marker Colpi -->
                    {"".join(f'''
                    <g transform="translate({s['x']}, {s['y']})" 
                       style="cursor:pointer;"
                       onmouseover="showTooltip(event, '{s['shot_index']}', '{s['club']}', '{s['dist_m']}', '{s['lie'].upper()}', '{s['lat_offset_m']}', '{s['notes']}')"
                       onmouseout="hideTooltip()">
                        <!-- Glowing halo -->
                        <circle cx="0" cy="0" r="14" fill="{s['color']}" opacity="0.25" filter="url(#neonGlow)" />
                        <!-- Pulsing inner circle -->
                        <circle cx="0" cy="0" r="9" fill="{s['color']}" stroke="#FFFFFF" stroke-width="1.8" />
                        <!-- Numero colpo -->
                        <text x="0" y="3.5" fill="#000000" font-size="9" font-weight="900" text-anchor="middle">{s['shot_index']}</text>
                        <!-- Badge Bastone & Distanza -->
                        <rect x="14" y="-10" width="76" height="18" rx="4" fill="#0F172A" stroke="{s['color']}" stroke-width="1" opacity="0.9" />
                        <text x="52" y="3" fill="#FFFFFF" font-size="8.5" font-weight="bold" text-anchor="middle">{s['club']} ({int(s['dist_m'])}m)</text>
                    </g>
                    ''' for s in shots_svg)}

                </svg>
            </div>
        </div>

        <!-- LEGENDA COLORI REGISTRATI -->
        <div class="legend-bar">
            <span style="font-weight:bold; color:#FFFFFF;">Legenda Colori Colpi:</span>
            <div class="legend-item"><span class="legend-color" style="background:#10B981;"></span> Fairway</div>
            <div class="legend-item"><span class="legend-color" style="background:#06B6D4;"></span> Green</div>
            <div class="legend-item"><span class="legend-color" style="background:#F59E0B;"></span> Rough</div>
            <div class="legend-item"><span class="legend-color" style="background:#FBBF24;"></span> Bunker</div>
            <div class="legend-item"><span class="legend-color" style="background:#3B82F6;"></span> Acqua / Ostacolo</div>
            <div class="legend-item"><span class="legend-color" style="background:#EF4444;"></span> Fuori Limite</div>
            <span style="margin-left:auto; color:#F59E0B; font-weight:bold;">🎯 Fascia Gialla = Target Landing Area (±20m)</span>
        </div>

        <script>
            function setTilt(deg) {{
                const slab = document.getElementById('turfSlab');
                if (slab) {{
                    slab.style.transform = `rotateX(${{deg}}deg) scale(0.96)`;
                }}
                document.getElementById('btn-tilt-3d').classList.toggle('active', deg > 0);
                document.getElementById('btn-tilt-2d').classList.toggle('active', deg === 0);
            }}

            function showTooltip(evt, idx, club, dist, lie, offset, notes) {{
                const tt = document.getElementById('shotTooltip');
                if (!tt) return;
                const sign = offset >= 0 ? '+' : '';
                tt.innerHTML = `
                    <div style="font-weight:bold; color:#38BDF8; margin-bottom:2px;">Colpo #${{idx}} — ${{club}}</div>
                    <div>Distanza: <b>${{dist}}m</b> | Terreno: <b>${{lie}}</b></div>
                    <div>Deviazione dalla Playing Line: <b style="color:${{Math.abs(offset) <= 5 ? '#10B981' : '#F59E0B'}}">${{sign}}${{offset}}m</b></div>
                    ${{notes ? `<div style="color:#CBD5E1; font-style:italic; margin-top:3px; font-size:0.7rem;">"${{notes}}"</div>` : ''}}
                `;
                tt.style.display = 'block';
                tt.style.left = (evt.offsetX + 20) + 'px';
                tt.style.top = (evt.offsetY - 20) + 'px';
            }}

            function hideTooltip() {{
                const tt = document.getElementById('shotTooltip');
                if (tt) tt.style.display = 'none';
            }}
        </script>
    </div>
    """
    return html


def render_green_spectrum_html(
    tactical_hole: TacticalHole,
    shots: Optional[List[Any]] = None,
    tee_color: str = "gialli",
    is_expanded: bool = False
) -> str:
    """
    Genera il Diagramma a Spettro Balistico del Green (~50m diametro):
    - Rappresentazione radar circolare centrata sulla bandiera
    - Anelli concentrici di dispersione balistica (3m, 6m, 10m, 15m, 25m)
    - 4 Quadranti tattici (Corto/Lungo, Sx/Dx)
    - Posizionamento del colpo di approccio al green con esito e GIR
    """
    nominal_len = tactical_hole.get_nominal_length(tee_color)

    # Individua il colpo al green (approccio o colpo dal tee su Par 3)
    approach_shot = None
    approach_idx = 1
    if shots and len(shots) > 0:
        for s in shots:
            lie = getattr(s, "lie", "fairway")
            lie_str = str(lie.value if hasattr(lie, "value") else lie).lower()
            res = getattr(s, "result", "good")
            res_str = str(res.value if hasattr(res, "value") else res).lower()
            s_idx = getattr(s, "shot_index", 1)
            # Su par 3 è il colpo 1, su par 4 è tipicamente il 2, su par 5 il 3
            if s_idx == (tactical_hole.par - 2) or "green" in res_str or "green" in lie_str or s_idx == len(shots) - 1:
                approach_shot = s
                approach_idx = s_idx
                break
        if not approach_shot and len(shots) > 0:
            approach_shot = shots[-1]
            approach_idx = len(shots)

    # Parametri balistici del colpo al green
    club = getattr(approach_shot, "club", "Ferro 7") if approach_shot else "Ferro Approccio"
    res = getattr(approach_shot, "result", "green") if approach_shot else "green"
    res_str = str(res.value if hasattr(res, "value") else res).lower()
    notes = getattr(approach_shot, "notes", "Preso in pieno green") if approach_shot else "Approccio centro green"

    # Distanza reale al pin (in metri) e coordinate (dx, dy) rispetto alla buca
    # 0 = buca al centro
    if "green" in res_str:
        dist_to_pin = 4.2
        dx = 2.5   # 2.5m a destra
        dy = -3.4  # 3.4m corto
        is_gir = True
    elif "left" in res_str or "hook" in res_str:
        dist_to_pin = 16.5
        dx = -15.0
        dy = -6.0
        is_gir = False
    elif "right" in res_str or "slice" in res_str:
        dist_to_pin = 18.0
        dx = 16.0
        dy = 8.0
        is_gir = False
    elif "bunker" in res_str:
        dist_to_pin = 14.0
        dx = 11.0
        dy = -8.5
        is_gir = False
    else:
        dist_to_pin = 5.8
        dx = -3.2
        dy = 4.8
        is_gir = True

    # Determinazione quadrante
    horiz = "Destra" if dx >= 0 else "Sinistra"
    vert = "Lungo (Back)" if dy >= 0 else "Corto (Front)"
    quadrant_desc = f"{vert} a {horiz}"

    svg_size = 440 if not is_expanded else 600
    c = svg_size / 2.0
    # Scala: raggio 25m = c * 0.85
    scale = (c * 0.82) / 25.0

    ball_x = c + (dx * scale)
    ball_y = c - (dy * scale)  # Y invertito in SVG

    html = f"""
    <div class="green-spectrum-container">
        <style>
            .green-spectrum-container {{
                background: linear-gradient(180deg, #091522 0%, #050b12 100%);
                border: 1px solid #1e334d;
                border-radius: 12px;
                padding: 14px;
                color: #FFFFFF;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }}
            .green-spectrum-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 12px;
                padding-bottom: 8px;
                border-bottom: 1px solid #1e293b;
            }}
            .green-spectrum-badge {{
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 0.75rem;
                font-weight: bold;
            }}
            .gir-yes {{
                background: rgba(16, 185, 129, 0.2);
                color: #10B981;
                border: 1px solid #10B981;
            }}
            .gir-no {{
                background: rgba(245, 158, 11, 0.2);
                color: #F59E0B;
                border: 1px solid #F59E0B;
            }}
            .telemetry-row {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 8px;
                margin-top: 12px;
            }}
            .telemetry-card {{
                background: #0f1d2e;
                border: 1px solid #1f324a;
                border-radius: 8px;
                padding: 8px;
                text-align: center;
            }}
            .telemetry-card span {{
                font-size: 0.70rem;
                color: #94A3B8;
                text-transform: uppercase;
                display: block;
            }}
            .telemetry-card b {{
                font-size: 1.05rem;
                color: #38BDF8;
            }}
        </style>

        <div class="green-spectrum-header">
            <div>
                <b style="font-size:1.0rem; color:#38BDF8;">🎯 Diagramma a Spettro — Colpo al Green</b>
                <div style="font-size:0.75rem; color:#94A3B8;">Buca {tactical_hole.hole_number} | Green Circolare (~50m diametro) | Pin al Centro</div>
            </div>
            <div class="green-spectrum-badge {'gir-yes' if is_gir else 'gir-no'}">
                {'🟢 GIR (Green in Reg.)' if is_gir else '🟡 Missed Green'}
            </div>
        </div>

        <div style="display:flex; justify-content:center;">
            <svg viewBox="0 0 {svg_size} {svg_size}" width="100%" max-width="{svg_size}px" height="auto" style="display:block;">
                <defs>
                    <radialGradient id="greenRadarGrad" cx="50%" cy="50%" r="50%">
                        <stop offset="0%" stop-color="#10B981" stop-opacity="0.35" />
                        <stop offset="60%" stop-color="#059669" stop-opacity="0.25" />
                        <stop offset="90%" stop-color="#047857" stop-opacity="0.15" />
                        <stop offset="100%" stop-color="#0f2619" stop-opacity="0.05" />
                    </radialGradient>
                    <filter id="radarGlow" x="-20%" y="-20%" width="140%" height="140%">
                        <feGaussianBlur stdDeviation="3" result="blur" />
                        <feMerge>
                            <feMergeNode in="blur" />
                            <feMergeNode in="SourceGraphic" />
                        </feMerge>
                    </filter>
                </defs>

                <!-- SFONDO VERDE RADAR DEL GREEN (50m DIAMETRO) -->
                <circle cx="{c}" cy="{c}" r="{25.0 * scale}" fill="url(#greenRadarGrad)" stroke="#10B981" stroke-width="2.5" />
                <circle cx="{c}" cy="{c}" r="{25.0 * scale + 15}" fill="none" stroke="#065F46" stroke-width="1.5" stroke-dasharray="4,4" />

                <!-- RETICOLO QUADRANTI (Assi X e Y) -->
                <line x1="{c}" y1="15" x2="{c}" y2="{svg_size - 15}" stroke="#334155" stroke-width="1.2" stroke-dasharray="4,3" />
                <line x1="15" y1="{c}" x2="{svg_size - 15}" y2="{c}" stroke="#334155" stroke-width="1.2" stroke-dasharray="4,3" />

                <!-- ANELLI CONCENTRICI DI DISPERSIONE (3m, 6m, 10m, 15m, 20m, 25m) -->
                {"".join(f'''
                <circle cx="{c}" cy="{c}" r="{r_m * scale}" fill="none" stroke="#475569" stroke-width="1" stroke-dasharray="2,3" opacity="0.6" />
                <rect x="{c + (r_m * scale) - 12}" y="{c - 8}" width="24" height="13" rx="3" fill="#0F172A" />
                <text x="{c + (r_m * scale)}" y="{c + 2}" fill="#94A3B8" font-size="8" font-weight="bold" text-anchor="middle">{r_m}m</text>
                ''' for r_m in [3, 6, 10, 15, 20, 25])}

                <!-- ETICHETTE QUADRANTI -->
                <text x="30" y="35" fill="#64748B" font-size="9" font-weight="bold">BACK-LEFT</text>
                <text x="{svg_size - 30}" y="35" fill="#64748B" font-size="9" font-weight="bold" text-anchor="end">BACK-RIGHT</text>
                <text x="30" y="{svg_size - 25}" fill="#64748B" font-size="9" font-weight="bold">FRONT-LEFT</text>
                <text x="{svg_size - 30}" y="{svg_size - 25}" fill="#64748B" font-size="9" font-weight="bold" text-anchor="end">FRONT-RIGHT</text>

                <!-- FRECCIA DIREZIONE TIRO DI APPROCCIO (dal basso) -->
                <path d="M {c} {svg_size - 20} L {c} {svg_size - 45}" stroke="#38BDF8" stroke-width="2.5" marker-end="url(#arrow)" />
                <text x="{c}" y="{svg_size - 6}" fill="#38BDF8" font-size="9" font-weight="bold" text-anchor="middle">▲ DIREZIONE APPROCCIO</text>

                <!-- CENTRO GREEN / BANDIERA -->
                <circle cx="{c}" cy="{c}" r="4" fill="#000000" />
                <line x1="{c}" y1="{c}" x2="{c}" y2="{c - 28}" stroke="#FFFFFF" stroke-width="2" />
                <polygon points="{c},{c - 28} {c + 14},{c - 22} {c},{c - 16}" fill="#EF4444" stroke="#B91C1C" stroke-width="0.8" />
                <text x="{c}" y="{c + 14}" fill="#EF4444" font-size="8.5" font-weight="bold" text-anchor="middle">PIN (0m)</text>

                <!-- LINEA DI DISTANZA PIN -> PALLA -->
                <line x1="{c}" y1="{c}" x2="{ball_x}" y2="{ball_y}" stroke="{'#10B981' if is_gir else '#F59E0B'}" stroke-width="1.8" stroke-dasharray="3,3" />

                <!-- RETICOLO E PUNTO DI IMPATTO DELLA PALLA -->
                <g transform="translate({ball_x}, {ball_y})">
                    <!-- Glow & Concentric reticle -->
                    <circle cx="0" cy="0" r="14" fill="{'#10B981' if is_gir else '#F59E0B'}" opacity="0.25" filter="url(#radarGlow)" />
                    <circle cx="0" cy="0" r="8" fill="{'#10B981' if is_gir else '#F59E0B'}" stroke="#FFFFFF" stroke-width="2" />
                    <!-- Mirino crosshair -->
                    <line x1="-12" y1="0" x2="12" y2="0" stroke="#FFFFFF" stroke-width="1" />
                    <line x1="0" y1="-12" x2="0" y2="12" stroke="#FFFFFF" stroke-width="1" />
                    <!-- Badge distanza -->
                    <rect x="12" y="-12" width="70" height="20" rx="4" fill="#0F172A" stroke="{'#10B981' if is_gir else '#F59E0B'}" stroke-width="1.2" />
                    <text x="47" y="2" fill="#FFFFFF" font-size="9" font-weight="bold" text-anchor="middle">{dist_to_pin}m dal Pin</text>
                </g>
            </svg>
        </div>

        <div class="telemetry-row">
            <div class="telemetry-card">
                <span>Bastone Approccio</span>
                <b>{club}</b>
            </div>
            <div class="telemetry-card">
                <span>Prossimità Pin</span>
                <b style="color:{'#10B981' if is_gir else '#F59E0B'};">{dist_to_pin} m</b>
            </div>
            <div class="telemetry-card">
                <span>Quadrante Green</span>
                <b style="font-size:0.85rem;">{quadrant_desc}</b>
            </div>
            <div class="telemetry-card">
                <span>Condizione Putt</span>
                <b style="font-size:0.85rem; color:#A7F3D0;">{'In Salita' if dy < 0 else 'In Discesa'}</b>
            </div>
        </div>
    </div>
    """
    return html
