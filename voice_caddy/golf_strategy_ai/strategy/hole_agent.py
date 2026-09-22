from __future__ import annotations

import math
from typing import List, Dict, Any, Optional, Tuple, Union
from pydantic import BaseModel, Field

from ..models import (
    PlayerCategory,
    LieCategory,
    ShotQuality,
    GeoPoint,
    HoleGeometry,
    HoleStrategyResult,
    LandingZone
)
from ..club_profiles import (
    get_category_profile,
    estimate_category_from_handicap,
    rank_clubs_for_shot
)
from ..geo.geometry import (
    haversine_distance_m,
    bearing_deg,
    calculate_progress_and_offset,
    lateral_and_longitudinal_offset,
    point_in_polygon
)
from ..geo.projection import latlon_to_utm, utm_to_latlon
from .recommendations import analyze_hole_strategy


class ShotEvaluation(BaseModel):
    """Valutazione balistica del singolo colpo rispetto ai benchmark di categoria."""
    shot_index: int
    club: str
    category: PlayerCategory
    distance_m: float
    category_min_m: float
    category_mean_m: float
    category_max_m: float
    distance_delta_m: float
    distance_status: str  # "ottimale", "sopra_media", "corto", "molto_corto", "lungo"
    lateral_offset_m: float  # + a destra, - a sinistra dell'asse centrale in metri
    fairway_half_width_m: float
    lateral_status: str  # "centro_perfetto", "fairway_destro", "fairway_sinistro", "rough_destro", "rough_sinistro", "bunker", "ostacolo"
    landing_lie: str
    start_coord: Tuple[float, float]
    end_coord: Tuple[float, float]


class GreenApproachEvaluation(BaseModel):
    """Valutazione dettagliata dell'approccio al green e del putting."""
    approach_shot_index: int
    approach_club: str
    landing_coord: Tuple[float, float]
    pin_coord: Tuple[float, float]
    proximity_to_pin_m: float
    proximity_rating: str  # "tap_in", "birdie_chance", "buon_lag", "rischio_tre_putt"
    on_green: bool
    putts_count: int
    putt_traces: List[Tuple[Tuple[float, float], Tuple[float, float]]] = Field(default_factory=list)


class HolePerformanceEvaluation(BaseModel):
    """Riepilogo completo di come è stata giocata la buca con telemetria e rating."""
    hole_number: int
    par: int
    score: int
    player_category: PlayerCategory
    player_handicap: float
    shots_evaluations: List[ShotEvaluation] = Field(default_factory=list)
    green_evaluation: Optional[GreenApproachEvaluation] = None
    fairway_hit: Optional[bool] = None
    gir: bool = False
    tactical_verdict: str = ""
    caddy_advice_retrospective: str = ""


class MultiCategoryStrategy(BaseModel):
    """Piani strategici completi generati simultaneamente per le 3 categorie di gioco."""
    hole_number: int
    par: int
    length_m: float
    stroke_index: int
    prima: HoleStrategyResult
    seconda: HoleStrategyResult
    terza: HoleStrategyResult
    fairway_centerline: List[Tuple[float, float]] = Field(default_factory=list)
    green_entry_point: Tuple[float, float]


class HoleStrategyAgent:
    """
    Agente di Intelligenza Artificiale per l'analisi strategica di buca e la telemetria di gioco.
    Elabora piani di gioco personalizzati per ciascuna categoria (Prima, Seconda, Terza)
    e valuta i colpi giocati rispetto all'asse centrale del fairway e al green.
    """

    def __init__(self):
        pass

    def compute_fairway_centerline(
        self,
        hole: HoleGeometry,
        num_points: int = 12
    ) -> Tuple[List[Tuple[float, float]], Tuple[float, float]]:
        """
        Calcola l'asse centrale del fairway (Centerline) dal Tee al Green
        e individua il punto ideale di ingresso al green (Green Entry Corridor).
        Ritorna: (centerline_coords, green_entry_coord)
        """
        t_lat, t_lon = hole.tee.lat, hole.tee.lon
        g_lat, g_lon = hole.green_center.lat, hole.green_center.lon

        # Se c'è un dogleg apex, la linea spezzata passa per l'apex
        if hole.dogleg_apex:
            apex_lat, apex_lon = hole.dogleg_apex.lat, hole.dogleg_apex.lon
            pts1 = [
                (t_lat + (apex_lat - t_lat) * (i / 5.0), t_lon + (apex_lon - t_lon) * (i / 5.0))
                for i in range(5)
            ]
            pts2 = [
                (apex_lat + (g_lat - apex_lat) * (i / 6.0), apex_lon + (g_lon - apex_lon) * (i / 6.0))
                for i in range(7)
            ]
            centerline = pts1 + pts2
        else:
            centerline = [
                (round(t_lat + (g_lat - t_lat) * (i / float(num_points - 1)), 6),
                 round(t_lon + (g_lon - t_lon) * (i / float(num_points - 1)), 6))
                for i in range(num_points)
            ]

        # Il punto ideale di ingresso al green è a circa 15 metri prima del centro green
        entry_idx = max(0, len(centerline) - 2)
        green_entry = centerline[entry_idx]

        return centerline, green_entry

    def analyze_hole(
        self,
        hole: HoleGeometry,
        course_id: str = "golf_course"
    ) -> MultiCategoryStrategy:
        """
        Analizza la buca e genera i 3 piani strategici ideali simultanei
        per Prima Categoria (HCP 0-12), Seconda (HCP 12.1-26) e Terza (HCP 26.1-54).
        """
        centerline, green_entry = self.compute_fairway_centerline(hole)

        strat_prima = analyze_hole_strategy(hole, PlayerCategory.PRIMA, course_id=course_id)
        strat_seconda = analyze_hole_strategy(hole, PlayerCategory.SECONDA, course_id=course_id)
        strat_terza = analyze_hole_strategy(hole, PlayerCategory.TERZA, course_id=course_id)

        # Personalizzazione tattica per Terza Categoria su Par 4 e Par 5 (Bogey-Golf Strategy)
        if hole.par >= 4:
            strat_terza.caddy_strategy_text = (
                f"🛡️ <b>Terza Categoria (HCP 26.1–54) — Strategia Bogey-Golf:</b> "
                f"Hai a disposizione colpi di vantaggio su questa buca (SI {hole.stroke_index}). "
                f"Non forzare il green in regulation: gioca il tee shot sicuro con <b>{strat_terza.recommended_tee_club}</b> "
                f"sul centro fairway ({int(strat_terza.recommended_landing_zone.target_distance_from_tee_m)}m), "
                f"piazza il secondo colpo davanti al green evitando i bunker laterali, ed esegui un approccio facile per puntare al 4 netto o 5 netto."
            )

        return MultiCategoryStrategy(
            hole_number=hole.hole_number,
            par=hole.par,
            length_m=hole.length_m,
            stroke_index=hole.stroke_index,
            prima=strat_prima,
            seconda=strat_seconda,
            terza=strat_terza,
            fairway_centerline=centerline,
            green_entry_point=green_entry
        )

    def evaluate_played_hole(
        self,
        hole: HoleGeometry,
        shots: List[Any],
        user_handicap: float = 18.0,
        score: Optional[int] = None,
        putts: int = 2,
        pin_coord: Optional[Tuple[float, float]] = None
    ) -> HolePerformanceEvaluation:
        """
        Valuta come è stata effettivamente giocata la buca analizzando:
        - Ogni colpo rispetto ai benchmark della categoria del giocatore.
        - Scostamento laterale rispetto all'asse centrale del fairway (0m = centro).
        - Prossimità al pin e putting sul green.
        """
        category = estimate_category_from_handicap(user_handicap)
        cat_prof = get_category_profile(category)
        actual_score = score if score is not None else len(shots)

        shot_evals: List[ShotEvaluation] = []
        centerline, green_entry = self.compute_fairway_centerline(hole)
        half_fw = 18.0  # Semilarghezza nominale standard fairway in metri

        pin_lat, pin_lon = pin_coord if pin_coord else (hole.green_center.lat, hole.green_center.lon)
        approach_eval: Optional[GreenApproachEvaluation] = None

        # Coordinate correnti palla (inizia dal tee)
        curr_lat, curr_lon = hole.tee.lat, hole.tee.lon

        for idx, s in enumerate(shots, 1):
            club_name = getattr(s, "club", "Driver") or "Driver"
            dist_m = float(getattr(s, "distance_meters", None) or getattr(s, "raw_distance", None) or 150.0)

            # Cerca il profilo balistico del bastone
            clean_c = club_name.lower().replace(" ", "_").replace("ferro_", "iron_").replace("legno_", "wood_").replace("ibrido_", "hybrid_")
            c_stat = cat_prof.clubs.get(clean_c) or cat_prof.clubs.get("driver") if idx == 1 else cat_prof.clubs.get("iron_7")

            c_min = c_stat.total_min_m if c_stat else dist_m * 0.85
            c_mean = c_stat.total_mean_m if c_stat else dist_m
            c_max = c_stat.total_max_m if c_stat else dist_m * 1.15

            delta = dist_m - c_mean

            if delta >= 10.0:
                dist_status = "sopra_media"
            elif delta >= -12.0:
                dist_status = "ottimale"
            elif delta >= -30.0:
                dist_status = "corto"
            else:
                dist_status = "molto_corto"

            # Coordinate di arrivo del colpo
            s_lat = getattr(s, "latitude", None)
            s_lon = getattr(s, "longitude", None)

            if s_lat and s_lon:
                end_lat, end_lon = float(s_lat), float(s_lon)
            else:
                # Se mancano le coordinate GPS puntuali del colpo, stimiamo lungo l'asse buca
                frac = min(1.0, dist_m / max(1.0, hole.length_m))
                end_lat = curr_lat + (hole.green_center.lat - curr_lat) * frac
                end_lon = curr_lon + (hole.green_center.lon - curr_lon) * frac

            # Calcolo avanzamento e scostamento laterale dall'asse centrale Tee -> Green
            _, lat_off = calculate_progress_and_offset(
                point_lat=end_lat, point_lon=end_lon,
                origin_lat=curr_lat, origin_lon=curr_lon,
                target_lat=hole.green_center.lat, target_lon=hole.green_center.lon
            )

            # Lie e stato laterale
            lie_str = getattr(s, "lie", "fairway")
            if hasattr(lie_str, "value"):
                lie_str = lie_str.value
            lie_str = str(lie_str).lower()

            if abs(lat_off) <= 4.0:
                lat_status = "centro_perfetto"
            elif 4.0 < lat_off <= half_fw:
                lat_status = "fairway_destro"
            elif -half_fw <= lat_off < -4.0:
                lat_status = "fairway_sinistro"
            elif lat_off > half_fw:
                lat_status = "rough_destro" if "bunker" not in lie_str else "bunker"
            else:
                lat_status = "rough_sinistro" if "bunker" not in lie_str else "bunker"

            shot_evals.append(ShotEvaluation(
                shot_index=idx,
                club=club_name,
                category=category,
                distance_m=round(dist_m, 1),
                category_min_m=round(c_min, 1),
                category_mean_m=round(c_mean, 1),
                category_max_m=round(c_max, 1),
                distance_delta_m=round(delta, 1),
                distance_status=dist_status,
                lateral_offset_m=round(lat_off, 1),
                fairway_half_width_m=half_fw,
                lateral_status=lat_status,
                landing_lie=lie_str,
                start_coord=(round(curr_lat, 6), round(curr_lon, 6)),
                end_coord=(round(end_lat, 6), round(end_lon, 6))
            ))

            # Se il colpo è atterrato sul green o in prossimità del green (colpo d'approccio)
            is_approach = ("green" in lie_str or "putt" in club_name.lower() or idx == max(1, hole.par - 2))
            if is_approach and approach_eval is None:
                prox = haversine_distance_m(end_lat, end_lon, pin_lat, pin_lon)
                if prox <= 1.8:
                    prox_rating = "tap_in"
                elif prox <= 4.5:
                    prox_rating = "birdie_chance"
                elif prox <= 8.5:
                    prox_rating = "buon_lag"
                else:
                    prox_rating = "rischio_tre_putt"

                # Traccia del putt verso la bandiera
                putt_tr = [((end_lat, end_lon), (pin_lat, pin_lon))]

                approach_eval = GreenApproachEvaluation(
                    approach_shot_index=idx,
                    approach_club=club_name,
                    landing_coord=(round(end_lat, 6), round(end_lon, 6)),
                    pin_coord=(round(pin_lat, 6), round(pin_lon, 6)),
                    proximity_to_pin_m=round(prox, 1),
                    proximity_rating=prox_rating,
                    on_green=("green" in lie_str),
                    putts_count=putts,
                    putt_traces=putt_tr
                )

            curr_lat, curr_lon = end_lat, end_lon

        # Verdetto Tattico Complessivo
        fw_hit = (shot_evals[0].lateral_status in ("centro_perfetto", "fairway_destro", "fairway_sinistro")) if (hole.par >= 4 and shot_evals) else None
        gir = (approach_eval is not None and approach_eval.on_green and approach_eval.approach_shot_index <= (hole.par - 2))

        if gir and putts <= 2:
            verdict = "🏆 Esecuzione da Manuale (GIR & Par/Birdie)"
            advice = "Percorso giocato con precisione chirurgica: fairway centrato e approccio gestito sul piano di sicurezza."
        elif fw_hit is False:
            verdict = "⚠️ Errore dal Tee (Recupero Necessario)"
            advice = f"Il tee shot è uscito dall'asse di gioco ({shot_evals[0].lateral_offset_m}m). In questo scenario privilegia un secondo colpo di sicurezza (layup) verso il centro fairway."
        elif putts >= 3:
            verdict = "📉 Difficoltà sul Green (3-Putt riscontrato)"
            advice = "L'approccio è atterrato lontano dalla bandiera o il primo putt non ha coperto la distanza in modo ottimale. Lavora sulla velocità nei putt oltre 6 metri."
        else:
            verdict = "⛳ Buca Solida e Coerente"
            advice = "Gestione oculata della buca, perfettamente allineata alla strategia della tua categoria."

        return HolePerformanceEvaluation(
            hole_number=hole.hole_number,
            par=hole.par,
            score=actual_score,
            player_category=category,
            player_handicap=user_handicap,
            shots_evaluations=shot_evals,
            green_evaluation=approach_eval,
            fairway_hit=fw_hit,
            gir=gir,
            tactical_verdict=verdict,
            caddy_advice_retrospective=advice
        )
