from __future__ import annotations

import math
from typing import List, Dict, Any, Optional

from ..models import NormalizedShot, ShotRecord, DispersionEllipse, GeoPoint
from ..geo.projection import latlon_to_utm


def calculate_percentile(values: List[float], percentile: float) -> float:
    """Calcola un percentile lineare (0 - 100) per una lista di valori."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return round(d0 + d1, 2)


def calculate_shot_dispersion(shots: List[NormalizedShot]) -> Dict[str, Any]:
    """
    Calcola le statistiche aggregate di dispersione per un insieme di colpi:
    - Distanza media, mediana, P10, P25, P75, P90
    - Deviazione standard longitudinale (distanza) e laterale (direzione)
    - Percentuali di atterraggio (fairway, rough, bunker, acqua, OB)
    """
    if not shots:
        return {
            "count": 0,
            "mean_distance_m": 0.0,
            "median_distance_m": 0.0,
            "p25_m": 0.0, "p75_m": 0.0,
            "mean_lateral_m": 0.0,
            "lateral_std_m": 0.0,
            "longitudinal_std_m": 0.0,
            "fairway_pct": 0.0,
            "rough_pct": 0.0,
            "hazard_pct": 0.0,
            "bunker_pct": 0.0
        }

    n = len(shots)
    distances = [s.distance_m for s in shots]
    laterals = [s.lateral_offset_m for s in shots]

    mean_dist = sum(distances) / n
    mean_lat = sum(laterals) / n

    var_dist = sum((d - mean_dist)**2 for d in distances) / max(1, n - 1) if n > 1 else 0.0
    var_lat = sum((l - mean_lat)**2 for l in laterals) / max(1, n - 1) if n > 1 else 0.0

    std_dist = math.sqrt(var_dist)
    std_lat = math.sqrt(var_lat)

    fairway_count = sum(1 for s in shots if s.landing_lie.value == "fairway")
    rough_count = sum(1 for s in shots if s.landing_lie.value == "rough")
    bunker_count = sum(1 for s in shots if s.landing_lie.value == "bunker")
    hazard_count = sum(1 for s in shots if s.landing_lie.value in ("water", "out_of_bounds"))

    return {
        "count": n,
        "mean_distance_m": round(mean_dist, 1),
        "median_distance_m": calculate_percentile(distances, 50.0),
        "p10_m": calculate_percentile(distances, 10.0),
        "p25_m": calculate_percentile(distances, 25.0),
        "p75_m": calculate_percentile(distances, 75.0),
        "p90_m": calculate_percentile(distances, 90.0),
        "mean_lateral_m": round(mean_lat, 1),
        "lateral_std_m": round(std_lat, 1),
        "longitudinal_std_m": round(std_dist, 1),
        "sigma_lateral": round(std_lat, 1),
        "sigma_longitudinal": round(std_dist, 1),
        "fairway_pct": round((fairway_count / n) * 100.0, 1),
        "rough_pct": round((rough_count / n) * 100.0, 1),
        "bunker_pct": round((bunker_count / n) * 100.0, 1),
        "hazard_pct": round((hazard_count / n) * 100.0, 1)
    }


def build_dispersion_ellipse(
    center_lat: float,
    center_lon: float,
    semi_major_m: float,
    semi_minor_m: float,
    rotation_deg: float
) -> DispersionEllipse:
    """
    Costruisce l'oggetto DispersionEllipse con calcolo dell'area e raggio equivalente.
    semi_major_m: raggio longitudinale (avanzamento).
    semi_minor_m: raggio laterale (scostamento destra/sinistra).
    """
    c_x, c_y, _, _ = latlon_to_utm(center_lat, center_lon)
    area = math.pi * semi_major_m * semi_minor_m
    equiv_radius = math.sqrt(semi_major_m * semi_minor_m)

    return DispersionEllipse(
        center_point=GeoPoint(lat=center_lat, lon=center_lon),
        center_metric_x=c_x,
        center_metric_y=c_y,
        semi_major_axis_m=round(semi_major_m, 1),
        semi_minor_axis_m=round(semi_minor_m, 1),
        rotation_deg=round(rotation_deg, 1),
        area_sqm=round(area, 1),
        equivalent_radius_m=round(equiv_radius, 1)
    )


# Alias per brevità
calculate_dispersion = calculate_shot_dispersion
