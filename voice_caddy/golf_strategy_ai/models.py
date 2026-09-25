from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field


class PlayerCategory(str, Enum):
    """Categorie di gioco basate su handicap e statistiche prestazionali."""
    PRIMA = "prima"        # Handicap 0 - 12.0 (Avanzato / Basso HCP)
    SECONDA = "seconda"    # Handicap 12.1 - 26.0 (Intermedio)
    TERZA = "terza"        # Handicap 26.1 - 54.0 (Principiante / Alto HCP)


class LieCategory(str, Enum):
    """Classificazione delle superfici di atterraggio sul campo da golf."""
    TEE = "tee"
    FAIRWAY = "fairway"
    GREEN = "green"
    ROUGH = "rough"
    BUNKER = "bunker"
    WATER = "water"
    OUT_OF_BOUNDS = "out_of_bounds"
    TREES = "trees"
    UNKNOWN = "unknown"


class ShotQuality(str, Enum):
    """Valutazione qualitativa del colpo rispetto al target e al piano di gioco."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    RISKY = "risky"
    POOR = "poor"
    PENALTY = "penalty"


class GeoPoint(BaseModel):
    """Coordinate geografiche WGS84 con quota opzionale."""
    lat: float = Field(..., description="Latitudine in gradi decimali WGS84")
    lon: float = Field(..., description="Longitudine in gradi decimali WGS84")
    alt_m: Optional[float] = Field(default=None, description="Quota altimetrica in metri sul livello del mare")


class ClubStats(BaseModel):
    """Profilo balistico e statistico di un bastone per una determinata categoria."""
    club_id: str = Field(..., description="Identificativo univoco (es. 'driver', 'iron_7')")
    label: str = Field(..., description="Nome visualizzato del bastone")
    carry_mean_m: float = Field(..., description="Distanza media di volo in metri (carry)")
    carry_min_m: float = Field(..., description="Distanza minima realistica di volo in metri")
    carry_max_m: float = Field(..., description="Distanza massima realistica di volo in metri")
    total_mean_m: float = Field(..., description="Distanza totale media in metri (carry + rotolo)")
    total_min_m: float = Field(..., description="Distanza totale minima realistica in metri")
    total_max_m: float = Field(..., description="Distanza totale massima realistica in metri")
    lateral_dispersion_m: float = Field(..., description="Deviazione laterale media a sinistra/destra in metri (±)")
    longitudinal_dispersion_m: float = Field(..., description="Deviazione longitudinale media corto/lungo in metri (±)")
    target_radius_m: float = Field(..., description="Raggio consigliato della zona target in metri")
    confidence: str = Field(default="medium", description="Affidabilità del dato: high, medium, low")
    data_type: str = Field(default="estimated", description="Origine dato: observed, estimated, interpolated, configurable")
    notes: Optional[str] = Field(default="", description="Note tecniche o raccomandazioni d'uso")


class CategoryProfile(BaseModel):
    """Profilo balistico completo di una categoria di golfisti."""
    category: PlayerCategory
    handicap_range: Tuple[float, float]
    label: str
    driver_total_mean_m: float
    clubs: Dict[str, ClubStats] = Field(default_factory=dict)


class HoleGeometry(BaseModel):
    """Definizione geometrica e georeferenziata di una buca di golf."""
    hole_number: int
    par: int
    length_m: float
    stroke_index: int
    tee: GeoPoint
    green_center: GeoPoint
    course_id: Optional[str] = None
    green_front: Optional[GeoPoint] = None
    green_back: Optional[GeoPoint] = None
    dogleg_apex: Optional[GeoPoint] = None
    fairway_polygons: List[List[Tuple[float, float]]] = Field(default_factory=list, description="Lista di poligoni [(lat, lon), ...]")
    green_polygons: List[List[Tuple[float, float]]] = Field(default_factory=list)
    bunker_polygons: List[List[Tuple[float, float]]] = Field(default_factory=list)
    water_polygons: List[List[Tuple[float, float]]] = Field(default_factory=list)
    rough_polygons: List[List[Tuple[float, float]]] = Field(default_factory=list)
    out_of_bounds_polygons: List[List[Tuple[float, float]]] = Field(default_factory=list)


class ShotRecord(BaseModel):
    """Dati grezzi di un colpo eseguito con tracciamento GPS."""
    shot_id: str
    player_id: str
    hole_number: int
    shot_number: int
    club: str
    category: PlayerCategory
    start_point: GeoPoint
    end_point: GeoPoint
    timestamp: Optional[str] = None
    result_note: Optional[str] = None


class NormalizedShot(BaseModel):
    """Colpo normalizzato sul sistema di coordinate metriche locali della buca."""
    shot_id: str
    club: str
    distance_m: float
    progress_along_line_m: float
    lateral_offset_m: float = Field(..., description="+ a destra, - a sinistra dell'asse buca in metri")
    longitudinal_offset_m: float = Field(..., description="+ oltre target, - corto rispetto al target in metri")
    residual_to_green_m: float
    landing_lie: LieCategory
    quality: ShotQuality


class DispersionEllipse(BaseModel):
    """Ellisse di dispersione bidimensionale per visualizzazione cartografica."""
    center_point: GeoPoint
    center_metric_x: float
    center_metric_y: float
    semi_major_axis_m: float = Field(..., description="Semiasse longitudinale (profondità/distanza)")
    semi_minor_axis_m: float = Field(..., description="Semiasse laterale (larghezza/direzione)")
    rotation_deg: float = Field(..., description="Angolo di rotazione dell'ellisse rispetto al Nord")
    area_sqm: float
    equivalent_radius_m: float
    confidence_level: float = 0.95


class LandingZone(BaseModel):
    """Area di atterraggio ideale o osservata per una determinata buca e categoria."""
    zone_type: str = Field(..., description="'observed' (reale) oppure 'recommended' (consigliata)")
    target_distance_from_tee_m: float
    safe_range_m: Tuple[float, float]
    preferred_side: str = Field(..., description="'center', 'left_center', 'right_center', 'left', 'right'")
    landing_width_m: float
    residual_distance_to_green_m: float
    strategic_position_score: float
    fairway_hit_pct: Optional[float] = None
    hazard_risk_pct: Optional[float] = None


class HoleStrategyResult(BaseModel):
    """Risultato completo dell'analisi strategico-balistica per una buca e categoria."""
    course_id: str
    hole_number: int
    par: int
    category: PlayerCategory
    observed_landing_zone: Optional[LandingZone] = None
    recommended_landing_zone: LandingZone
    ideal_gir_position: LandingZone
    strategic_position_score: float
    dispersion_risk_score: float
    gir_opportunity_score: float
    recommended_tee_club: str
    recommended_approach_club: str
    main_risk_factor: str
    caddy_strategy_text: str
    dispersion_ellipse: Optional[DispersionEllipse] = None
