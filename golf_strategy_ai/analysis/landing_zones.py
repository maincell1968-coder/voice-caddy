from __future__ import annotations

from typing import List, Optional

from ..models import NormalizedShot, HoleGeometry, LandingZone, PlayerCategory
from ..club_profiles import get_category_profile, get_club_profile
from .dispersion import calculate_shot_dispersion


def calculate_observed_landing_zone(
    shots: List[NormalizedShot],
    hole: HoleGeometry,
    category: PlayerCategory
) -> Optional[LandingZone]:
    """Calcola la Landing Zone realmente osservata dai colpi registrati dal giocatore."""
    if not shots:
        return None

    stats = calculate_shot_dispersion(shots)
    mean_dist = stats["mean_distance_m"]
    residual = max(0.0, hole.length_m - mean_dist)

    p25 = stats["p25_m"]
    p75 = stats["p75_m"]
    mean_lat = stats["mean_lateral_m"]

    if mean_lat > 6.0:
        pref_side = "right"
    elif mean_lat > 2.0:
        pref_side = "right_center"
    elif mean_lat < -6.0:
        pref_side = "left"
    elif mean_lat < -2.0:
        pref_side = "left_center"
    else:
        pref_side = "center"

    # Strategic Position Score empirico basato su fairway hit e ostacoli
    sps = round(
        0.50 * stats["fairway_pct"]
        + 0.25 * max(0.0, 100.0 - abs(mean_lat) * 4.0)
        + 0.25 * max(0.0, 100.0 - stats["hazard_pct"] * 3.0),
        1
    )

    return LandingZone(
        zone_type="observed",
        target_distance_from_tee_m=mean_dist,
        safe_range_m=(p25, p75),
        preferred_side=pref_side,
        landing_width_m=round(stats["lateral_std_m"] * 2.0, 1),
        residual_distance_to_green_m=round(residual, 1),
        strategic_position_score=sps,
        fairway_hit_pct=stats["fairway_pct"],
        hazard_risk_pct=stats["hazard_pct"]
    )


def find_ideal_landing_zone(
    hole: HoleGeometry,
    category: PlayerCategory
) -> LandingZone:
    """
    Calcola la Landing Zone ideale consigliata dall'algoritmo tattico
    in funzione del Par della buca, della morfologia e del profilo della categoria.
    """
    cat_prof = get_category_profile(category)
    driver_stats = cat_prof.clubs.get("driver")
    wood_stats = cat_prof.clubs.get("wood_3")

    if hole.par == 3:
        # Su un Par 3 il target è direttamente il centro del green
        target_dist = hole.length_m
        safe_range = (target_dist - 10.0, target_dist + 10.0)
        return LandingZone(
            zone_type="recommended",
            target_distance_from_tee_m=target_dist,
            safe_range_m=safe_range,
            preferred_side="center",
            landing_width_m=26.0,  # Diametro medio green
            residual_distance_to_green_m=0.0,
            strategic_position_score=90.0
        )

    elif hole.par == 4:
        # Su un Par 4: la landing zone ideale cerca il miglior compromesso
        # tra distanza percorsa e precisione in fairway
        driver_total = driver_stats.total_mean_m if driver_stats else 200.0
        wood_total = wood_stats.total_mean_m if wood_stats else 180.0

        # Se la buca è corta (< 300m), il legno 3 o ibrido offre più controllo
        if hole.length_m < 310.0:
            target_dist = wood_total
            safe_range = (wood_total - 15.0, wood_total + 15.0)
            pref_side = "center"
        else:
            target_dist = driver_total
            safe_range = (driver_total - 18.0, driver_total + 18.0)
            pref_side = "left_center"  # Centro-sinistra per evitare lo slice tipico

        residual = max(50.0, hole.length_m - target_dist)
        return LandingZone(
            zone_type="recommended",
            target_distance_from_tee_m=round(target_dist, 1),
            safe_range_m=(round(safe_range[0], 1), round(safe_range[1], 1)),
            preferred_side=pref_side,
            landing_width_m=35.0,
            residual_distance_to_green_m=round(residual, 1),
            strategic_position_score=85.0
        )

    else:  # Par 5
        # Su un Par 5: prima landing zone dal tee, seconda per il lay-up
        driver_total = driver_stats.total_mean_m if driver_stats else 200.0
        target_dist = driver_total
        safe_range = (driver_total - 20.0, driver_total + 15.0)
        residual = max(180.0, hole.length_m - target_dist)

        return LandingZone(
            zone_type="recommended",
            target_distance_from_tee_m=round(target_dist, 1),
            safe_range_m=(round(safe_range[0], 1), round(safe_range[1], 1)),
            preferred_side="center",
            landing_width_m=40.0,
            residual_distance_to_green_m=round(residual, 1),
            strategic_position_score=88.0
        )
