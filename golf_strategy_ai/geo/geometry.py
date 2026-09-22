from __future__ import annotations

import math
from typing import List, Tuple, Dict, Any, Optional

from .projection import latlon_to_utm, utm_to_latlon

EARTH_RADIUS_M = 6371000.0


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcola la distanza geodetica ortodromica in metri tra due punti WGS84."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(EARTH_RADIUS_M * c, 2)


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcola l'angolo di rotta iniziale (bearing) in gradi da punto 1 a punto 2.
    0° = Nord, 90° = Est, 180° = Sud, 270° = Ovest.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)

    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    initial_bearing = math.atan2(y, x)
    return (math.degrees(initial_bearing) + 360.0) % 360.0


def lateral_and_longitudinal_offset(
    origin_x: float, origin_y: float,
    target_x: float, target_y: float,
    point_x: float, point_y: float
) -> Tuple[float, float]:
    """
    Calcola l'avanzamento longitudinale e la deviazione laterale in metri
    rispetto all'asse origin -> target in un sistema piano UTM.

    Ritorna: (progress_m, lateral_m)
    - progress_m: distanza proiettata lungo l'asse dall'origine.
    - lateral_m: scostamento perpendicolare (+ a destra della linea di mira, - a sinistra).
    """
    vx = target_x - origin_x
    vy = target_y - origin_y
    line_len = math.hypot(vx, vy)

    if line_len < 1e-6:
        return 0.0, 0.0

    ux = vx / line_len
    uy = vy / line_len

    wx = point_x - origin_x
    wy = point_y - origin_y

    # Proiezione scalare lungo la linea
    progress_m = wx * ux + wy * uy

    # Componente perpendicolare con orientamento 2D (Cross Product z-component)
    # ux * wy - uy * wx > 0 se il punto è a destra rispetto alla direzione (ux, uy)
    lateral_m = wx * (-uy) + wy * ux

    return round(progress_m, 2), round(lateral_m, 2)


def point_in_polygon(lat: float, lon: float, polygon: List[Tuple[float, float]]) -> bool:
    """
    Algoritmo Ray Casting per verificare se un punto (lat, lon) cade all'interno
    di un poligono geografico specificato come sequenza di vertici [(lat, lon), ...].
    """
    if len(polygon) < 3:
        return False

    inside = False
    n = len(polygon)
    p1_lat, p1_lon = polygon[0]

    for i in range(1, n + 1):
        p2_lat, p2_lon = polygon[i % n]
        if min(p1_lon, p2_lon) < lon <= max(p1_lon, p2_lon):
            if lat <= max(p1_lat, p2_lat):
                if p1_lon != p2_lon:
                    lat_intersection = (lon - p1_lon) * (p2_lat - p1_lat) / (p2_lon - p1_lon) + p1_lat
                else:
                    lat_intersection = p1_lat
                if p1_lat == p2_lat or lat <= lat_intersection:
                    inside = not inside
        p1_lat, p1_lon = p2_lat, p2_lon

    return inside


def polygon_centroid(polygon: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Calcola il baricentro geografico (lat, lon) di un poligono."""
    if not polygon:
        return 0.0, 0.0
    sum_lat = sum(p[0] for p in polygon)
    sum_lon = sum(p[1] for p in polygon)
    return round(sum_lat / len(polygon), 7), round(sum_lon / len(polygon), 7)


def generate_ellipse_points(
    center_lat: float,
    center_lon: float,
    semi_major_m: float,
    semi_minor_m: float,
    rotation_deg: float,
    num_points: int = 36
) -> List[Tuple[float, float]]:
    """
    Genera il perimetro di un'ellisse di dispersione in coordinate WGS84 [(lat, lon), ...].
    semi_major_m: semiasse maggiore (longitudinale).
    semi_minor_m: semiasse minore (laterale).
    rotation_deg: rotazione dell'asse maggiore rispetto al Nord (0° = Nord, 90° = Est).
    """
    c_x, c_y, zone, hemi = latlon_to_utm(center_lat, center_lon)
    theta_rad = math.radians(rotation_deg)

    coords_wgs84: List[Tuple[float, float]] = []
    for i in range(num_points):
        angle = 2.0 * math.pi * i / num_points
        # Ellisse non ruotata con asse maggiore lungo Y
        local_x = semi_minor_m * math.cos(angle)
        local_y = semi_major_m * math.sin(angle)

        # Rotazione verso la direzione di tiro (bearing)
        # Se theta=0 (Nord), Y locale punta verso Nord (+y UTM)
        rot_x = local_x * math.cos(theta_rad) + local_y * math.sin(theta_rad)
        rot_y = -local_x * math.sin(theta_rad) + local_y * math.cos(theta_rad)

        pt_x = c_x + rot_x
        pt_y = c_y + rot_y

        pt_lat, pt_lon = utm_to_latlon(pt_x, pt_y, zone, hemi)
        coords_wgs84.append((pt_lat, pt_lon))

    # Chiudi il poligono ripetendo il primo vertice
    if coords_wgs84:
        coords_wgs84.append(coords_wgs84[0])

    return coords_wgs84


def generate_distance_arc(
    center_lat: float,
    center_lon: float,
    distance_m: float,
    start_bearing_deg: float,
    end_bearing_deg: float,
    num_points: int = 24
) -> List[Tuple[float, float]]:
    """
    Genera un arco di cerchio geografico a distanza fissa dal green (es. 50m, 100m, 150m, 200m).
    """
    c_x, c_y, zone, hemi = latlon_to_utm(center_lat, center_lon)

    # Gestione attraversamento del Nord (360°)
    b_start = start_bearing_deg % 360.0
    b_end = end_bearing_deg % 360.0
    if b_end < b_start:
        b_end += 360.0

    step = (b_end - b_start) / max(1, num_points - 1)
    arc_coords: List[Tuple[float, float]] = []

    for i in range(num_points):
        b = math.radians(b_start + i * step)
        pt_x = c_x + distance_m * math.sin(b)
        pt_y = c_y + distance_m * math.cos(b)
        pt_lat, pt_lon = utm_to_latlon(pt_x, pt_y, zone, hemi)
        arc_coords.append((pt_lat, pt_lon))

    return arc_coords


def calculate_progress_and_offset(
    point_lat: float, point_lon: float,
    origin_lat: float, origin_lon: float,
    target_lat: float, target_lon: float
) -> Tuple[float, float]:
    """
    Calcola l'avanzamento longitudinale e la deviazione laterale in metri
    di un punto geografico (point_lat, point_lon) rispetto all'asse origin -> target.
    Ritorna: (progress_m, lateral_m)
    """
    ox, oy, zone, hem = latlon_to_utm(origin_lat, origin_lon)
    tx, ty, _, _ = latlon_to_utm(target_lat, target_lon, zone=zone)
    px, py, _, _ = latlon_to_utm(point_lat, point_lon, zone=zone)
    return lateral_and_longitudinal_offset(ox, oy, tx, ty, px, py)
