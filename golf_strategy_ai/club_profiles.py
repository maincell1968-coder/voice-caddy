from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple, Any

from .models import PlayerCategory, ClubStats, CategoryProfile

METERS_TO_YARDS = 1.0936132983
YARDS_TO_METERS = 0.9144


def meters_to_yards(meters: float) -> float:
    """Converte una distanza da metri a yard."""
    return meters * METERS_TO_YARDS


def yards_to_meters(yards: float) -> float:
    """Converte una distanza da yard a metri."""
    return yards * YARDS_TO_METERS


def calculate_target_radius(lateral_m: float, longitudinal_m: float) -> float:
    """
    Calcola il raggio equivalente di dispersione circolare:
    r = sqrt(lateral² + longitudinal²)
    """
    return round(math.sqrt(lateral_m ** 2 + longitudinal_m ** 2), 1)


# ---------------------------------------------------------------------------
# Database Statistico Balistico per Categoria
# Fonti: Shot Scope, TrackMan Amateur Averages, USGA/R&A Distance Reports, Arccos
# ---------------------------------------------------------------------------
RAW_CLUB_DATA: Dict[str, Dict[str, Any]] = {
    # -----------------------------------------------------------------------
    # 1. PRIMA CATEGORIA (Handicap 0 - 12.0)
    # -----------------------------------------------------------------------
    "prima": {
        "label": "Prima Categoria (HCP 0–12)",
        "handicap_range": (0.0, 12.0),
        "driver_total_mean_m": 235.0,
        "clubs": {
            "driver": {
                "label": "Driver",
                "carry_mean_m": 215.0, "carry_min_m": 195.0, "carry_max_m": 240.0,
                "total_mean_m": 235.0, "total_min_m": 215.0, "total_max_m": 260.0,
                "lateral_dispersion_m": 22.0, "longitudinal_dispersion_m": 18.0,
                "confidence": "high", "data_type": "observed", "notes": "Massima distanza, dispersione laterale contenuta."
            },
            "wood_3": {
                "label": "Legno 3",
                "carry_mean_m": 200.0, "carry_min_m": 185.0, "carry_max_m": 220.0,
                "total_mean_m": 215.0, "total_min_m": 198.0, "total_max_m": 235.0,
                "lateral_dispersion_m": 19.0, "longitudinal_dispersion_m": 16.0,
                "confidence": "high", "data_type": "observed", "notes": "Alternativa dal tee con fairway stretti o per attacco al green su par 5."
            },
            "hybrid_3": {
                "label": "Ibrido 3 (19°)",
                "carry_mean_m": 185.0, "carry_min_m": 170.0, "carry_max_m": 200.0,
                "total_mean_m": 198.0, "total_min_m": 182.0, "total_max_m": 212.0,
                "lateral_dispersion_m": 16.0, "longitudinal_dispersion_m": 14.0,
                "confidence": "high", "data_type": "observed", "notes": "Traiettoria alta e atterraggio morbido."
            },
            "hybrid_4": {
                "label": "Ibrido 4 (22°)",
                "carry_mean_m": 175.0, "carry_min_m": 162.0, "carry_max_m": 190.0,
                "total_mean_m": 186.0, "total_min_m": 172.0, "total_max_m": 200.0,
                "lateral_dispersion_m": 14.0, "longitudinal_dispersion_m": 12.0,
                "confidence": "high", "data_type": "observed", "notes": "Controllo elevato dal rough leggero."
            },
            "iron_4": {
                "label": "Ferro 4",
                "carry_mean_m": 172.0, "carry_min_m": 158.0, "carry_max_m": 185.0,
                "total_mean_m": 182.0, "total_min_m": 168.0, "total_max_m": 195.0,
                "lateral_dispersion_m": 15.0, "longitudinal_dispersion_m": 13.0,
                "confidence": "high", "data_type": "observed", "notes": "Ferro lungo per tee shot su par 3 o colpi bassi controllati."
            },
            "iron_5": {
                "label": "Ferro 5",
                "carry_mean_m": 162.0, "carry_min_m": 150.0, "carry_max_m": 175.0,
                "total_mean_m": 170.0, "total_min_m": 158.0, "total_max_m": 182.0,
                "lateral_dispersion_m": 13.0, "longitudinal_dispersion_m": 11.0,
                "confidence": "high", "data_type": "observed", "notes": "Ottima precisione per approcci lunghi."
            },
            "iron_6": {
                "label": "Ferro 6",
                "carry_mean_m": 152.0, "carry_min_m": 142.0, "carry_max_m": 164.0,
                "total_mean_m": 158.0, "total_min_m": 148.0, "total_max_m": 170.0,
                "lateral_dispersion_m": 11.0, "longitudinal_dispersion_m": 9.5,
                "confidence": "high", "data_type": "observed", "notes": "Regolarità elevata su target medi."
            },
            "iron_7": {
                "label": "Ferro 7",
                "carry_mean_m": 142.0, "carry_min_m": 132.0, "carry_max_m": 152.0,
                "total_mean_m": 146.0, "total_min_m": 136.0, "total_max_m": 156.0,
                "lateral_dispersion_m": 9.5, "longitudinal_dispersion_m": 8.0,
                "confidence": "high", "data_type": "observed", "notes": "Bastone di riferimento per la taratura della sacca."
            },
            "iron_8": {
                "label": "Ferro 8",
                "carry_mean_m": 130.0, "carry_min_m": 122.0, "carry_max_m": 140.0,
                "total_mean_m": 133.0, "total_min_m": 125.0, "total_max_m": 143.0,
                "lateral_dispersion_m": 8.0, "longitudinal_dispersion_m": 7.0,
                "confidence": "high", "data_type": "observed", "notes": "Attacco diretto alla bandiera."
            },
            "iron_9": {
                "label": "Ferro 9",
                "carry_mean_m": 118.0, "carry_min_m": 110.0, "carry_max_m": 126.0,
                "total_mean_m": 120.0, "total_min_m": 112.0, "total_max_m": 128.0,
                "lateral_dispersion_m": 7.0, "longitudinal_dispersion_m": 6.0,
                "confidence": "high", "data_type": "observed", "notes": "Fermo quasi immediato sul green."
            },
            "pitching_wedge": {
                "label": "Pitching Wedge (46°)",
                "carry_mean_m": 106.0, "carry_min_m": 98.0, "carry_max_m": 114.0,
                "total_mean_m": 108.0, "total_min_m": 100.0, "total_max_m": 116.0,
                "lateral_dispersion_m": 5.5, "longitudinal_dispersion_m": 5.0,
                "confidence": "high", "data_type": "observed", "notes": "Punteggio bersaglio elevato."
            },
            "wedge_52": {
                "label": "Gap Wedge (52°)",
                "carry_mean_m": 92.0, "carry_min_m": 84.0, "carry_max_m": 100.0,
                "total_mean_m": 93.0, "total_min_m": 85.0, "total_max_m": 101.0,
                "lateral_dispersion_m": 4.5, "longitudinal_dispersion_m": 4.5,
                "confidence": "high", "data_type": "observed", "notes": "Controllo dello spin e distanza precisa."
            },
            "wedge_56": {
                "label": "Sand Wedge (56°)",
                "carry_mean_m": 78.0, "carry_min_m": 70.0, "carry_max_m": 86.0,
                "total_mean_m": 79.0, "total_min_m": 71.0, "total_max_m": 87.0,
                "lateral_dispersion_m": 4.0, "longitudinal_dispersion_m": 4.0,
                "confidence": "high", "data_type": "observed", "notes": "Approccio morbido o uscita da bunker."
            }
        }
    },

    # -----------------------------------------------------------------------
    # 2. SECONDA CATEGORIA (Handicap 12.1 - 26.0)
    # -----------------------------------------------------------------------
    "seconda": {
        "label": "Seconda Categoria (HCP 12.1–26)",
        "handicap_range": (12.1, 26.0),
        "driver_total_mean_m": 205.0,
        "clubs": {
            "driver": {
                "label": "Driver",
                "carry_mean_m": 185.0, "carry_min_m": 160.0, "carry_max_m": 210.0,
                "total_mean_m": 205.0, "total_min_m": 180.0, "total_max_m": 230.0,
                "lateral_dispersion_m": 32.0, "longitudinal_dispersion_m": 24.0,
                "confidence": "high", "data_type": "observed", "notes": "Dispersione laterale marcata; valutare la larghezza del fairway."
            },
            "wood_3": {
                "label": "Legno 3",
                "carry_mean_m": 170.0, "carry_min_m": 150.0, "carry_max_m": 190.0,
                "total_mean_m": 185.0, "total_min_m": 165.0, "total_max_m": 205.0,
                "lateral_dispersion_m": 28.0, "longitudinal_dispersion_m": 22.0,
                "confidence": "high", "data_type": "observed", "notes": "Spesso più affidabile del driver per centrare il fairway."
            },
            "hybrid_3": {
                "label": "Ibrido 3 (19°)",
                "carry_mean_m": 158.0, "carry_min_m": 140.0, "carry_max_m": 176.0,
                "total_mean_m": 170.0, "total_min_m": 152.0, "total_max_m": 188.0,
                "lateral_dispersion_m": 24.0, "longitudinal_dispersion_m": 19.0,
                "confidence": "high", "data_type": "observed", "notes": "Facilita il decollo della palla rispetto al ferro lungo."
            },
            "hybrid_4": {
                "label": "Ibrido 4 (22°)",
                "carry_mean_m": 148.0, "carry_min_m": 132.0, "carry_max_m": 164.0,
                "total_mean_m": 158.0, "total_min_m": 142.0, "total_max_m": 174.0,
                "lateral_dispersion_m": 21.0, "longitudinal_dispersion_m": 16.0,
                "confidence": "high", "data_type": "observed", "notes": "Bastone eccellente per il lay-up o approcci lunghi."
            },
            "iron_4": {
                "label": "Ferro 4",
                "carry_mean_m": 145.0, "carry_min_m": 128.0, "carry_max_m": 162.0,
                "total_mean_m": 155.0, "total_min_m": 138.0, "total_max_m": 172.0,
                "lateral_dispersion_m": 26.0, "longitudinal_dispersion_m": 20.0,
                "confidence": "medium", "data_type": "observed", "notes": "Spesso difficile da colpire con regolarità; preferire l'ibrido."
            },
            "iron_5": {
                "label": "Ferro 5",
                "carry_mean_m": 138.0, "carry_min_m": 124.0, "carry_max_m": 152.0,
                "total_mean_m": 146.0, "total_min_m": 132.0, "total_max_m": 160.0,
                "lateral_dispersion_m": 20.0, "longitudinal_dispersion_m": 16.0,
                "confidence": "high", "data_type": "observed", "notes": "Buono dal tee su par 3 o da fairway pulito."
            },
            "iron_6": {
                "label": "Ferro 6",
                "carry_mean_m": 130.0, "carry_min_m": 118.0, "carry_max_m": 142.0,
                "total_mean_m": 136.0, "total_min_m": 124.0, "total_max_m": 148.0,
                "lateral_dispersion_m": 17.0, "longitudinal_dispersion_m": 14.0,
                "confidence": "high", "data_type": "observed", "notes": "Colpo di medio raggio standard."
            },
            "iron_7": {
                "label": "Ferro 7",
                "carry_mean_m": 122.0, "carry_min_m": 112.0, "carry_max_m": 133.0,
                "total_mean_m": 127.0, "total_min_m": 117.0, "total_max_m": 138.0,
                "lateral_dispersion_m": 14.0, "longitudinal_dispersion_m": 11.5,
                "confidence": "high", "data_type": "observed", "notes": "Solidità di contatto e buona ripetibilità."
            },
            "iron_8": {
                "label": "Ferro 8",
                "carry_mean_m": 113.0, "carry_min_m": 104.0, "carry_max_m": 122.0,
                "total_mean_m": 117.0, "total_min_m": 108.0, "total_max_m": 126.0,
                "lateral_dispersion_m": 12.0, "longitudinal_dispersion_m": 10.0,
                "confidence": "high", "data_type": "observed", "notes": "Controllo accurato verso il centro del green."
            },
            "iron_9": {
                "label": "Ferro 9",
                "carry_mean_m": 103.0, "carry_min_m": 94.0, "carry_max_m": 112.0,
                "total_mean_m": 106.0, "total_min_m": 97.0, "total_max_m": 115.0,
                "lateral_dispersion_m": 10.0, "longitudinal_dispersion_m": 8.5,
                "confidence": "high", "data_type": "observed", "notes": "Alta probabilità di atterraggio in green."
            },
            "pitching_wedge": {
                "label": "Pitching Wedge (46°)",
                "carry_mean_m": 92.0, "carry_min_m": 84.0, "carry_max_m": 100.0,
                "total_mean_m": 94.0, "total_min_m": 86.0, "total_max_m": 102.0,
                "lateral_dispersion_m": 8.0, "longitudinal_dispersion_m": 7.0,
                "confidence": "high", "data_type": "observed", "notes": "Precisione elevata da 90–100 metri."
            },
            "wedge_52": {
                "label": "Gap Wedge (52°)",
                "carry_mean_m": 80.0, "carry_min_m": 72.0, "carry_max_m": 88.0,
                "total_mean_m": 81.0, "total_min_m": 73.0, "total_max_m": 89.0,
                "lateral_dispersion_m": 7.0, "longitudinal_dispersion_m": 6.5,
                "confidence": "high", "data_type": "observed", "notes": "Ideale per il controllo della profondità."
            },
            "wedge_56": {
                "label": "Sand Wedge (56°)",
                "carry_mean_m": 68.0, "carry_min_m": 60.0, "carry_max_m": 76.0,
                "total_mean_m": 69.0, "total_min_m": 61.0, "total_max_m": 77.0,
                "lateral_dispersion_m": 6.0, "longitudinal_dispersion_m": 6.0,
                "confidence": "high", "data_type": "observed", "notes": "Uscite dal bunker e approcci corti."
            }
        }
    },

    # -----------------------------------------------------------------------
    # 3. TERZA CATEGORIA (Handicap 26.1 - 54.0)
    # -----------------------------------------------------------------------
    "terza": {
        "label": "Terza Categoria (HCP 26.1–54)",
        "handicap_range": (26.1, 54.0),
        "driver_total_mean_m": 170.0,
        "clubs": {
            "driver": {
                "label": "Driver",
                "carry_mean_m": 150.0, "carry_min_m": 120.0, "carry_max_m": 180.0,
                "total_mean_m": 170.0, "total_min_m": 140.0, "total_max_m": 200.0,
                "lateral_dispersion_m": 45.0, "longitudinal_dispersion_m": 35.0,
                "confidence": "high", "data_type": "observed", "notes": "Dispersione molto ampia (slice/hook frequenti); evitare tee shot rischiosi."
            },
            "wood_3": {
                "label": "Legno 3",
                "carry_mean_m": 138.0, "carry_min_m": 115.0, "carry_max_m": 160.0,
                "total_mean_m": 152.0, "total_min_m": 130.0, "total_max_m": 175.0,
                "lateral_dispersion_m": 40.0, "longitudinal_dispersion_m": 30.0,
                "confidence": "medium", "data_type": "observed", "notes": "Difficile da alzare da terra; usarlo prevalentemente dal tee."
            },
            "hybrid_4": {
                "label": "Ibrido 4 (22°)",
                "carry_mean_m": 128.0, "carry_min_m": 110.0, "carry_max_m": 145.0,
                "total_mean_m": 138.0, "total_min_m": 120.0, "total_max_m": 155.0,
                "lateral_dispersion_m": 30.0, "longitudinal_dispersion_m": 22.0,
                "confidence": "high", "data_type": "observed", "notes": "Il bastone lungo più sicuro ed efficace per questa categoria."
            },
            "iron_5": {
                "label": "Ferro 5",
                "carry_mean_m": 115.0, "carry_min_m": 95.0, "carry_max_m": 130.0,
                "total_mean_m": 122.0, "total_min_m": 102.0, "total_max_m": 138.0,
                "lateral_dispersion_m": 32.0, "longitudinal_dispersion_m": 24.0,
                "confidence": "medium", "data_type": "observed", "notes": "Poco consistente; spesso produce la stessa distanza del ferro 6."
            },
            "iron_6": {
                "label": "Ferro 6",
                "carry_mean_m": 110.0, "carry_min_m": 95.0, "carry_max_m": 124.0,
                "total_mean_m": 116.0, "total_min_m": 100.0, "total_max_m": 130.0,
                "lateral_dispersion_m": 26.0, "longitudinal_dispersion_m": 19.0,
                "confidence": "high", "data_type": "observed", "notes": "Inizio dei ferri giocabili con consistenza accettabile."
            },
            "iron_7": {
                "label": "Ferro 7",
                "carry_mean_m": 102.0, "carry_min_m": 90.0, "carry_max_m": 115.0,
                "total_mean_m": 107.0, "total_min_m": 95.0, "total_max_m": 120.0,
                "lateral_dispersion_m": 22.0, "longitudinal_dispersion_m": 16.0,
                "confidence": "high", "data_type": "observed", "notes": "Bastone consigliato per i colpi dal fairway."
            },
            "iron_8": {
                "label": "Ferro 8",
                "carry_mean_m": 94.0, "carry_min_m": 84.0, "carry_max_m": 105.0,
                "total_mean_m": 98.0, "total_min_m": 88.0, "total_max_m": 109.0,
                "lateral_dispersion_m": 18.0, "longitudinal_dispersion_m": 14.0,
                "confidence": "high", "data_type": "observed", "notes": "Buona traiettoria e controllo."
            },
            "iron_9": {
                "label": "Ferro 9",
                "carry_mean_m": 85.0, "carry_min_m": 75.0, "carry_max_m": 95.0,
                "total_mean_m": 88.0, "total_min_m": 78.0, "total_max_m": 98.0,
                "lateral_dispersion_m": 15.0, "longitudinal_dispersion_m": 12.0,
                "confidence": "high", "data_type": "observed", "notes": "Affidabile per approcci al green."
            },
            "pitching_wedge": {
                "label": "Pitching Wedge (46°)",
                "carry_mean_m": 75.0, "carry_min_m": 65.0, "carry_max_m": 85.0,
                "total_mean_m": 77.0, "total_min_m": 67.0, "total_max_m": 87.0,
                "lateral_dispersion_m": 12.0, "longitudinal_dispersion_m": 10.0,
                "confidence": "high", "data_type": "observed", "notes": "Massima consistenza sotto gli 80 metri."
            },
            "wedge_56": {
                "label": "Sand Wedge (56°)",
                "carry_mean_m": 55.0, "carry_min_m": 45.0, "carry_max_m": 65.0,
                "total_mean_m": 56.0, "total_min_m": 46.0, "total_max_m": 66.0,
                "lateral_dispersion_m": 9.0, "longitudinal_dispersion_m": 8.0,
                "confidence": "high", "data_type": "observed", "notes": "Usare con cautela per evitare colpi 'top' o 'fat'."
            }
        }
    }
}


def build_category_profile(cat_key: str) -> CategoryProfile:
    """Costruisce un oggetto CategoryProfile Pydantic con tutti i ClubStats calcolati."""
    raw = RAW_CLUB_DATA[cat_key]
    cat_enum = PlayerCategory(cat_key)
    clubs_dict = {}

    for c_id, c_data in raw["clubs"].items():
        lat_m = c_data["lateral_dispersion_m"]
        long_m = c_data["longitudinal_dispersion_m"]
        rad_m = calculate_target_radius(lat_m, long_m)

        clubs_dict[c_id] = ClubStats(
            club_id=c_id,
            label=c_data["label"],
            carry_mean_m=c_data["carry_mean_m"],
            carry_min_m=c_data["carry_min_m"],
            carry_max_m=c_data["carry_max_m"],
            total_mean_m=c_data["total_mean_m"],
            total_min_m=c_data["total_min_m"],
            total_max_m=c_data["total_max_m"],
            lateral_dispersion_m=lat_m,
            longitudinal_dispersion_m=long_m,
            target_radius_m=rad_m,
            confidence=c_data.get("confidence", "medium"),
            data_type=c_data.get("data_type", "estimated"),
            notes=c_data.get("notes", "")
        )

    return CategoryProfile(
        category=cat_enum,
        handicap_range=raw["handicap_range"],
        label=raw["label"],
        driver_total_mean_m=raw["driver_total_mean_m"],
        clubs=clubs_dict
    )


# Inizializzazione dei profili precompilati
CLUB_PROFILES: Dict[PlayerCategory, CategoryProfile] = {
    PlayerCategory.PRIMA: build_category_profile("prima"),
    PlayerCategory.SECONDA: build_category_profile("seconda"),
    PlayerCategory.TERZA: build_category_profile("terza")
}


def get_category_profile(category: str | PlayerCategory) -> CategoryProfile:
    """Restituisce il CategoryProfile per la categoria richiesta."""
    if isinstance(category, PlayerCategory):
        return CLUB_PROFILES[category]
    val = str(category).lower().strip().split(".")[-1]
    cat_enum = PlayerCategory(val)
    return CLUB_PROFILES[cat_enum]


def get_club_profile(category: str | PlayerCategory, club_id: str) -> Optional[ClubStats]:
    """Restituisce i dati balistici di un bastone per la categoria indicata."""
    c_prof = get_category_profile(category)
    clean_id = club_id.lower().strip().replace(" ", "_")
    return c_prof.clubs.get(clean_id)


def list_clubs(category: str | PlayerCategory) -> List[str]:
    """Restituisce la lista degli identificativi delle mazze disponibili per la categoria."""
    c_prof = get_category_profile(category)
    return list(c_prof.clubs.keys())


def estimate_category_from_handicap(handicap: float) -> PlayerCategory:
    """
    Classifica automaticamente il giocatore in Prima, Seconda o Terza Categoria
    in base al suo Handicap Index WHS ufficiale.
    """
    if handicap <= 12.0:
        return PlayerCategory.PRIMA
    elif handicap <= 26.0:
        return PlayerCategory.SECONDA
    else:
        return PlayerCategory.TERZA


def calculate_shot_suitability(
    required_total_m: float,
    required_carry_m: float,
    landing_zone_width_m: float,
    category: str | PlayerCategory,
    club_id: str,
    hazard_carry_m: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calcola il punteggio di adeguatezza (Shot Suitability Score) di una mazza per coprire
    una determinata landing zone, tenendo conto di carry, dispersione e ostacoli.
    """
    c_stat = get_club_profile(category, club_id)
    if not c_stat:
        return {
            "club": club_id,
            "total_score": 0.0,
            "recommendation": "not_recommended",
            "notes": [f"Bastone '{club_id}' non presente nel profilo."]
        }

    # 1. Punteggio Distanza Totale (Target Distance Match)
    dist_error = abs(c_stat.total_mean_m - required_total_m)
    distance_score = max(0.0, 100.0 - dist_error * 3.5)

    # 2. Punteggio Dispersione Laterale rispetto alla larghezza utile della landing zone
    half_width = landing_zone_width_m / 2.0
    excess_dispersion = max(0.0, c_stat.lateral_dispersion_m - half_width)
    dispersion_score = max(0.0, 100.0 - excess_dispersion * 4.0)

    # 3. Punteggio Carry / Superamento Ostacoli
    carry_score = 100.0
    notes = []
    if hazard_carry_m is not None and hazard_carry_m > 0:
        safety_margin = 10.0
        if c_stat.carry_mean_m >= hazard_carry_m + safety_margin:
            carry_score = 100.0
            notes.append(f"Supera l'ostacolo con margine sicuro (+{int(c_stat.carry_mean_m - hazard_carry_m)}m).")
        elif c_stat.carry_mean_m >= hazard_carry_m:
            carry_score = 70.0
            notes.append("Carry sufficiente ma con poco margine rispetto all'ostacolo.")
        else:
            deficit = hazard_carry_m - c_stat.carry_mean_m
            carry_score = max(0.0, 40.0 - deficit * 4.0)
            notes.append(f"Rischio ostacolo: carry medio inferiore di {int(deficit)}m.")
    elif required_carry_m > 0:
        if c_stat.carry_mean_m < required_carry_m:
            carry_score = max(0.0, 100.0 - (required_carry_m - c_stat.carry_mean_m) * 3.0)

    # Punteggio composito ponderato
    total_score = round(
        0.40 * distance_score + 0.35 * dispersion_score + 0.25 * carry_score,
        1
    )

    if total_score >= 80.0:
        rec = "recommended"
    elif total_score >= 60.0:
        rec = "acceptable"
    elif total_score >= 40.0:
        rec = "risky"
    else:
        rec = "not_recommended"

    return {
        "category": str(category),
        "club": club_id,
        "club_id": club_id,
        "label": c_stat.label,
        "distance_score": round(distance_score, 1),
        "dispersion_score": round(dispersion_score, 1),
        "carry_score": round(carry_score, 1),
        "total_score": total_score,
        "suitability_score": total_score,
        "recommendation": rec,
        "notes": notes
    }


def rank_clubs_for_shot(
    required_total_m: float,
    required_carry_m: float,
    landing_zone_width_m: float,
    category: str | PlayerCategory,
    hazard_carry_m: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Valuta e ordina tutte le mazze disponibili per la categoria dalla più adatta alla meno adatta.
    """
    clubs = list_clubs(category)
    results = []
    for c_id in clubs:
        suitability = calculate_shot_suitability(
            required_total_m=required_total_m,
            required_carry_m=required_carry_m,
            landing_zone_width_m=landing_zone_width_m,
            category=category,
            club_id=c_id,
            hazard_carry_m=hazard_carry_m
        )
        results.append(suitability)

    results.sort(key=lambda x: x["total_score"], reverse=True)
    return results
