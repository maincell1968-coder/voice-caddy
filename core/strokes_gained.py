from __future__ import annotations

from typing import Dict, Any
from core.schemas import GolfRoundData, StrokesLostBreakdown


class StrokesGainedBenchmarkEngine:
    """
    Strokes Gained Benchmark Engine.
    Compares the player's Strokes Lost breakdown against standard Handicap Target Baselines
    (Scratch, 5-HCP, 10-HCP, 18-HCP, 28-HCP) to identify specific areas for game improvement.
    """

    HANDICAP_BASELINES: Dict[str, Dict[str, float]] = {
        "Scratch (HCP 0)": {"gir_pct": 66.0, "fairway_pct": 65.0, "avg_putts_per_round": 29.0, "scrambling_pct": 58.0},
        "Single Digit (HCP 5)": {"gir_pct": 52.0, "fairway_pct": 58.0, "avg_putts_per_round": 31.0, "scrambling_pct": 48.0},
        "Mid Handicap (HCP 10-15)": {"gir_pct": 36.0, "fairway_pct": 50.0, "avg_putts_per_round": 33.0, "scrambling_pct": 35.0},
        "High Handicap (HCP 18-24)": {"gir_pct": 22.0, "fairway_pct": 42.0, "avg_putts_per_round": 35.0, "scrambling_pct": 22.0},
        "Beginner (HCP 28+)": {"gir_pct": 12.0, "fairway_pct": 35.0, "avg_putts_per_round": 38.0, "scrambling_pct": 12.0}
    }

    @classmethod
    def compare_with_target(cls, round_data: GolfRoundData, target_hcp_label: str = "Mid Handicap (HCP 10-15)") -> Dict[str, Any]:
        baseline = cls.HANDICAP_BASELINES.get(target_hcp_label, cls.HANDICAP_BASELINES["Mid Handicap (HCP 10-15)"])
        summary = round_data.performance_summary
        total_holes = round_data.round_info.holes_played or 18
        scaling_factor = 18.0 / total_holes

        # Scale metrics to 18-hole equivalent if less played
        scaled_putts = summary.total_putts * scaling_factor

        diff_gir = round(summary.gir_pct - baseline["gir_pct"], 1)
        diff_fairway = round(summary.fairway_accuracy_pct - baseline["fairway_pct"], 1)
        diff_putts = round(baseline["avg_putts_per_round"] - scaled_putts, 1) # Positive is better (fewer putts)
        diff_scrambling = round(summary.scrambling_pct - baseline["scrambling_pct"], 1)

        # Identify biggest bottleneck area
        sl: StrokesLostBreakdown = summary.strokes_lost_breakdown
        categories = {
            "Dal Tee (Driver)": sl.tee_shots,
            "Approcci (>50m)": sl.approach_shots,
            "Gioco Corto (<50m)": sl.short_game_around_green,
            "Putting": sl.putting,
            "Penalità": sl.penalties
        }

        biggest_loss_category = max(categories, key=categories.get)
        max_strokes_lost = categories[biggest_loss_category]

        return {
            "target_label": target_hcp_label,
            "baseline": baseline,
            "player_metrics": {
                "gir_pct": summary.gir_pct,
                "fairway_pct": summary.fairway_accuracy_pct,
                "putts_18h_equivalent": round(scaled_putts, 1),
                "scrambling_pct": summary.scrambling_pct
            },
            "differentials": {
                "gir_diff": diff_gir,
                "fairway_diff": diff_fairway,
                "putts_diff": diff_putts,
                "scrambling_diff": diff_scrambling
            },
            "biggest_bottleneck": biggest_loss_category,
            "max_strokes_lost": max_strokes_lost
        }
