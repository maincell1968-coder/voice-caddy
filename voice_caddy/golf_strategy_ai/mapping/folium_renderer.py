from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..models import HoleGeometry, HoleStrategyResult, NormalizedShot
from .geojson_builder import build_hole_geojson


def render_hole_map_html(
    hole: HoleGeometry,
    strategy: Optional[HoleStrategyResult] = None,
    shots: Optional[List[Any]] = None,
    width: str = "100%",
    height: str = "650px",
    title: Optional[str] = None
) -> str:
    """
    Genera una pagina HTML interattiva e indipendente basata su Leaflet.js e
    ortofoto satellitare ad alta risoluzione (Esri World Imagery).
    Visualizza poligoni vettoriali, archi metrici, ellissi di dispersione e HUD tattico.
    """
    geojson_data = build_hole_geojson(hole, strategy, shots)
    geojson_json_str = json.dumps(geojson_data)

    # Centro mappa: punto medio tra Tee e Centro Green
    center_lat = (hole.tee.lat + hole.green_center.lat) / 2.0
    center_lon = (hole.tee.lon + hole.green_center.lon) / 2.0

    hud_title = title or f"BUCA {hole.hole_number} — PAR {hole.par} ({int(hole.length_m)} m)"

    caddy_advice = strategy.caddy_strategy_text if strategy else "Mappa tattica ad alta risoluzione con rilievo vettoriale."
    sps_val = strategy.strategic_position_score if strategy else 85.0
    drs_val = strategy.dispersion_risk_score if strategy else 35.0
    gos_val = strategy.gir_opportunity_score if strategy else 65.0
    tee_club = strategy.recommended_tee_club if strategy else "Driver"
    app_club = strategy.recommended_approach_club if strategy else "Ferro 7"

    html_content = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{hud_title}</title>
    <!-- Leaflet CSS & JS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body, html {{
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #0d1117;
            color: #f0f6fc;
        }}
        #map {{
            width: {width};
            height: {height};
            z-index: 1;
        }}
        /* HUD Sovrapposto in Glassmorphism */
        .tactical-hud {{
            position: absolute;
            top: 14px;
            left: 14px;
            z-index: 1000;
            background: rgba(13, 17, 23, 0.88);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            padding: 12px 16px;
            max-width: 380px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
        }}
        .hud-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid rgba(255, 255, 255, 0.12);
            padding-bottom: 6px;
            margin-bottom: 8px;
        }}
        .hud-title {{
            font-size: 15px;
            font-weight: 700;
            color: #58a6ff;
            letter-spacing: 0.5px;
        }}
        .hud-pills {{
            display: flex;
            gap: 6px;
            margin-bottom: 8px;
        }}
        .pill {{
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 20px;
            text-transform: uppercase;
        }}
        .pill-sps {{ background: #238636; color: #fff; }}
        .pill-drs {{ background: #d29922; color: #fff; }}
        .pill-gos {{ background: #1f6feb; color: #fff; }}
        .hud-advice {{
            font-size: 12px;
            line-height: 1.45;
            color: #c9d1d9;
        }}
        .hud-clubs {{
            display: flex;
            justify-content: space-between;
            margin-top: 8px;
            padding-top: 6px;
            border-top: 1px dashed rgba(255, 255, 255, 0.1);
            font-size: 11px;
            color: #8b949e;
        }}
        .hud-clubs strong {{ color: #f0f6fc; }}
        /* Legenda in basso a destra */
        .map-legend {{
            position: absolute;
            bottom: 20px;
            right: 14px;
            z-index: 1000;
            background: rgba(13, 17, 23, 0.85);
            backdrop-filter: blur(6px);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 11px;
            line-height: 1.6;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .color-box {{
            width: 12px;
            height: 12px;
            border-radius: 3px;
            display: inline-block;
        }}
    </style>
</head>
<body>
    <div id="map"></div>

    <!-- HUD Tattico Caddie -->
    <div class="tactical-hud">
        <div class="hud-header">
            <span class="hud-title">⛳ {hud_title}</span>
        </div>
        <div class="hud-pills">
            <span class="pill pill-sps" title="Strategic Position Score">SPS {sps_val}</span>
            <span class="pill pill-drs" title="Dispersion Risk Score">DRS {drs_val}</span>
            <span class="pill pill-gos" title="GIR Opportunity Score">GIR {gos_val}%</span>
        </div>
        <div class="hud-advice">
            {caddy_advice}
        </div>
        <div class="hud-clubs">
            <span>Tee: <strong>{tee_club}</strong></span>
            <span>Approccio: <strong>{app_club}</strong></span>
        </div>
    </div>

    <!-- Legenda Colori -->
    <div class="map-legend">
        <div class="legend-item"><span class="color-box" style="background:#2ECC71;"></span> Green</div>
        <div class="legend-item"><span class="color-box" style="background:#27AE60;"></span> Fairway</div>
        <div class="legend-item"><span class="color-box" style="background:#F39C12;"></span> Bunker</div>
        <div class="legend-item"><span class="color-box" style="background:#2980B9;"></span> Ostacolo Acqua</div>
        <div class="legend-item"><span class="color-box" style="background:#3498DB; opacity:0.6;"></span> Ellisse Dispersione</div>
    </div>

    <script>
        // 1. Inizializzazione Mappa Leaflet
        const map = L.map('map', {{
            center: [{center_lat}, {center_lon}],
            zoom: 17,
            zoomControl: true,
            attributionControl: false
        }});

        // 2. Basemap Vettoriale Architettonico Scuro (Dark Blueprint)
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
            attribution: '&copy; CartoDB &copy; OpenStreetMap'
        }).addTo(map);

        // 3. Caricamento Dati GeoJSON Vettoriali
        const geojsonData = {geojson_json_str};

        L.geoJSON(geojsonData, {{
            style: function(feature) {{
                const p = feature.properties;
                return {{
                    color: p.stroke_color || '#3388ff',
                    weight: p.stroke_weight || 2,
                    opacity: p.stroke_opacity || 0.9,
                    dashArray: p.dash_array || null,
                    fillColor: p.fill_color || '#3388ff',
                    fillOpacity: p.fill_opacity !== undefined ? p.fill_opacity : 0.4
                }};
            }},
            pointToLayer: function(feature, latlng) {{
                const p = feature.properties;
                if (p.feature_class === 'tee') {{
                    return L.circleMarker(latlng, {{
                        radius: 8,
                        fillColor: p.marker_color || '#E67E22',
                        color: '#FFFFFF',
                        weight: 2,
                        opacity: 1,
                        fillOpacity: 0.9
                    }});
                }} else if (p.feature_class === 'pin') {{
                    return L.circleMarker(latlng, {{
                        radius: 7,
                        fillColor: '#E74C3C',
                        color: '#FFFFFF',
                        weight: 2,
                        opacity: 1,
                        fillOpacity: 1.0
                    }});
                }}
                return L.circleMarker(latlng, {{
                    radius: 5,
                    fillColor: p.marker_color || '#3498DB',
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

        // 4. Auto-fit dei confini della buca
        const bounds = L.latLngBounds([
            [{hole.tee.lat}, {hole.tee.lon}],
            [{hole.green_center.lat}, {hole.green_center.lon}]
        ]);
        map.fitBounds(bounds, {{ padding: [60, 60] }});
    </script>
</body>
</html>
"""
    return html_content


def save_hole_map_html(
    hole: HoleGeometry,
    output_path: str | Path,
    strategy: Optional[HoleStrategyResult] = None,
    shots: Optional[List[Any]] = None
) -> Path:
    """Salva la mappa HTML completa su disco."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    html_code = render_hole_map_html(hole, strategy, shots)
    out_p.write_text(html_code, encoding="utf-8")
    return out_p
