from __future__ import annotations

from typing import Dict, Any, List, Optional
from core.schemas import GolfRoundData, HoleData, PerformanceSummary, CourseManagementStats, ShotIntent


class GolfMetricsCalculator:
    """
    Deterministic mathematical engine for Voice Caddy.
    Re-calculates and reconciles scores, GIR %, Fairway %, Scrambling %,
    3-putt tracking, and miss tendencies strictly from raw hole data without LLM hallucinations.
    """

    @staticmethod
    def calculate_score_relation_to_par(holes: List[HoleData]) -> int:
        total_par = sum(h.par for h in holes)
        total_score = sum(h.score for h in holes)
        return total_score - total_par

    @classmethod
    def recompute_and_reconcile(cls, round_data: GolfRoundData) -> GolfRoundData:
        holes = round_data.holes
        if not holes:
            return round_data

        # 1. Order holes by hole_number
        holes = sorted(holes, key=lambda h: h.hole_number)

        # 2. Mathematical reconciliation per hole
        for h in holes:
            # Recompute GIR strictly based on par vs shot sequence/green entry
            # GIR = True if ball reaches green in (Par - 2) shots or fewer
            # If putts are specified, shots to green = score - putts - penalties
            shots_to_green = h.score - h.putts - h.penalties
            calculated_gir = (shots_to_green <= (h.par - 2)) if h.score >= h.putts else h.gir
            h.gir = calculated_gir

            # Ensure fairway_hit is None on Par 3s
            if h.par == 3:
                h.fairway_hit = None

            # Calcolo Netto e Stableford deterministico (Regole 3 & 21.1)
            received = h.received_strokes if h.received_strokes is not None else 0
            h.received_strokes = received
            h.net_score = h.score - received
            h.stableford_points = max(0, 2 + h.par - h.net_score)
            h.stableford_gross_points = max(0, 2 + h.par - h.score)

        total_holes = len(holes)
        total_score = sum(h.score for h in holes)
        total_putts = sum(h.putts for h in holes)
        total_penalties = sum(h.penalties for h in holes)

        # Calcolo Colpi Netti totali
        playing_hcp = round_data.round_info.playing_hcp
        if playing_hcp is not None:
            if playing_hcp >= 0:
                total_score_net = total_score - playing_hcp
            else:
                total_score_net = total_score + abs(playing_hcp)
        else:
            total_score_net = sum(h.net_score for h in holes)

        total_stbl_net = sum(h.stableford_points for h in holes)
        total_stbl_gross = sum(h.stableford_gross_points for h in holes)

        # 3. Fairway Accuracy %
        eligible_drive_holes = [h for h in holes if h.par in (4, 5)]
        fairways_hit = [h for h in eligible_drive_holes if h.fairway_hit is True]
        fairway_pct = (
            round((len(fairways_hit) / len(eligible_drive_holes)) * 100, 1)
            if eligible_drive_holes else 0.0
        )

        # 4. GIR %
        gir_holes = [h for h in holes if h.gir is True]
        gir_pct = round((len(gir_holes) / total_holes) * 100, 1)

        # 5. Scrambling % (Par or better when GIR is missed)
        missed_gir_holes = [h for h in holes if h.gir is False]
        scrambling_successes = [h for h in missed_gir_holes if h.score <= h.par]
        scrambling_pct = (
            round((len(scrambling_successes) / len(missed_gir_holes)) * 100, 1)
            if missed_gir_holes else 100.0
        )

        # 6. 3-Putt Holes
        three_putt_holes = [h.hole_number for h in holes if h.putts >= 3]

        # 7. Extract primary miss tendency
        miss_summary = cls._extract_miss_tendencies(holes)

        # 8. Course Management Stats (layup, recovery, bump & run)
        cm_stats = cls.calculate_course_management_stats(holes)

        # Re-build validated PerformanceSummary (with professional_diagnosis preserved)
        updated_summary = PerformanceSummary(
            total_score=total_score,
            total_score_net=total_score_net,
            total_stableford_points=total_stbl_net,
            total_stableford_gross_points=total_stbl_gross,
            total_putts=total_putts,
            fairway_accuracy_pct=fairway_pct,
            gir_pct=gir_pct,
            scrambling_pct=scrambling_pct,
            three_putt_holes=three_putt_holes,
            penalty_strokes_total=total_penalties,
            primary_miss_tendency=miss_summary or round_data.performance_summary.primary_miss_tendency,
            professional_diagnosis=round_data.performance_summary.professional_diagnosis,
            strokes_lost_breakdown=round_data.performance_summary.strokes_lost_breakdown,
            training_drills_recommended=round_data.performance_summary.training_drills_recommended,
            course_management_stats=cm_stats
        )

        round_data.holes = holes
        round_data.round_info.holes_played = total_holes
        round_data.performance_summary = updated_summary
        return round_data

    @staticmethod
    def _extract_miss_tendencies(holes: List[HoleData]) -> Optional[str]:
        error_counts: Dict[str, int] = {}
        neutral_results = {"good", "fairway", "green"}

        for hole in holes:
            for shot in hole.shots:
                res = shot.result.value if hasattr(shot.result, 'value') else str(shot.result)
                if res not in neutral_results:
                    error_counts[res] = error_counts.get(res, 0) + 1

        if not error_counts:
            return None

        most_frequent_miss = max(error_counts, key=error_counts.get)
        labels_it = {
            "slice": "Slice / Sbandata a destra",
            "hook": "Hook / Sbandata a sinistra",
            "pull": "Pull a sinistra",
            "push": "Push a destra",
            "fat": "Colpo pesante (Fat)",
            "thin": "Colpo liscio (Thin)",
            "topped": "Top / Palla rasoterra",
            "short": "Approcci costantemente corti",
            "long": "Approcci lunghi",
            "bunker": "Tendenza bunker",
            "water": "Palla in acqua",
            "miss_left": "Errore a sinistra del green/fairway",
            "miss_right": "Errore a destra del green/fairway"
        }
        return labels_it.get(most_frequent_miss, f"Errore ricorrente: {most_frequent_miss}")

    @classmethod
    def calculate_course_management_stats(cls, holes: List[HoleData]) -> CourseManagementStats:
        layups = 0
        recoveries = 0
        bump_runs = 0
        recovery_holes_count = 0
        recovery_success_count = 0

        for h in holes:
            hole_had_recovery = False
            for s in h.shots:
                # Check layup
                if getattr(s, "is_layup", False) or getattr(s, "intent", None) == ShotIntent.LAYUP:
                    layups += 1
                # Check recovery
                if getattr(s, "is_recovery", False) or getattr(s, "intent", None) in (ShotIntent.RECOVERY_PUNCH, ShotIntent.ESCAPE_TROUBLE):
                    recoveries += 1
                    hole_had_recovery = True
                # Check bump and run
                if getattr(s, "intent", None) == ShotIntent.BUMP_AND_RUN:
                    bump_runs += 1

            if hole_had_recovery:
                recovery_holes_count += 1
                # Success if score <= par or net_score <= par (Net Par or better)
                net_par_target = h.par + (h.received_strokes or 0)
                if h.score <= h.par or (h.net_score is not None and h.net_score <= h.par) or h.score <= net_par_target:
                    recovery_success_count += 1

        recovery_rate = (
            round((recovery_success_count / recovery_holes_count) * 100.0, 1)
            if recovery_holes_count > 0 else 100.0
        )

        if layups >= 2 and recoveries <= 2:
            rating = "Gestione del Percorso Esemplare e Disciplinata"
        elif recoveries >= 4 and recovery_rate < 40.0:
            rating = "Troppi Rischi Inutili / Gestione Difficoltà da Ottimizzare"
        elif layups >= 1 or bump_runs >= 1:
            rating = "Strategia Solida e Paziente"
        else:
            rating = "Standard"

        return CourseManagementStats(
            layups_count=layups,
            recoveries_count=recoveries,
            bump_and_runs_count=bump_runs,
            recovery_success_rate=recovery_rate,
            course_management_rating=rating
        )

    @staticmethod
    def get_scorecard_matrix(holes: List[HoleData]) -> List[Dict[str, Any]]:
        rows = []
        for h in holes:
            diff = h.score - h.par
            if diff <= -2:
                status = "Eagle or Better"
            elif diff == -1:
                status = "Birdie"
            elif diff == 0:
                status = "Par"
            elif diff == 1:
                status = "Bogey"
            else:
                status = "Double+ Bogey"

            net_sc = h.net_score if h.net_score is not None else (h.score - (h.received_strokes or 0))
            stbl_gross = h.stableford_gross_points if h.stableford_gross_points is not None else max(0, 2 + h.par - h.score)
            stbl_net = h.stableford_points if h.stableford_points is not None else max(0, 2 + h.par - net_sc)

            rows.append({
                "Buca": h.hole_number,
                "Par": h.par,
                "SI": h.stroke_index if h.stroke_index is not None else "-",
                "HCP": h.received_strokes if h.received_strokes is not None else 0,
                "Score": h.score,
                "Score Netto": net_sc,
                "Stabl. Lordo": stbl_gross,
                "Stabl. Netto": stbl_net,
                "+/-": f"{'+' if diff > 0 else ''}{diff}" if diff != 0 else "E",
                "Status": status,
                "FIR": "Sì" if h.fairway_hit is True else ("No" if h.fairway_hit is False else "-"),
                "GIR": "Sì" if h.gir else "No",
                "Putts": h.putts,
                "Penalità": h.penalties,
                "Dettaglio Errore": h.root_cause_error or "Nessun errore rilevante"
            })
        return rows
