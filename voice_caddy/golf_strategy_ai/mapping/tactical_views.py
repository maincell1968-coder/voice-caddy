from __future__ import annotations

import json
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from ..models import HoleGeometry, PlayerCategory
from ..strategy.hole_agent import HolePerformanceEvaluation, GreenApproachEvaluation, ShotEvaluation
from ..geo.geometry import haversine_distance_m, bearing_deg


from core.tactical_course_manager import tactical_course_manager, TacticalHole


def render_view_a_map_html(
    hole: HoleGeometry,
    perf_eval: Optional[HolePerformanceEvaluation] = None,
    tactical_hole: Optional[TacticalHole] = None,
    centerline: Optional[List[Tuple[float, float]]] = None,
    width: str = "100%",
    height: str = "520px"
) -> str:
    """
    VISTA A: Mappa Tattica con Costruzione Completa del Piano dai dati Excel:
    - Corridoio Fairway Vettoriale (larghezza reale es. 35m)
    - Fascia Orizzontale Ottimale di Atterraggio Landing Area 1 e 2 (±20m)
    - 3 Tee di Partenza Reali (Bianchi, Gialli, Rossi) con distanze metriche
    - Superficie Green (diametro 50m) e Pin
    - Sequenza Colpi Numerati ①②③ e Playing Line
    - Layer switcher: Piano Architettonico Vettoriale Scuro (default) vs Ortofoto Satellitare Esri HD
    """
    # Recupera TacticalHole dai dati reali di coordinate_campi.xlsx se non fornito
    tactical_h = tactical_hole
    if not tactical_h:
        tactical_h = tactical_course_manager.get_tactical_hole(hole.course_id, hole.hole_number)

    center_lat = (hole.tee.lat + hole.green_center.lat) / 2.0
    center_lon = (hole.tee.lon + hole.green_center.lon) / 2.0

    # Ricava GeoJSON completo dai dati reali Excel
    if tactical_h:
        tactical_geojson = tactical_course_manager.get_hole_tactical_geojson(
            tactical_h,
            tee_color="gialli",
            shots=perf_eval.shots_evaluations if perf_eval else None
        )
        hole_par = tactical_h.par
        hole_hcp = tactical_h.hcp
        dist_b = int(tactical_h.dist_bianchi) if tactical_h.dist_bianchi else None
        dist_g = int(tactical_h.dist_gialli) if tactical_h.dist_gialli else int(hole.length_m)
        dist_r = int(tactical_h.dist_rossi) if tactical_h.dist_rossi else None
        fw_w = int(tactical_h.fairway_width)
    else:
        tactical_geojson = {"type": "FeatureCollection", "features": []}
        hole_par = hole.par
        hole_hcp = hole.stroke_index
        dist_b, dist_g, dist_r = None, int(hole.length_m), None
        fw_w = 35

    tactical_geojson_str = json.dumps(tactical_geojson)

    hud_tees = []
    if dist_b:
        hud_tees.append(f"<span style='color:#ffffff; font-weight:600;'>⚪ {dist_b}m</span>")
    hud_tees.append(f"<span style='color:#fbbf24; font-weight:600;'>🟡 {dist_g}m</span>")
    if dist_r:
        hud_tees.append(f"<span style='color:#ef4444; font-weight:600;'>🔴 {dist_r}m</span>")
    tees_str = " &nbsp;|&nbsp; ".join(hud_tees)

    html_code = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #0b111e; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        #map {{ width: {width}; height: {height}; }}
        .hud-overlay {{
            position: absolute; top: 12px; left: 12px; z-index: 1000;
            background: rgba(11, 17, 30, 0.92); backdrop-filter: blur(8px);
            border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 10px;
            padding: 10px 14px; max-width: 340px; color: #f0f6fc; box-shadow: 0 8px 24px rgba(0,0,0,0.6);
        }}
        .hud-title {{ font-size: 14px; font-weight: 800; color: #38bdf8; margin-bottom: 4px; display:flex; justify-content:space-between; }}
        .hud-sub {{ font-size: 11px; color: #94a3b8; line-height: 1.45; }}
        .shot-marker-div {{
            width: 24px; height: 24px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-weight: 800; font-size: 12px; color: #ffffff;
            border: 2px solid #ffffff; box-shadow: 0 0 8px rgba(0,0,0,0.8);
        }}
        .legend-box {{
            position: absolute; bottom: 15px; right: 12px; z-index: 1000;
            background: rgba(11, 17, 30, 0.90); border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px; padding: 8px 12px; font-size: 11px; color: #cbd5e1;
            backdrop-filter: blur(6px);
        }}
        .legend-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }}
        .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
        .leaflet-control-layers {{
            background: rgba(11, 17, 30, 0.92) !important;
            color: #f1f5f9 !important;
            border: 1px solid rgba(56, 189, 248, 0.3) !important;
            border-radius: 8px !important;
            font-size: 11px !important;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <div class="hud-overlay">
        <div class="hud-title">
            <span>⛳ Buca {hole.hole_number} — Par {hole_par}</span>
            <span style="color:#22c55e; font-size:12px;">HCP {hole_hcp}</span>
        </div>
        <div class="hud-sub">
            📐 <b>Costruzione da Dati Excel:</b> Fairway {fw_w}m | Green Ø 50m<br>
            🏌️ <b>Battitori:</b> {tees_str}<br>
            🎯 <b>Target:</b> Landing Area (±20m) & Playing Line attiva
        </div>
    </div>

    <div class="legend-box">
        <div class="legend-row"><span class="dot" style="background:#10B981;"></span> Corridoio Fairway ({fw_w}m)</div>
        <div class="legend-row"><span class="dot" style="background:#06B6D4;"></span> Landing Area 1 (±20m Drive)</div>
        <div class="legend-row"><span class="dot" style="background:#22C55E;"></span> Green (Diametro 50m)</div>
        <div class="legend-row"><span style="width:14px; height:2px; background:#F59E0B; display:inline-block;"></span> Playing Line Ideale</div>
        <div class="legend-row"><span class="dot" style="background:#DC2626;"></span> Pin / Bandiera</div>
    </div>

    <script>
        // 1. Basemap Vettoriale Architettonico Scuro (Dark Blueprint — Sostituisce la visione satellitare)
        const darkBasemap = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            maxZoom: 19,
            attribution: '&copy; CartoDB &copy; OpenStreetMap'
        }});

        // 2. Mappa centrata sul fairway
        const map = L.map('map', {{
            center: [{center_lat}, {center_lon}],
            zoom: 17,
            layers: [darkBasemap],
            attributionControl: false
        }});

        // 4. Caricamento Dati GeoJSON Vettoriali da Excel
        const tacticalData = {tactical_geojson_str};

        if (tacticalData.features && tacticalData.features.length > 0) {{
            L.geoJSON(tacticalData, {{
                style: function(feature) {{
                    const p = feature.properties || {{}};
                    return {{
                        color: p.stroke_color || '#10b981',
                        weight: p.stroke_weight || 2,
                        opacity: p.stroke_opacity !== undefined ? p.stroke_opacity : 0.9,
                        dashArray: p.dash_array || null,
                        fillColor: p.fill_color || '#10b981',
                        fillOpacity: p.fill_opacity !== undefined ? p.fill_opacity : 0.4
                    }};
                }},
                pointToLayer: function(feature, latlng) {{
                    const p = feature.properties || {{}};
                    if (p.feature_class === 'tee') {{
                        return L.circleMarker(latlng, {{
                            radius: p.radius || 7,
                            fillColor: p.marker_color || '#FBBF24',
                            color: '#FFFFFF',
                            weight: 2,
                            fillOpacity: 1.0
                        }});
                    }} else if (p.feature_class === 'pin') {{
                        return L.circleMarker(latlng, {{
                            radius: 8,
                            fillColor: '#DC2626',
                            color: '#FFFFFF',
                            weight: 2,
                            fillOpacity: 1.0
                        }});
                    }} else if (p.feature_class === 'shot') {{
                        const customIcon = L.divIcon({{
                            className: 'custom-div-icon',
                            html: `<div class="shot-marker-div" style="background:${{p.marker_color || '#10B981'}};">${{p.shot_index || 1}}</div>`,
                            iconSize: [24, 24],
                            iconAnchor: [12, 12]
                        }});
                        return L.marker(latlng, {{ icon: customIcon }});
                    }}
                    return L.circleMarker(latlng, {{
                        radius: 6,
                        fillColor: p.marker_color || '#38BDF8',
                        color: '#FFFFFF',
                        weight: 1.5,
                        fillOpacity: 0.9
                    }});
                }},
                onEachFeature: function(feature, layer) {{
                    if (feature.properties && feature.properties.label) {{
                        layer.bindTooltip(feature.properties.label, {{
                            sticky: true,
                            direction: 'top'
                        }});
                    }}
                }}
            }}).addTo(map);
        }}

        // 5. Adattamento vista ai limiti della buca
        map.fitBounds([[{hole.tee.lat}, {hole.tee.lon}], [{hole.green_center.lat}, {hole.green_center.lon}]], {{ padding: [60, 60] }});
    </script>
</body>
</html>
"""
    return html_code


def render_view_b_benchmark_html(
    perf_eval: HolePerformanceEvaluation,
    width: str = "100%"
) -> str:
    """
    VISTA B: Benchmark Balistico di Categoria & Gauge di Dispersione Fairway.
    Confronta distanza reale vs range categoria e deviazione laterale dal centro fairway (0m).
    """
    shots_html = ""
    cat_label = {
        PlayerCategory.PRIMA: "Prima Categoria (HCP 0–12)",
        PlayerCategory.SECONDA: "Seconda Categoria (HCP 12.1–26)",
        PlayerCategory.TERZA: "Terza Categoria (HCP 26.1–54)"
    }.get(perf_eval.player_category, "Seconda Categoria")

    for se in perf_eval.shots_evaluations:
        # Calcolo posizione percentuale nel range di categoria
        range_span = max(1.0, se.category_max_m - se.category_min_m)
        clamped_dist = max(se.category_min_m - 20.0, min(se.category_max_m + 20.0, se.distance_m))
        dist_pct = ((clamped_dist - (se.category_min_m - 20.0)) / (range_span + 40.0)) * 100.0

        # Badge stato distanza
        if se.distance_status in ("ottimale", "sopra_media"):
            d_badge_color = "#2ECC71"
            d_badge_text = f"✅ Distanza In Linea ({int(se.distance_m)}m)"
        elif se.distance_status == "corto":
            d_badge_color = "#F39C12"
            d_badge_text = f"⚠️ Corto di {-int(se.distance_delta_m)}m ({int(se.distance_m)}m)"
        else:
            d_badge_color = "#E74C3C"
            d_badge_text = f"❌ Sotto Benchmark ({int(se.distance_m)}m)"

        # Calcolo Gauge Dispersione Laterale (-30m a +30m)
        # Centro = 50%
        gauge_pos_pct = 50.0 + (se.lateral_offset_m / 60.0) * 100.0
        gauge_pos_pct = max(5.0, min(95.0, gauge_pos_pct))

        off_sign = "+" if se.lateral_offset_m > 0 else ""
        if se.lateral_status == "centro_perfetto":
            l_badge_color = "#2ECC71"
            l_badge_text = f"🎯 Centro Fairway ({off_sign}{se.lateral_offset_m}m)"
        elif "fairway" in se.lateral_status:
            l_badge_color = "#27AE60"
            l_badge_text = f"⛳ Fairway ({off_sign}{se.lateral_offset_m}m)"
        elif "bunker" in se.lateral_status:
            l_badge_color = "#D35400"
            l_badge_text = f"🏖️ In Bunker ({off_sign}{se.lateral_offset_m}m)"
        else:
            l_badge_color = "#E67E22"
            l_badge_text = f"🌳 Rough Laterale ({off_sign}{se.lateral_offset_m}m)"

        shots_html += f"""
        <div class="shot-card">
            <div class="shot-header">
                <span class="shot-title">🏌️ Colpo {se.shot_index}: <b>{se.club}</b></span>
                <span class="badge" style="background:rgba(255,255,255,0.1); color:#58a6ff;">HCP {perf_eval.player_handicap}</span>
            </div>

            <!-- 1. Barra di Distanza vs Categoria -->
            <div class="metric-section">
                <div class="metric-label-row">
                    <span>📏 Distanza del Colpo: <b>{int(se.distance_m)}m</b></span>
                    <span style="color:{d_badge_color}; font-weight:700;">{d_badge_text}</span>
                </div>
                <div class="bar-container">
                    <div class="category-band" style="left:20%; width:60%;"></div>
                    <div class="mean-marker" style="left:50%;" title="Media Categoria: {int(se.category_mean_m)}m"></div>
                    <div class="ball-cursor" style="left:{dist_pct:.1f}%;" title="Tua palla: {int(se.distance_m)}m"></div>
                </div>
                <div class="bar-legend">
                    <span>Min ({int(se.category_min_m)}m)</span>
                    <span>Media Categoria ({int(se.category_mean_m)}m)</span>
                    <span>Max ({int(se.category_max_m)}m)</span>
                </div>
            </div>

            <!-- 2. Gauge Dispersione Laterale dal Centro Fairway -->
            <div class="metric-section" style="margin-top:14px;">
                <div class="metric-label-row">
                    <span>🎯 Scostamento Asse Centrale (0m): <b>{off_sign}{se.lateral_offset_m}m</b></span>
                    <span style="color:{l_badge_color}; font-weight:700;">{l_badge_text}</span>
                </div>
                <div class="gauge-container">
                    <div class="fairway-zone" style="left:20%; width:60%;" title="Corridoio Fairway (±18m)"></div>
                    <div class="centerline-marker" style="left:50%;" title="Centro Fairway (0m)"></div>
                    <div class="ball-cursor-lateral" style="left:{gauge_pos_pct:.1f}%;" title="Offset: {off_sign}{se.lateral_offset_m}m"></div>
                </div>
                <div class="gauge-legend">
                    <span>⬅️ Sinistra (-30m)</span>
                    <span>Centro (0m)</span>
                    <span>Destra (+30m) ➡️</span>
                </div>
            </div>
        </div>
        """

    html_content = f"""
    <style>
        .benchmark-wrapper {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #f0f6fc;
            background: #0d1117;
            padding: 14px;
            border-radius: 12px;
            border: 1px solid #30363d;
        }}
        .benchmark-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #21262d;
            padding-bottom: 8px;
            margin-bottom: 12px;
        }}
        .benchmark-title {{ font-size: 15px; font-weight: 700; color: #58a6ff; }}
        .shot-card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 10px;
            padding: 14px;
            margin-bottom: 12px;
        }}
        .shot-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }}
        .shot-title {{ font-size: 14px; color: #f0f6fc; }}
        .metric-section {{ margin-top: 6px; }}
        .metric-label-row {{
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            margin-bottom: 4px;
            color: #c9d1d9;
        }}
        .bar-container, .gauge-container {{
            position: relative;
            height: 18px;
            background: #21262d;
            border-radius: 9px;
            overflow: visible;
        }}
        .category-band {{
            position: absolute;
            top: 0; bottom: 0;
            background: rgba(46, 204, 113, 0.25);
            border-left: 2px solid #2ECC71;
            border-right: 2px solid #2ECC71;
        }}
        .fairway-zone {{
            position: absolute;
            top: 0; bottom: 0;
            background: rgba(39, 174, 96, 0.35);
            border-left: 2px dashed #27AE60;
            border-right: 2px dashed #27AE60;
        }}
        .mean-marker, .centerline-marker {{
            position: absolute;
            top: -2px; bottom: -2px;
            width: 2px;
            background: #F1C40F;
            z-index: 2;
        }}
        .ball-cursor {{
            position: absolute;
            top: -4px;
            width: 14px; height: 14px;
            border-radius: 50%;
            background: #ffffff;
            border: 2px solid #58a6ff;
            box-shadow: 0 0 6px rgba(88, 166, 255, 0.8);
            transform: translateX(-50%);
            z-index: 5;
        }}
        .ball-cursor-lateral {{
            position: absolute;
            top: -4px;
            width: 14px; height: 14px;
            border-radius: 50%;
            background: #ffffff;
            border: 2px solid #E74C3C;
            box-shadow: 0 0 6px rgba(231, 76, 60, 0.8);
            transform: translateX(-50%);
            z-index: 5;
        }}
        .bar-legend, .gauge-legend {{
            display: flex;
            justify-content: space-between;
            font-size: 10px;
            color: #8b949e;
            margin-top: 3px;
        }}
    </style>
    <div class="benchmark-wrapper" style="width:{width};">
        <div class="benchmark-header">
            <span class="benchmark-title">📊 VISTA B: Benchmark di Categoria & Dispersione Fairway</span>
            <span style="font-size:12px; color:#8b949e;">{cat_label}</span>
        </div>
        {shots_html}
    </div>
    """
    return html_content


def render_view_c_green_radar_html(
    hole: HoleGeometry,
    app_eval: Optional[GreenApproachEvaluation] = None,
    width: str = "100%",
    height: str = "450px"
) -> str:
    """
    VISTA C: Green Radar & Proximity to Pin.
    Visualizzazione ingrandita 2D del putting green con posizione del pin,
    punto di atterraggio dell'approccio, vettore di prossimità al foro in metri e zone putting.
    """
    pin_lat = app_eval.pin_coord[0] if app_eval else hole.green_center.lat
    pin_lon = app_eval.pin_coord[1] if app_eval else hole.green_center.lon

    land_lat = app_eval.landing_coord[0] if app_eval else hole.green_center.lat + 0.00003
    land_lon = app_eval.landing_coord[1] if app_eval else hole.green_center.lon - 0.00004
    prox_m = app_eval.proximity_to_pin_m if app_eval else 4.2
    putts = app_eval.putts_count if app_eval else 2
    app_club = app_eval.approach_club if app_eval else "Pitching Wedge"

    # Sagoma green in coordinate relative centrate sul pin
    green_coords = [[[p[1], p[0]] for p in poly] for poly in hole.green_polygons]

    html_code = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #0d1117; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        #map {{ width: {width}; height: {height}; }}
        .radar-card {{
            position: absolute; top: 12px; left: 12px; z-index: 1000;
            background: rgba(13, 17, 23, 0.92); backdrop-filter: blur(8px);
            border: 1px solid rgba(255,255,255,0.15); border-radius: 10px;
            padding: 12px 16px; max-width: 320px; color: #f0f6fc; box-shadow: 0 8px 24px rgba(0,0,0,0.6);
        }}
        .prox-metric {{
            font-size: 24px; font-weight: 800; color: #2ECC71; margin: 4px 0;
        }}
        .legend-card {{
            position: absolute; bottom: 15px; right: 12px; z-index: 1000;
            background: rgba(13, 17, 23, 0.88); border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px; padding: 8px 12px; font-size: 11px; color: #c9d1d9;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <div class="radar-card">
        <div style="font-size:14px; font-weight:700; color:#58a6ff;">🎯 VISTA C: Green Radar & Proximity</div>
        <div class="prox-metric">{prox_m} m <span style="font-size:13px; font-weight:500; color:#8b949e;">dal Pin</span></div>
        <div style="font-size:12px; color:#c9d1d9; line-height:1.4;">
            • Bastone Approccio: <b>{app_club}</b><br>
            • Risultato Putting: <b>{putts} Putt</b><br>
            • Zona: <b style="color:#F1C40F;">Attacco al Birdie / 2-Putt Sicuro</b>
        </div>
    </div>

    <div class="legend-card">
        <div><span style="color:#2ECC71;">⬤</span> Cerchio Verde: 1-Putt (<2m)</div>
        <div><span style="color:#F1C40F;">⬤</span> Cerchio Giallo: 2-Putt (2-8m)</div>
        <div><span style="color:#E74C3C;">⬤</span> Cerchio Rosso: Rischio 3-Putt (>8m)</div>
    </div>

    <script>
        const map = L.map('map', {{
            center: [{pin_lat}, {pin_lon}],
            zoom: 19,
            maxZoom: 22,
            attributionControl: false
        }});

        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            maxZoom: 22
        }}).addTo(map);

        // 1. Poligoni Green
        const grCoords = {json.dumps(green_coords)};
        grCoords.forEach(c => {{
            L.polygon(c.map(p => [p[1], p[0]]), {{ color: '#27AE60', weight: 2, fillColor: '#2ECC71', fillOpacity: 0.65 }}).addTo(map);
        }});

        // 2. Zone Concentriche di Putting attorno al Pin (2m, 8m)
        L.circle([{pin_lat}, {pin_lon}], {{ radius: 2.0, color: '#2ECC71', weight: 1.5, fillOpacity: 0.15 }}).addTo(map);
        L.circle([{pin_lat}, {pin_lon}], {{ radius: 8.0, color: '#F1C40F', weight: 1.5, dashArray: '4, 4', fillOpacity: 0.08 }}).addTo(map);

        // 3. Linea Vettore di Prossimità Palla -> Bandiera
        L.polyline([[{land_lat}, {land_lon}], [{pin_lat}, {pin_lon}]], {{
            color: '#00D2D3',
            weight: 3,
            dashArray: '4, 4'
        }}).addTo(map);

        // 4. Punto di Atterraggio della Palla (Approccio)
        L.circleMarker([{land_lat}, {land_lon}], {{
            radius: 8,
            fillColor: '#3498DB',
            color: '#FFFFFF',
            weight: 2,
            fillOpacity: 1
        }}).addTo(map).bindTooltip('📍 Palla Atterrata ({prox_m}m dalla bandiera)', {{ permanent: true, direction: 'top' }});

        // 5. Bandiera Pin
        L.circleMarker([{pin_lat}, {pin_lon}], {{
            radius: 8,
            fillColor: '#E74C3C',
            color: '#FFFFFF',
            weight: 2,
            fillOpacity: 1
        }}).addTo(map).bindTooltip('🚩 Bandiera / Pin', {{ permanent: true, direction: 'bottom' }});
    </script>
</body>
</html>
"""
    return html_code
