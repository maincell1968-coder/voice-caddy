from __future__ import annotations

from typing import List, Optional, Tuple

from ..models import (
    HoleGeometry, HoleStrategyResult, LandingZone, PlayerCategory,
    NormalizedShot, LieCategory
)
from ..club_profiles import get_category_profile, rank_clubs_for_shot
from .scoring import (
    calculate_strategic_position_score,
    calculate_dispersion_risk_score,
    calculate_gir_opportunity_score
)
from ..analysis.landing_zones import find_ideal_landing_zone, calculate_observed_landing_zone
from ..analysis.dispersion import build_dispersion_ellipse
from ..geo.geometry import bearing_deg


def recommend_clubs_for_hole(
    hole: HoleGeometry,
    category: PlayerCategory
) -> Tuple[str, str]:
    """
    Seleziona la mazza ottimale dal tee e la mazza stimata per il colpo al green.
    Ritorna: (recommended_tee_club, recommended_approach_club)
    """
    cat_prof = get_category_profile(category)

    if hole.par == 3:
        # Su Par 3: cerca la mazza che copre esattamente la lunghezza della buca
        ranked = rank_clubs_for_shot(
            required_total_m=hole.length_m,
            required_carry_m=hole.length_m - 8.0,
            landing_zone_width_m=26.0,
            category=category
        )
        tee_club = ranked[0]["label"] if ranked else "Ferro 6"
        return tee_club, "Putter"

    elif hole.par == 4:
        # Su Par 4: valuta se usare il Driver o una mazza di sicurezza (Legno 3 / Ibrido)
        if hole.length_m < 310.0 and "wood_3" in cat_prof.clubs:
            tee_club = cat_prof.clubs["wood_3"].label
            target_dist = cat_prof.clubs["wood_3"].total_mean_m
        else:
            tee_club = cat_prof.clubs["driver"].label if "driver" in cat_prof.clubs else "Driver"
            target_dist = cat_prof.clubs["driver"].total_mean_m if "driver" in cat_prof.clubs else 200.0

        residual = max(50.0, hole.length_m - target_dist)
        approach_ranked = rank_clubs_for_shot(
            required_total_m=residual,
            required_carry_m=residual - 6.0,
            landing_zone_width_m=28.0,
            category=category
        )
        approach_club = approach_ranked[0]["label"] if approach_ranked else "Ferro 8"
        return tee_club, approach_club

    else:  # Par 5
        tee_club = cat_prof.clubs["driver"].label if "driver" in cat_prof.clubs else "Driver"
        t_dist = cat_prof.clubs["driver"].total_mean_m if "driver" in cat_prof.clubs else 210.0
        residual = max(180.0, hole.length_m - t_dist)

        # Secondo colpo tipicamente ibrido o legno da terra
        if "hybrid_4" in cat_prof.clubs:
            approach_club = cat_prof.clubs["hybrid_4"].label
        elif "wood_3" in cat_prof.clubs:
            approach_club = cat_prof.clubs["wood_3"].label
        else:
            approach_club = "Ferro 6"

        return tee_club, approach_club


def generate_caddy_strategy_text(
    hole: HoleGeometry,
    category: PlayerCategory,
    rec_lz: LandingZone,
    tee_club: str,
    approach_club: str,
    risk_factor: str
) -> str:
    """Genera il commento strategico naturale del Caddie professionista."""
    cat_label = {
        PlayerCategory.PRIMA: "Prima Categoria",
        PlayerCategory.SECONDA: "Seconda Categoria",
        PlayerCategory.TERZA: "Terza Categoria"
    }.get(category, "Seconda Categoria")

    if hole.par == 3:
        return (
            f"🎯 <b>Par 3 da {int(hole.length_m)}m:</b> Per un giocatore di {cat_label}, il colpo consigliato è con <b>{tee_club}</b> "
            f"mirando al centro del green. Attenzione al rischio principale ({risk_factor}): preferisci un atterraggio "
            f"nella zona sicura evitando penalità frontali."
        )
    elif hole.par == 4:
        return (
            f"🏌️ <b>Par 4 da {int(hole.length_m)}m:</b> Strategia consigliata dal tee con <b>{tee_club}</b> "
            f"per coprire tra {int(rec_lz.safe_range_m[0])}m e {int(rec_lz.safe_range_m[1])}m "
            f"sul lato <b>{rec_lz.preferred_side}</b> del fairway. "
            f"Questo lascia un secondo colpo ideale di circa {int(rec_lz.residual_distance_to_green_m)}m con <b>{approach_club}</b> "
            f"per attaccare il green in regulation ({risk_factor})."
        )
    else:  # Par 5
        return (
            f"⛳ <b>Par 5 da {int(hole.length_m)}m:</b> Strategia a 3 colpi. Tee shot con <b>{tee_club}</b> sul centro fairway "
            f"({int(rec_lz.target_distance_from_tee_m)}m). Secondo colpo di piazzamento con <b>{approach_club}</b> "
            f"per lasciare un comodo approccio con wedge al green. Rischio da monitorare: {risk_factor}."
        )


def analyze_hole_strategy(
    hole: HoleGeometry,
    category: PlayerCategory,
    course_id: str = "conero_golf_club",
    shots: Optional[List[NormalizedShot]] = None
) -> HoleStrategyResult:
    """
    Funzione principale del motore strategico: analizza la buca, identifica landing zone
    ideali e reali, calcola i punteggi SPS/DRS/GOS e genera le raccomandazioni.
    """
    cat_prof = get_category_profile(category)
    rec_lz = find_ideal_landing_zone(hole, category)
    obs_lz = calculate_observed_landing_zone(shots, hole, category) if shots else None

    tee_club, approach_club = recommend_clubs_for_hole(hole, category)

    # Identifica il fattore di rischio principale
    has_water = bool(hole.water_polygons)
    has_bunker = bool(hole.bunker_polygons)
    if has_water:
        risk_factor = "ostacolo d'acqua in gioco"
    elif has_bunker:
        risk_factor = "bunker di protezione"
    else:
        risk_factor = "rough laterale / alberi"

    sps = calculate_strategic_position_score(
        residual_distance_m=rec_lz.residual_distance_to_green_m,
        landing_lie=LieCategory.FAIRWAY,
        fairway_width_m=rec_lz.landing_width_m,
        has_hazard_in_line=has_water,
        category=category
    )

    driver_stat = cat_prof.clubs.get("driver")
    lat_std = driver_stat.lateral_dispersion_m if driver_stat else 25.0
    drs = calculate_dispersion_risk_score(
        lateral_std_m=lat_std,
        fairway_width_m=rec_lz.landing_width_m,
        hazard_nearby=has_bunker,
        water_in_play=has_water
    )

    gos = calculate_gir_opportunity_score(
        residual_distance_m=rec_lz.residual_distance_to_green_m,
        landing_lie=LieCategory.FAIRWAY,
        category=category
    )

    strategy_text = generate_caddy_strategy_text(
        hole=hole,
        category=category,
        rec_lz=rec_lz,
        tee_club=tee_club,
        approach_club=approach_club,
        risk_factor=risk_factor
    )

    # Ellisse di dispersione centrata sulla landing zone ideale
    shot_bearing = bearing_deg(
        hole.tee.lat, hole.tee.lon,
        hole.green_center.lat, hole.green_center.lon
    )
    # Calcolo coordinate geografiche del centroide della landing zone
    fraction = min(1.0, rec_lz.target_distance_from_tee_m / max(1.0, hole.length_m))
    lz_lat = hole.tee.lat + (hole.green_center.lat - hole.tee.lat) * fraction
    lz_lon = hole.tee.lon + (hole.green_center.lon - hole.tee.lon) * fraction

    disp_ellipse = build_dispersion_ellipse(
        center_lat=lz_lat,
        center_lon=lz_lon,
        semi_major_m=driver_stat.longitudinal_dispersion_m if driver_stat else 20.0,
        semi_minor_m=driver_stat.lateral_dispersion_m if driver_stat else 25.0,
        rotation_deg=shot_bearing
    )

    return HoleStrategyResult(
        course_id=course_id,
        hole_number=hole.hole_number,
        par=hole.par,
        category=category,
        observed_landing_zone=obs_lz,
        recommended_landing_zone=rec_lz,
        ideal_gir_position=rec_lz,
        strategic_position_score=sps,
        dispersion_risk_score=drs,
        gir_opportunity_score=gos,
        recommended_tee_club=tee_club,
        recommended_approach_club=approach_club,
        main_risk_factor=risk_factor,
        caddy_strategy_text=strategy_text,
        dispersion_ellipse=disp_ellipse
    )
