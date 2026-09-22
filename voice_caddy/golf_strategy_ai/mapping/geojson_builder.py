import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..models import HoleGeometry, HoleStrategyResult, NormalizedShot, ShotRecord, GeoPoint
from ..geo.geometry import generate_ellipse_points, generate_distance_arc, bearing_deg, haversine_distance_m


def build_hole_geojson(
    hole: HoleGeometry,
    strategy: Optional[HoleStrategyResult] = None,
    shots: Optional[List[Any]] = None
) -> Dict[str, Any]:
    """
    Costruisce una FeatureCollection GeoJSON standard contenente tutti gli elementi
    della buca, i layer vettoriali, le linee di gioco, gli archi metrici e la dispersione.
    """
    features: List[Dict[str, Any]] = []

    # 1. Fairway Polygons
    for idx, poly in enumerate(hole.fairway_polygons):
        features.append({
            "type": "Feature",
            "properties": {
                "feature_class": "fairway",
                "label": f"Fairway Buca {hole.hole_number}",
                "fill_color": "#27AE60",
                "fill_opacity": 0.45,
                "stroke_color": "#1E8449",
                "stroke_weight": 2
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[p[1], p[0]] for p in poly] + ([[poly[0][1], poly[0][0]]] if poly and poly[0] != poly[-1] else [])]
            }
        })

    # 2. Green Polygons
    for idx, poly in enumerate(hole.green_polygons):
        features.append({
            "type": "Feature",
            "properties": {
                "feature_class": "green",
                "label": f"Green Buca {hole.hole_number} (Par {hole.par})",
                "fill_color": "#2ECC71",
                "fill_opacity": 0.75,
                "stroke_color": "#27AE60",
                "stroke_weight": 2
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[p[1], p[0]] for p in poly] + ([[poly[0][1], poly[0][0]]] if poly and poly[0] != poly[-1] else [])]
            }
        })

    # 3. Bunker Polygons
    for idx, poly in enumerate(hole.bunker_polygons):
        features.append({
            "type": "Feature",
            "properties": {
                "feature_class": "bunker",
                "label": f"Bunker Buca {hole.hole_number}",
                "fill_color": "#F39C12",
                "fill_opacity": 0.65,
                "stroke_color": "#D68910",
                "stroke_weight": 2
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[p[1], p[0]] for p in poly] + ([[poly[0][1], poly[0][0]]] if poly and poly[0] != poly[-1] else [])]
            }
        })

    # 4. Water Polygons
    for idx, poly in enumerate(hole.water_polygons):
        features.append({
            "type": "Feature",
            "properties": {
                "feature_class": "water",
                "label": f"Ostacolo d'Acqua Buca {hole.hole_number}",
                "fill_color": "#2980B9",
                "fill_opacity": 0.65,
                "stroke_color": "#1F618D",
                "stroke_weight": 2
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[p[1], p[0]] for p in poly] + ([[poly[0][1], poly[0][0]]] if poly and poly[0] != poly[-1] else [])]
            }
        })

    # 5. Tee Point
    features.append({
        "type": "Feature",
        "properties": {
            "feature_class": "tee",
            "label": f"Tee di Partenza — Buca {hole.hole_number} (Par {hole.par}, {int(hole.length_m)}m)",
            "marker_color": "#E67E22"
        },
        "geometry": {
            "type": "Point",
            "coordinates": [hole.tee.lon, hole.tee.lat]
        }
    })

    # 6. Green Center Point
    features.append({
        "type": "Feature",
        "properties": {
            "feature_class": "pin",
            "label": f"Centro Green — Buca {hole.hole_number}",
            "marker_color": "#E74C3C"
        },
        "geometry": {
            "type": "Point",
            "coordinates": [hole.green_center.lon, hole.green_center.lat]
        }
    })

    # 7. Linea Ideale di Gioco (Tee -> Apex / LZ -> Green)
    line_coords = [[hole.tee.lon, hole.tee.lat]]
    if hole.dogleg_apex:
        line_coords.append([hole.dogleg_apex.lon, hole.dogleg_apex.lat])
    line_coords.append([hole.green_center.lon, hole.green_center.lat])

    features.append({
        "type": "Feature",
        "properties": {
            "feature_class": "ideal_line",
            "label": f"Linea Ideale di Gioco ({int(hole.length_m)}m)",
            "stroke_color": "#F39C12",
            "stroke_weight": 3,
            "dash_array": "6, 6"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": line_coords
        }
    })

    # 8. Archi Metrici di Distanza dal Green (50m, 100m, 150m, 200m)
    tee_bearing = bearing_deg(hole.green_center.lat, hole.green_center.lon, hole.tee.lat, hole.tee.lon)
    arc_distances = [50.0, 100.0, 150.0, 200.0]
    for dist in arc_distances:
        if dist < hole.length_m - 20.0:
            arc_pts = generate_distance_arc(
                center_lat=hole.green_center.lat,
                center_lon=hole.green_center.lon,
                distance_m=dist,
                start_bearing_deg=tee_bearing - 45.0,
                end_bearing_deg=tee_bearing + 45.0
            )
            features.append({
                "type": "Feature",
                "properties": {
                    "feature_class": "distance_arc",
                    "distance_m": dist,
                    "label": f"{int(dist)}m al centro green",
                    "stroke_color": "#FFFFFF",
                    "stroke_weight": 1.5,
                    "stroke_opacity": 0.7,
                    "dash_array": "4, 4"
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[p[1], p[0]] for p in arc_pts]
                }
            })

    # 9. Ellisse di Dispersione (se presente nella strategia)
    if strategy and strategy.dispersion_ellipse:
        ell = strategy.dispersion_ellipse
        ell_pts = generate_ellipse_points(
            center_lat=ell.center_point.lat,
            center_lon=ell.center_point.lon,
            semi_major_m=ell.semi_major_axis_m,
            semi_minor_m=ell.semi_minor_axis_m,
            rotation_deg=ell.rotation_deg
        )
        cat_color = {
            "prima": "#3498DB",
            "seconda": "#E67E22",
            "terza": "#E74C3C"
        }.get(strategy.category.value if hasattr(strategy.category, "value") else str(strategy.category), "#3498DB")

        features.append({
            "type": "Feature",
            "properties": {
                "feature_class": "dispersion_ellipse",
                "category": strategy.category.value if hasattr(strategy.category, "value") else str(strategy.category),
                "label": f"Ellisse Dispersione 95% ({strategy.category.value.title()} Categoria)",
                "fill_color": cat_color,
                "fill_opacity": 0.25,
                "stroke_color": cat_color,
                "stroke_weight": 2.5
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[p[1], p[0]] for p in ell_pts]]
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features
    }


def load_hole_geometry_from_geojson(geojson_path: str | Path) -> HoleGeometry:
    """
    Carica un file GeoJSON e costruisce un oggetto HoleGeometry completo.
    Estrae Tee, Green, Fairway, Bunkers e Ostacoli d'acqua.
    """
    path = Path(geojson_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tee: Optional[GeoPoint] = None
    green_center: Optional[GeoPoint] = None
    green_front: Optional[GeoPoint] = None
    green_back: Optional[GeoPoint] = None
    dogleg_apex: Optional[GeoPoint] = None

    hole_number = 1
    par = 4
    length_m = 0.0
    stroke_index = 1

    fairway_polygons: List[List[tuple[float, float]]] = []
    green_polygons: List[List[tuple[float, float]]] = []
    bunker_polygons: List[List[tuple[float, float]]] = []
    water_polygons: List[List[tuple[float, float]]] = []
    rough_polygons: List[List[tuple[float, float]]] = []

    features = data.get("features", [])
    for feat in features:
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        f_class = props.get("feature_class", "").lower()
        coords = geom.get("coordinates", [])

        if "hole_number" in props and props["hole_number"]:
            hole_number = int(props["hole_number"])
        if "par" in props and props["par"]:
            par = int(props["par"])
        if "length_m" in props and props["length_m"]:
            length_m = float(props["length_m"])
        if "stroke_index" in props and props["stroke_index"]:
            stroke_index = int(props["stroke_index"])

        if f_class == "tee":
            # Point: [lon, lat]
            tee = GeoPoint(lat=coords[1], lon=coords[0], alt_m=props.get("elevation_m"))
        elif f_class in ("pin", "green_center"):
            green_center = GeoPoint(lat=coords[1], lon=coords[0], alt_m=props.get("elevation_m"))
        elif f_class == "green_front":
            green_front = GeoPoint(lat=coords[1], lon=coords[0])
        elif f_class == "green_back":
            green_back = GeoPoint(lat=coords[1], lon=coords[0])
        elif f_class == "dogleg":
            dogleg_apex = GeoPoint(lat=coords[1], lon=coords[0])
        elif f_class == "fairway":
            # Polygon: [[[lon, lat], ...]] -> [(lat, lon), ...]
            if geom.get("type") == "Polygon" and coords:
                fairway_polygons.append([(pt[1], pt[0]) for pt in coords[0]])
        elif f_class == "green":
            if geom.get("type") == "Polygon" and coords:
                green_polygons.append([(pt[1], pt[0]) for pt in coords[0]])
        elif f_class == "bunker":
            if geom.get("type") == "Polygon" and coords:
                bunker_polygons.append([(pt[1], pt[0]) for pt in coords[0]])
        elif f_class == "water":
            if geom.get("type") == "Polygon" and coords:
                water_polygons.append([(pt[1], pt[0]) for pt in coords[0]])
        elif f_class == "rough":
            if geom.get("type") == "Polygon" and coords:
                rough_polygons.append([(pt[1], pt[0]) for pt in coords[0]])

    if not tee:
        raise ValueError(f"Feature 'tee' non trovata nel file GeoJSON: {geojson_path}")
    if not green_center:
        raise ValueError(f"Feature 'pin' / 'green_center' non trovata nel file GeoJSON: {geojson_path}")

    if length_m <= 0.0:
        length_m = haversine_distance_m(tee.lat, tee.lon, green_center.lat, green_center.lon)

    return HoleGeometry(
        hole_number=hole_number,
        par=par,
        length_m=length_m,
        stroke_index=stroke_index,
        tee=tee,
        green_center=green_center,
        green_front=green_front,
        green_back=green_back,
        dogleg_apex=dogleg_apex,
        fairway_polygons=fairway_polygons,
        green_polygons=green_polygons,
        bunker_polygons=bunker_polygons,
        water_polygons=water_polygons,
        rough_polygons=rough_polygons
    )
