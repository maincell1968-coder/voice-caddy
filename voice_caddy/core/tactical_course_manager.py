"""
Modulo di gestione e caricamento delle coordinate tattiche dei percorsi da golf.
Supporta:
- Coordinate Campi.xlsx (archiviato in voice_caddy/data/coordinate_campi.xlsx e con SafeVault backup)
- Parsing e cache JSON rapida (tactical_courses.json)
- Modello geometrico del corridoio fairway (larghezza media, stretta, ampia)
- Waypoints della Playing Line (Tee -> Landing Area 1 -> Landing Area 2 -> Green)
- Fasce orizzontali di atterraggio ottimale (±20 metri rispetto al centro della landing area)
- Proiezione balistica dei colpi eseguiti dal giocatore (offset longitudinale e deviazione laterale)
- Spettro radar balistico del green (diametro 50m, anelli metrici concentrici e quadranti)
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from core.elevation_service import haversine_distance


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EXCEL_PATH = DATA_DIR / "coordinate_campi.xlsx"
CACHE_JSON_PATH = DATA_DIR / "tactical_courses.json"


@dataclass
class TacticalHole:
    hole_number: int
    par: int
    hcp: int
    dist_bianchi: Optional[float] = None
    dist_gialli: Optional[float] = None
    dist_rossi: Optional[float] = None
    tee_bianchi: Optional[Tuple[float, float]] = None  # (lat, lon)
    tee_gialli: Optional[Tuple[float, float]] = None   # (lat, lon)
    tee_rossi: Optional[Tuple[float, float]] = None    # (lat, lon)
    fairway_width: float = 30.0                        # larghezza fairway in metri (es. 25, 35, 40)
    special_hazard: Optional[str] = None               # es. 'lago' o note speciali
    landing_1: Optional[Tuple[float, float]] = None    # (lat, lon)
    landing_2: Optional[Tuple[float, float]] = None    # (lat, lon)
    green_center: Optional[Tuple[float, float]] = None # (lat, lon)
    green_diameter: float = 50.0                       # diametro indicativo green (~50m da specifica)

    def get_tee_coords(self, tee_color: str = "gialli") -> Optional[Tuple[float, float]]:
        tc = str(tee_color).strip().lower()
        if "bianc" in tc or "white" in tc:
            return self.tee_bianchi or self.tee_gialli or self.tee_rossi
        if "ross" in tc or "red" in tc:
            return self.tee_rossi or self.tee_gialli or self.tee_bianchi
        return self.tee_gialli or self.tee_bianchi or self.tee_rossi

    def get_nominal_length(self, tee_color: str = "gialli") -> float:
        tc = str(tee_color).strip().lower()
        if ("bianc" in tc or "white" in tc) and self.dist_bianchi:
            return float(self.dist_bianchi)
        if ("ross" in tc or "red" in tc) and self.dist_rossi:
            return float(self.dist_rossi)
        if self.dist_gialli:
            return float(self.dist_gialli)
        # Fallback calcolo Haversine tee -> green
        tee = self.get_tee_coords(tee_color)
        if tee and self.green_center:
            return round(haversine_distance(tee[0], tee[1], self.green_center[0], self.green_center[1]), 1)
        return 300.0


@dataclass
class TacticalCourse:
    course_id: str
    name: str
    holes_count: int
    holes: Dict[int, TacticalHole] = field(default_factory=dict)

    def get_hole(self, hole_number: int) -> Optional[TacticalHole]:
        return self.holes.get(hole_number)


class TacticalCourseManager:
    """
    Gestore centralizzato dei corridoi tattici 3D e coordinate geodetiche
    per Conero Golf Club, Torrenova Golf, Riviera Golf e Golf Club Perugia.
    """

    def __init__(self, excel_path: Optional[Path] = None):
        self.excel_path = excel_path or EXCEL_PATH
        self.cache_json = CACHE_JSON_PATH
        self.courses: Dict[str, TacticalCourse] = {}
        self._load_data()

    def _normalize_course_key(self, name_or_id: str) -> str:
        s = str(name_or_id).strip().lower().replace("_", " ")
        if "conero" in s:
            return "conero_golf_club"
        if "torrenova" in s:
            return "torrenova_golf_club"
        if "riviera" in s:
            return "riviera_golf_resort"
        if "perugia" in s:
            return "golf_club_perugia"
        return s.replace(" ", "_")

    def _load_data(self):
        # 1. Prova da cache JSON veloce
        if self.cache_json.exists():
            try:
                content = json.loads(self.cache_json.read_text(encoding="utf-8"))
                for cid, c_data in content.items():
                    holes_dict = {}
                    for h_str, h_dict in c_data.get("holes", {}).items():
                        # converte tuple lat/lon
                        for k in ["tee_bianchi", "tee_gialli", "tee_rossi", "landing_1", "landing_2", "green_center"]:
                            if h_dict.get(k):
                                h_dict[k] = tuple(h_dict[k])
                        h_obj = TacticalHole(**h_dict)
                        holes_dict[h_obj.hole_number] = h_obj
                    self.courses[cid] = TacticalCourse(
                        course_id=cid,
                        name=c_data["name"],
                        holes_count=c_data["holes_count"],
                        holes=holes_dict
                    )
                if len(self.courses) >= 4:
                    return
            except Exception:
                pass

        # 2. Parsing diretto da Coordinate Campi.xlsx
        self._parse_excel_and_cache()

    def _parse_excel_and_cache(self):
        if not self.excel_path.exists():
            return

        import pandas as pd

        df = pd.read_excel(self.excel_path)

        def clean_s(v):
            if pd.isna(v):
                return None
            s = str(v).strip()
            return s if s and s.lower() != "nan" else None

        def parse_n(v):
            if pd.isna(v):
                return None
            if isinstance(v, (int, float)):
                return float(v)
            s = str(v).strip()
            try:
                return float(s.replace(",", "."))
            except ValueError:
                return None

        def parse_pt(v) -> Optional[Tuple[float, float]]:
            s = clean_s(v)
            if not s or any(w in s.lower() for w in ["coordinate", "tee", "green", "landing"]):
                return None
            parts = [p.strip() for p in s.replace("\n", " ").split(",") if p.strip()]
            if len(parts) >= 2:
                try:
                    return (float(parts[0]), float(parts[1]))
                except ValueError:
                    pass
            return None

        courses_raw: Dict[str, List[Dict[str, Any]]] = {}
        curr_course = "Conero Golf Club"
        courses_raw[curr_course] = []

        for idx, row in df.iterrows():
            val0 = clean_s(row.iloc[0])
            if not val0:
                continue
            if any(k in val0.lower() for k in ["torrenova", "riviera", "perugia"]):
                curr_course = val0.strip()
                courses_raw[curr_course] = []
                continue
            if "buca" in val0.lower():
                digits = "".join(c for c in val0 if c.isdigit())
                if not digits:
                    continue
                h_num = int(digits)

                # Larghezza fairway
                w_m = parse_n(row.iloc[9])
                w_s = parse_n(row.iloc[10])
                w_a = parse_n(row.iloc[11])

                note = None
                for col_i in [9, 10, 11]:
                    rv = clean_s(row.iloc[col_i])
                    if rv and parse_n(rv) is None and "larghezza" not in rv.lower():
                        note = rv

                fairway_width = 35.0  # standard medio
                if w_s:
                    fairway_width = w_s
                elif w_m:
                    fairway_width = w_m
                elif w_a:
                    fairway_width = w_a

                # Par & HCP con sanificazione
                raw_par = parse_n(row.iloc[1])
                raw_hcp = parse_n(row.iloc[2])

                dist_g = parse_n(row.iloc[4])

                # Autocorrezione par errato da trascrizione (es. buca 7,8,9 Riviera)
                if raw_par and raw_par > 5:
                    if dist_g and dist_g > 450:
                        par_val = 5
                    elif dist_g and dist_g > 230:
                        par_val = 4
                    else:
                        par_val = 3
                else:
                    par_val = int(raw_par) if raw_par is not None else 4

                hcp_val = int(raw_hcp) if raw_hcp is not None else h_num

                courses_raw[curr_course].append({
                    "hole_number": h_num,
                    "par": par_val,
                    "hcp": hcp_val,
                    "dist_bianchi": parse_n(row.iloc[3]),
                    "dist_gialli": dist_g,
                    "dist_rossi": parse_n(row.iloc[5]),
                    "tee_bianchi": parse_pt(row.iloc[6]),
                    "tee_gialli": parse_pt(row.iloc[7]),
                    "tee_rossi": parse_pt(row.iloc[8]),
                    "fairway_width": float(fairway_width),
                    "special_hazard": note,
                    "landing_1": parse_pt(row.iloc[12]),
                    "landing_2": parse_pt(row.iloc[13]),
                    "green_center": parse_pt(row.iloc[14]),
                    "green_diameter": 50.0
                })

        # Costruisce i 4 percorsi
        for cname, raw_holes in courses_raw.items():
            cid = self._normalize_course_key(cname)
            official_name = cname.strip()
            if "conero" in cid:
                official_name = "Conero Golf Club"
            elif "torrenova" in cid:
                official_name = "Torrenova Golf"
            elif "riviera" in cid:
                official_name = "Riviera Golf"
            elif "perugia" in cid:
                official_name = "Golf Club Perugia"

            holes_dict = {h["hole_number"]: TacticalHole(**h) for h in raw_holes}
            self.courses[cid] = TacticalCourse(
                course_id=cid,
                name=official_name,
                holes_count=len(holes_dict),
                holes=holes_dict
            )

        # Salva cache JSON
        try:
            dumpable = {}
            for cid, c_obj in self.courses.items():
                c_dict = {
                    "course_id": c_obj.course_id,
                    "name": c_obj.name,
                    "holes_count": c_obj.holes_count,
                    "holes": {h_num: asdict(h_obj) for h_num, h_obj in c_obj.holes.items()}
                }
                dumpable[cid] = c_dict
            self.cache_json.write_text(json.dumps(dumpable, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_course(self, course_id_or_name: str) -> Optional[TacticalCourse]:
        cid = self._normalize_course_key(course_id_or_name)
        if cid in self.courses:
            return self.courses[cid]
        for key, c in self.courses.items():
            if cid in key or key in cid or course_id_or_name.lower() in c.name.lower():
                return c
        return self.courses.get("conero_golf_club")

    def get_tactical_hole(self, course_id_or_name: str, hole_number: int) -> Optional[TacticalHole]:
        c = self.get_course(course_id_or_name)
        if c:
            return c.get_hole(hole_number)
        return None

    def get_playing_line_waypoints(
        self,
        tactical_hole: TacticalHole,
        tee_color: str = "gialli"
    ) -> List[Tuple[float, float]]:
        """
        Restituisce la sequenza ordinata di coordinate GPS (lat, lon) che definiscono la playing line:
        Tee -> Landing 1 (se presente) -> Landing 2 (se presente) -> Green Center
        """
        tee = tactical_hole.get_tee_coords(tee_color)
        pts: List[Tuple[float, float]] = []
        if tee:
            pts.append(tee)
        if tactical_hole.landing_1:
            pts.append(tactical_hole.landing_1)
        if tactical_hole.landing_2:
            pts.append(tactical_hole.landing_2)
        if tactical_hole.green_center:
            pts.append(tactical_hole.green_center)
        return pts

    def get_landing_zones_info(
        self,
        tactical_hole: TacticalHole,
        tee_color: str = "gialli"
    ) -> List[Dict[str, Any]]:
        """
        Calcola i parametri della fascia orizzontale di atterraggio ottimale:
        - Centro = Landing Area GPS
        - Estensione = 20 metri verso la bandiera + 20 metri verso il tee (profondità totale 40m)
        - Larghezza = larghezza fairway della buca
        """
        zones = []
        pts = self.get_playing_line_waypoints(tactical_hole, tee_color)
        if len(pts) < 2:
            return zones

        # Identifica le landing areas
        landing_points = []
        if tactical_hole.landing_1:
            landing_points.append(("Landing Area 1 (Drive Target)", tactical_hole.landing_1))
        if tactical_hole.landing_2:
            landing_points.append(("Landing Area 2 (Layup Target)", tactical_hole.landing_2))

        tee_pt = pts[0]
        green_pt = pts[-1]
        total_len = haversine_distance(tee_pt[0], tee_pt[1], green_pt[0], green_pt[1])

        for label, l_pt in landing_points:
            dist_from_tee = haversine_distance(tee_pt[0], tee_pt[1], l_pt[0], l_pt[1])
            dist_to_green = haversine_distance(l_pt[0], l_pt[1], green_pt[0], green_pt[1])
            zones.append({
                "label": label,
                "center_lat": l_pt[0],
                "center_lon": l_pt[1],
                "dist_from_tee_m": round(dist_from_tee, 1),
                "dist_to_green_m": round(dist_to_green, 1),
                "depth_forward_m": 20.0,
                "depth_backward_m": 20.0,
                "total_depth_m": 40.0,
                "width_m": tactical_hole.fairway_width
            })

        return zones

    def project_shot_along_corridor(
        self,
        tactical_hole: TacticalHole,
        shot_data: Any,
        tee_color: str = "gialli",
        prev_cumulative_dist: float = 0.0
    ) -> Dict[str, Any]:
        """
        Proietta un colpo (oggetto Shot o dict) lungo il corridoio della buca:
        - Determina distanza lungo il corridoio dal tee
        - Determina deviazione laterale in metri rispetto alla playing line
        - Assegna colore specifico in base al lie registrato
        """
        shot_idx = getattr(shot_data, "shot_index", 1)
        club = getattr(shot_data, "club", "N/D") or "N/D"
        dist_m = getattr(shot_data, "distance_meters", None) or 150.0
        lie = getattr(shot_data, "lie", "fairway")
        lie_str = str(lie.value if hasattr(lie, "value") else lie).lower()
        res = getattr(shot_data, "result", "good")
        res_str = str(res.value if hasattr(res, "value") else res).lower()
        notes = getattr(shot_data, "notes", "") or ""

        # Posizione cumulata lungo il corridoio
        cum_dist = prev_cumulative_dist + float(dist_m)
        total_nominal = tactical_hole.get_nominal_length(tee_color)

        # Coordinate GPS effettive se registrate da smartphone
        lat = getattr(shot_data, "latitude", None)
        lon = getattr(shot_data, "longitude", None)

        lateral_offset_m = 0.0
        if lat and lon and tactical_hole.green_center:
            tee_coords = tactical_hole.get_tee_coords(tee_color)
            if tee_coords:
                # Calcola scostamento laterale geodetico reale
                dist_tee_ball = haversine_distance(tee_coords[0], tee_coords[1], lat, lon)
                cum_dist = dist_tee_ball
                # Stima deviazione laterale da angolo o cross-track
                # Per accuratezza usiamo un'approssimazione metrica
                from golf_strategy_ai.geo.projection import latlon_to_utm
                from golf_strategy_ai.geo.geometry import lateral_and_longitudinal_offset
                tx, ty, _, _ = latlon_to_utm(tee_coords[0], tee_coords[1])
                gx, gy, _, _ = latlon_to_utm(tactical_hole.green_center[0], tactical_hole.green_center[1])
                bx, by, _, _ = latlon_to_utm(lat, lon)
                prog_m, lat_m = lateral_and_longitudinal_offset(tx, ty, gx, gy, bx, by)
                cum_dist = max(5.0, prog_m)
                lateral_offset_m = lat_m
        else:
            # Stima balistica dall'esito e lie del colpo
            fw_half = tactical_hole.fairway_width / 2.0
            if "left" in res_str or "hook" in res_str or "pull" in res_str:
                lateral_offset_m = -(fw_half + 8.0)
            elif "right" in res_str or "slice" in res_str or "push" in res_str:
                lateral_offset_m = +(fw_half + 8.0)
            elif "bunker" in lie_str or "bunker" in res_str:
                lateral_offset_m = +(fw_half + 3.0)
            elif "rough" in lie_str:
                lateral_offset_m = -(fw_half + 5.0)
            elif "green" in lie_str:
                lateral_offset_m = 0.5
            else:
                lateral_offset_m = 1.0  # centro fairway

        # Determina la superficie di arrivo (Landing Surface) per il colore del colpo
        landing_surface = "fairway"
        if "green" in res_str or "green" in lie_str or "hole" in res_str or "putt" in str(club).lower():
            landing_surface = "green"
        elif "fairway" in res_str or "fairway" in lie_str:
            landing_surface = "fairway"
        elif "bunker" in res_str or "bunker" in lie_str:
            landing_surface = "bunker"
        elif "rough" in res_str or "rough" in lie_str or "miss" in res_str:
            landing_surface = "rough"
        elif "water" in res_str or "water" in lie_str or "hazard" in res_str or "hazard" in lie_str:
            landing_surface = "water"
        elif "out_of_bounds" in res_str or "out_of_bounds" in lie_str:
            landing_surface = "out_of_bounds"
        elif "tee" in lie_str:
            landing_surface = "fairway"  # drive standard in fairway se non diversamente specificato

        color_map = {
            "fairway": "#10B981",       # Smeraldo vivace (Fairway)
            "green": "#06B6D4",         # Ciano / Menta brillante (Green)
            "rough": "#F59E0B",         # Ambra dorata (Rough)
            "bunker": "#FBBF24",        # Giallo sabbia (Bunker)
            "hazard": "#3B82F6",        # Blu elettrico (Ostacolo)
            "water": "#3B82F6",         # Blu acqua
            "tee": "#94A3B8",           # Grigio platino
            "out_of_bounds": "#EF4444"  # Rosso allerta
        }
        color = color_map.get(landing_surface, "#10B981")

        # Verifica se è nella landing area
        in_landing = False
        for lz in self.get_landing_zones_info(tactical_hole, tee_color):
            lz_c = lz["dist_from_tee_m"]
            if (lz_c - 20.0) <= cum_dist <= (lz_c + 20.0) and abs(lateral_offset_m) <= (lz["width_m"] / 2.0):
                in_landing = True
                break

        # Distanza residua al green
        remaining_to_green = max(0.0, total_nominal - cum_dist)

        return {
            "shot_index": shot_idx,
            "club": club,
            "dist_m": round(float(dist_m), 1),
            "cum_dist_m": round(cum_dist, 1),
            "remaining_to_green_m": round(remaining_to_green, 1),
            "lateral_offset_m": round(lateral_offset_m, 1),
            "lie": lie_str,
            "result": res_str,
            "notes": notes,
            "color": color,
            "in_landing_zone": in_landing,
            "is_on_green": ("green" in lie_str or remaining_to_green <= 15.0)
        }


# Istanza singleton globale pronta all'uso
tactical_course_manager = TacticalCourseManager()
