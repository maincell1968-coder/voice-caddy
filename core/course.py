from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field


class HoleCoordinates(BaseModel):
    """
    Struttura dati per le coordinate geografiche e altimetriche della buca.
    Supporta coordinate di partenza (Tee), centro green e pin personalizzato (bandiera).
    """
    tee_lat: float = Field(..., description="Latitudine GPS del Tee di partenza")
    tee_lon: float = Field(..., description="Longitudine GPS del Tee di partenza")
    tee_altitude: Optional[float] = Field(default=None, description="Quota altimetrica del Tee in metri s.l.m.")

    green_lat: float = Field(..., description="Latitudine GPS del centro green")
    green_lon: float = Field(..., description="Longitudine GPS del centro green")
    green_altitude: Optional[float] = Field(default=None, description="Quota altimetrica del centro green in metri s.l.m.")

    pin_lat: Optional[float] = Field(default=None, description="Latitudine della posizione effettiva della bandiera/pin (se specificata)")
    pin_lon: Optional[float] = Field(default=None, description="Longitudine della posizione effettiva della bandiera/pin (se specificata)")
    pin_altitude: Optional[float] = Field(default=None, description="Quota altimetrica della bandiera in metri s.l.m.")

    @property
    def target_lat(self) -> float:
        """Restituisce la latitudine del target attivo (pin se presente, altrimenti centro green)."""
        return self.pin_lat if self.pin_lat is not None else self.green_lat

    @property
    def target_lon(self) -> float:
        """Restituisce la longitudine del target attivo (pin se presente, altrimenti centro green)."""
        return self.pin_lon if self.pin_lon is not None else self.green_lon

    @property
    def target_altitude(self) -> Optional[float]:
        """Restituisce la quota del target attivo."""
        return self.pin_altitude if self.pin_altitude is not None else self.green_altitude


class HoleInfo(BaseModel):
    hole_number: int = Field(..., ge=1, le=18)
    par: int = Field(..., ge=3, le=5)
    distance_meters: Optional[int] = Field(None, description="Distanza nominale dal tee in metri")
    handicap_index: Optional[int] = Field(None, ge=1, le=18, description="Indice di difficoltà della buca")
    slope_elevation_profile: str = Field(default="In pianura", description="Profilo orografico e pendenze dal tee al green")
    coordinates: Optional[HoleCoordinates] = Field(default=None, description="Coordinate geografiche e altimetriche di Tee e Green/Pin")


class GolfCourse(BaseModel):
    course_id: str = Field(..., description="ID univoco del campo")
    name: str = Field(..., description="Nome ufficiale del circolo da golf")
    city: str = Field(default="Italia", description="Città o località")
    total_par: int = Field(default=71, description="Par totale del campo o del percorso 9/18 buche")
    holes_count: int = Field(default=18, description="Numero totale di buche del tracciato (9 o 18)")
    terrain_description: str = Field(default="Standard", description="Descrizione generale dell'orografia e pendenze del campo")
    holes: List[HoleInfo] = Field(..., description="Dettaglio delle buche")

    def get_hole(self, hole_number: int) -> Optional[HoleInfo]:
        """Recupera le informazioni di una specifica buca."""
        for h in self.holes:
            if h.hole_number == hole_number:
                return h
        return None

    def get_target_pin_coordinates(self, hole_number: int) -> Optional[Tuple[float, float, Optional[float]]]:
        """
        Recupera le coordinate target (lat, lon, quota) per la buca richiesta.
        Restituisce (target_lat, target_lon, target_altitude).
        """
        h = self.get_hole(hole_number)
        if h and h.coordinates:
            return (h.coordinates.target_lat, h.coordinates.target_lon, h.coordinates.target_altitude)
        return None

    def set_pin_override(self, hole_number: int, pin_lat: float, pin_lon: float, pin_altitude: Optional[float] = None) -> bool:
        """Imposta una posizione pin personalizzata per la buca."""
        h = self.get_hole(hole_number)
        if h and h.coordinates:
            h.coordinates.pin_lat = pin_lat
            h.coordinates.pin_lon = pin_lon
            h.coordinates.pin_altitude = pin_altitude
            return True
        return False


# Pre-loaded Course 1: Conero Golf Club (18 Buche - Par 71) a Sirolo (AN)
# Calibrato con coordinate reali, altimetrie s.l.m. e distanze Haversine fedeli allo scorecard
CONERO_GOLF_CLUB = GolfCourse(
    course_id="conero_golf_club",
    name="Conero Golf Club",
    city="Sirolo (AN)",
    total_par=71,
    holes_count=18,
    terrain_description="Percorso tecnico e collinare con dislivelli orografici significativi (buche con salite, discese e vallate che incidono sulle distanze reali dei colpi).",
    holes=[
        HoleInfo(
            hole_number=1, par=4, distance_meters=342, handicap_index=5,
            slope_elevation_profile="Primi 2/3 in pianura, ultimo terzo in salita",
            coordinates=HoleCoordinates(
                tee_lat=43.5228, tee_lon=13.6060, tee_altitude=102.0,
                green_lat=43.5199, green_lon=13.6072, green_altitude=110.0
            )
        ),
        HoleInfo(
            hole_number=2, par=3, distance_meters=134, handicap_index=17,
            slope_elevation_profile="In discesa",
            coordinates=HoleCoordinates(
                tee_lat=43.5198, tee_lon=13.6074, tee_altitude=110.0,
                green_lat=43.5188, green_lon=13.6083, green_altitude=102.0
            )
        ),
        HoleInfo(
            hole_number=3, par=4, distance_meters=402, handicap_index=3,
            slope_elevation_profile="Primi 2/3 in discesa, ultimo terzo in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.5185, tee_lon=13.6085, tee_altitude=102.0,
                green_lat=43.5152, green_lon=13.6105, green_altitude=94.0
            )
        ),
        HoleInfo(
            hole_number=4, par=5, distance_meters=433, handicap_index=15,
            slope_elevation_profile="In pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.5150, tee_lon=13.6108, tee_altitude=94.0,
                green_lat=43.5140, green_lon=13.6160, green_altitude=94.0
            )
        ),
        HoleInfo(
            hole_number=5, par=4, distance_meters=292, handicap_index=9,
            slope_elevation_profile="In pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.5142, tee_lon=13.6162, tee_altitude=94.0,
                green_lat=43.5165, green_lon=13.6180, green_altitude=95.0
            )
        ),
        HoleInfo(
            hole_number=6, par=3, distance_meters=139, handicap_index=13,
            slope_elevation_profile="In pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.5168, tee_lon=13.6182, tee_altitude=95.0,
                green_lat=43.5178, green_lon=13.6190, green_altitude=95.0
            )
        ),
        HoleInfo(
            hole_number=7, par=4, distance_meters=320, handicap_index=7,
            slope_elevation_profile="Primo terzo in pianura, 2/3 finali in salita",
            coordinates=HoleCoordinates(
                tee_lat=43.5180, tee_lon=13.6192, tee_altitude=95.0,
                green_lat=43.5204, green_lon=13.6175, green_altitude=107.0
            )
        ),
        HoleInfo(
            hole_number=8, par=4, distance_meters=343, handicap_index=11,
            slope_elevation_profile="Prima metà in discesa, resto in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.5206, tee_lon=13.6173, tee_altitude=107.0,
                green_lat=43.5233, green_lon=13.6152, green_altitude=100.0
            )
        ),
        HoleInfo(
            hole_number=9, par=4, distance_meters=390, handicap_index=1,
            slope_elevation_profile="Prima metà in salita, seconda metà in leggera salita",
            coordinates=HoleCoordinates(
                tee_lat=43.5235, tee_lon=13.6150, tee_altitude=100.0,
                green_lat=43.5262, green_lon=13.6120, green_altitude=112.0
            )
        ),
        HoleInfo(
            hole_number=10, par=4, distance_meters=334, handicap_index=10,
            slope_elevation_profile="Prima metà in discesa, seconda metà in salita",
            coordinates=HoleCoordinates(
                tee_lat=43.5255, tee_lon=13.6110, tee_altitude=110.0,
                green_lat=43.5230, green_lon=13.6085, green_altitude=111.0
            )
        ),
        HoleInfo(
            hole_number=11, par=4, distance_meters=307, handicap_index=6,
            slope_elevation_profile="Tutto in salita",
            coordinates=HoleCoordinates(
                tee_lat=43.5228, tee_lon=13.6083, tee_altitude=108.0,
                green_lat=43.5205, green_lon=13.6065, green_altitude=122.0
            )
        ),
        HoleInfo(
            hole_number=12, par=5, distance_meters=477, handicap_index=18,
            slope_elevation_profile="Tutto in discesa",
            coordinates=HoleCoordinates(
                tee_lat=43.5203, tee_lon=13.6063, tee_altitude=122.0,
                green_lat=43.5165, green_lon=13.6035, green_altitude=104.0
            )
        ),
        HoleInfo(
            hole_number=13, par=3, distance_meters=168, handicap_index=14,
            slope_elevation_profile="In pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.5163, tee_lon=13.6033, tee_altitude=104.0,
                green_lat=43.5150, green_lon=13.6022, green_altitude=104.0
            )
        ),
        HoleInfo(
            hole_number=14, par=4, distance_meters=287, handicap_index=12,
            slope_elevation_profile="In pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.5152, tee_lon=13.6020, tee_altitude=104.0,
                green_lat=43.5173, green_lon=13.6005, green_altitude=105.0
            )
        ),
        HoleInfo(
            hole_number=15, par=5, distance_meters=500, handicap_index=4,
            slope_elevation_profile="In pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.5175, tee_lon=13.6003, tee_altitude=105.0,
                green_lat=43.5215, green_lon=13.5975, green_altitude=106.0
            )
        ),
        HoleInfo(
            hole_number=16, par=3, distance_meters=133, handicap_index=16,
            slope_elevation_profile="In salita",
            coordinates=HoleCoordinates(
                tee_lat=43.5218, tee_lon=13.5977, tee_altitude=106.0,
                green_lat=43.5228, green_lon=13.5985, green_altitude=114.0
            )
        ),
        HoleInfo(
            hole_number=17, par=4, distance_meters=376, handicap_index=8,
            slope_elevation_profile="Tutto in discesa",
            coordinates=HoleCoordinates(
                tee_lat=43.5230, tee_lon=13.5988, tee_altitude=114.0,
                green_lat=43.5255, green_lon=13.6020, green_altitude=102.0
            )
        ),
        HoleInfo(
            hole_number=18, par=4, distance_meters=334, handicap_index=2,
            slope_elevation_profile="Tutto in salita",
            coordinates=HoleCoordinates(
                tee_lat=43.5252, tee_lon=13.6025, tee_altitude=102.0,
                green_lat=43.5230, green_lon=13.6055, green_altitude=116.0
            )
        ),
    ]
)

# Pre-loaded Course 2: Torrenova Golf (9 Buche - Par 34) a Porto Potenza Picena (MC)
TORRENOVA_GOLF_CLUB = GolfCourse(
    course_id="torrenova_golf_club",
    name="Torrenova Golf",
    city="Porto Potenza Picena (MC)",
    total_par=34,
    holes_count=9,
    terrain_description="Percorso interamente in pianura (terreno piatto senza complicazioni di pendenze o dislivelli altimetrici).",
    holes=[
        HoleInfo(
            hole_number=1, par=4, distance_meters=330, handicap_index=5,
            slope_elevation_profile="Tutto in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.3980, tee_lon=13.6820, tee_altitude=5.0,
                green_lat=43.3955, green_lon=13.6840, green_altitude=5.0
            )
        ),
        HoleInfo(
            hole_number=2, par=3, distance_meters=140, handicap_index=9,
            slope_elevation_profile="Tutto in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.3952, tee_lon=13.6842, tee_altitude=5.0,
                green_lat=43.3942, green_lon=13.6850, green_altitude=5.0
            )
        ),
        HoleInfo(
            hole_number=3, par=4, distance_meters=350, handicap_index=1,
            slope_elevation_profile="Tutto in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.3940, tee_lon=13.6852, tee_altitude=5.0,
                green_lat=43.3912, green_lon=13.6870, green_altitude=5.0
            )
        ),
        HoleInfo(
            hole_number=4, par=4, distance_meters=310, handicap_index=7,
            slope_elevation_profile="Tutto in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.3910, tee_lon=13.6872, tee_altitude=5.0,
                green_lat=43.3932, green_lon=13.6888, green_altitude=5.0
            )
        ),
        HoleInfo(
            hole_number=5, par=5, distance_meters=465, handicap_index=3,
            slope_elevation_profile="Tutto in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.3935, tee_lon=13.6890, tee_altitude=5.0,
                green_lat=43.3970, green_lon=13.6910, green_altitude=5.0
            )
        ),
        HoleInfo(
            hole_number=6, par=3, distance_meters=155, handicap_index=8,
            slope_elevation_profile="Tutto in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.3972, tee_lon=13.6912, tee_altitude=5.0,
                green_lat=43.3984, green_lon=13.6920, green_altitude=5.0
            )
        ),
        HoleInfo(
            hole_number=7, par=4, distance_meters=340, handicap_index=2,
            slope_elevation_profile="Tutto in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.3986, tee_lon=13.6918, tee_altitude=5.0,
                green_lat=43.3960, green_lon=13.6895, green_altitude=5.0
            )
        ),
        HoleInfo(
            hole_number=8, par=4, distance_meters=325, handicap_index=6,
            slope_elevation_profile="Tutto in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.3958, tee_lon=13.6892, tee_altitude=5.0,
                green_lat=43.3975, green_lon=13.6865, green_altitude=5.0
            )
        ),
        HoleInfo(
            hole_number=9, par=3, distance_meters=135, handicap_index=4,
            slope_elevation_profile="Tutto in pianura",
            coordinates=HoleCoordinates(
                tee_lat=43.3978, tee_lon=13.6862, tee_altitude=5.0,
                green_lat=43.3988, green_lon=13.6852, green_altitude=5.0
            )
        ),
    ]
)


class CourseRegistry:
    """
    Registry for golf courses. Pre-loaded with Conero Golf Club (18h)
    and Torrenova Golf (9h), supporting importing custom user courses.
    """

    def __init__(self, storage_dir: Path = Path("courses")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.courses: Dict[str, GolfCourse] = {
            CONERO_GOLF_CLUB.course_id: CONERO_GOLF_CLUB,
            TORRENOVA_GOLF_CLUB.course_id: TORRENOVA_GOLF_CLUB
        }
        self._load_saved_courses()

    def _load_saved_courses(self):
        for json_file in self.storage_dir.glob("*.json"):
            try:
                content = json_file.read_text(encoding="utf-8")
                course = GolfCourse.model_validate_json(content)
                self.courses[course.course_id] = course
            except Exception:
                pass

    def get_course(self, course_id: str) -> Optional[GolfCourse]:
        return self.courses.get(course_id)

    def get_default_course(self) -> GolfCourse:
        return CONERO_GOLF_CLUB

    def list_courses(self) -> List[GolfCourse]:
        return list(self.courses.values())

    def save_custom_course(self, course: GolfCourse):
        self.courses[course.course_id] = course
        file_path = self.storage_dir / f"{course.course_id}.json"
        file_path.write_text(course.model_dump_json(indent=2), encoding="utf-8")
