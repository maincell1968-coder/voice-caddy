from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class HoleInfo(BaseModel):
    hole_number: int = Field(..., ge=1, le=18)
    par: int = Field(..., ge=3, le=5)
    distance_meters: Optional[int] = Field(None, description="Distanza dal tee in metri")
    handicap_index: Optional[int] = Field(None, ge=1, le=18, description="Indice di difficoltà della buca")
    slope_elevation_profile: str = Field(default="In pianura", description="Profilo orografico e pendenze dal tee al green")


class GolfCourse(BaseModel):
    course_id: str = Field(..., description="ID univoco del campo")
    name: str = Field(..., description="Nome ufficiale del circolo da golf")
    city: str = Field(default="Italia", description="Città o località")
    total_par: int = Field(default=71, description="Par totale del campo o del percorso 9/18 buche")
    holes_count: int = Field(default=18, description="Numero totale di buche del tracciato (9 o 18)")
    terrain_description: str = Field(default="Standard", description="Descrizione generale dell'orografia e pendenze del campo")
    holes: List[HoleInfo] = Field(..., description="Dettaglio delle buche")


# Pre-loaded Course 1: Conero Golf Club (18 Buche - Par 71)
CONERO_GOLF_CLUB = GolfCourse(
    course_id="conero_golf_club",
    name="Conero Golf Club",
    city="Sirolo (AN)",
    total_par=71,
    holes_count=18,
    terrain_description="Percorso tecnico e collinare con dislivelli orografici significativi (buche con salite, discese e vallate che incidono sulle distanze reali dei colpi).",
    holes=[
        HoleInfo(hole_number=1, par=4, distance_meters=356, handicap_index=7, slope_elevation_profile="Primi 2/3 in pianura, ultimo terzo in salita"),
        HoleInfo(hole_number=2, par=5, distance_meters=475, handicap_index=11, slope_elevation_profile="In pianura"),
        HoleInfo(hole_number=3, par=3, distance_meters=152, handicap_index=15, slope_elevation_profile="Primi 2/3 in discesa, ultimo terzo in pianura"),
        HoleInfo(hole_number=4, par=4, distance_meters=378, handicap_index=3, slope_elevation_profile="In pianura"),
        HoleInfo(hole_number=5, par=4, distance_meters=340, handicap_index=13, slope_elevation_profile="In pianura"),
        HoleInfo(hole_number=6, par=3, distance_meters=170, handicap_index=9, slope_elevation_profile="In pianura"),
        HoleInfo(hole_number=7, par=4, distance_meters=390, handicap_index=1, slope_elevation_profile="Primo terzo in pianura, 2/3 finali in salita"),
        HoleInfo(hole_number=8, par=4, distance_meters=315, handicap_index=17, slope_elevation_profile="Prima metà in discesa, resto in pianura"),
        HoleInfo(hole_number=9, par=5, distance_meters=490, handicap_index=5, slope_elevation_profile="Prima metà in salita, seconda metà in leggera salita"),
        HoleInfo(hole_number=10, par=4, distance_meters=365, handicap_index=8, slope_elevation_profile="Prima metà in discesa, seconda metà in salita"),
        HoleInfo(hole_number=11, par=3, distance_meters=145, handicap_index=16, slope_elevation_profile="Tutto in salita"),
        HoleInfo(hole_number=12, par=5, distance_meters=485, handicap_index=10, slope_elevation_profile="Tutto in discesa"),
        HoleInfo(hole_number=13, par=4, distance_meters=380, handicap_index=2, slope_elevation_profile="In pianura"),
        HoleInfo(hole_number=14, par=4, distance_meters=330, handicap_index=14, slope_elevation_profile="In pianura"),
        HoleInfo(hole_number=15, par=3, distance_meters=160, handicap_index=12, slope_elevation_profile="In pianura"),
        HoleInfo(hole_number=16, par=4, distance_meters=350, handicap_index=6, slope_elevation_profile="In pianura"),
        HoleInfo(hole_number=17, par=4, distance_meters=345, handicap_index=18, slope_elevation_profile="Tutto in discesa"),
        HoleInfo(hole_number=18, par=5, distance_meters=500, handicap_index=4, slope_elevation_profile="Tutto in salita"),
    ]
)

# Pre-loaded Course 2: Torrenova Golf (9 Buche - Par 34)
TORRENOVA_GOLF_CLUB = GolfCourse(
    course_id="torrenova_golf_club",
    name="Torrenova Golf",
    city="Porto Potenza Picena (MC)",
    total_par=34,
    holes_count=9,
    terrain_description="Percorso interamente in pianura (terreno piatto senza complicazioni di pendenze o dislivelli altimetrici).",
    holes=[
        HoleInfo(hole_number=1, par=4, distance_meters=330, handicap_index=5, slope_elevation_profile="Tutto in pianura"),
        HoleInfo(hole_number=2, par=3, distance_meters=140, handicap_index=9, slope_elevation_profile="Tutto in pianura"),
        HoleInfo(hole_number=3, par=4, distance_meters=350, handicap_index=1, slope_elevation_profile="Tutto in pianura"),
        HoleInfo(hole_number=4, par=4, distance_meters=310, handicap_index=7, slope_elevation_profile="Tutto in pianura"),
        HoleInfo(hole_number=5, par=5, distance_meters=465, handicap_index=3, slope_elevation_profile="Tutto in pianura"),
        HoleInfo(hole_number=6, par=3, distance_meters=155, handicap_index=8, slope_elevation_profile="Tutto in pianura"),
        HoleInfo(hole_number=7, par=4, distance_meters=340, handicap_index=2, slope_elevation_profile="Tutto in pianura"),
        HoleInfo(hole_number=8, par=4, distance_meters=325, handicap_index=6, slope_elevation_profile="Tutto in pianura"),
        HoleInfo(hole_number=9, par=3, distance_meters=135, handicap_index=4, slope_elevation_profile="Tutto in pianura"),
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
