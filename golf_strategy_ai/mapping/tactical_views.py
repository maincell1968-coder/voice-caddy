from __future__ import annotations

import json
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from ..models import HoleGeometry, PlayerCategory
from ..strategy.hole_agent import HolePerformanceEvaluation, GreenApproachEvaluation, ShotEvaluation
from ..geo.geometry import haversine_distance_m, bearing_deg


def render_view_a_map_html(
    hole: HoleGeometry,
    perf_eval: Optional[HolePerformanceEvaluation] = None,
    centerline: Optional[List[Tuple[float, float]]] = None,
    width: str = "100%",
    height: str = "520px"
) -> str:
    """
    VISTA A: Mappa Tattica Satellitare con Sequenza Colpi Numerati ①②③,
    Asse Centrale del Fairway (Centerline) e Corridoio di Ingresso al Green.
    """
    center_lat = (hole.tee.lat + hole.green_center.lat) / 2.0
    center_lon = (hole.tee.lon + hole.green_center.lon) / 2.0

    # Punti della Centerline
    if not centerline:
        t_lat, t_lon = hole.tee.lat, hole.tee.lon
        g_lat, g_lon = hole.green_center.lat, hole.green_center.lon
        centerline = [
            (t_lat + (g_lat - t_lat) * (i / 10.0), t_lon + (g_lon - t_lon) * (i / 10.0))
            for i in range(11)
        ]
    centerline_geojson = [[p[1], p[0]] for p in centerline]

    # Marker Colpi
    shots_data = []
    trajectory_coords = [[hole.tee.lon, hole.tee.lat]]

    if perf_eval and perf_eval.shots_evaluations:
        for se in perf_eval.shots_evaluations:
            shots_data.append({
                "index": se.shot_index,
                "club": se.club,
                "distance": se.distance_m,
                "lat_offset": se.lateral_offset_m,
                "status": se.lateral_status,
                "lie": se.landing_lie,
                "lat": se.end_coord[0],
                "lon": se.end_coord[1]
            })
            trajectory_coords.append([se.end_coord[1], se.end_coord[0]])
    else:
        # Colpi di default simulati se la buca non ha ancora colpi registrati
        shots_data.append({
            "index": 1,
            "club": "Tee di Partenza",
            "distance": 0.0,
            "lat_offset": 0.0,
            "status": "tee",
            "lie": "tee",
            "lat": hole.tee.lat,
            "lon": hole.tee.lon
        })

    shots_json = json.dumps(shots_data)
    trajectory_json = json.dumps(trajectory_coords)
    centerline_json = json.dumps(centerline_geojson)

    # Poligoni della buca per il layer vettoriale
    fairway_coords = [[[p[1], p[0]] for p in poly] for poly in hole.fairway_polygons]
    green_coords = [[[p[1], p[0]] for p in poly] for poly in hole.green_polygons]
    bunker_coords = [[[p[1], p[0]] for p in poly] for poly in hole.bunker_polygons]
    water_coords = [[[p[1], p[0]] for p in poly] for poly in hole.water_polygons]

    html_code = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html {{ margin: 0; padding: 0; width: 100%; height: 100%; background: #0d1117; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        #map {{ width: {width}; height: {height}; }}
        .hud-overlay {{
            position: absolute; top: 12px; left: 12px; z-index: 1000;
            background: rgba(13, 17, 23, 0.92); backdrop-filter: blur(8px);
            border: 1px solid rgba(255,255,255,0.15); border-radius: 10px;
            padding: 10px 14px; max-width: 320px; color: #f0f6fc; box-shadow: 0 8px 24px rgba(0,0,0,0.6);
        }}
        .hud-title {{ font-size: 14px; font-weight: 700; color: #58a6ff; margin-bottom: 4px; }}
        .hud-sub {{ font-size: 11px; color: #8b949e; line-height: 1.4; }}
        .shot-marker-div {{
            width: 26px; height: 26px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-weight: 800; font-size: 13px; color: #ffffff;
            border: 2px solid #ffffff; box-shadow: 0 0 8px rgba(0,0,0,0.8);
        }}
        .legend-box {{
            position: absolute; bottom: 15px; right: 12px; z-index: 1000;
            background: rgba(13, 17, 23, 0.88); border: 1px solid rgba(255,255,255,0.12);
            border-radius: 8px; padding: 8px 12px; font-size: 11px; color: #c9d1d9;
        }}
        .legend-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }}
        .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
    </style>
</head>
<body>
    <div id="map"></div>

    <div class="hud-overlay">
        <div class="hud-title">📍 VISTA A: Tracciato Colpi ①②③</div>
        <div class="hud-sub">
            <b>Buca {hole.hole_number} (Par {hole.par} — {int(hole.length_m)}m)</b><br>
            • Linea gialla: Asse centrale del Fairway (Centerline)<br>
            • Linea ciano: Traiettoria effettiva dei tuoi colpi
        </div>
    </div>

    <div class="legend-box">
        <div class="legend-row"><span class="dot" style="background:#2ECC71;"></span> Fairway / Green</div>
        <div class="legend-row"><span class="dot" style="background:#E67E22;"></span> Rough</div>
        <div class="legend-row"><span class="dot" style="background:#D35400;"></span> Bunker</div>
        <div class="legend-row"><span style="width:14px; height:2px; background:#F1C40F; display:inline-block;"></span> Asse Centro Fairway</div>
    </div>

    <script>
        const map = L.map('map', {{
            center: [{center_lat}, {center_lon}],
            zoom: 17,
            attributionControl: false
        }});

        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
            maxZoom: 19
        }}).addTo(map);

        // 1. Poligoni Fairway
        const fwCoords = {json.dumps(fairway_coords)};
        fwCoords.forEach(c => {{
            L.polygon(c.map(p => [p[1], p[0]]), {{ color: '#1E8449', weight: 2, fillColor: '#27AE60', fillOpacity: 0.45 }}).addTo(map);
        }});

        // 2. Poligoni Green
        const grCoords = {json.dumps(green_coords)};
        grCoords.forEach(c => {{
            L.polygon(c.map(p => [p[1], p[0]]), {{ color: '#27AE60', weight: 2, fillColor: '#2ECC71', fillOpacity: 0.75 }}).addTo(map);
        }});

        // 3. Poligoni Bunker
        const bkCoords = {json.dumps(bunker_coords)};
        bkCoords.forEach(c => {{
            L.polygon(c.map(p => [p[1], p[0]]), {{ color: '#D68910', weight: 2, fillColor: '#F39C12', fillOpacity: 0.7 }}).addTo(map);
        }});

        // 4. Asse Centrale Fairway (Centerline)
        const centerline = {centerline_json};
        L.polyline(centerline.map(p => [p[1], p[0]]), {{
            color: '#F1C40F',
            weight: 3,
            dashArray: '5, 5',
            opacity: 0.95
        }}).addTo(map).bindTooltip('🎯 Asse Centrale del Fairway (Linea Ideale)', {{ sticky: true }});

        // 5. Traiettoria Effettiva Colpi
        const traj = {trajectory_json};
        L.polyline(traj.map(p => [p[1], p[0]]), {{
            color: '#00D2D3',
            weight: 3,
            opacity: 0.9
        }}).addTo(map);

        // 6. Marker Numerati dei Colpi ①②③
        const shots = {shots_json};
        shots.forEach(s => {{
            let bg = '#2ECC71';
            if (s.lie === 'rough') bg = '#E67E22';
            else if (s.lie === 'bunker') bg = '#D35400';
            else if (s.index === 1) bg = '#3498DB';

            const customIcon = L.divIcon({{
                className: 'custom-div-icon',
                html: `<div class="shot-marker-div" style="background:${{bg}};">${{s.index}}</div>`,
                iconSize: [26, 26],
                iconAnchor: [13, 13]
            }});

            const offText = s.lat_offset >= 0 ? `+${{s.lat_offset}}m a destra` : `${{s.lat_offset}}m a sinistra`;
            L.marker([s.lat, s.lon], {{ icon: customIcon }}).addTo(map)
             .bindPopup(`<b>Colpo ${{s.index}} — ${{s.club}}</b><br>Distanza: <b>${{s.distance}}m</b><br>Scostamento asse: <b>${{offText}}</b><br>Superficie: <b>${{s.lie}}</b>`);
        }});

        // Bandiera Pin Green
        L.circleMarker([{hole.green_center.lat}, {hole.green_center.lon}], {{
            radius: 7, fillColor: '#E74C3C', color: '#FFFFFF', weight: 2, fillOpacity: 1
        }}).addTo(map).bindTooltip('🚩 Bandiera / Centro Green');

        // Fit Bounds
        map.fitBounds([[{hole.tee.lat}, {hole.tee.lon}], [{hole.green_center.lat}, {hole.green_center.lon}]], {{ padding: [50, 50] }});
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
