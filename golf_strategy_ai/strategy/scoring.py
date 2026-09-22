from __future__ import annotations

from typing import Optional
from ..models import PlayerCategory, LieCategory


def calculate_strategic_position_score(
    residual_distance_m: float,
    landing_lie: LieCategory,
    fairway_width_m: float = 35.0,
    has_hazard_in_line: bool = False,
    category: PlayerCategory = PlayerCategory.SECONDA
) -> float:
    """
    Calcola lo Strategic Position Score (SPS) [0 - 100]:
    Misura quanto una posizione di atterraggio è favorevole per giocare il colpo successivo.
    Formula:
    SPS = 0.30 * DistanceFit + 0.25 * LieScore + 0.20 * GreenAngle + 0.15 * HazardAvoidance + 0.10 * GIRProb
    """
    # 1. Distance Fit Score: distanza residua ottimale per la categoria
    # Range ideale di approccio: Prima 80-140m, Seconda 70-130m, Terza 60-110m
    ideal_min, ideal_max = {
        PlayerCategory.PRIMA: (80.0, 140.0),
        PlayerCategory.SECONDA: (70.0, 130.0),
        PlayerCategory.TERZA: (55.0, 110.0)
    }.get(category, (70.0, 130.0))

    if ideal_min <= residual_distance_m <= ideal_max:
        dist_score = 100.0
    elif residual_distance_m < ideal_min:
        dist_score = max(50.0, 100.0 - (ideal_min - residual_distance_m) * 1.5)
    else:
        dist_score = max(20.0, 100.0 - (residual_distance_m - ideal_max) * 0.9)

    # 2. Lie Score
    lie_scores = {
        LieCategory.GREEN: 100.0,
        LieCategory.FAIRWAY: 95.0,
        LieCategory.ROUGH: 60.0,
        LieCategory.BUNKER: 25.0,
        LieCategory.TREES: 15.0,
        LieCategory.WATER: 0.0,
        LieCategory.OUT_OF_BOUNDS: 0.0,
        LieCategory.UNKNOWN: 50.0
    }
    lie_score = lie_scores.get(landing_lie, 50.0)

    # 3. Green Angle / Corridoio utile
    angle_score = min(100.0, max(40.0, fairway_width_m * 2.2))

    # 4. Hazard Avoidance
    hazard_score = 40.0 if has_hazard_in_line else 100.0

    # 5. GIR Probability Score
    gir_score = max(0.0, min(100.0, 100.0 - (residual_distance_m / 2.2)))

    sps = (
        0.30 * dist_score
        + 0.25 * lie_score
        + 0.20 * angle_score
        + 0.15 * hazard_score
        + 0.10 * gir_score
    )

    return round(max(0.0, min(100.0, sps)), 1)


def calculate_dispersion_risk_score(
    lateral_std_m: float,
    fairway_width_m: float,
    hazard_nearby: bool = False,
    water_in_play: bool = False,
    out_of_bounds_in_play: bool = False
) -> float:
    """
    Calcola il Dispersion Risk Score (DRS) [0 - 100]:
    Misura il grado di pericolo derivante dalla dispersione statistica del giocatore
    rispetto alla conformazione della buca e agli ostacoli presenti.
    Un DRS alto (> 70) indica che il colpo rischia fortemente di finire fuori gioco.
    """
    half_width = fairway_width_m / 2.0
    # Rapporto tra dispersione laterale (1 sigma) e semilarghezza del fairway
    dispersion_ratio = lateral_std_m / max(5.0, half_width)

    # Base di rischio geometrico
    base_risk = min(100.0, dispersion_ratio * 45.0)

    # Penalità per ostacoli
    if water_in_play:
        base_risk += 25.0
    if out_of_bounds_in_play:
        base_risk += 30.0
    if hazard_nearby:
        base_risk += 15.0

    return round(max(0.0, min(100.0, base_risk)), 1)


def calculate_gir_opportunity_score(
    residual_distance_m: float,
    landing_lie: LieCategory,
    category: PlayerCategory
) -> float:
    """
    Calcola il Green In Regulation Opportunity Score (GOS) [0 - 100]:
    Stima la probabilità concreta di colpire il green con il colpo successivo.
    """
    # Soglie massime realistiche per raggiungere il green per categoria
    max_gir_reach = {
        PlayerCategory.PRIMA: 185.0,    # Fino a ferro 4 / ibrido
        PlayerCategory.SECONDA: 155.0,  # Fino a ferro 6 / ibrido
        PlayerCategory.TERZA: 125.0     # Fino a ferro 7 / ferro 8
    }.get(category, 150.0)

    if residual_distance_m > max_gir_reach + 30.0:
        return 5.0  # Troppo lungo per un attacco realistico

    reach_score = max(10.0, 100.0 - (residual_distance_m / max_gir_reach) * 55.0)

    lie_multiplier = {
        LieCategory.FAIRWAY: 1.0,
        LieCategory.GREEN: 1.0,
        LieCategory.ROUGH: 0.65,
        LieCategory.BUNKER: 0.25,
        LieCategory.TREES: 0.10,
        LieCategory.WATER: 0.0,
        LieCategory.OUT_OF_BOUNDS: 0.0
    }.get(landing_lie, 0.5)

    gos = reach_score * lie_multiplier
    return round(max(0.0, min(100.0, gos)), 1)
