from __future__ import annotations

import math
from typing import List, Optional

from ..models import ShotRecord, NormalizedShot, HoleGeometry, LieCategory, ShotQuality
from ..geo.projection import latlon_to_utm
from ..geo.geometry import haversine_distance_m, lateral_and_longitudinal_offset, point_in_polygon


def classify_shot_lie(end_lat: float, end_lon: float, hole: HoleGeometry) -> LieCategory:
    """Classifica la superficie di atterraggio del colpo controllando i poligoni della buca."""
    # 1. Green
    for poly in hole.green_polygons:
        if point_in_polygon(end_lat, end_lon, poly):
            return LieCategory.GREEN

    # 2. Bunker
    for poly in hole.bunker_polygons:
        if point_in_polygon(end_lat, end_lon, poly):
            return LieCategory.BUNKER

    # 3. Acqua / Ostacolo
    for poly in hole.water_polygons:
        if point_in_polygon(end_lat, end_lon, poly):
            return LieCategory.WATER

    # 4. Out of bounds
    for poly in hole.out_of_bounds_polygons:
        if point_in_polygon(end_lat, end_lon, poly):
            return LieCategory.OUT_OF_BOUNDS

    # 5. Fairway
    for poly in hole.fairway_polygons:
        if point_in_polygon(end_lat, end_lon, poly):
            return LieCategory.FAIRWAY

    # 6. Rough
    for poly in hole.rough_polygons:
        if point_in_polygon(end_lat, end_lon, poly):
            return LieCategory.ROUGH

    # Se non ricade in fairway o green o bunker, è rough di default
    return LieCategory.ROUGH


def assess_shot_quality(lie: LieCategory, lateral_offset_m: float, residual_m: float) -> ShotQuality:
    """Valuta qualitativamente l'esito del colpo in funzione della posizione e della deviazione."""
    if lie in (LieCategory.WATER, LieCategory.OUT_OF_BOUNDS):
        return ShotQuality.PENALTY
    elif lie == LieCategory.BUNKER:
        return ShotQuality.RISKY

    abs_lat = abs(lateral_offset_m)

    if lie in (LieCategory.FAIRWAY, LieCategory.GREEN):
        if abs_lat <= 10.0:
            return ShotQuality.EXCELLENT
        elif abs_lat <= 18.0:
            return ShotQuality.GOOD
        else:
            return ShotQuality.ACCEPTABLE

    # Se in rough
    if abs_lat <= 15.0:
        return ShotQuality.ACCEPTABLE
    elif abs_lat <= 28.0:
        return ShotQuality.RISKY
    else:
        return ShotQuality.POOR


def normalize_shot_to_hole(
    shot: ShotRecord,
    hole: HoleGeometry,
    target_distance_m: Optional[float] = None
) -> NormalizedShot:
    """
    Normalizza il colpo calcolando distanza reale, avanzamento lungo l'asse buca,
    deviazione laterale, distanza residua al green e superficie di atterraggio.
    """
    shot_dist = haversine_distance_m(
        shot.start_point.lat, shot.start_point.lon,
        shot.end_point.lat, shot.end_point.lon
    )

    residual_dist = haversine_distance_m(
        shot.end_point.lat, shot.end_point.lon,
        hole.green_center.lat, hole.green_center.lon
    )

    # Conversione in coordinate piane UTM
    t_x, t_y, _, _ = latlon_to_utm(hole.tee.lat, hole.tee.lon)
    g_x, g_y, _, _ = latlon_to_utm(hole.green_center.lat, hole.green_center.lon)
    b_x, b_y, _, _ = latlon_to_utm(shot.end_point.lat, shot.end_point.lon)

    # Se la buca ha un dogleg e il colpo è il tee shot, il target di riferimento è l'apex
    if hole.dogleg_apex and shot.shot_number == 1:
        tgt_x, tgt_y, _, _ = latlon_to_utm(hole.dogleg_apex.lat, hole.dogleg_apex.lon)
    else:
        tgt_x, tgt_y = g_x, g_y

    progress_m, lateral_m = lateral_and_longitudinal_offset(
        origin_x=t_x, origin_y=t_y,
        target_x=tgt_x, target_y=tgt_y,
        point_x=b_x, point_y=b_y
    )

    # Scostamento rispetto alla lunghezza totale attesa dal tee al target
    if target_distance_m is not None:
        target_dist_m = target_distance_m
    else:
        target_dist_m = math.hypot(tgt_x - t_x, tgt_y - t_y)
    longitudinal_offset = progress_m - target_dist_m

    landing_lie = classify_shot_lie(shot.end_point.lat, shot.end_point.lon, hole)
    quality = assess_shot_quality(landing_lie, lateral_m, residual_dist)

    return NormalizedShot(
        shot_id=shot.shot_id,
        club=shot.club,
        distance_m=shot_dist,
        progress_along_line_m=progress_m,
        lateral_offset_m=lateral_m,
        longitudinal_offset_m=round(longitudinal_offset, 2),
        residual_to_green_m=residual_dist,
        landing_lie=landing_lie,
        quality=quality
    )


# Alias per brevità
classify_lie = classify_shot_lie
normalize_shot = normalize_shot_to_hole
