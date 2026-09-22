"""Sottomodulo di strategia, scoring e raccomandazioni per golf_strategy_ai."""
from .scoring import (
    calculate_strategic_position_score,
    calculate_dispersion_risk_score,
    calculate_gir_opportunity_score,
)
from .recommendations import (
    recommend_clubs_for_hole,
    generate_caddy_strategy_text,
    analyze_hole_strategy,
)
from .hole_agent import (
    HoleStrategyAgent,
    MultiCategoryStrategy,
    ShotEvaluation,
    GreenApproachEvaluation,
    HolePerformanceEvaluation
)

__all__ = [
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
]
