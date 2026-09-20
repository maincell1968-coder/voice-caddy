from __future__ import annotations

import json
import sqlite3
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

from core.elevation_service import haversine_distance


def normalize_club_name(raw_name: Optional[str]) -> Optional[str]:
    """
    Normalizza la denominazione dei bastoni in una forma canonica coerente con la sacca.
    Esempio: 'f7', 'Ferro 7', '7-iron' -> 'Ferro 7'
    """
    if not raw_name:
        return None
    n = raw_name.lower().strip()

    if "putt" in n:
        return "Putter"
    if "driver" in n or n in ["d", "1w"]:
        return "Driver"

    # Legni
    if "legno 3" in n or "3w" in n or "spoon" in n:
        return "Legno 3"
    if "legno 5" in n or "5w" in n:
        return "Legno 5"
    if "legno 7" in n or "7w" in n:
        return "Legno 7"
    if "legno" in n:
        return "Legno 3"

    # Ibridi
    if "ibrido 3" in n or "3h" in n or "h3" in n:
        return "Ibrido 3"
    if "ibrido 4" in n or "4h" in n or "h4" in n or "ibrido" in n:
        return "Ibrido 4"
    if "ibrido 5" in n or "5h" in n or "h5" in n:
        return "Ibrido 5"

    # Ferri
    for i in range(1, 10):
        if f"ferro {i}" in n or f"f{i}" in n or f"{i} iron" in n or f"{i}-iron" in n or n == f"f{i}":
            return f"Ferro {i}"

    # Wedges
    if "pitching" in n or "pw" in n:
        return "Pitching Wedge"
    if "approach" in n or "aw" in n or "gw" in n or "gap" in n:
        return "Approach Wedge (AW)"
    if "sand" in n or "sw" in n or "56" in n:
        return "Sand Wedge (56°)"
    if "lob" in n or "lw" in n or "60" in n or "58" in n:
        return "Lob Wedge (60°)"
    if "wedge" in n:
        return "Pitching Wedge"

    # Ritorna formato title come fallback
    return raw_name.strip().title()


class ClubDistanceService:
    """
    Servizio di analisi statistica e aggregazione delle distanze reali misurate su erba in campo/gara.
    Recupera i campioni dai colpi GPS registrati in live_shots e dalle scorecard storiche (rounds).
    """

    @staticmethod
    def get_club_grass_performance(
        db_path: str | Path,
        user_id: str = "strafatti_stefano_pirani",
        chat_id: Optional[str | int] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calcola le metriche su erba per ciascun bastone:
        {
            "Driver": {"count": 14, "avg_meters": 212.5, "min_meters": 195, "max_meters": 235, "samples": [...]},
            ...
        }
        """
        club_samples: Dict[str, List[float]] = {}

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Recupera campioni da live_shots (colpi registrati dal bot interattivo o live location)
        try:
            cursor.execute("PRAGMA table_info(live_shots)")
            cols = [r["name"] for r in cursor.fetchall()]
            club_col = "club" if "club" in cols else ("club_used" if "club_used" in cols else None)
            dist_col = "distance_covered" if "distance_covered" in cols else ("distance_meters" if "distance_meters" in cols else None)

            if club_col and dist_col:
                query = f"""
                    SELECT {club_col} as club_val, {dist_col} as dist_val
                    FROM live_shots
                    WHERE {dist_col} IS NOT NULL AND {dist_col} > 15
                """
                params = []
                if chat_id and "chat_id" in cols:
                    query += " AND chat_id = ?"
                    params.append(str(chat_id))
                elif user_id and "user_id" in cols:
                    query += " AND user_id = ?"
                    params.append(str(user_id))

                cursor.execute(query, params)
                for row in cursor.fetchall():
                    c_raw = row["club_val"]
                    dist = row["dist_val"]
                    c_norm = normalize_club_name(c_raw)
                    if not c_norm or c_norm == "Putter":
                        continue
                    if dist and dist >= 20:
                        club_samples.setdefault(c_norm, []).append(float(dist))
        except Exception:
            pass

        # 2. Recupera campioni dalle partite storiche registrate (rounds)
        try:
            cursor.execute("SELECT user_id, json_data FROM rounds WHERE user_id = ?", (user_id,))
            for row in cursor.fetchall():
                json_str = row["json_data"]
                if not json_str:
                    continue
                round_dict = json.loads(json_str)
                holes = round_dict.get("holes", [])
                for h in holes:
                    shots = h.get("shots", [])
                    for idx, s in enumerate(shots):
                        c_raw = s.get("club")
                        dist = s.get("distance_meters")
                        c_norm = normalize_club_name(c_raw)
                        if not c_norm or c_norm == "Putter":
                            continue

                        # Se la distanza è presente direttamente nel colpo
                        if dist and dist >= 20:
                            club_samples.setdefault(c_norm, []).append(float(dist))
                        elif not dist and idx + 1 < len(shots):
                            # Calcola distanza colpo tra coordinate successive
                            lat1 = s.get("latitude") or (s.get("start_coords")[0] if s.get("start_coords") else None)
                            lon1 = s.get("longitude") or (s.get("start_coords")[1] if s.get("start_coords") else None)
                            next_s = shots[idx + 1]
                            lat2 = next_s.get("latitude") or (next_s.get("start_coords")[0] if next_s.get("start_coords") else (s.get("end_coords")[0] if s.get("end_coords") else None))
                            lon2 = next_s.get("longitude") or (next_s.get("start_coords")[1] if next_s.get("start_coords") else (s.get("end_coords")[1] if s.get("end_coords") else None))
                            if lat1 and lon1 and lat2 and lon2:
                                d_calc = haversine_distance(lat1, lon1, lat2, lon2)
                                if 20 <= d_calc <= 350:
                                    club_samples.setdefault(c_norm, []).append(float(d_calc))
        except Exception:
            pass
        finally:
            conn.close()

        # 3. Calcola le metriche aggregate
        stats: Dict[str, Dict[str, Any]] = {}
        for club, samples in club_samples.items():
            if not samples:
                continue
            # Rimuovi outlier estremi se ci sono abbastanza campioni (almeno 4)
            cleaned = sorted(samples)
            if len(cleaned) >= 4:
                # Scarta il min e il max estremo per robustezza statistica
                eval_samples = cleaned[1:-1]
            else:
                eval_samples = cleaned

            avg_val = round(sum(eval_samples) / len(eval_samples), 1)
            min_val = round(min(samples), 1)
            max_val = round(max(samples), 1)

            stats[club] = {
                "count": len(samples),
                "avg_meters": avg_val,
                "min_meters": min_val,
                "max_meters": max_val,
                "samples_count": len(samples)
            }

        return stats
