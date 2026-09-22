"""
GOLF STRATEGY AI - Motore Balistico, Cartografico e Strategico di Livello Tour.
Sviluppato per Voice Caddy Pro.
"""

from .models import (
    PlayerCategory,
    LieCategory,
    ShotQuality,
    GeoPoint,
    ClubStats,
    CategoryProfile,
    HoleGeometry,
    ShotRecord,
    NormalizedShot,
    DispersionEllipse,
    LandingZone,
    HoleStrategyResult
)
from .club_profiles import (
    get_category_profile,
    estimate_category_from_handicap,
    rank_clubs_for_shot,
    calculate_shot_suitability
)
from .geo import (
    to_utm,
    from_utm,
    haversine_distance_m,
    bearing_deg,
    calculate_progress_and_offset,
    point_in_polygon,
    generate_ellipse_points,
    generate_distance_arc
)
from .analysis import (
    classify_lie,
    assess_shot_quality,
    normalize_shot,
    calculate_dispersion,
    build_dispersion_ellipse,
    find_ideal_landing_zone,
    calculate_observed_landing_zone
)
from .strategy import (
    calculate_strategic_position_score,
    calculate_dispersion_risk_score,
    calculate_gir_opportunity_score,
    recommend_clubs_for_hole,
    generate_caddy_strategy_text,
    analyze_hole_strategy,
    HoleStrategyAgent,
    MultiCategoryStrategy,
    ShotEvaluation,
    GreenApproachEvaluation,
    HolePerformanceEvaluation
)
from .mapping import (
    build_hole_geojson,
    load_hole_geometry_from_geojson,
    render_hole_map_html,
    save_hole_map_html,
    render_view_a_map_html,
    render_view_b_benchmark_html,
    render_view_c_green_radar_html
)

__all__ = [
    # Modelli
    "PlayerCategory",
    "LieCategory",
    "ShotQuality",
    "GeoPoint",
    "ClubStats",
    "CategoryProfile",
    "HoleGeometry",
    "ShotRecord",
    "NormalizedShot",
    "DispersionEllipse",
    "LandingZone",
    "HoleStrategyResult",
    # Profili Bastoni & Categorie
    "get_category_profile",
    "estimate_category_from_handicap",
    "rank_clubs_for_shot",
    "calculate_shot_suitability",
    # Motore Geometrico e Geodetico
    "to_utm",
    "from_utm",
    "haversine_distance_m",
    "bearing_deg",
    "calculate_progress_and_offset",
    "point_in_polygon",
    "generate_ellipse_points",
    "generate_distance_arc",
    # Analisi Balistica e Dispersione
    "classify_lie",
    "assess_shot_quality",
    "normalize_shot",
    "calculate_dispersion",
    "build_dispersion_ellipse",
    "find_ideal_landing_zone",
    "calculate_observed_landing_zone",
    # Strategia e Raccomandazioni Caddie
    "calculate_strategic_position_score",
    "calculate_dispersion_risk_score",
    "calculate_gir_opportunity_score",
    "recommend_clubs_for_hole",
    "generate_caddy_strategy_text",
    "analyze_hole_strategy",
    "HoleStrategyAgent",
    "MultiCategoryStrategy",
    "ShotEvaluation",
    "GreenApproachEvaluation",
    "HolePerformanceEvaluation",
    # Cartografia e Visualizzazione
    "build_hole_geojson",
    "load_hole_geometry_from_geojson",
    "render_hole_map_html",
    "save_hole_map_html",
    "render_view_a_map_html",
    "render_view_b_benchmark_html",
    "render_view_c_green_radar_html",
]
